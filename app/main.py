"""API + painel web do PostOp."""

from __future__ import annotations

import logging
import secrets
import shutil
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import quote

from fastapi import Depends, FastAPI, File, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from . import auth, tiktok
from . import settings_store as st
from .config import config
from .db import Job, Video, get_db, init_db
from .openrouter import OpenRouter, OpenRouterError, summarize_models
from .pipelines.themes import STYLES, STYLES2D, THEME_MAP, public_styles, public_styles2d, public_themes
from .pipelines.youtube_clips import check_params as check_youtube
from .pipelines.youtube_clips import is_youtube_url, parse_ranges, parse_time, split_parts
from .tts import DEFAULT_VOICE, VOICES, public_voices

STATIC = Path(__file__).parent / "static"
log = logging.getLogger("postop")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    for d in (config.media_dir, config.work_dir, config.models_dir, config.data_dir / "uploads"):
        d.mkdir(parents=True, exist_ok=True)
    init_db()
    for warning in config.insecure_defaults():
        log.warning("ATENÇÃO: %s", warning)
    yield


app = FastAPI(title="PostOp", version=config.version, lifespan=lifespan, docs_url=None, redoc_url=None)
app.mount("/static", StaticFiles(directory=STATIC), name="static")

User = Depends(auth.require_user)


# ------------------------------------------------------------------ páginas
@app.get("/", include_in_schema=False)
def index() -> Response:
    # ?v=versão nos arquivos estáticos: depois de atualizar, o navegador baixa o painel novo
    html = (STATIC / "index.html").read_text(encoding="utf-8").replace("{{v}}", quote(config.version))
    return Response(html, media_type="text/html", headers={"Cache-Control": "no-cache"})


@app.get("/termos", include_in_schema=False)
def terms() -> FileResponse:
    return FileResponse(STATIC / "termos.html")


@app.get("/privacidade", include_in_schema=False)
def privacy() -> FileResponse:
    return FileResponse(STATIC / "privacidade.html")


@app.get("/api/health")
def health() -> dict:
    return {"ok": True, "version": config.version}


# -------------------------------------------------------------------- login
class LoginIn(BaseModel):
    username: str
    password: str


@app.post("/api/login")
def login(data: LoginIn, request: Request) -> JSONResponse:
    ip = auth.client_ip(request)
    if auth.too_many_failures(ip):
        raise HTTPException(429, "Muitas tentativas. Aguarde 10 minutos.")
    if not auth.check_credentials(data.username, data.password):
        auth.register_failure(ip)
        raise HTTPException(401, "Usuário ou senha inválidos")
    resp = JSONResponse({"ok": True, "user": data.username})
    resp.set_cookie(
        auth.COOKIE_NAME,
        auth.make_token(data.username),
        httponly=True,
        samesite="lax",
        secure=auth.cookie_secure(),
        max_age=config.session_days * 86400,
    )
    return resp


@app.post("/api/logout")
def logout() -> JSONResponse:
    resp = JSONResponse({"ok": True})
    resp.delete_cookie(auth.COOKIE_NAME)
    return resp


@app.get("/api/me")
def me(user: str = User) -> dict:
    return {"user": user, "version": config.version, "public_url": config.public_url}


# ----------------------------------------------------------- configurações
class SettingsIn(BaseModel):
    values: dict[str, str] = Field(default_factory=dict)
    clear: list[str] = Field(default_factory=list)


@app.get("/api/settings")
def get_settings(_: str = User) -> dict:
    return {"fields": st.public_view(), "tiktok": tiktok.status(), "styles": list(STYLES)}


@app.put("/api/settings")
def put_settings(data: SettingsIn, _: str = User) -> dict:
    values: dict[str, str] = {}
    for key, value in data.values.items():
        f = st.FIELD_MAP.get(key)
        if f is None:
            continue
        value = (value or "").strip() if f.kind != "textarea" else (value or "")
        if f.secret and not value:
            continue  # campo secreto vazio = manter o valor atual
        values[key] = value
    for key in data.clear:
        if key in st.FIELD_MAP:
            values[key] = ""
    st.set_many(values)
    return get_settings(_)


