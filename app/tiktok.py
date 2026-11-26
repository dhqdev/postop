"""Integração com a TikTok Content Posting API (OAuth v2 + upload de vídeo).

Conferido com a documentação oficial (nov/2026):
- OAuth: /v2/auth/authorize (web) -> /v2/oauth/token (code e refresh_token) -> /v2/oauth/revoke;
  sempre guardar o refresh_token mais recente; access_token dura 24 h e refresh_token 365 dias.
- Post direto: /v2/post/publish/creator_info/query (antes de postar) -> /v2/post/publish/video/init
  (post_info + source_info FILE_UPLOAD) -> PUT em upload_url (Content-Range, válido por 1 h) ->
  /v2/post/publish/status/fetch. Rascunho: /v2/post/publish/inbox/video/init (escopo video.upload).
- Título até 2200 runas UTF-16; privacidade precisa estar em privacy_level_options; conteúdo de marca
  não pode ser "só eu"; duração até max_video_post_duration_sec; init limitado a 6 pedidos/min.
- App não auditado: posts só "só eu" e a conta do TikTok precisa estar PRIVADA na hora de postar.
"""

from __future__ import annotations

import time
from pathlib import Path
from urllib.parse import urlencode

import httpx

from . import settings_store as st
from .config import config

AUTH_URL = "https://www.tiktok.com/v2/auth/authorize/"
API = "https://open.tiktokapis.com/v2"
SCOPES = "user.info.basic,video.publish,video.upload"
MIN_CHUNK = 5 * 1024 * 1024
MAX_SINGLE = 64 * 1024 * 1024
CHUNK = 10 * 1024 * 1024
TITLE_MAX = 2200

# Mensagens claras para os erros mais comuns da API
HINTS = {
    "unaudited_client_can_only_post_to_private_accounts": (
        "App ainda não aprovado pelo TikTok: deixe a sua conta do TikTok PRIVADA (app do TikTok > Perfil > ☰ > "
        "Configurações e privacidade > Privacidade > Conta privada) e poste como 'Só eu'."
    ),
    "spam_risk_too_many_posts": "Limite diário de posts pela API atingido para esta conta (cerca de 15 por dia). Tente amanhã.",
    "spam_risk_user_banned_from_posting": "O TikTok bloqueou novos posts desta conta no momento.",
    "spam_risk_too_many_pending_share": (
        "Já existem 5 envios esperando nos rascunhos/notificações do app do TikTok. Publique ou descarte alguns e tente de novo."
    ),
    "reached_active_user_cap": "O app atingiu o limite diário de contas que postam (apps não aprovados: até 5 por dia).",
    "privacy_level_option_mismatch": "Essa privacidade não está disponível para esta conta agora. Escolha outra opção.",
    "scope_not_authorized": "Falta permissão no app do TikTok (video.publish / video.upload). Adicione e clique em Reconectar.",
    "access_token_invalid": "A conexão com o TikTok expirou. Vá em Configurações > TikTok e clique em Reconectar.",
    "rate_limit_exceeded": "Muitos pedidos ao TikTok em pouco tempo. Aguarde um minuto e tente de novo.",
    "invalid_grant": "A autorização do TikTok expirou ou foi revogada. Conecte a conta de novo.",
    "url_ownership_unverified": "O TikTok não reconheceu o domínio do vídeo.",
    "file_format_check_failed": "O TikTok recusou o formato do arquivo de vídeo.",
    "duration_check_failed": "O vídeo está mais longo do que esta conta pode postar.",
    "picture_size_check_failed": "A resolução do vídeo não foi aceita pelo TikTok.",
}


class TikTokError(RuntimeError):
    def __init__(self, msg: str, code: str = ""):
        super().__init__(msg)
        self.code = code


def utf16_trim(text: str, limit: int = TITLE_MAX) -> str:
    """Corta o texto em `limit` unidades UTF-16 (como o TikTok conta), sem partir emojis."""
    out, n = [], 0
    for ch in text or "":
        k = 2 if ord(ch) > 0xFFFF else 1
        if n + k > limit:
            break
        out.append(ch)
        n += k
    return "".join(out)


