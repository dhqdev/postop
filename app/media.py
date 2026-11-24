"""FFmpeg, legendas ASS, transcrição e enquadramento 9:16."""

from __future__ import annotations

import json
import logging
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

log = logging.getLogger("postop.media")

W, H, FPS = 1080, 1920, 30
FONT = "Montserrat ExtraBold"


class MediaError(RuntimeError):
    pass


def run(cmd: list[str], timeout: int = 3600) -> str:
    log.debug("run: %s", " ".join(cmd))
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    if proc.returncode != 0:
        raise MediaError(f"{Path(cmd[0]).name} falhou: {proc.stderr[-1500:]}")
    return proc.stdout


def ffmpeg(*args: str, timeout: int = 3600) -> None:
    run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", *args], timeout=timeout)


def probe(path: Path) -> dict:
    out = run(["ffprobe", "-v", "error", "-print_format", "json", "-show_format", "-show_streams", str(path)])
    return json.loads(out)


def duration_of(path: Path) -> float:
    try:
        return float(probe(path)["format"]["duration"])
    except (KeyError, ValueError, MediaError):
        return 0.0


def video_size(path: Path) -> tuple[int, int]:
    for s in probe(path).get("streams", []):
        if s.get("codec_type") == "video":
            return int(s["width"]), int(s["height"])
    raise MediaError("Arquivo sem trilha de vídeo")


def has_audio(path: Path) -> bool:
    return any(s.get("codec_type") == "audio" for s in probe(path).get("streams", []))


def thumbnail(video: Path, out: Path, at: float = 1.0) -> Path:
    ffmpeg("-ss", f"{at:.2f}", "-i", str(video), "-frames:v", "1", "-vf", "scale=360:-2", str(out))
    return out


# ------------------------------------------------------------------ legendas
@dataclass
class Word:
    start: float
    end: float
    text: str


