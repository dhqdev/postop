"""Post no TikTok pelo worker, com a API do TikTok simulada (sem rede)."""

from starlette.requests import Request

from app import auth, tiktok
from app import worker as worker_mod
from app.config import config
from app.db import Job, Video, init_db, session_scope
from app.worker import JobRunner, claim_next


def _video(**fields) -> int:
    f = config.media_dir / "job_tt" / "v.mp4"
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_bytes(b"0" * 1024)
    with session_scope() as s:
        v = Video(kind="youtube", title="t", caption="c", file_path="job_tt/v.mp4", **fields)
        s.add(v)
        s.flush()
        return v.id


def _run_post(params: dict) -> Job:
    with session_scope() as s:
        s.query(Job).filter(Job.status == "queued").update({"status": "canceled"})
        s.add(Job(kind="tiktok_post", title="post", params=params))
    job = claim_next()
    assert job is not None and job.kind == "tiktok_post"
    JobRunner(job).run()
    with session_scope() as s:
        return s.get(Job, job.id)


def test_tiktok_post_publishes_and_tracks_status(monkeypatch):
    init_db()
    monkeypatch.setattr(worker_mod, "POLL_INTERVAL", 0)
    calls = []
    monkeypatch.setattr(tiktok, "publish", lambda *a, **k: calls.append(k) or "pub_1")
    monkeypatch.setattr(tiktok, "publish_status", lambda pid: {"status": "PUBLISH_COMPLETE"})
    vid = _video()
    j = _run_post({"video_id": vid, "mode": "direct", "privacy": "SELF_ONLY"})
    assert j.status == "done", j.error
    assert len(calls) == 1
    with session_scope() as s:
        v = s.get(Video, vid)
        assert (v.tiktok_status, v.tiktok_publish_id) == ("published", "pub_1")


def test_tiktok_post_resumed_after_restart_does_not_repost(monkeypatch):
    init_db()
    monkeypatch.setattr(worker_mod, "POLL_INTERVAL", 0)
    monkeypatch.setattr(
        tiktok, "publish", lambda *a, **k: (_ for _ in ()).throw(AssertionError("postou de novo"))
    )
    monkeypatch.setattr(tiktok, "publish_status", lambda pid: {"status": "SEND_TO_USER_INBOX"})
    vid = _video(tiktok_status="processing", tiktok_publish_id="pub_old")
    j = _run_post({"video_id": vid, "mode": "inbox", "_retries": 1})
    assert j.status == "done", j.error
    with session_scope() as s:
        assert s.get(Video, vid).tiktok_status == "inbox"


def test_tiktok_post_failure_marks_video(monkeypatch):
    init_db()
    monkeypatch.setattr(worker_mod, "POLL_INTERVAL", 0)
    monkeypatch.setattr(tiktok, "publish", lambda *a, **k: "pub_2")
    monkeypatch.setattr(tiktok, "publish_status", lambda pid: {"status": "FAILED", "fail_reason": "spam"})
    vid = _video()
    j = _run_post({"video_id": vid})
    assert j.status == "error" and "spam" in j.error
    with session_scope() as s:
        v = s.get(Video, vid)
        assert v.tiktok_status == "error" and "spam" in v.tiktok_error


def test_client_ip_uses_last_forwarded_hop():
    scope = {
        "type": "http",
        "headers": [(b"x-forwarded-for", b"1.2.3.4, 203.0.113.9")],
        "client": ("10.0.0.2", 1234),
    }
    assert auth.client_ip(Request(scope)) == "203.0.113.9"
    assert auth.client_ip(Request({"type": "http", "headers": [], "client": ("10.0.0.2", 1)})) == "10.0.0.2"
