"""Modo 1: link do YouTube -> cortes verticais com legenda queimada."""

from __future__ import annotations

import re
from pathlib import Path

from ..config import config
from ..media import (
    Word,
    build_ass,
    duration_of,
    face_center_x,
    ffmpeg,
    render_clip,
    thumbnail,
    transcribe,
    words_to_segments,
)
from ..openrouter import OpenRouter, OpenRouterError
from . import Cancelled, Ctx

YOUTUBE_RE = re.compile(r"^(https?://)?(www\.|m\.|music\.)?(youtube\.com|youtu\.be)/", re.I)

CLIP_SYSTEM = """Você é um editor de vídeos virais para TikTok/Reels/Shorts.
Recebe a transcrição com tempos (segundos) de um vídeo do YouTube e escolhe os MELHORES trechos
para virar cortes verticais independentes. Cada corte precisa:
- começar com um gancho forte (frase que prende nos 3 primeiros segundos);
- ter início e fim naturais (não cortar no meio de uma frase);
- fazer sentido sozinho, sem contexto do resto do vídeo.
Responda APENAS com JSON no formato:
{"clips": [{"start": 12.3, "end": 55.0, "title": "título curto",
 "caption": "legenda do post com emoji e chamada", "hashtags": ["#tag1", "#tag2"],
 "score": 0-100, "reason": "por que viraliza"}]}
Escreva title, caption e hashtags no mesmo idioma da transcrição."""


def _score(c: dict) -> float:
    try:
        return float(c.get("score", 0) or 0)
    except (TypeError, ValueError):
        return 0.0


def is_youtube_url(url: str) -> bool:
    return bool(YOUTUBE_RE.match(url.strip()))


def download(url: str, work: Path, cookies: str, ctx: Ctx) -> tuple[Path, dict]:
    import yt_dlp

    opts: dict = {
        "format": "bv*[height<=1080][ext=mp4]+ba[ext=m4a]/bv*[height<=1080]+ba/b[height<=1080]/b",
        "merge_output_format": "mp4",
        "outtmpl": str(work / "source.%(ext)s"),
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
        "retries": 3,
    }
    if cookies.strip():
        cookie_file = work / "cookies.txt"
        cookie_file.write_text(cookies)
        opts["cookiefile"] = str(cookie_file)

    def hook(d: dict) -> None:
        if ctx.cancelled():
            raise Cancelled()
        if d.get("status") == "downloading":
            total = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
            if total:
                pct = int(d.get("downloaded_bytes", 0) * 100 / total)
                ctx.report(2 + pct // 6, f"Baixando vídeo do YouTube ({pct}%)")

    opts["progress_hooks"] = [hook]
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=True)
    files = sorted(work.glob("source.*"), key=lambda p: p.stat().st_size, reverse=True)
    files = [f for f in files if f.suffix in (".mp4", ".mkv", ".webm", ".mov")]
    if not files:
        raise RuntimeError("Download do YouTube não gerou arquivo de vídeo")
    return files[0], {
        "title": info.get("title", ""),
        "duration": info.get("duration"),
        "channel": info.get("uploader", ""),
        "id": info.get("id"),
    }


def _snap(words: list[Word], start: float, end: float) -> tuple[float, float]:
    starts = [w.start for w in words if w.start >= start - 1.0]
    s = min(starts, key=lambda t: abs(t - start)) if starts else start
    ends = [w.end for w in words if w.end <= end + 1.5]
    e = min(ends, key=lambda t: abs(t - end)) if ends else end
    return max(0.0, s - 0.15), e + 0.25


def heuristic_clips(segments: list[dict], n: int, min_s: float, max_s: float) -> list[dict]:
    """Sem LLM: pega blocos contínuos com mais fala por segundo."""
    blocks: list[dict] = []
    i = 0
    while i < len(segments):
        start = segments[i]["start"]
        text = []
        j = i
        while j < len(segments) and segments[j]["end"] - start < max_s:
            text.append(segments[j]["text"])
            j += 1
        end = segments[j - 1]["end"] if j > i else segments[i]["end"]
        if end - start >= min_s:
            density = len(" ".join(text).split()) / max(end - start, 1)
            blocks.append(
                {
                    "start": start,
                    "end": end,
                    "title": " ".join(text)[:60],
                    "caption": "",
                    "hashtags": [],
                    "score": round(density * 20, 1),
                    "reason": "densidade de fala",
                }
            )
        i = max(j, i + 1)
    blocks.sort(key=lambda b: b["score"], reverse=True)
    return sorted(blocks[:n], key=lambda b: b["start"])


def clean_clips(
    raw: list[dict], words: list[Word], total: float, n: int, min_s: float, max_s: float
) -> list[dict]:
    clips: list[dict] = []
    for c in raw:
        try:
            start, end = float(c["start"]), float(c["end"])
        except (KeyError, TypeError, ValueError):
            continue
        if end <= start:
            continue
        if end - start > max_s:
            end = start + max_s
        if end - start < min_s:
            end = min(start + min_s, total)
        start, end = _snap(words, start, end) if words else (start, end)
        end = min(end, total)
        if end - start < min(min_s, 5):
            continue
        if any(not (end <= o["start"] or start >= o["end"]) for o in clips):
            continue
        tags = c.get("hashtags") or []
        if isinstance(tags, str):
            tags = tags.split()
        tags = [t if t.startswith("#") else f"#{t}" for t in tags if t]
        clips.append(
            {
                "start": round(start, 2),
                "end": round(end, 2),
                "title": str(c.get("title", ""))[:200],
                "caption": str(c.get("caption", "")),
                "hashtags": tags[:8],
                "score": _score(c),
                "reason": str(c.get("reason", "")),
            }
        )
        if len(clips) >= n:
            break
    return clips


