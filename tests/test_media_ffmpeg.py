"""Testes de integração com ffmpeg real (rápidos, vídeos sintéticos)."""

import shutil
from pathlib import Path

import pytest

from app import media

pytestmark = pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg ausente")


def _source_video(path: Path, seconds: int = 4) -> Path:
    media.ffmpeg(
        "-f",
        "lavfi",
        "-i",
        f"testsrc=size=1280x720:rate=30:duration={seconds}",
        "-f",
        "lavfi",
        "-i",
        f"sine=frequency=440:duration={seconds}",
        "-c:v",
        "libx264",
        "-preset",
        "ultrafast",
        "-c:a",
        "aac",
        "-shortest",
        str(path),
    )
    return path


def test_render_clip_vertical_with_subtitles(tmp_path):
    src = _source_video(tmp_path / "src.mp4")
    ass = tmp_path / "s.ass"
    ass.write_text(
        media.build_ass([media.Word(0.1, 0.6, "Olá"), media.Word(0.6, 1.2, "TikTok")]), encoding="utf-8"
    )
    out = tmp_path / "out.mp4"
    media.render_clip(src, out, 0.5, 2.5, ass, mode="blur", center_x=None)
    assert media.video_size(out) == (1080, 1920)
    assert 1.8 <= media.duration_of(out) <= 2.3
    assert media.has_audio(out)
    thumb = media.thumbnail(out, tmp_path / "t.jpg")
    assert thumb.exists()


def test_concat_and_finalize_scenes(tmp_path):
    clips = []
    for i, color in enumerate(["red", "blue"]):
        c = tmp_path / f"c{i}.mp4"
        media.ffmpeg(
            "-f", "lavfi", "-i", f"color=c={color}:size=1080x1920:rate=30:duration=1.5",
            "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p", str(c),
        )  # fmt: skip
        clips.append(c)
    joined = tmp_path / "joined.mp4"
    total = media.concat_xfade(clips, joined, fade=0.5)
    assert 2.0 <= total <= 3.0
    ass = tmp_path / "scenes.ass"
    ass.write_text(media.build_scene_ass([(0, 1, "Cena 1"), (1, 2.5, "Cena 2")]), encoding="utf-8")
    final = tmp_path / "final.mp4"
    media.finalize(joined, final, ass)
    assert media.video_size(final) == (1080, 1920)
    assert media.has_audio(final)