@app.get("/api/themes")
def get_themes(_: str = User) -> dict:
    return {
        "themes": public_themes(),
        "styles": public_styles(),
        "styles2d": public_styles2d(),
        "voices": public_voices(),
    }


@app.post("/api/openrouter/test")
def openrouter_test(_: str = User) -> dict:
    try:
        info = OpenRouter(st.get("openrouter_api_key"), timeout=30).key_info()
    except OpenRouterError as exc:
        raise HTTPException(400, str(exc)) from exc
    return {"ok": True, "info": info}


@app.get("/api/openrouter/models")
def openrouter_models(_: str = User) -> dict:
    client = OpenRouter(st.get("openrouter_api_key"), timeout=60)
    try:
        return summarize_models(client.list_models())
    except OpenRouterError as exc:
        raise HTTPException(400, str(exc)) from exc


# --------------------------------------------------------------------- jobs
def job_dict(j: Job, with_log: bool = False) -> dict:
    d = {
        "id": j.id,
        "kind": j.kind,
        "status": j.status,
        "title": j.title,
        "stage": j.stage,
        "progress": j.progress,
        "params": {k: v for k, v in (j.params or {}).items() if not k.startswith("_")},
        "result": j.result,
        "error": j.error,
        "cost_usd": round(j.cost_usd or 0, 4),
        "created_at": j.created_at.isoformat() if j.created_at else None,
        "finished_at": j.finished_at.isoformat() if j.finished_at else None,
    }
    if with_log:
        d["log"] = j.log
    return d


class YoutubeIn(BaseModel):
    url: str
    # modo: a IA escolhe | eu digo os trechos | dividir em partes
    mode: str = Field("ai", pattern="^(ai|manual|parts)$")
    start: str = ""  # trecho do vídeo (ex.: 12:30); vazio = desde o começo
    end: str = ""  # vazio = até o fim
    clips: str = ""  # modo manual: um corte por linha ("1:20-2:05 Título")
    part_seconds: int = Field(60, ge=10, le=600)
    part_label: bool = True
    max_clips: int = Field(5, ge=1, le=20)
    min_seconds: int = Field(20, ge=5, le=180)
    max_seconds: int = Field(60, ge=10, le=600)
    reframe: str = Field("auto", pattern="^(auto|face|crop|blur)$")
    subtitle_style: str = Field("", pattern="^(|highlight|simple|none)$")
    language: str = ""
    instructions: str = ""
    auto_post: bool = False
    post_mode: str = ""
    privacy: str = ""


class Prompt3DIn(BaseModel):
    prompt: str = Field(min_length=3)
    scenes: int = Field(6, ge=1, le=15)
    seconds_per_scene: float = Field(3.5, ge=2, le=10)
    style: str = "pixar3d"
    theme: str = ""
    narration: bool = True
    voice: str = DEFAULT_VOICE
    sfx: bool = True
    captions: bool = True
    music_path: str = ""
    auto_post: bool = False
    post_mode: str = ""
    privacy: str = ""


class Anim2DIn(BaseModel):
    prompt: str = Field(min_length=3)
    scenes: int = Field(6, ge=1, le=15)
    seconds_per_scene: float = Field(4.0, ge=2, le=10)
    style: str = "papel"
    theme: str = ""
    narration: bool = True
    voice: str = DEFAULT_VOICE
    sfx: bool = True
    captions: bool = True
    music_path: str = ""
    auto_post: bool = False
    post_mode: str = ""
    privacy: str = ""


def _music(params: dict) -> dict:
    """Só aceita música enviada pelo painel (arquivo dentro de DATA_DIR/uploads)."""
    if params.get("music_path"):
        p = config.data_dir / "uploads" / Path(params["music_path"]).name
        params["music_path"] = str(p) if p.exists() else ""
    return params


def _enqueue(db: Session, kind: str, title: str, params: dict) -> dict:
    job = Job(kind=kind, title=title[:300], params=params)
    db.add(job)
    db.commit()
    db.refresh(job)
    return job_dict(job)