def choose_clips(ctx: Ctx, segments: list[dict], words: list[Word], total: float, meta: dict) -> list[dict]:
    p = ctx.params
    n = int(p.get("max_clips", 5))
    min_s, max_s = float(p.get("min_seconds", 20)), float(p.get("max_seconds", 60))
    api_key = ctx.settings.get("openrouter_api_key", "")
    if api_key and segments:
        transcript = "\n".join(f"[{s['start']:.1f}-{s['end']:.1f}] {s['text']}" for s in segments)
        extra = p.get("instructions", "").strip()
        user = (
            f"Título do vídeo: {meta.get('title', '')}\nDuração total: {total:.0f}s\n"
            f"Quero até {n} cortes, cada um entre {min_s:.0f} e {max_s:.0f} segundos.\n"
            + (f"Instruções extras: {extra}\n" if extra else "")
            + f"\nTranscrição:\n{transcript}"
        )
        try:
            client = OpenRouter(api_key)
            data, cost, model = client.chat_json(
                [ctx.settings.get("text_model", ""), ctx.settings.get("text_fallback_model", "")],
                CLIP_SYSTEM,
                user,
            )
            ctx.add_cost(cost)
            ctx.log(f"Cortes escolhidos por {model}")
            raw = data.get("clips", []) if isinstance(data, dict) else data
            raw = [c for c in (raw if isinstance(raw, list) else []) if isinstance(c, dict)]
            raw = sorted(raw, key=_score, reverse=True)
            clips = clean_clips(raw, words, total, n, min_s, max_s)
            if clips:
                return clips
            ctx.log("LLM não retornou cortes válidos, usando heurística")
        except OpenRouterError as exc:
            ctx.log(f"Falha no LLM ({exc}); usando heurística")
    else:
        ctx.log("Sem API key do OpenRouter: escolhendo cortes por heurística")
    return clean_clips(heuristic_clips(segments, n, min_s, max_s), words, total, n, min_s, max_s)


def run(ctx: Ctx, work: Path, out_dir: Path) -> list[dict]:
    url = ctx.params["url"].strip()
    ctx.report(2, "Baixando vídeo do YouTube")
    src, meta = download(url, work, ctx.settings.get("youtube_cookies", ""), ctx)
    total = duration_of(src) or float(meta.get("duration") or 0)
    ctx.log(f"Baixado: {meta.get('title')} ({total:.0f}s)")

    if ctx.cancelled():
        raise Cancelled()
    ctx.report(20, "Extraindo áudio")
    audio = work / "audio.wav"
    ffmpeg("-i", str(src), "-vn", "-ac", "1", "-ar", "16000", str(audio))

    ctx.report(25, "Transcrevendo (Whisper local)")
    lang = ctx.params.get("language") or ctx.settings.get("whisper_language", "pt")
    words = transcribe(audio, ctx.settings.get("whisper_model", "base"), lang, config.models_dir)
    ctx.log(f"Transcrição: {len(words)} palavras")
    segments = words_to_segments(words)

    if ctx.cancelled():
        raise Cancelled()
    ctx.report(50, "Escolhendo os melhores trechos com IA")
    clips = choose_clips(ctx, segments, words, total, meta)
    if not clips:
        raise RuntimeError("Não foi possível encontrar trechos para cortar (vídeo sem fala?)")

    style = ctx.params.get("subtitle_style") or ctx.settings.get("subtitle_style", "highlight")
    color = ctx.settings.get("subtitle_color", "#FFE14D")
    mode = ctx.params.get("reframe", "auto")
    outputs: list[dict] = []
    for idx, clip in enumerate(clips, start=1):
        if ctx.cancelled():
            raise Cancelled()
        ctx.report(55 + int(40 * (idx - 1) / len(clips)), f"Renderizando corte {idx}/{len(clips)}")
        s, e = clip["start"], clip["end"]
        clip_words = [
            Word(w.start - s, w.end - s, w.text) for w in words if w.start >= s and w.end <= e + 0.3
        ]
        ass_path = None
        if style != "none":
            ass_path = work / f"clip{idx}.ass"
            ass_path.write_text(build_ass(clip_words, style=style, highlight=color), encoding="utf-8")
        cx = face_center_x(src, s, e) if mode in ("auto", "face") else None
        out = out_dir / f"corte_{idx:02d}.mp4"
        render_clip(src, out, s, e, ass_path, mode="crop" if mode == "face" else mode, center_x=cx)
        thumb = thumbnail(out, out_dir / f"corte_{idx:02d}.jpg", at=min(1.5, (e - s) / 2))
        outputs.append(
            {
                "file": out,
                "thumb": thumb,
                "title": clip["title"] or f"{meta.get('title', 'Corte')} #{idx}",
                "caption": clip["caption"],
                "hashtags": " ".join(clip["hashtags"]),
                "duration": duration_of(out),
                "score": clip["score"],
                "meta": {
                    "source_url": url,
                    "source_title": meta.get("title"),
                    "start": s,
                    "end": e,
                    "reason": clip["reason"],
                    "transcript": " ".join(w.text.strip() for w in clip_words),
                },
            }
        )
    return outputs
