"""Pipeline 3D completo com OpenRouter simulado (sem rede)."""

import shutil
import subprocess

import pytest

from app import settings_store as st
from app.config import config
from app.db import Job, Video, init_db, session_scope
from app.openrouter import OpenRouter
from app.worker import JobRunner, claim_next

pytestmark = pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg ausente")


def _png() -> bytes:
    return subprocess.run(
        [
            "ffmpeg",
            "-loglevel",
            "error",
            "-f",
            "lavfi",
            "-i",
            "color=c=orange:size=576x1024",
            "-frames:v",
            "1",
            "-f",
            "image2pipe",
            "-vcodec",
            "png",
            "-",
        ],
        capture_output=True,
        check=True,
    ).stdout


def test_prompt3d_job_end_to_end(monkeypatch):
    init_db()
    st.set_many({"openrouter_api_key": "sk-or-fake-key-123"})
    script = {
        "title": "Gato astronauta",
        "caption": "Olha isso 🚀",
        "hashtags": ["gato", "#3d"],
        "scenes": [
            {"image_prompt": "cat astronaut", "motion_prompt": "zoom", "text": "Cena um"},
            {"image_prompt": "candy planet", "motion_prompt": "pan", "text": "Cena dois"},
        ],
    }
    monkeypatch.setattr(
        OpenRouter, "chat_json", lambda self, models, system, user: (script, 0.001, "fake/model")
    )
    png = _png()
    monkeypatch.setattr(
        OpenRouter, "generate_image", lambda self, model, prompt, aspect_ratio="9:16": (png, 0.002)
    )
    monkeypatch.setattr(OpenRouter, "video_models", lambda self: [])

    with session_scope() as s:
        s.query(Job).filter(Job.status == "queued").update({"status": "canceled"})
        s.add(
            Job(
                kind="prompt3d", title="teste", params={"prompt": "gato", "scenes": 2, "seconds_per_scene": 2}
            )
        )
    job = claim_next()
    assert job is not None and job.kind == "prompt3d"
    JobRunner(job).run()

    with session_scope() as s:
        j = s.get(Job, job.id)
        assert j.status == "done", j.error
        assert abs(j.cost_usd - 0.005) < 1e-9
        vids = s.query(Video).filter(Video.job_id == job.id).all()
        assert len(vids) == 1
        v = vids[0]
        assert v.hashtags == "#gato #3d"
        assert (config.media_dir / v.file_path).exists()
        assert 3.5 <= v.duration <= 5.5
