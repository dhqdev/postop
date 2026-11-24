"""Pipeline 3D completo: roteiro pela IA (simulada, sem rede) e cenas pelo motor 3D próprio."""

import shutil

import pytest

from app import settings_store as st
from app.config import config
from app.db import Job, Video, init_db, session_scope
from app.openrouter import OpenRouter
from app.worker import JobRunner, claim_next

pytestmark = pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg ausente")


def _run_job(params: dict) -> tuple[dict, list[dict]]:
    with session_scope() as s:
        s.query(Job).filter(Job.status == "queued").update({"status": "canceled"})
        s.add(Job(kind="prompt3d", title="teste", params=params))
    job = claim_next()
    assert job is not None and job.kind == "prompt3d"
    JobRunner(job).run()
    with session_scope() as s:
        j = s.get(Job, job.id)
        info = {"status": j.status, "error": j.error, "cost": j.cost_usd, "log": j.log or ""}
        vids = [
            {"hashtags": v.hashtags, "file": v.file_path, "duration": v.duration, "meta": v.meta}
            for v in s.query(Video).filter(Video.job_id == job.id).all()
        ]
    return info, vids


def test_prompt3d_job_end_to_end(monkeypatch):
    init_db()
    st.set_many({"openrouter_api_key": "sk-or-fake-key-123"})
    script = {
        "title": "Gato astronauta",
        "caption": "Olha isso 🚀",
        "hashtags": ["gato", "#3d"],
        "scenes": [
            {
                "text": "Cena um",
                "scene3d": {
                    "setting": "space",
                    "camera": "orbit",
                    "actors": [{"type": "cat", "actions": ["float"]}, {"type": "planet", "position": "left"}],
                },
            },
            {
                "text": "Cena dois",
                "scene3d": {
                    "setting": "floresta",
                    "actors": [{"type": "blocos", "count": 4, "actions": ["empilhar"]}],
                },
            },
        ],
    }
    calls = []

    def fake_chat(self, models, system, user):
        calls.append(system)
        return script, 0.001, "fake/model"

    monkeypatch.setattr(OpenRouter, "chat_json", fake_chat)
    j, vids = _run_job({"prompt": "gato", "scenes": 2, "seconds_per_scene": 2})
    assert j["status"] == "done", j["error"]
    assert abs(j["cost"] - 0.001) < 1e-9  # só o roteiro usa IA
    assert len(calls) == 1 and "CATÁLOGO 3D" in calls[0]
    assert len(vids) == 1
    v = vids[0]
    assert v["hashtags"] == "#gato #3d"
    assert (config.media_dir / v["file"]).exists()
    assert 3.5 <= v["duration"] <= 5.5
    assert v["meta"]["engine"] == "render3d"
    assert v["meta"]["scenes"][1]["scene3d"]["setting"] == "forest"
    assert v["meta"]["scenes"][1]["scene3d"]["actors"][0]["actions"] == ["stack"]
    assert "Cena 1: space" in j["log"]


def test_prompt3d_without_api_key_uses_automatic_script():
    init_db()
    st.set_many({"openrouter_api_key": ""})
    j, vids = _run_job(
        {"prompt": "um robô dançando na praia", "scenes": 1, "seconds_per_scene": 2, "theme": "humor"}
    )
    assert j["status"] == "done", j["error"]
    assert not j["cost"]
    assert "roteiro automático" in j["log"]
    scene = vids[0]["meta"]["scenes"][0]["scene3d"]
    assert scene["setting"] == "beach"
    assert scene["actors"][0]["type"] == "robot" and scene["actors"][0]["actions"] == ["dance"]
