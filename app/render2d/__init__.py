"""Motor de animação 2D do PostOp (estilo desenho animado / recorte de papel), sem IA de imagem.

Fluxo: a IA de texto escreve o roteiro com o catálogo (`catalog_text`), `normalize_story` confere e
completa, `Scene2D` monta cenário, personagens, objetos, textos e efeitos, e `render_scene2d`
desenha os quadros e grava o clipe 9:16 (com a trilha de efeitos, se pedida).
"""

from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path

import numpy as np

from ..pipelines.themes import STYLE2D_NAMES, STYLES2D
from .scene import Element2D, Scene2D, SceneSpec2D
from .story import Story, catalog_text, normalize_story, offline_story

__all__ = [
    "Element2D",
    "Scene2D",
    "SceneSpec2D",
    "STYLES2D",
    "STYLE2D_NAMES",
    "Story",
    "catalog_text",
    "describe",
    "normalize_story",
    "offline_story",
    "render_scene2d",
]


def render_scene2d(
    spec: SceneSpec2D,
    out: str | Path,
    seconds: float,
    style: str = "papel",
    seed: int = 0,
    index: int = 0,
    width: int = 1080,
    height: int = 1920,
    fps: int = 30,
    audio_out: str | None = None,
    words=None,
    caption_style: str = "highlight",
    caption_color=(255, 216, 77),
) -> str:
    """Renderiza uma cena 2D em mp4 (sem áudio) e, se pedido, a trilha de efeitos em wav.

    Função de módulo para poder rodar em outro processo.
    """
    scene = Scene2D(spec, seconds, style, seed, index, width, height, words, caption_style, caption_color)
    frames = max(int(round(seconds * fps)), 1)
    err = tempfile.TemporaryFile()
    cmd = [
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
        "-f", "rawvideo", "-pix_fmt", "bgr24", "-s", f"{width}x{height}", "-r", str(fps), "-i", "-",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "19", "-pix_fmt", "yuv420p", "-an", str(out),
    ]  # fmt: skip
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stderr=err)
    try:
        assert proc.stdin is not None
        for i in range(frames):
            img = scene.frame(i / fps)
            proc.stdin.write(np.ascontiguousarray(img).data)
        proc.stdin.close()
        code = proc.wait(timeout=600)
    except BaseException:
        proc.kill()
        raise
    if code != 0:
        err.seek(0)
        raise RuntimeError("ffmpeg falhou ao gravar a cena 2D: " + err.read().decode(errors="replace")[-800:])
    if audio_out:
        from ..render3d.sound import write_wav
        from .audio import scene_audio2d

        write_wav(audio_out, scene_audio2d(scene, seed))
    return str(out)


def describe(spec: SceneSpec2D) -> str:
    """Resumo curto da cena para o log do job."""
    els = ", ".join(
        (f"{e.count}x " if e.count > 1 else "")
        + (e.ref or e.type)
        + (f" ({'/'.join(e.actions)})" if e.actions else "")
        for e in spec.elements
    )
    extra = [x for x in (spec.banner and f"faixa '{spec.banner}'", spec.fx and f"efeito {spec.fx}") if x]
    return f"{spec.place}/{spec.time} · {els}" + (f" · {', '.join(extra)}" if extra else "")