def authorize_url(state: str) -> str:
    key = st.get("tiktok_client_key")
    if not key:
        raise TikTokError("Preencha o Client Key do TikTok em Configurações > TikTok.")
    q = {
        "client_key": key,
        "scope": SCOPES,
        "response_type": "code",
        "redirect_uri": config.tiktok_redirect_uri,
        "state": state,
    }
    return f"{AUTH_URL}?{urlencode(q)}"


def _check(resp: httpx.Response, what: str) -> dict:
    try:
        body = resp.json()
    except Exception as exc:
        raise TikTokError(f"{what}: HTTP {resp.status_code} {resp.text[:300]}") from exc
    err = body.get("error")
    if isinstance(err, dict) and err.get("code") not in (None, "", "ok"):
        code = str(err.get("code"))
        hint = HINTS.get(code)
        msg = f"{what}: {hint}" if hint else f"{what}: {code} - {err.get('message')}"
        raise TikTokError(msg + (f" [{code}]" if hint else ""), code)
    if isinstance(err, str) and err:
        hint = HINTS.get(err)
        raise TikTokError(f"{what}: {hint or err} - {body.get('error_description', '')}".rstrip(" -"), err)
    if resp.status_code >= 400:
        raise TikTokError(f"{what}: HTTP {resp.status_code} {body}")
    return body


def _save_tokens(body: dict) -> None:
    now = int(time.time())
    values = {
        "tiktok_access_token": body["access_token"],
        "tiktok_open_id": body.get("open_id", "") or st.get("tiktok_open_id"),
        "tiktok_scope": body.get("scope", "") or st.get("tiktok_scope"),
        "tiktok_expires_at": str(now + int(body.get("expires_in", 86400) or 86400)),
    }
    if body.get("refresh_token"):  # sempre o mais recente; se não veio, mantém o atual
        values["tiktok_refresh_token"] = body["refresh_token"]
        values["tiktok_refresh_expires_at"] = str(now + int(body.get("refresh_expires_in", 0) or 0))
    st.set_many(values)


def _client(timeout=30.0) -> httpx.Client:
    return httpx.Client(timeout=timeout)


def exchange_code(code: str, client: httpx.Client | None = None) -> dict:
    own = client is None
    client = client or _client()
    try:
        resp = client.post(
            f"{API}/oauth/token/",
            data={
                "client_key": st.get("tiktok_client_key"),
                "client_secret": st.get("tiktok_client_secret"),
                "code": code,
                "grant_type": "authorization_code",
                "redirect_uri": config.tiktok_redirect_uri,
            },
            headers={"Content-Type": "application/x-www-form-urlencoded", "Cache-Control": "no-cache"},
        )
        body = _check(resp, "Token TikTok")
        _save_tokens(body)
        try:
            info = user_info(client)
            st.set_many(
                {
                    "tiktok_display_name": info.get("display_name", ""),
                    "tiktok_avatar_url": info.get("avatar_url", ""),
                }
            )
        except TikTokError:
            pass
        return body
    finally:
        if own:
            client.close()


def refresh(client: httpx.Client | None = None) -> str:
    rt = st.get("tiktok_refresh_token")
    if not rt:
        raise TikTokError("Conta do TikTok não conectada. Vá em Configurações > TikTok > Conectar.")
    own = client is None
    client = client or _client()
    try:
        resp = client.post(
            f"{API}/oauth/token/",
            data={
                "client_key": st.get("tiktok_client_key"),
                "client_secret": st.get("tiktok_client_secret"),
                "grant_type": "refresh_token",
                "refresh_token": rt,
            },
            headers={"Content-Type": "application/x-www-form-urlencoded", "Cache-Control": "no-cache"},
        )
        try:
            body = _check(resp, "Renovar conexão com o TikTok")
        except TikTokError as exc:
            if exc.code in ("invalid_grant", "invalid_request") or "refresh_token" in str(exc):
                # aparece como desconectado no painel
                st.set_many({"tiktok_access_token": "", "tiktok_refresh_token": ""})
            raise
        _save_tokens(body)
        return body["access_token"]
    finally:
        if own:
            client.close()