@app.post("/api/jobs/youtube")
def create_youtube(data: YoutubeIn, db: Session = Depends(get_db), _: str = User) -> dict:
    if not is_youtube_url(data.url):
        raise HTTPException(400, "Informe um link válido do YouTube")
    if data.mode == "ai" and data.min_seconds >= data.max_seconds:
        raise HTTPException(400, "Duração mínima deve ser menor que a máxima")
    err = check_youtube(data.model_dump())
    if err:
        raise HTTPException(400, err)
    label = {"ai": "Cortes", "manual": "Trechos", "parts": "Partes"}[data.mode]
    return _enqueue(db, "youtube", f"{label}: {data.url}", data.model_dump())


class YoutubePreviewIn(BaseModel):
    mode: str = "ai"
    start: str = ""
    end: str = ""
    clips: str = ""
    part_seconds: int = 60


@app.post("/api/youtube/preview")
def youtube_preview(data: YoutubePreviewIn, _: str = User) -> dict:
    """Lê os tempos com a mesma regra do worker, para o painel mostrar o que vai ser cortado."""
    p = data.model_dump()
    err = check_youtube(p)
    if err:
        return {"error": err, "clips": [], "parts": None}
    clips = parse_ranges(p["clips"]) if data.mode == "manual" else []
    start, end = parse_time(data.start), parse_time(data.end)
    parts = None
    if data.mode == "parts" and end is not None:  # sem o fim do trecho, depende da duração do vídeo
        parts = len(split_parts(start or 0.0, end, max(10, data.part_seconds), []))
    return {"error": "", "clips": clips, "start": start, "end": end, "parts": parts}


@app.post("/api/jobs/prompt3d")
def create_prompt3d(data: Prompt3DIn, db: Session = Depends(get_db), _: str = User) -> dict:
    if data.theme and data.theme not in THEME_MAP:
        raise HTTPException(400, "Tema desconhecido")
    if data.style not in STYLES:
        raise HTTPException(400, "Estilo desconhecido")
    if data.voice not in VOICES:
        raise HTTPException(400, "Voz desconhecida")
    params = _music(data.model_dump())
    label = THEME_MAP[data.theme].name if data.theme else "3D"
    return _enqueue(db, "prompt3d", f"{label}: {data.prompt[:120]}", params)


@app.post("/api/jobs/anim2d")
def create_anim2d(data: Anim2DIn, db: Session = Depends(get_db), _: str = User) -> dict:
    if data.theme and (data.theme not in THEME_MAP or "2d" not in THEME_MAP[data.theme].modes):
        raise HTTPException(400, "Tema desconhecido")
    if data.style not in STYLES2D:
        raise HTTPException(400, "Estilo desconhecido")
    if data.voice not in VOICES:
        raise HTTPException(400, "Voz desconhecida")
    params = _music(data.model_dump())
    label = THEME_MAP[data.theme].name if data.theme else "Animação 2D"
    return _enqueue(db, "anim2d", f"{label}: {data.prompt[:120]}", params)


@app.post("/api/uploads/music")
async def upload_music(file: UploadFile = File(...), _: str = User) -> dict:
    ext = Path(file.filename or "").suffix.lower()
    if ext not in (".mp3", ".m4a", ".wav", ".aac", ".ogg"):
        raise HTTPException(400, "Envie um arquivo de áudio (mp3, m4a, wav, aac, ogg)")
    name = f"music_{secrets.token_hex(6)}{ext}"
    dest = config.data_dir / "uploads" / name
    with dest.open("wb") as fh:
        shutil.copyfileobj(file.file, fh)
    return {"music_path": name}


@app.get("/api/jobs")
def list_jobs(limit: int = 50, kind: str = "", db: Session = Depends(get_db), _: str = User) -> list[dict]:
    stmt = select(Job).order_by(Job.id.desc()).limit(min(limit, 200))
    if kind:
        stmt = stmt.where(Job.kind == kind)
    return [job_dict(j) for j in db.execute(stmt).scalars()]


@app.get("/api/jobs/{job_id}")
def get_job(job_id: int, db: Session = Depends(get_db), _: str = User) -> dict:
    j = db.get(Job, job_id)
    if j is None:
        raise HTTPException(404, "Job não encontrado")
    return job_dict(j, with_log=True)


@app.post("/api/jobs/{job_id}/cancel")
def cancel_job(job_id: int, db: Session = Depends(get_db), _: str = User) -> dict:
    j = db.get(Job, job_id)
    if j is None:
        raise HTTPException(404, "Job não encontrado")
    if j.status in ("queued", "running"):
        j.stage = "Cancelando..." if j.status == "running" else "Cancelado"
        j.status = "canceled"
        db.commit()
    return job_dict(j)


