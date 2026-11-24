"""Narração: download do modelo (simulado) e voz real (Kokoro, ~350 MB: só com POSTOP_TTS_TEST=1)."""

import os

import numpy as np
import pytest

real_voice = pytest.mark.skipif(os.environ.get("POSTOP_TTS_TEST") != "1", reason="defina POSTOP_TTS_TEST=1")


@real_voice
@pytest.mark.parametrize("voice", ["pf_dora", "pm_alex", "pm_santa"])
def test_kokoro_speaks_portuguese(voice, tmp_path):
    from app.render3d import sound as S
    from app.tts import Narrator

    narrator = Narrator(voice)
    audio, sr = narrator.say("Olá! Você sabia que o polvo tem três corações e sangue azul?")
    assert sr > 8000 and audio.dtype == np.float32
    dur = len(audio) / sr
    assert 1.5 < dur < 12, dur
    assert float(np.abs(audio).max()) > 0.3
    out = os.environ.get("POSTOP_TTS_SAMPLES")
    if out:  # guarda amostras para conferir (artefato do CI)
        os.makedirs(out, exist_ok=True)
        S.write_wav(os.path.join(out, f"{voice}.wav"), S.resample(audio, sr))


class _FakeStream:
    def __init__(self, data: bytes, length: int | None = None, status: int = 200):
        self.data, self.status_code = data, status
        self.headers = {"content-length": str(len(data) if length is None else length)}

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def iter_bytes(self, n):
        for i in range(0, len(self.data), n):
            yield self.data[i : i + n]


def _fake_httpx(monkeypatch, stream):
    import sys
    import types

    class HTTPError(Exception):
        pass

    fake = types.SimpleNamespace(stream=stream, Timeout=lambda *a, **k: None, HTTPError=HTTPError)
    monkeypatch.setitem(sys.modules, "httpx", fake)


def test_model_download_once_with_overall_progress(tmp_path, monkeypatch):
    from app import tts

    sizes = {"m.onnx": 3_000_000, "v.bin": 1_000_000}
    monkeypatch.setattr(tts, "FILES", {"model": ("m.onnx", 2_900_000), "voices": ("v.bin", 900_000)})
    monkeypatch.setattr(tts, "model_dir", lambda: tmp_path / "kokoro")
    calls = []

    def fake_stream(method, url, **kw):
        name = url.rsplit("/", 1)[-1]
        calls.append(name)
        return _FakeStream(b"x" * sizes[name])

    _fake_httpx(monkeypatch, fake_stream)
    msgs = []
    model, voices = tts.ensure_files(msgs.append)
    assert model.stat().st_size == 3_000_000 and voices.stat().st_size == 1_000_000
    assert calls == ["m.onnx", "v.bin"]
    pcts = [int(m.rsplit(" ", 1)[-1].rstrip("%")) for m in msgs]
    assert pcts == sorted(pcts) and pcts[-1] == 100  # uma barra só, de 0 a 100
    assert not list((tmp_path / "kokoro").glob("*.part"))
    tts.ensure_files(msgs.append)  # já baixado: não baixa de novo
    assert calls == ["m.onnx", "v.bin"]


def test_model_download_rejects_truncated_file(tmp_path, monkeypatch):
    from app import tts

    monkeypatch.setattr(tts, "FILES", {"model": ("m.onnx", 10), "voices": ("v.bin", 10)})
    monkeypatch.setattr(tts, "model_dir", lambda: tmp_path / "kokoro")
    _fake_httpx(monkeypatch, lambda *a, **k: _FakeStream(b"x" * 500, length=1000))
    with pytest.raises(tts.TTSError, match="incompleto"):
        tts.ensure_files()
    assert not list((tmp_path / "kokoro").iterdir())  # nada pela metade fica no disco