def access_token(client: httpx.Client | None = None) -> str:
    token = st.get("tiktok_access_token")
    if not token:
        raise TikTokError("Conta do TikTok não conectada. Vá em Configurações > TikTok > Conectar.")
    try:
        expires = int(st.get("tiktok_expires_at") or 0)
    except ValueError:
        expires = 0
    if expires and expires - time.time() < 300:
        token = refresh(client)
    return token


def revoke(client: httpx.Client | None = None) -> None:
    """Desconecta o app da conta no TikTok (o app some de "Apps conectados" no TikTok)."""
    token = st.get("tiktok_access_token")
    if not token:
        return
    own = client is None
    client = client or _client(15.0)
    try:
        client.post(
            f"{API}/oauth/revoke/",
            data={
                "client_key": st.get("tiktok_client_key"),
                "client_secret": st.get("tiktok_client_secret"),
                "token": token,
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
    except httpx.HTTPError:
        pass
    finally:
        if own:
            client.close()


def disconnect() -> None:
    try:
        revoke()
    except Exception:  # noqa: BLE001 — desconectar localmente sempre funciona
        pass
    st.set_many({k: "" for k in st.INTERNAL_KEYS})


def status() -> dict:
    connected = bool(st.get("tiktok_access_token"))
    return {
        "configured": bool(st.get("tiktok_client_key") and st.get("tiktok_client_secret")),
        "connected": connected,
        "display_name": st.get("tiktok_display_name"),
        "username": st.get("tiktok_username"),
        "avatar_url": st.get("tiktok_avatar_url"),
        "scope": st.get("tiktok_scope"),
        "redirect_uri": config.tiktok_redirect_uri,
        "expires_at": st.get("tiktok_expires_at"),
        "refresh_expires_at": st.get("tiktok_refresh_expires_at"),
    }


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json; charset=UTF-8"}


def _call(client: httpx.Client, method: str, path: str, what: str, **kw) -> dict:
    """Chama a API com o token; se o TikTok disser que o token expirou, renova e tenta mais uma vez."""
    for attempt in range(2):
        token = access_token(client)
        resp = client.request(method, f"{API}{path}", headers=_auth(token), **kw)
        try:
            return _check(resp, what)
        except TikTokError as exc:
            if exc.code == "access_token_invalid" and attempt == 0 and st.get("tiktok_refresh_token"):
                refresh(client)
                continue
            raise
    raise TikTokError(f"{what}: falha ao renovar a conexão")  # pragma: no cover


def user_info(client: httpx.Client | None = None) -> dict:
    own = client is None
    client = client or _client()
    try:
        body = _call(
            client,
            "GET",
            "/user/info/",
            "Usuário TikTok",
            params={"fields": "open_id,avatar_url,display_name"},
        )
        return body.get("data", {}).get("user", {})
    finally:
        if own:
            client.close()


def creator_info(client: httpx.Client | None = None) -> dict:
    own = client is None
    client = client or _client()
    try:
        data = _call(client, "POST", "/post/publish/creator_info/query/", "Perfil do criador", json={}).get(
            "data", {}
        )
        if data.get("creator_username"):
            st.set_many({"tiktok_username": data.get("creator_username", "")})
        return data
    finally:
        if own:
            client.close()


def chunk_plan(size: int) -> tuple[int, int]:
    """(chunk_size, total_chunk_count) segundo as regras da API (o último pedaço leva o resto)."""
    if size <= MAX_SINGLE:
        return size, 1
    count = size // CHUNK
    return CHUNK, count


def upload(upload_url: str, path: Path, client: httpx.Client) -> None:
    size = path.stat().st_size
    chunk_size, count = chunk_plan(size)
    with path.open("rb") as fh:
        for i in range(count):
            start = i * chunk_size
            end = size - 1 if i == count - 1 else start + chunk_size - 1
            fh.seek(start)
            data = fh.read(end - start + 1)
            for attempt in range(3):
                try:
                    resp = client.put(
                        upload_url,
                        content=data,
                        headers={
                            "Content-Type": "video/mp4",
                            "Content-Length": str(len(data)),
                            "Content-Range": f"bytes {start}-{end}/{size}",
                        },
                    )
                except httpx.HTTPError as exc:  # rede instável: tenta o mesmo pedaço de novo
                    if attempt == 2:
                        raise TikTokError(f"Upload falhou (parte {i + 1}/{count}): {exc}") from exc
                    time.sleep(2 + attempt * 3)
                    continue
                if resp.status_code in (200, 201, 206):
                    break
                if resp.status_code >= 500 and attempt < 2:
                    time.sleep(2 + attempt * 3)
                    continue
                raise TikTokError(
                    f"Upload falhou (parte {i + 1}/{count}): HTTP {resp.status_code} {resp.text[:300]}"
                )


def check_duration(path: Path, info: dict) -> None:
    from .media import duration_of

    limit = info.get("max_video_post_duration_sec")
    try:
        limit = int(limit or 0)
    except (TypeError, ValueError):
        limit = 0
    dur = duration_of(path)
    if limit and dur > limit + 0.5:
        raise TikTokError(
            f"O vídeo tem {dur:.0f} s e esta conta do TikTok só permite postar até {limit} s pela API.",
            "duration_check_failed",
        )


def publish(
    path: Path,
    title: str,
    mode: str = "direct",
    privacy: str = "SELF_ONLY",
    disable_comment: bool = False,
    disable_duet: bool = False,
    disable_stitch: bool = False,
    is_aigc: bool = False,
    brand_organic: bool = False,
    brand_content: bool = False,
    client: httpx.Client | None = None,
) -> str:
    """Envia o vídeo. Retorna o publish_id."""
    own = client is None
    client = client or httpx.Client(timeout=httpx.Timeout(60, write=600, read=120))
    try:
        size = path.stat().st_size
        chunk_size, count = chunk_plan(size)
        source = {
            "source": "FILE_UPLOAD",
            "video_size": size,
            "chunk_size": chunk_size,
            "total_chunk_count": count,
        }
        if mode == "inbox":
            path_init = "/post/publish/inbox/video/init/"
            payload: dict = {"source_info": source}
        else:
            info = creator_info(client)
            check_duration(path, info)
            options = info.get("privacy_level_options") or []
            if options and privacy not in options:
                privacy = "SELF_ONLY" if "SELF_ONLY" in options else options[0]
            if brand_content and privacy == "SELF_ONLY":
                raise TikTokError("Conteúdo de marca (parceria paga) não pode ser postado como 'Só eu'.")
            path_init = "/post/publish/video/init/"
            payload = {
                "post_info": {
                    "title": utf16_trim(title),
                    "privacy_level": privacy,
                    "disable_comment": disable_comment or bool(info.get("comment_disabled")),
                    "disable_duet": disable_duet or bool(info.get("duet_disabled")),
                    "disable_stitch": disable_stitch or bool(info.get("stitch_disabled")),
                    "video_cover_timestamp_ms": 1000,
                    "brand_content_toggle": bool(brand_content),
                    "brand_organic_toggle": bool(brand_organic),
                    "is_aigc": bool(is_aigc),
                },
                "source_info": source,
            }
        body = _call(client, "POST", path_init, "Iniciar post TikTok", json=payload)
        data = body.get("data", {})
        publish_id, upload_url = data.get("publish_id"), data.get("upload_url")
        if not publish_id or not upload_url:
            raise TikTokError(f"Resposta inesperada do TikTok: {body}")
        upload(upload_url, path, client)
        return publish_id
    finally:
        if own:
            client.close()


def publish_status(publish_id: str, client: httpx.Client | None = None) -> dict:
    own = client is None
    client = client or _client()
    try:
        return _call(
            client, "POST", "/post/publish/status/fetch/", "Status do post", json={"publish_id": publish_id}
        ).get("data", {})
    finally:
        if own:
            client.close()


def post_url(status_data: dict) -> str:
    """Link do vídeo publicado (quando o TikTok devolve o id e sabemos o @ da conta)."""
    ids = (
        status_data.get("publicaly_available_post_id") or status_data.get("publicly_available_post_id") or []
    )
    user = st.get("tiktok_username")
    if ids and user:
        return f"https://www.tiktok.com/@{user}/video/{ids[0]}"
    return ""