@app.post("/api/jobs/{job_id}/retry")
def retry_job(job_id: int, db: Session = Depends(get_db), _: str = User) -> dict:
    j = db.get(Job, job_id)
    if j is None:
        raise HTTPException(404, "Job não encontrado")
    params = {k: v for k, v in (j.params or {}).items() if not k.startswith("_")}
    if j.kind == "tiktok_post" and params.get("video_id"):
        v = db.get(Video, int(params["video_id"]))
        if v is not None:
            v.tiktok_status, v.tiktok_error = "queued", ""
    return _enqueue(db, j.kind, j.title, params)


@app.delete("/api/jobs/{job_id}")
def delete_job(job_id: int, db: Session = Depends(get_db), _: str = User) -> dict:
    j = db.get(Job, job_id)
    if j is None:
        raise HTTPException(404, "Job não encontrado")
    if j.status == "running":
        raise HTTPException(400, "Cancele o job antes de apagar")
    db.delete(j)
    db.commit()
    return {"ok": True}


# ------------------------------------------------------------------ vídeos
def video_dict(v: Video) -> dict:
    return {
        "id": v.id,
        "job_id": v.job_id,
        "kind": v.kind,
        "title": v.title,
        "caption": v.caption,
        "hashtags": v.hashtags,
        "duration": round(v.duration, 1),
        "score": v.score,
        "url": f"/media/{v.file_path}",
        "thumb": f"/media/{v.thumb_path}" if v.thumb_path else "",
        "meta": v.meta,
        "tiktok_status": v.tiktok_status,
        "tiktok_error": v.tiktok_error,
        "tiktok_publish_id": v.tiktok_publish_id,
        "created_at": v.created_at.isoformat() if v.created_at else None,
    }


@app.get("/api/videos")
def list_videos(
    limit: int = 100, job_id: int | None = None, db: Session = Depends(get_db), _: str = User
) -> list[dict]:
    stmt = select(Video).order_by(Video.id.desc()).limit(min(limit, 500))
    if job_id:
        stmt = stmt.where(Video.job_id == job_id)
    return [video_dict(v) for v in db.execute(stmt).scalars()]


class VideoPatch(BaseModel):
    title: str | None = None
    caption: str | None = None
    hashtags: str | None = None


@app.patch("/api/videos/{video_id}")
def patch_video(video_id: int, data: VideoPatch, db: Session = Depends(get_db), _: str = User) -> dict:
    v = db.get(Video, video_id)
    if v is None:
        raise HTTPException(404, "Vídeo não encontrado")
    for k, val in data.model_dump(exclude_none=True).items():
        setattr(v, k, val)
    db.commit()
    return video_dict(v)


@app.delete("/api/videos/{video_id}")
def delete_video(video_id: int, db: Session = Depends(get_db), _: str = User) -> dict:
    v = db.get(Video, video_id)
    if v is None:
        raise HTTPException(404, "Vídeo não encontrado")
    for rel in (v.file_path, v.thumb_path):
        if rel:
            (config.media_dir / rel).unlink(missing_ok=True)
    db.delete(v)
    db.commit()
    return {"ok": True}


class PostIn(BaseModel):
    mode: str = Field("", pattern="^(|direct|inbox)$")
    privacy: str = Field(
        "", pattern="^(|SELF_ONLY|MUTUAL_FOLLOW_FRIENDS|FOLLOWER_OF_CREATOR|PUBLIC_TO_EVERYONE)$"
    )
    title: str = Field("", max_length=4000)
    disable_comment: bool = False
    disable_duet: bool = False
    disable_stitch: bool = False
    brand_organic: bool = False  # "Sua marca": conteúdo promocional do próprio negócio
    brand_content: bool = False  # "Conteúdo de marca": parceria paga com terceiros


