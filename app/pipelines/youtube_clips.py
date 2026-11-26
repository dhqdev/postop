"""Modo 1: link do YouTube -> cortes verticais com legenda queimada.

Três jeitos de escolher os cortes:
- "ai": a IA escolhe os melhores trechos (só da parte do vídeo pedida, com a transcrição compacta);
- "manual": você diz os trechos (um por linha, ex.: "1:20-2:05 Título") e nada passa pela IA;
- "parts": divide a parte escolhida em partes seguidas (Parte 1, 2, 3...), também sem IA.

Com trecho definido (início/fim ou cortes manuais) só essa parte do vídeo é baixada e transcrita.
"""

from __future__ import annotations

import re
from pathlib import Path

from ..config import config
from ..media import (
    Word,
    ass_title_line,
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
MODES = ("ai", "manual", "parts")
MAX_PARTS = 60

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


# ------------------------------------------------------------------ tempos e trechos
_HMS = re.compile(r"^\s*(?:(\d+)\s*h)?\s*(?:(\d+)\s*m(?:in)?)?\s*(?:(\d+(?:[.,]\d+)?)\s*s)?\s*$", re.I)


def parse_time(value) -> float | None:
    """'83', '1:23', '01:02:03', '1:23.5', '1m23s', '1h2m' -> segundos. Vazio -> None. Inválido -> ValueError."""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        if value < 0:
            raise ValueError("tempo negativo")
        return float(value)
    s = str(value).strip().lower().replace(",", ".")
    if not s:
        return None
    if re.fullmatch(r"\d+(\.\d+)?", s):
        return float(s)
    if re.fullmatch(r"\d{1,3}(:\d{1,2}){1,2}(\.\d+)?", s):
        parts = s.split(":")
        secs = float(parts[-1])
        mins = int(parts[-2])
        hours = int(parts[-3]) if len(parts) == 3 else 0
        if secs >= 60 or (len(parts) == 3 and mins >= 60):
            raise ValueError(f"tempo inválido: {value}")
        return hours * 3600 + mins * 60 + secs
    m = _HMS.match(s)
    if m and any(m.groups()):
        h, mi, se = m.groups()
        return int(h or 0) * 3600 + int(mi or 0) * 60 + float(se or 0)
    raise ValueError(f"tempo inválido: {value}")


def fmt_time(t: float) -> str:
    t = max(0, int(round(t)))
    h, rem = divmod(t, 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


_TIME_TOKEN = r"\d{1,3}(?::\d{1,2}){1,2}(?:[.,]\d+)?|\d+(?:[.,]\d+)?\s*[hms][\dhms.,]*|\d+(?:[.,]\d+)?"
_RANGE = re.compile(
    rf"^\s*(?:de\s+)?(?P<a>{_TIME_TOKEN})\s*(?:-|–|—|a|até|ate|to|>)\s*(?P<b>{_TIME_TOKEN})\s*[|:\-–—]?\s*(?P<title>.*)$",
    re.I,
)


def parse_ranges(text: str, limit: int = 30) -> list[dict]:
    """Um corte por linha: "1:20-2:05 Título opcional". Erros dizem a linha."""
    out: list[dict] = []
    for n, line in enumerate(str(text or "").splitlines(), start=1):
        line = line.strip().lstrip("•*-– ").strip()
        if not line:
            continue
        m = _RANGE.match(line)
        if not m:
            raise ValueError(f"Linha {n}: use o formato início-fim, ex.: 1:20-2:05")
        try:
            a, b = parse_time(m.group("a")), parse_time(m.group("b"))
        except ValueError as exc:
            raise ValueError(f"Linha {n}: {exc}") from exc
        if a is None or b is None or b <= a:
            raise ValueError(f"Linha {n}: o fim precisa ser depois do início")
        if b - a < 3:
            raise ValueError(f"Linha {n}: corte muito curto (mínimo 3 s)")
        if b - a > 600:
            raise ValueError(f"Linha {n}: corte muito longo (máximo 10 minutos)")
        out.append({"start": a, "end": b, "title": m.group("title").strip()[:200]})
        if len(out) >= limit:
            break
    return out


def check_params(p: dict) -> str | None:
    """Valida o pedido (mesma regra no painel, na API e no worker). Devolve a mensagem de erro ou None."""
    mode = p.get("mode") or "ai"
    if mode not in MODES:
        return "Modo de corte desconhecido"
    try:
        start, end = parse_time(p.get("start")), parse_time(p.get("end"))
    except ValueError as exc:
        return f"Trecho do vídeo: {exc}"
    if start is not None and end is not None and end <= start:
        return "O fim do trecho precisa ser depois do início"
    if start is not None and end is not None and end - start < 5:
        return "O trecho escolhido é curto demais (mínimo 5 s)"
    if mode == "manual":
        try:
            clips = parse_ranges(p.get("clips", ""))
        except ValueError as exc:
            return str(exc)
        if not clips:
            return "Escreva pelo menos um corte (ex.: 1:20-2:05)"
    return None


def is_youtube_url(url: str) -> bool:
    return bool(YOUTUBE_RE.match(url.strip()))


def _score(c: dict) -> float:
    try:
        return float(c.get("score", 0) or 0)
    except (TypeError, ValueError):
        return 0.0


# ------------------------------------------------------------------ download
def download(
    url: str, work: Path, cookies: str, ctx: Ctx, span: tuple | None = None
) -> tuple[Path, dict, float]:
    """Baixa o vídeo (ou só o trecho `span` = (início, fim)). Devolve (arquivo, info, início do arquivo no vídeo)."""
    try:
        return _download(url, work, cookies, ctx, span)
    except Cancelled:
        raise
    except Exception as exc:  # noqa: BLE001 — trecho falhou: tenta o vídeo inteiro
        if span is None:
            raise
        ctx.log(f"Download só do trecho falhou ({str(exc)[:200]}); baixando o vídeo inteiro")
        for f in work.glob("source.*"):
            f.unlink(missing_ok=True)
        return _download(url, work, cookies, ctx, None)


def _download(url: str, work: Path, cookies: str, ctx: Ctx, span: tuple | None) -> tuple[Path, dict, float]:
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
    used: dict = {"start": 0.0}
    if span is not None:

        def ranges(info: dict, _ydl):
            dur = float(info.get("duration") or 0)
            a = max(0.0, float(span[0] or 0))
            b = float(span[1]) if span[1] is not None else dur
            if dur:
                b = min(b, dur)
            if not dur or b - a >= dur * 0.7 or b <= a:
                yield {}  # quase o vídeo todo: baixa inteiro (mais simples e confiável)
                return
            used["start"] = a
            yield {"start_time": a, "end_time": b}

        opts["download_ranges"] = ranges

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
    if used["start"]:
        ctx.log(f"Baixado só o trecho a partir de {fmt_time(used['start'])}")
    return (
        files[0],
        {
            "title": info.get("title", ""),
            "duration": info.get("duration"),
            "channel": info.get("uploader", ""),
            "id": info.get("id"),
        },
        float(used["start"]),
    )


# ------------------------------------------------------------------ transcrição
def transcribe_range(src: Path, work: Path, a: float, b: float, ctx: Ctx, tag: str = "audio") -> list[Word]:
    """Transcreve só [a, b] do arquivo (tempos devolvidos relativos ao arquivo)."""
    audio = work / f"{tag}.wav"
    ffmpeg(
        "-ss",
        f"{max(0.0, a):.3f}",
        "-to",
        f"{b:.3f}",
        "-i",
        str(src),
        "-vn",
        "-ac",
        "1",
        "-ar",
        "16000",
        str(audio),
    )
    lang = ctx.params.get("language") or ctx.settings.get("whisper_language", "pt")
    words = transcribe(audio, ctx.settings.get("whisper_model", "base"), lang, config.models_dir)
    audio.unlink(missing_ok=True)
    return [Word(w.start + a, w.end + a, w.text) for w in words]


def compact_transcript(segments: list[dict], offset: float = 0.0, block: float = 18.0) -> str:
    """Transcrição curta para a IA (menos tokens): blocos de ~18 s com tempos inteiros."""
    out: list[str] = []
    cur: list[dict] = []
    for s in segments:
        cur.append(s)
        if cur[-1]["end"] - cur[0]["start"] >= block:
            out.append(_block(cur, offset))
            cur = []
    if cur:
        out.append(_block(cur, offset))
    return "\n".join(out)


def _block(segs: list[dict], offset: float) -> str:
    text = " ".join(s["text"].strip() for s in segs)
    marks = (
        "".join(f" |{int(s['start'] + offset)}| {s['text'].strip()}" for s in segs) if len(segs) > 1 else ""
    )
    if marks:
        text = marks.strip()
    return f"[{int(segs[0]['start'] + offset)}-{int(segs[-1]['end'] + offset + 0.99)}] {text}"


# ------------------------------------------------------------------ escolha dos cortes
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
    raw: list[dict], words: list[Word], total: float, n: int, min_s: float, max_s: float, lo: float = 0.0
) -> list[dict]:
    clips: list[dict] = []
    for c in raw:
        try:
            start, end = float(c["start"]), float(c["end"])
        except (KeyError, TypeError, ValueError):
            continue
        if end <= start or end <= lo + 1:  # fora do trecho escolhido
            continue
        start = max(start, lo)
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


def choose_clips(
    ctx: Ctx, segments: list[dict], words: list[Word], total: float, meta: dict, offset: float = 0.0,
    lo: float = 0.0, hi: float | None = None,
) -> list[dict]:  # fmt: skip
    """Cortes pela IA (tempos do arquivo). A IA vê só a parte pedida, com tempos do vídeo original."""
    p = ctx.params
    n = int(p.get("max_clips", 5))
    min_s, max_s = float(p.get("min_seconds", 20)), float(p.get("max_seconds", 60))
    hi = total if hi is None else hi
    segs = [s for s in segments if s["end"] > lo and s["start"] < hi]
    api_key = ctx.settings.get("openrouter_api_key", "")
    if api_key and segs:
        transcript = compact_transcript(segs, offset)
        extra = p.get("instructions", "").strip()
        user = (
            f"Título do vídeo: {meta.get('title', '')}\n"
            f"Trecho analisado: {fmt_time(lo + offset)} a {fmt_time(hi + offset)}\n"
            f"Quero até {n} cortes, cada um entre {min_s:.0f} e {max_s:.0f} segundos.\n"
            + (f"Instruções extras: {extra}\n" if extra else "")
            + "Tempos em segundos do vídeo original. |t| marca o início de cada frase.\n"
            + f"\nTranscrição:\n{transcript}"
        )
        try:
            client = OpenRouter(api_key)
            data, cost, model = client.chat_json(
                [ctx.settings.get("text_model", ""), ctx.settings.get("text_fallback_model", "")],
                CLIP_SYSTEM,
                user,
                max_tokens=min(3000, 300 + 220 * n),
            )
            ctx.add_cost(cost)
            ctx.log(f"Cortes escolhidos por {model} ({len(transcript)} caracteres de transcrição)")
            raw = data.get("clips", []) if isinstance(data, dict) else data
            raw = [c for c in (raw if isinstance(raw, list) else []) if isinstance(c, dict)]
            for c in raw:
                for k in ("start", "end"):
                    try:
                        c[k] = float(c[k]) - offset
                    except (KeyError, TypeError, ValueError):
                        c[k] = None
            raw = sorted(
                [c for c in raw if c.get("start") is not None and c.get("end") is not None],
                key=_score,
                reverse=True,
            )
            clips = clean_clips(raw, words, min(total, hi), n, min_s, max_s, lo)
            if clips:
                return clips
            ctx.log("LLM não retornou cortes válidos, usando heurística")
        except OpenRouterError as exc:
            ctx.log(f"Falha no LLM ({exc}); usando heurística")
    else:
        ctx.log("Sem API key do OpenRouter: escolhendo cortes por heurística")
    return clean_clips(heuristic_clips(segs, n, min_s, max_s), words, min(total, hi), n, min_s, max_s, lo)


def split_parts(lo: float, hi: float, part: float, words: list[Word]) -> list[tuple[float, float]]:
    """Divide [lo, hi] em partes seguidas de ~`part` s, cortando no fim de uma frase quando dá."""
    ends = sorted(w.end for w in words if w.text.strip().endswith((".", "!", "?")) and lo < w.end < hi)
    pauses = [words[i].end for i in range(len(words) - 1) if words[i + 1].start - words[i].end > 0.45]
    marks = sorted(set(ends) | {t for t in pauses if lo < t < hi})
    out: list[tuple[float, float]] = []
    s = lo
    while hi - s > 1.0 and len(out) < MAX_PARTS:
        target = s + part
        if target >= hi - part * 0.3:
            out.append((s, hi))
            break
        near = [m for m in marks if target - part * 0.25 <= m <= target + part * 0.2]
        e = min(near, key=lambda m: abs(m - target)) + 0.15 if near else target
        out.append((s, e))
        s = e
    return out


# ------------------------------------------------------------------ execução
def run(ctx: Ctx, work: Path, out_dir: Path) -> list[dict]:
    p = ctx.params
    url = p["url"].strip()
    err = check_params(p)
    if err:
        raise RuntimeError(err)
    mode = p.get("mode") or "ai"
    w_start, w_end = parse_time(p.get("start")), parse_time(p.get("end"))
    manual = parse_ranges(p.get("clips", "")) if mode == "manual" else []
    span = None
    if manual:
        span = (max(0.0, min(c["start"] for c in manual) - 2.0), max(c["end"] for c in manual) + 2.0)
    elif w_start is not None or w_end is not None:
        span = (w_start or 0.0, w_end)

    ctx.report(2, "Baixando vídeo do YouTube")
    src, meta, offset = download(url, work, ctx.settings.get("youtube_cookies", ""), ctx, span)
    total = duration_of(src) or float(meta.get("duration") or 0)
    ctx.log(
        f"Baixado: {meta.get('title')} ({total:.0f}s{f', a partir de {fmt_time(offset)}' if offset else ''})"
    )
    if ctx.cancelled():
        raise Cancelled()

    style = p.get("subtitle_style") or ctx.settings.get("subtitle_style", "highlight")
    # janela pedida, em tempos do arquivo
    lo = max(0.0, (w_start or 0.0) - offset) if mode != "manual" else 0.0
    hi = min(total, (w_end - offset) if w_end is not None else total) if mode != "manual" else total
    if mode != "manual" and hi - lo < 3:
        raise RuntimeError("O trecho escolhido está fora do vídeo (confira início e fim)")

    words: list[Word] = []
    if mode == "manual":
        cuts = []
        for c in manual:
            s, e = c["start"] - offset, c["end"] - offset
            if e <= 0 or s >= total:
                ctx.log(f"Corte {fmt_time(c['start'])}-{fmt_time(c['end'])} está fora do vídeo; pulado")
                continue
            cuts.append({"start": max(0.0, s), "end": min(total, e), "title": c["title"], "caption": "",
                         "hashtags": [], "score": 0.0, "reason": "trecho escolhido por você"})  # fmt: skip
        if not cuts:
            raise RuntimeError("Nenhum dos cortes está dentro do vídeo")
        if style != "none":
            for i, c in enumerate(cuts):
                if ctx.cancelled():
                    raise Cancelled()
                ctx.report(
                    22 + int(25 * i / len(cuts)), f"Transcrevendo o corte {i + 1}/{len(cuts)} (Whisper local)"
                )
                words += transcribe_range(src, work, c["start"], c["end"] + 0.3, ctx, f"a{i}")
        ctx.log(f"{len(cuts)} corte(s) escolhidos por você (sem IA)")
    else:
        if mode == "ai" or style != "none":
            ctx.report(22, "Transcrevendo (Whisper local)")
            words = transcribe_range(src, work, lo, hi, ctx)
            ctx.log(f"Transcrição: {len(words)} palavras")
        if ctx.cancelled():
            raise Cancelled()
        if mode == "ai":
            ctx.report(50, "Escolhendo os melhores trechos com IA")
            cuts = choose_clips(ctx, words_to_segments(words), words, total, meta, offset, lo, hi)
            if not cuts:
                raise RuntimeError("Não foi possível encontrar trechos para cortar (vídeo sem fala?)")
        else:
            part = float(p.get("part_seconds", 60))
            ranges = split_parts(lo, hi, part, words)
            cuts = [{"start": s, "end": e, "title": "", "caption": "", "hashtags": [], "score": 0.0,
                     "reason": f"parte {i + 1} de {len(ranges)}"} for i, (s, e) in enumerate(ranges)]  # fmt: skip
            ctx.log(f"Dividido em {len(cuts)} partes de ~{part:.0f}s (sem IA)")

    color = ctx.settings.get("subtitle_color", "#FFE14D")
    reframe = p.get("reframe", "auto")
    label_parts = mode == "parts" and bool(p.get("part_label", True))
    base_title = meta.get("title") or "Corte"
    outputs: list[dict] = []
    n = len(cuts)
    for idx, clip in enumerate(cuts, start=1):
        if ctx.cancelled():
            raise Cancelled()
        ctx.report(55 + int(40 * (idx - 1) / n), f"Renderizando corte {idx}/{n}")
        s, e = clip["start"], clip["end"]
        clip_words = [
            Word(w.start - s, w.end - s, w.text) for w in words if w.start >= s and w.end <= e + 0.3
        ]
        ass_text = build_ass(clip_words, style=style, highlight=color) if style != "none" else ""
        if label_parts:
            ass_text = (ass_text or build_ass([], style="none")) + ass_title_line(f"PARTE {idx}", 0.0, e - s)
        ass_path = None
        if ass_text:
            ass_path = work / f"clip{idx}.ass"
            ass_path.write_text(ass_text, encoding="utf-8")
        cx = face_center_x(src, s, e) if reframe in ("auto", "face") else None
        out = out_dir / f"corte_{idx:02d}.mp4"
        render_clip(src, out, s, e, ass_path, mode="crop" if reframe == "face" else reframe, center_x=cx)
        thumb = thumbnail(out, out_dir / f"corte_{idx:02d}.jpg", at=min(1.5, (e - s) / 2))
        if mode == "parts":
            title = f"{base_title} · Parte {idx}/{n}"
            caption = clip["caption"] or f"{base_title} (parte {idx}/{n})"
        elif mode == "manual":
            title = clip["title"] or f"{base_title} · {fmt_time(s + offset)}"
            caption = clip["caption"] or (clip["title"] or base_title)
        else:
            title = clip["title"] or f"{base_title} #{idx}"
            caption = clip["caption"]
        outputs.append(
            {
                "file": out,
                "thumb": thumb,
                "title": title[:200],
                "caption": caption,
                "hashtags": " ".join(clip["hashtags"]),
                "duration": duration_of(out),
                "score": clip["score"],
                "meta": {
                    "source_url": url,
                    "source_title": meta.get("title"),
                    "mode": mode,
                    "start": round(s + offset, 2),
                    "end": round(e + offset, 2),
                    "reason": clip["reason"],
                    "transcript": " ".join(w.text.strip() for w in clip_words),
                },
            }
        )
    return outputs
