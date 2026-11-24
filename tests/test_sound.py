"""Som gerado por código: eventos das cenas, trilha, mixagem com ducking e legenda pela fala."""

import shutil

import numpy as np
import pytest

from app.render3d import normalize_scene
from app.render3d import sound as S
from app.render3d.scene import Scene
from app.tts import clean_text, word_timings


def _scene(raw, seconds=4.0):
    return Scene(normalize_scene(raw), seconds, "pixar3d", seed=1)


def _count(events, name):
    return sum(1 for _t, n, _o in events if n == name)


def test_events_follow_the_actions():
    stack = S.scene_events(_scene({"actors": [{"type": "block", "count": 6, "actions": ["stack"]}]}))
    assert _count(stack, "knock") == 6
    domino = S.scene_events(_scene({"actors": [{"type": "domino", "count": 9, "actions": ["domino"]}]}))
    assert _count(domino, "clack") == 9
    boom = S.scene_events(_scene({"actors": [{"type": "lego", "count": 8, "actions": ["build", "explode"]}]}))
    assert _count(boom, "boom") == 1
    walk = S.scene_events(_scene({"actors": [{"type": "person", "actions": ["walk"]}]}))
    steps = [t for t, n, _o in walk if n == "step"]
    assert len(steps) >= 8 and all(0 <= t < 4.0 for t in steps)
    rocket = S.scene_events(
        _scene({"setting": "moon", "actors": [{"type": "rocket", "actions": ["idle", "launch"]}]})
    )
    assert _count(rocket, "rocket") == 1


def test_scene_audio_is_a_clean_stereo_track():
    for setting, weather in (
        ("forest", "none"),
        ("city", "storm"),
        ("underwater", "none"),
        ("space", "none"),
    ):
        sc = _scene(
            {
                "setting": setting,
                "weather": weather,
                "actors": [{"type": "cat", "actions": ["walk", "jump"]}],
            },
            3.0,
        )
        a = S.scene_audio(sc, 3)
        assert a.shape == (S._n(3.0), 2), setting
        assert np.isfinite(a).all() and 0.005 < float(np.abs(a).max()) <= 1.5, setting


def test_wav_roundtrip_and_resample(tmp_path):
    x = (np.sin(np.linspace(0, 200, 24000)) * 0.5).astype(np.float32)
    y = S.resample(x, 24000)
    assert abs(len(y) - S.SR) <= 1
    path = S.write_wav(tmp_path / "a.wav", np.stack([y, y], axis=1))
    back = S.read_wav(path)
    assert back.shape == (len(y), 2) and np.allclose(back[:, 0], y, atol=1e-3)


@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg ausente")
def test_mix_ducks_music_under_the_voice(tmp_path):
    from app import media

    music = tmp_path / "m.wav"
    media.ffmpeg("-f", "lavfi", "-i", "sine=frequency=220:duration=2", str(music))
    t = np.arange(S._n(2.0)) / S.SR
    voice = (np.sin(2 * np.pi * 3000 * t) * 0.5).astype(np.float32)  # "voz" em outra frequência
    total = 6.0
    track = np.zeros((S._n(3.0), 2), np.float32)
    out = S.mix_soundtrack(total, [(0.0, track), (2.5, track)], [(3.0, voice)], music, 0.5, [2.5])
    assert out.shape[1] == 2 and len(out) >= S._n(total)
    assert np.isfinite(out).all() and float(np.abs(out).max()) <= 1.0

    def level(freq, a, b):
        seg = out[S._n(a) : S._n(b), 0]
        spec = np.abs(np.fft.rfft(seg * np.hanning(len(seg))))
        k = int(round(freq * len(seg) / S.SR))
        return float(spec[k - 2 : k + 3].max())

    before, during = level(220, 1.4, 2.4), level(220, 3.5, 4.5)
    assert before > 0 and during < before * 0.5  # a música abaixa enquanto a voz fala
    assert level(3000, 3.5, 4.5) > level(3000, 1.4, 2.4) * 10  # e a voz entra


def test_word_timings_and_clean_text():
    text = clean_text("Você sabia? 🚀 O polvo tem três corações! #ciencia https://x.y")
    assert "🚀" not in text and "#" not in text and "http" not in text and text.endswith("!")
    words = word_timings(text, 3.0, start=10.0)
    assert [w.text.strip() for w in words] == text.split()
    assert words[0].start == 10.0 and words[-1].end <= 13.0 + 1e-6
    assert all(a.start < b.start for a, b in zip(words, words[1:], strict=False))
