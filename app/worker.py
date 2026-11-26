"""Worker: processa a fila de jobs guardada no Postgres (sem Redis)."""

from __future__ import annotations

import logging
import shutil
import signal
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import select

from . import settings_store as st
from . import tiktok
from .config import config
from .db import Job, Video, init_db, session_scope
from .pipelines import Cancelled, Ctx, anim2d, prompt3d, youtube_clips

log = logging.getLogger("postop.worker")
_stop = False
POLL_ATTEMPTS = 60  # status do post TikTok: 60 x 10s = 10 min
POLL_INTERVAL = 10.0


def _now() -> datetime:
    return datetime.now(timezone.utc)


def claim_next() -> Job | None:
    with session_scope() as s:
        stmt = (
            select(Job)
            .where(Job.status == "queued")
            .order_by(Job.id)
            .limit(1)
            .with_for_update(skip_locked=True)
        )
        job = s.execute(stmt).scalars().first()
        if job is None:
            return None
        job.status = "running"
        job.started_at = _now()
        job.stage = "Iniciando"
        job.progress = 1
        s.flush()
        s.expunge(job)
        return job


def recover_stale() -> None:
    """Jobs que estavam rodando quando o worker caiu voltam para a fila uma vez."""
    with session_scope() as s:
        for job in s.execute(select(Job).where(Job.status == "running")).scalars():
            retries = int((job.params or {}).get("_retries", 0))
            if retries >= 1:
                job.status = "error"
                job.error = "Worker reiniciou durante o processamento (2x). Tente de novo."
                job.finished_at = _now()
            else:
                job.params = {**(job.params or {}), "_retries": retries + 1}
                job.status = "queued"
                job.stage = "Reenfileirado após reinício"


