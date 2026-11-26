"""Pipeline 3D completo: roteiro pela IA (simulada, sem rede) e cenas pelo motor 3D próprio."""

import shutil

import pytest

from app import settings_store as st
from app.config import config
from app.db import Job, Video, init_db, session_scope
from app.openrouter import OpenRouter
from app.worker import JobRunner, claim_next

pytestmark = pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg ausente")


def _run_job(params: dict, kind: str = "prompt3d") -> tuple[dict, list[dict]]:
    with session_scope() as s:
        s.query(Job).filter(Job.status == "queued").update({"status": "canceled"})
        s.add(Job(kind=kind, title="teste", params=params))
    job = claim_next()
    assert job is not None and job.kind == kind
    JobRunner(job).run()
    with session_scope() as s:
        j = s.get(Job, job.id)
        info = {"status": j.status, "error": j.error, "cost": j.cost_usd, "log": j.log or ""}
        vids = [
            {
                "hashtags": v.hashtags,
                "file": v.file_path,
                "duration": v.duration,
                "meta": v.meta,
                "kind": v.kind,
            }
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


class FakeNarrator:
    """Voz simulada (tom) para testar o fluxo sem baixar o modelo."""

    def __init__(self, voice="pf_dora", speed=1.05, report=None):
        self.voice, self.speed = voice, speed

    def say(self, text, speed=None):
        import numpy as np

        n = int(24000 * 0.45 * max(1, len(text.split())))
        return (np.sin(np.arange(n) * 0.11) * 0.6).astype(np.float32), 24000


def test_prompt3d_with_narration_and_sound_effects(monkeypatch):
    from app import media, tts

    init_db()
    st.set_many({"openrouter_api_key": ""})
    monkeypatch.setattr(tts, "Narrator", FakeNarrator)
    j, vids = _run_job(
        {"prompt": "blocos coloridos empilhando numa torre", "scenes": 1, "seconds_per_scene": 2,
         "narration": True, "voice": "pm_alex", "sfx": True, "captions": True}
    )  # fmt: skip
    assert j["status"] == "done", j["error"]
    assert "Narração gerada" in j["log"]
    v = vids[0]
    assert v["meta"]["narration"] is True and v["meta"]["sfx"] is True and v["meta"]["voice"] == "pm_alex"
    path = config.media_dir / v["file"]
    assert media.has_audio(path)
    # 6 palavras x 0,45 s de fala: a cena cresce além dos 2 s pedidos
    assert v["duration"] > 2.9


def test_anim2d_job_through_the_worker():
    init_db()
    st.set_many({"openrouter_api_key": ""})
    j, vids = _run_job(
        {"prompt": "um rei e uma estátua de ouro no palácio", "scenes": 2, "seconds_per_scene": 2, "theme": "biblia",
         "style": "papel", "narration": False, "sfx": True, "captions": True},
        kind="anim2d",
    )  # fmt: skip
    assert j["status"] == "done", j["error"]
    assert not j["cost"] and "roteiro automático" in j["log"]
    assert len(vids) == 1 and vids[0]["kind"] == "anim2d"
    v = vids[0]
    assert (config.media_dir / v["file"]).exists() and v["meta"]["engine"] == "render2d"
    assert "#biblia" in v["hashtags"]
