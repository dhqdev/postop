"""Motor 3D procedural do PostOp: cenas montadas e animadas por código (numpy + OpenCV + ffmpeg).

Fluxo: a IA de texto descreve cada cena com o catálogo (`catalog_text`), `normalize_scene`
confere e completa a descrição, `Scene` monta cenário, atores e câmera, e `render_to_mp4`
desenha os quadros e grava o clipe 9:16. Nada aqui usa IA ou rede.
"""

from __future__ import annotations

from pathlib import Path

from .renderer import render_to_mp4
from .scene import ActorSpec, Scene, SceneSpec
from .spec import catalog_text, normalize_scene, offline_script

__all__ = [
    "ActorSpec",
    "Scene",
    "SceneSpec",
    "catalog_text",
    "describe",
    "init_worker",
    "normalize_scene",
    "offline_script",
    "render_scene",
]


def render_scene(
    spec: SceneSpec,
    out: str | Path,
    seconds: float,
    look: str = "pixar3d",
    seed: int = 0,
    index: int = 0,
    width: int = 1080,
    height: int = 1920,
    fps: int = 30,
) -> str:
    """Renderiza uma cena em mp4 (sem áudio). Função de módulo para rodar em outro processo."""
    scene = Scene(spec, seconds, look, seed, index)
    render_to_mp4(scene, Path(out), seconds, fps, width, height)
    return str(out)


def init_worker() -> None:
    """Processo de renderização em paralelo: 1 thread do OpenCV por processo (evita disputa de núcleos)."""
    import cv2

    cv2.setNumThreads(1)


def describe(spec: SceneSpec) -> str:
    """Resumo curto da cena para o log do job."""
    actors = ", ".join(
        f"{a.count}x {a.type}" + (f" ({'/'.join(a.actions)})" if a.actions else "") for a in spec.actors
    )
    return f"{spec.setting}/{spec.time} · câmera {spec.camera or 'auto'} · {actors}"
