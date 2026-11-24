"""Narração com voz local (Kokoro, ONNX): roda no próprio servidor, sem API e sem custo.

Na primeira narração o modelo (~350 MB) é baixado uma vez para `DATA_DIR/models/kokoro`,
do mesmo jeito que o Whisper baixa o modelo de transcrição. Vozes em português do Brasil:
Dora (feminina), Alex e Santa (masculinas).
"""

from __future__ import annotations

import logging
import os
import re
import unicodedata
from collections.abc import Callable
from pathlib import Path

import numpy as np

from .config import config
from .media import Word

log = logging.getLogger("postop.tts")

VOICES = {"pf_dora": "Dora (feminina)", "pm_alex": "Alex (masculina)", "pm_santa": "Santa (masculina)"}
DEFAULT_VOICE = "pf_dora"
LANG = "pt-br"
BASE_URL = "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/"
# arquivo e tamanho mínimo aceito (menor que isso é download quebrado: baixa de novo)
FILES = {"model": ("kokoro-v1.0.onnx", 250_000_000), "voices": ("voices-v1.0.bin", 20_000_000)}


class TTSError(RuntimeError):
    pass


def public_voices() -> list[dict]:
    return [{"key": k, "name": v} for k, v in VOICES.items()]


def model_dir() -> Path:
    return config.models_dir / "kokoro"


def _download(url: str, dest: Path, progress: Callable[[float], None]) -> None:
    """Baixa `url` para `dest` (arquivo temporário + rename: nunca deixa um modelo pela metade)."""
    import httpx

    tmp = dest.with_name(f"{dest.name}.{os.getpid()}.part")
    try:
        with httpx.stream("GET", url, follow_redirects=True, timeout=httpx.Timeout(60.0, read=300.0)) as r:
            if r.status_code >= 400:
                raise TTSError(f"download de {dest.name} falhou: HTTP {r.status_code}")
            total = int(r.headers.get("content-length") or 0)
            done = 0
            with tmp.open("wb") as fh:
                for chunk in r.iter_bytes(1 << 20):
                    fh.write(chunk)
                    done += len(chunk)
                    progress(done / total if total else 0.0)
        if total and done != total:
            raise TTSError(f"download de {dest.name} incompleto ({done} de {total} bytes)")
        tmp.replace(dest)
    except httpx.HTTPError as exc:
        raise TTSError(f"download de {dest.name} falhou: {exc}") from exc
    finally:
        tmp.unlink(missing_ok=True)


def ensure_files(report: Callable[[str], None] | None = None) -> tuple[Path, Path]:
    """Garante o modelo e as vozes em `DATA_DIR/models/kokoro` (baixa só o que falta)."""
    d = model_dir()
    d.mkdir(parents=True, exist_ok=True)
    paths = {key: d / name for key, (name, _size) in FILES.items()}
    missing = [
        (key, size)
        for key, (_name, size) in FILES.items()
        if not paths[key].exists() or paths[key].stat().st_size < size
    ]
    expected = sum(size for _key, size in missing) or 1
    acc, last = 0.0, -1
    for key, size in missing:
        log.info("baixando %s", paths[key].name)
        share = size / expected  # peso do arquivo na barra de progresso

        def progress(frac: float, acc: float = acc, share: float = share) -> None:
            nonlocal last
            pct = min(100, int((acc + share * min(frac, 1.0)) * 100))
            if report and pct // 10 != last:
                last = pct // 10
                report(f"Baixando a voz da narração (só na primeira vez): {pct}%")

        _download(BASE_URL + FILES[key][0], paths[key], progress)
        acc += share
    return paths["model"], paths["voices"]


_EMOJI = re.compile(r"[\U0001F000-\U0001FAFF☀-➿️‍]")


def clean_text(text: str) -> str:
    """Tira emoji, hashtag, link e símbolos que a voz leria de forma estranha."""
    t = _EMOJI.sub(" ", str(text or ""))
    t = re.sub(r"https?://\S+", " ", t)
    t = re.sub(r"#\w+", " ", t)
    t = t.replace("*", " ").replace("_", " ").replace("…", "...").replace("—", ", ").replace("–", ", ")
    t = re.sub(r"\s+", " ", t).strip()
    if t and t[-1] not in ".!?…":
        t += "."
    return t


def _syllables(word: str) -> float:
    w = unicodedata.normalize("NFKD", word.lower()).encode("ascii", "ignore").decode()
    groups = len(re.findall(r"[aeiouy]+", w)) or (1 if re.search(r"\d", w) else 0)
    digits = len(re.findall(r"\d", w))
    return max(1.0, groups + digits * 1.5)


def word_timings(text: str, duration: float, start: float = 0.0) -> list[Word]:
    """Estima quando cada palavra é falada (proporcional às sílabas, com pausas na pontuação)."""
    words = [w for w in str(text or "").split() if w.strip()]
    if not words or duration <= 0:
        return []
    weights = []
    for w in words:
        pause = 1.4 if w[-1] in ".!?…" else 0.8 if w[-1] in ",;:" else 0.0
        weights.append((_syllables(w), pause))
    total = sum(s + p for s, p in weights)
    k = duration / total
    out, t = [], start
    for w, (s, p) in zip(words, weights, strict=True):
        out.append(Word(t, t + s * k, " " + w))
        t += (s + p) * k
    return out


class Narrator:
    """Carrega o modelo uma vez e gera a fala de cada cena."""

    def __init__(
        self, voice: str = DEFAULT_VOICE, speed: float = 1.05, report: Callable[[str], None] | None = None
    ):
        try:
            from kokoro_onnx import Kokoro
        except ImportError as exc:  # pacote não instalado
            raise TTSError("o pacote kokoro-onnx não está instalado") from exc
        model, voices = ensure_files(report)
        try:
            import onnxruntime

            onnxruntime.set_default_logger_severity(3)  # só erros (sem avisos de hardware no log)
            self.kokoro = Kokoro(str(model), str(voices))
        except Exception as exc:  # noqa: BLE001 — arquivo corrompido, runtime etc.
            raise TTSError(f"não foi possível carregar a voz: {exc}") from exc
        self.voice = voice if voice in VOICES else DEFAULT_VOICE
        self.speed = speed

    def say(self, text: str, speed: float | None = None) -> tuple[np.ndarray, int]:
        text = clean_text(text)
        if not text:
            return np.zeros(0, np.float32), 24000
        try:
            samples, sr = self.kokoro.create(
                text, voice=self.voice, speed=float(speed or self.speed), lang=LANG
            )
        except Exception as exc:  # noqa: BLE001
            raise TTSError(f"falha ao gerar a fala: {exc}") from exc
        audio = np.asarray(samples, dtype=np.float32).reshape(-1)
        peak = float(np.max(np.abs(audio))) if len(audio) else 0.0
        if peak > 1e-6:
            audio = audio * (0.9 / peak)
        return audio, int(sr)
