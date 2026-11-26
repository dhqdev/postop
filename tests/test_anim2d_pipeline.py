"""Animação 2D completa: roteiro da IA (simulada, sem rede), voz simulada, cenas 2D, som e vídeo final."""

import shutil

import numpy as np
import pytest

from app import media, tts
from app.openrouter import OpenRouter
from app.pipelines import Ctx, anim2d

pytestmark = pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg ausente")


class FakeNarrator:
    def __init__(self, voice="pf_dora", speed=1.05, report=None):
        self.voice = voice

    def say(self, text, speed=None):
        n = int(24000 * 0.4 * max(1, len(text.split())))
        return (np.sin(np.arange(n) * 0.11) * 0.6).astype(np.float32), 24000


def _run(tmp_path, params, settings):
    logs, costs = [], []
    ctx = Ctx(
        job_id=7,
        params=params,
        settings=settings,
        report=lambda *_: None,
        add_cost=costs.append,
        log=logs.append,
    )
    work, out = tmp_path / "work", tmp_path / "out"
    work.mkdir()
    out.mkdir()
    return anim2d.run(ctx, work, out), logs, costs


def test_anim2d_with_ai_story_voice_and_sound(monkeypatch, tmp_path):
    story = {
        "title": "Os três jovens na fornalha",
        "caption": "A fé que não queimou 🔥",
        "hashtags": ["#fe"],
        "cast": [{"id": "rei", "type": "king"}, {"id": "jovem", "type": "biblical_man"}],
        "scenes": [
            {"narration": "O rei mandou todos se curvarem.", "place": "palace", "banner": "DANIEL 3",
             "show": [{"id": "rei", "do": ["point"]}, {"prop": "statue", "do": ["glow"]}]},
            {"narration": "Mas três jovens ficaram de pé.", "place": "fire",
             "show": [{"id": "jovem", "count": 3, "do": ["pray"]}], "fx": "embers"},
        ],
    }  # fmt: skip
    calls = []

    def fake_chat(self, models, system, user, max_tokens=4000):
        calls.append((system, user, max_tokens))
        return story, 0.0004, "fake/model"

    monkeypatch.setattr(OpenRouter, "chat_json", fake_chat)
    monkeypatch.setattr(tts, "Narrator", FakeNarrator)
    params = {"prompt": "Daniel 3", "scenes": 2, "seconds_per_scene": 2, "theme": "biblia", "style": "papel",
              "narration": True, "voice": "pf_dora", "sfx": True, "captions": True}  # fmt: skip
    out, logs, costs = _run(tmp_path, params, {"openrouter_api_key": "sk-or-teste", "text_model": "a/b"})

    assert costs == [0.0004] and len(calls) == 1  # uma chamada curta à IA por vídeo
    system, user, max_tokens = calls[0]
    assert "CATÁLOGO 2D" in system and "Daniel 3" in user and max_tokens <= 1000
    assert len(out) == 1
    v = out[0]
    assert v["file"].exists() and v["thumb"].exists() and media.has_audio(v["file"])
    assert (
        v["title"] == "Os três jovens na fornalha" and "#biblia" in v["hashtags"] and "#fe" in v["hashtags"]
    )
    assert v["duration"] > 4.0  # cada cena dura o tempo da fala (2 cenas x ~2,8 s)
    meta = v["meta"]
    assert meta["engine"] == "render2d" and meta["script_by_ai"] is True and meta["narration"] is True
    assert [s["narration"] for s in meta["scenes"]] == [s["narration"] for s in story["scenes"]]
    assert any("Cena 2: fire" in line for line in logs)


def test_anim2d_without_key_uses_automatic_story(tmp_path):
    params = {"prompt": "um gato astronauta descobre um planeta de doces", "scenes": 1, "seconds_per_scene": 2,
              "style": "flat", "narration": False, "sfx": False, "captions": True}  # fmt: skip
    out, logs, costs = _run(tmp_path, params, {})
    assert not costs and any("roteiro automático" in line for line in logs)
    v = out[0]
    assert v["meta"]["script_by_ai"] is False and v["meta"]["style"] == "flat"
    assert 2.0 <= v["duration"] <= 5.0  # sem voz, a cena dura o tempo de ler a legenda