@app.post("/api/videos/{video_id}/tiktok")
def post_video(video_id: int, data: PostIn, db: Session = Depends(get_db), _: str = User) -> dict:
    v = db.get(Video, video_id)
    if v is None:
        raise HTTPException(404, "Vídeo não encontrado")
    if not st.get("tiktok_access_token", db):
        raise HTTPException(400, "Conecte sua conta do TikTok em Configurações > TikTok")
    params = data.model_dump()
    params["video_id"] = video_id
    params["mode"] = params["mode"] or st.get("tiktok_default_mode", db)
    params["privacy"] = params["privacy"] or st.get("tiktok_default_privacy", db)
    if params["mode"] == "direct" and params["brand_content"] and params["privacy"] == "SELF_ONLY":
        raise HTTPException(400, "Conteúdo de marca (parceria paga) não pode ser postado como 'Só eu'")
    v.tiktok_status, v.tiktok_error = "queued", ""
    db.commit()
    return _enqueue(db, "tiktok_post", f"Postar vídeo #{video_id} no TikTok", params)


@app.get("/media/{path:path}", include_in_schema=False)
def media(path: str, _: str = User) -> FileResponse:
    base = config.media_dir.resolve()
    target = (base / path).resolve()
    if not target.is_relative_to(base) or not target.is_file():
        raise HTTPException(404, "Arquivo não encontrado")
    return FileResponse(target)


@app.get("/api/stats")
def stats(db: Session = Depends(get_db), _: str = User) -> dict:
    by_status = dict(db.execute(select(Job.status, func.count()).group_by(Job.status)).all())
    total_cost = db.execute(select(func.coalesce(func.sum(Job.cost_usd), 0.0))).scalar() or 0.0
    videos = db.execute(select(func.count()).select_from(Video)).scalar() or 0
    posted = (
        db.execute(
            select(func.count()).select_from(Video).where(Video.tiktok_status.in_(["published", "inbox"]))
        ).scalar()
        or 0
    )
    return {"jobs": by_status, "videos": videos, "posted": posted, "cost_usd": round(float(total_cost), 4)}


# ------------------------------------------------------------------ TikTok
@app.get("/api/tiktok/status")
def tiktok_status(_: str = User) -> dict:
    return tiktok.status()


@app.get("/api/tiktok/connect", include_in_schema=False)
def tiktok_connect(_: str = User) -> RedirectResponse:
    state = secrets.token_urlsafe(24)
    try:
        url = tiktok.authorize_url(state)
    except tiktok.TikTokError as exc:
        return _back(str(exc))
    resp = RedirectResponse(url, status_code=302)
    resp.set_cookie(
        "tiktok_state", state, httponly=True, samesite="lax", secure=auth.cookie_secure(), max_age=900
    )
    return resp


@app.get("/api/tiktok/callback", include_in_schema=False)
def tiktok_callback(
    request: Request,
    code: str = "",
    state: str = "",
    error: str = "",
    error_description: str = "",
    _: str = User,
) -> Response:
    if error:
        return _back(f"TikTok recusou a conexão: {error} {error_description}")
    expected = request.cookies.get("tiktok_state", "")
    if not code or not state or not secrets.compare_digest(state, expected):
        return _back("Falha de segurança na conexão (state inválido). Tente conectar de novo.")
    try:
        tiktok.exchange_code(code)
    except tiktok.TikTokError as exc:
        return _back(str(exc))
    resp = RedirectResponse("/#/configuracoes?tiktok=ok", status_code=302)
    resp.delete_cookie("tiktok_state")
    return resp


def _back(msg: str) -> RedirectResponse:
    return RedirectResponse(f"/#/configuracoes?tiktok_error={quote(msg[:300])}", status_code=302)


@app.post("/api/tiktok/disconnect")
def tiktok_disconnect(_: str = User) -> dict:
    tiktok.disconnect()
    return tiktok.status()


@app.get("/api/tiktok/creator")
def tiktok_creator(_: str = User) -> dict:
    try:
        return tiktok.creator_info()
    except tiktok.TikTokError as exc:
        raise HTTPException(400, str(exc)) from exc


@app.exception_handler(401)
async def unauthorized(request: Request, exc: HTTPException):
    # Navegação do navegador (conectar TikTok) sem login volta para a tela de login
    if request.url.path in ("/api/tiktok/connect", "/api/tiktok/callback"):
        return RedirectResponse("/", status_code=302)
    return JSONResponse({"detail": exc.detail}, status_code=401)