class JobRunner:
    def __init__(self, job: Job):
        self.job = job
        self._last_cancel_check = 0.0
        self._cancelled = False

    def update(self, **fields) -> None:
        with session_scope() as s:
            j = s.get(Job, self.job.id)
            if j is None:
                return
            for k, v in fields.items():
                setattr(j, k, v)

    def report(self, progress: int, stage: str) -> None:
        log.info("job %s: %s%% %s", self.job.id, progress, stage)
        self.update(progress=max(0, min(progress, 99)), stage=stage)

    def add_cost(self, cost: float) -> None:
        if not cost:
            return
        with session_scope() as s:
            j = s.get(Job, self.job.id)
            if j is not None:
                j.cost_usd = (j.cost_usd or 0.0) + float(cost)

    def write_log(self, line: str) -> None:
        log.info("job %s: %s", self.job.id, line)
        stamp = time.strftime("%H:%M:%S")
        with session_scope() as s:
            j = s.get(Job, self.job.id)
            if j is not None:
                j.log = ((j.log or "") + f"[{stamp}] {line}\n")[-20000:]

    def cancelled(self) -> bool:
        if self._cancelled:
            return True
        if time.time() - self._last_cancel_check > 3:
            self._last_cancel_check = time.time()
            with session_scope() as s:
                j = s.get(Job, self.job.id)
                self._cancelled = j is None or j.status == "canceled"
        return self._cancelled

    def cancelled_now(self) -> bool:
        self._last_cancel_check = 0.0
        return self.cancelled()

    def ctx(self) -> Ctx:
        return Ctx(
            job_id=self.job.id,
            params=self.job.params or {},
            settings=st.get_many(),
            report=self.report,
            add_cost=self.add_cost,
            log=self.write_log,
            cancelled=self.cancelled,
        )

    # ------------------------------------------------------------ execução
    def run(self) -> None:
        job = self.job
        work = config.work_dir / f"job_{job.id}"
        out_dir = config.media_dir / f"job_{job.id}"
        try:
            if job.kind == "tiktok_post":
                result = self.run_tiktok()
            else:
                work.mkdir(parents=True, exist_ok=True)
                out_dir.mkdir(parents=True, exist_ok=True)
                pipeline = {"youtube": youtube_clips.run, "prompt3d": prompt3d.run, "anim2d": anim2d.run}.get(
                    job.kind
                )
                if pipeline is None:
                    raise RuntimeError(f"Tipo de job desconhecido: {job.kind}")
                outputs = pipeline(self.ctx(), work, out_dir)
                result = {"videos": self.save_videos(outputs)}
                if (job.params or {}).get("auto_post"):
                    self.enqueue_posts(result["videos"])
            if self.cancelled_now():
                # cancelado no fim do processamento: guarda o resultado, mas mantém "cancelado"
                self.update(stage="Cancelado", result=result, finished_at=_now())
            else:
                self.update(status="done", progress=100, stage="Concluído", result=result, finished_at=_now())
        except Cancelled:
            self.update(stage="Cancelado", finished_at=_now())
        except Exception as exc:
            log.exception("job %s falhou", job.id)
            self.write_log(traceback.format_exc()[-3000:])
            self.update(status="error", error=str(exc)[:4000], stage="Erro", finished_at=_now())
        finally:
            if job.kind != "tiktok_post":
                shutil.rmtree(work, ignore_errors=True)

    def save_videos(self, outputs: list[dict]) -> list[int]:
        ids = []
        with session_scope() as s:
            for o in outputs:
                v = Video(
                    job_id=self.job.id,
                    kind=self.job.kind,
                    title=o.get("title", ""),
                    caption=o.get("caption", ""),
                    hashtags=o.get("hashtags", ""),
                    file_path=str(Path(o["file"]).relative_to(config.media_dir)),
                    thumb_path=str(Path(o["thumb"]).relative_to(config.media_dir)) if o.get("thumb") else "",
                    duration=float(o.get("duration") or 0),
                    score=float(o.get("score") or 0),
                    meta=o.get("meta") or {},
                )
                s.add(v)
                s.flush()
                ids.append(v.id)
        return ids

    def enqueue_posts(self, video_ids: list[int]) -> None:
        p = self.job.params or {}
        with session_scope() as s:
            for vid in video_ids:
                s.add(
                    Job(
                        kind="tiktok_post",
                        title=f"Postar vídeo #{vid} no TikTok",
                        params={
                            "video_id": vid,
                            "mode": p.get("post_mode") or st.get("tiktok_default_mode"),
                            "privacy": p.get("privacy") or st.get("tiktok_default_privacy"),
                        },
                    )
                )
                v = s.get(Video, vid)
                if v:
                    v.tiktok_status = "queued"

    def run_tiktok(self) -> dict:
        p = self.job.params or {}
        with session_scope() as s:
            v = s.get(Video, int(p["video_id"]))
            if v is None:
                raise RuntimeError("Vídeo não encontrado")
            path = config.media_dir / v.file_path
            title = p.get("title") or " ".join(x for x in [v.caption or v.title, v.hashtags] if x).strip()
            is_aigc = v.kind in ("prompt3d", "anim2d")
            vid = v.id
            # Worker reiniciou depois do envio: só acompanha o status (não posta de novo)
            resume_id = v.tiktok_publish_id if (p.get("_retries") and v.tiktok_status == "processing") else ""
            if not resume_id:
                v.tiktok_status, v.tiktok_error, v.tiktok_publish_id = "uploading", "", ""
        if not resume_id and not path.is_file():
            self._set_video(vid, tiktok_status="error", tiktok_error="Arquivo do vídeo não existe mais")
            raise RuntimeError(f"Arquivo do vídeo não encontrado: {path.name}")
        try:
            if resume_id:
                publish_id = resume_id
                self.write_log(f"Retomando acompanhamento do post {publish_id}")
            else:
                self.report(20, "Enviando vídeo para o TikTok")
                publish_id = tiktok.publish(
                    path,
                    title,
                    mode=p.get("mode", "direct"),
                    privacy=p.get("privacy", "SELF_ONLY"),
                    is_aigc=is_aigc,
                    disable_comment=bool(p.get("disable_comment")),
                    disable_duet=bool(p.get("disable_duet")),
                    disable_stitch=bool(p.get("disable_stitch")),
                    brand_organic=bool(p.get("brand_organic")),
                    brand_content=bool(p.get("brand_content")),
                )
                self._set_video(vid, tiktok_status="processing", tiktok_publish_id=publish_id)
            self.report(70, "TikTok processando o vídeo")
            final: dict = {}
            for _ in range(POLL_ATTEMPTS):
                time.sleep(POLL_INTERVAL)
                final = tiktok.publish_status(publish_id)
                status = final.get("status", "")
                if status == "PUBLISH_COMPLETE":
                    self._set_video(vid, tiktok_status="published")
                    self._save_post_url(vid, final)
                    break
                if status == "SEND_TO_USER_INBOX":
                    self._set_video(vid, tiktok_status="inbox")
                    break
                if status == "FAILED":
                    raise tiktok.TikTokError(f"TikTok recusou: {final.get('fail_reason')}")
                if self.cancelled():
                    # o vídeo já foi enviado; só paramos de acompanhar
                    self._set_video(vid, tiktok_error="Acompanhamento cancelado; confira no app do TikTok.")
                    raise Cancelled()
            else:
                self._set_video(
                    vid,
                    tiktok_error="O TikTok ainda não confirmou a publicação. Confira no app do TikTok.",
                )
                self.write_log(f"Sem confirmação após {POLL_ATTEMPTS * POLL_INTERVAL:.0f}s: {final}")
            return {"publish_id": publish_id, "status": final}
        except Cancelled:
            raise
        except Exception as exc:
            self._set_video(vid, tiktok_status="error", tiktok_error=str(exc)[:2000])
            raise

    @staticmethod
    def _save_post_url(vid: int, final: dict) -> None:
        try:
            url = tiktok.post_url(final)
        except Exception:  # noqa: BLE001 — o link é só um extra
            url = ""
        if not url:
            return
        with session_scope() as s:
            v = s.get(Video, vid)
            if v:
                v.meta = {**(v.meta or {}), "tiktok_url": url}

    @staticmethod
    def _set_video(vid: int, **fields) -> None:
        with session_scope() as s:
            v = s.get(Video, vid)
            if v:
                for k, val in fields.items():
                    setattr(v, k, val)


def _handle_stop(*_args) -> None:
    global _stop
    _stop = True
    log.info("Encerrando worker após o job atual...")


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    signal.signal(signal.SIGTERM, _handle_stop)
    signal.signal(signal.SIGINT, _handle_stop)
    for d in (config.media_dir, config.work_dir, config.models_dir):
        d.mkdir(parents=True, exist_ok=True)
    init_db()
    recover_stale()
    log.info("Worker PostOp %s pronto", config.version)
    while not _stop:
        job = claim_next()
        if job is None:
            time.sleep(config.worker_poll_seconds)
            continue
        log.info("Processando job %s (%s)", job.id, job.kind)
        JobRunner(job).run()


if __name__ == "__main__":
    main()