def _ass_time(t: float) -> str:
    t = max(t, 0.0)
    h = int(t // 3600)
    m = int((t % 3600) // 60)
    s = t % 60
    return f"{h}:{m:02d}:{s:05.2f}"


def _hex_to_ass(color: str) -> str:
    c = color.lstrip("#")
    if len(c) != 6:
        c = "FFE14D"
    r, g, b = c[0:2], c[2:4], c[4:6]
    return f"&H00{b}{g}{r}".upper()


def _escape(text: str) -> str:
    return text.replace("\\", "").replace("{", "(").replace("}", ")").replace("\n", " ")


def ass_header(font_size: int = 86, margin_v: int = 520, wrap: int = 2) -> str:
    """wrap: 2 = sem quebra (legenda palavra a palavra); 0 = quebra automática (frases das cenas)."""
    return f"""[Script Info]
ScriptType: v4.00+
PlayResX: {W}
PlayResY: {H}
WrapStyle: {wrap}
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Main,{FONT},{font_size},&H00FFFFFF,&H00FFFFFF,&H00000000,&H96000000,-1,0,0,0,100,100,0,0,1,6,3,2,70,70,{margin_v},1
Style: Title,{FONT},72,&H00FFFFFF,&H00FFFFFF,&H00000000,&H96000000,-1,0,0,0,100,100,0,0,3,4,0,8,80,80,160,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""


def group_words(
    words: list[Word], max_words: int = 3, max_gap: float = 0.6, max_dur: float = 1.6
) -> list[list[Word]]:
    groups: list[list[Word]] = []
    cur: list[Word] = []
    for w in words:
        if not w.text.strip():
            continue
        if cur and (
            len(cur) >= max_words
            or w.start - cur[-1].end > max_gap
            or w.end - cur[0].start > max_dur
            or cur[-1].text.rstrip().endswith((".", "!", "?"))
        ):
            groups.append(cur)
            cur = []
        cur.append(w)
    if cur:
        groups.append(cur)
    return groups


def build_ass(
    words: list[Word], style: str = "highlight", highlight: str = "#FFE14D", uppercase: bool = True
) -> str:
    """Gera legendas ASS a partir de palavras com tempo (relativas ao início do corte)."""
    out = [ass_header()]
    if style == "none" or not words:
        return out[0]
    hl = _hex_to_ass(highlight)
    for group in group_words(words):
        texts = [_escape(w.text.strip()) for w in group]
        if uppercase:
            texts = [t.upper() for t in texts]
        g_end = group[-1].end + 0.05
        if style == "simple":
            out.append(
                f"Dialogue: 0,{_ass_time(group[0].start)},{_ass_time(g_end)},Main,,0,0,0,,{' '.join(texts)}\n"
            )
            continue
        for i, w in enumerate(group):
            start = w.start
            end = group[i + 1].start if i + 1 < len(group) else g_end
            if end <= start:
                end = start + 0.05
            parts = []
            for j, t in enumerate(texts):
                if j == i:
                    parts.append(f"{{\\c{hl}\\fscx108\\fscy108}}{t}{{\\c&H00FFFFFF&\\fscx100\\fscy100}}")
                else:
                    parts.append(t)
            out.append(f"Dialogue: 0,{_ass_time(start)},{_ass_time(end)},Main,,0,0,0,,{' '.join(parts)}\n")
    return "".join(out)


def build_scene_ass(scenes: list[tuple[float, float, str]]) -> str:
    """Legendas fixas por cena (modo prompt/3D)."""
    out = [ass_header(font_size=74, margin_v=380, wrap=0)]
    for start, end, text in scenes:
        if text.strip():
            out.append(
                f"Dialogue: 0,{_ass_time(start)},{_ass_time(end)},Main,,0,0,0,,"
                f"{{\\fad(200,200)}}{_escape(text.strip())}\n"
            )
    return "".join(out)


def _filter_path(p: Path) -> str:
    # escapar para uso dentro de filtros do ffmpeg
    return str(p).replace("\\", "/").replace(":", "\\:").replace("'", "\\'")


# ----------------------------------------------------------------- transcrição
_whisper_cache: dict[str, object] = {}


def transcribe(audio: Path, model_size: str, language: str, models_dir: Path) -> list[Word]:
    from faster_whisper import WhisperModel  # import tardio (pesado)

    key = model_size
    if key not in _whisper_cache:
        models_dir.mkdir(parents=True, exist_ok=True)
        _whisper_cache[key] = WhisperModel(
            model_size, device="cpu", compute_type="int8", download_root=str(models_dir)
        )
    model = _whisper_cache[key]
    lang = None if language in ("", "auto") else language
    segments, _info = model.transcribe(str(audio), language=lang, word_timestamps=True, vad_filter=True)  # type: ignore[attr-defined]
    words: list[Word] = []
    for seg in segments:
        for w in seg.words or []:
            words.append(Word(float(w.start), float(w.end), w.word))
    return words


def words_to_segments(words: list[Word], max_len: float = 12.0) -> list[dict]:
    """Agrupa palavras em frases curtas com tempo, para o LLM escolher os cortes."""
    segs: list[dict] = []
    cur: list[Word] = []
    for w in words:
        cur.append(w)
        text = w.text.strip()
        if text.endswith((".", "!", "?")) or (cur[-1].end - cur[0].start) >= max_len:
            segs.append(
                {
                    "start": round(cur[0].start, 2),
                    "end": round(cur[-1].end, 2),
                    "text": "".join(x.text for x in cur).strip(),
                }
            )
            cur = []
    if cur:
        segs.append(
            {
                "start": round(cur[0].start, 2),
                "end": round(cur[-1].end, 2),
                "text": "".join(x.text for x in cur).strip(),
            }
        )
    return segs


# ------------------------------------------------------------ enquadramento
def face_center_x(video: Path, start: float, end: float, samples: int = 12) -> float | None:
    """Centro horizontal (0..1) médio dos rostos no trecho, ou None."""
    try:
        import cv2
    except ImportError:  # pragma: no cover
        return None
    cascade_path = Path(cv2.data.haarcascades) / "haarcascade_frontalface_default.xml"
    if not cascade_path.exists():
        return None
    cascade = cv2.CascadeClassifier(str(cascade_path))
    cap = cv2.VideoCapture(str(video))
    xs: list[float] = []
    try:
        width = cap.get(cv2.CAP_PROP_FRAME_WIDTH) or 1
        span = max(end - start, 0.1)
        for i in range(samples):
            t = start + span * (i + 0.5) / samples
            cap.set(cv2.CAP_PROP_POS_MSEC, t * 1000)
            ok, frame = cap.read()
            if not ok:
                continue
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            small = cv2.resize(gray, None, fx=0.5, fy=0.5)
            faces = cascade.detectMultiScale(small, scaleFactor=1.1, minNeighbors=6, minSize=(40, 40))
            if len(faces):
                x, _y, w, _h = max(faces, key=lambda f: f[2] * f[3])
                xs.append(((x + w / 2) * 2) / width)
    finally:
        cap.release()
    if len(xs) < max(2, samples // 4):
        return None
    xs.sort()
    return xs[len(xs) // 2]


def reframe_filter(src_w: int, src_h: int, mode: str, center_x: float | None) -> str:
    """Filtro ffmpeg que leva o vídeo para 1080x1920."""
    if src_w / src_h <= W / H + 0.01:  # já é vertical
        return f"scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},setsar=1"
    if mode == "blur" or (mode == "auto" and center_x is None):
        return (
            f"split=2[bg][fg];[bg]scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},"
            f"boxblur=20:2,eq=brightness=-0.08[bg2];[fg]scale={W}:-2[fg2];"
            f"[bg2][fg2]overlay=(W-w)/2:(H-h)/2,setsar=1"
        )
    cx = 0.5 if center_x is None else center_x
    scaled_w = int(round(src_w * H / src_h / 2) * 2)
    x = int(min(max(cx * scaled_w - W / 2, 0), scaled_w - W))
    return f"scale={scaled_w}:{H},crop={W}:{H}:{x}:0,setsar=1"


def render_clip(
    src: Path, out: Path, start: float, end: float, ass: Path | None, mode: str, center_x: float | None
) -> None:
    sw, sh = video_size(src)
    vf = reframe_filter(sw, sh, mode, center_x)
    if ass is not None:
        vf += f",subtitles='{_filter_path(ass)}':fontsdir=/usr/share/fonts"
    vf += f",fps={FPS},format=yuv420p"
    args = ["-ss", f"{start:.3f}", "-to", f"{end:.3f}", "-i", str(src)]
    args += ["-filter_complex", f"[0:v]{vf}[v]", "-map", "[v]"]
    if has_audio(src):
        args += ["-map", "0:a:0", "-c:a", "aac", "-b:a", "160k", "-ar", "44100"]
    args += [
        "-c:v",
        "libx264",
        "-preset",
        "veryfast",
        "-crf",
        "21",
        "-profile:v",
        "high",
        "-movflags",
        "+faststart",
        str(out),
    ]
    ffmpeg(*args)


# ------------------------------------------------------------ montagem
def concat_xfade(clips: list[Path], out: Path, fade: float = 0.5) -> float:
    """Junta clipes com transição suave. Retorna a duração final."""
    if not clips:
        raise MediaError("Nenhum clipe para juntar")
    if len(clips) == 1:
        shutil.copy(clips[0], out)
        return duration_of(out)
    durations = [duration_of(c) for c in clips]
    inputs: list[str] = []
    for c in clips:
        inputs += ["-i", str(c)]
    parts = []
    prev = "[0:v]"
    offset = 0.0
    for i in range(1, len(clips)):
        offset += durations[i - 1] - fade
        label = f"[x{i}]"
        parts.append(f"{prev}[{i}:v]xfade=transition=fade:duration={fade}:offset={offset:.3f}{label}")
        prev = label
    ffmpeg(
        *inputs,
        "-filter_complex",
        ";".join(parts),
        "-map",
        prev,
        "-c:v",
        "libx264",
        "-preset",
        "veryfast",
        "-crf",
        "20",
        "-pix_fmt",
        "yuv420p",
        str(out),
    )
    return sum(durations) - fade * (len(clips) - 1)


def finalize(video: Path, out: Path, ass: Path | None, music: Path | None = None) -> None:
    """Queima legendas e adiciona trilha (opcional) ao vídeo final."""
    vf = "format=yuv420p"
    if ass is not None:
        vf = f"subtitles='{_filter_path(ass)}':fontsdir=/usr/share/fonts,format=yuv420p"
    args = ["-i", str(video)]
    if music is not None:
        args += ["-stream_loop", "-1", "-i", str(music)]
    args += ["-vf", vf, "-map", "0:v"]
    if music is not None:
        args += [
            "-map",
            "1:a",
            "-c:a",
            "aac",
            "-b:a",
            "160k",
            "-shortest",
            "-af",
            "volume=0.6,afade=t=in:d=1",
        ]
    else:
        # TikTok aceita sem áudio, mas alguns players preferem trilha silenciosa
        args = [
            "-i",
            str(video),
            "-f",
            "lavfi",
            "-i",
            "anullsrc=r=44100:cl=stereo",
            "-vf",
            vf,
            "-map",
            "0:v",
            "-map",
            "1:a",
            "-c:a",
            "aac",
            "-shortest",
        ]
    args += ["-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-movflags", "+faststart", str(out)]
    ffmpeg(*args)
