"""Elementos de tela no estilo dos vídeos de animação explicativa.

Faixa de título (fita vermelha), cartão branco, etiqueta de referência no canto, adesivo em
explosão, balão de fala, nome em cima do personagem, checklist, contador de número, gráfico e a
legenda palavra por palavra com a palavra atual destacada. Tudo é desenhado em pixels da tela.
"""

from __future__ import annotations

import math
import re
from functools import lru_cache

from PIL import Image, ImageDraw

from .draw import (
    INK,
    Pen,
    Sprite,
    fit_size,
    pen_sprite,
    pil_sprite,
    rgb,
    shade,
    star_pts,
    text_image,
    text_size,
)

BANNER_COLORS = [(222, 84, 64), (52, 92, 170), (130, 70, 170), (40, 140, 110), (226, 130, 40)]
STICKER = (255, 214, 64)
CHECK = (60, 170, 90)


def _paper_kw(paper: float, scale: float) -> dict:
    return {"shadow": 0.28 if paper > 0 else 0.0, "paper": paper, "shadow_scale": max(0.5, scale)}


def _text_layer(p: Pen, cx: float, cy: float, lines: list[str], size: int, fill, stroke: int = 0, stroke_fill=None,
                spacing: float = 1.08) -> None:  # fmt: skip
    from .draw import font

    f = font(size)
    asc, desc = f.getmetrics()
    lh = (asc + desc) * spacing
    y0 = cy - lh * (len(lines) - 1) / 2
    for i, ln in enumerate(lines):
        p.text(cx, y0 + i * lh, ln, size, fill, stroke, stroke_fill)


@lru_cache(maxsize=64)
def banner(text: str, W: int, color: tuple = BANNER_COLORS[0], paper: float = 0.0) -> Sprite:
    s = W / 1080
    size, lines = fit_size(text.upper(), int(52 * s), int(W * 0.66), int(26 * s), 2)
    tw = max(text_size(ln, size)[0] for ln in lines)
    hh = (size * 1.18) * len(lines) + 30 * s
    w = tw + 70 * s
    tail = 34 * s
    p = Pen((-w / 2 - tail - 10, -hh / 2 - 12, w / 2 + tail + 10, hh / 2 + 18), 1.0, ss=2)
    dark = shade(color, 0.7)
    for sgn in (-1, 1):
        x0 = sgn * (w / 2 - 6)
        x1 = sgn * (w / 2 + tail)
        p.poly([(x0, -hh / 2 + 10 * s), (x1, -hh / 2 + 10 * s), (x1 - sgn * 14 * s, hh * 0.08 + 10 * s),
                (x1, hh / 2 + 10 * s), (x0, hh / 2 + 10 * s)], dark)  # fmt: skip
    p.poly(
        [
            (-w / 2, -hh / 2),
            (w / 2, -hh / 2 + 3 * s),
            (w / 2 - 2 * s, hh / 2),
            (-w / 2 + 2 * s, hh / 2 + 3 * s),
        ],
        color,
    )
    p.soft(
        lambda q: q.line(
            [(-w / 2 + 6, -hh / 2 + 5 * s), (w / 2 - 6, -hh / 2 + 8 * s)], 3 * s, (255, 255, 255, 60)
        )
    )
    _text_layer(p, 0, 2 * s, lines, size, (255, 255, 255))
    return pen_sprite(p, (0, 0), **_paper_kw(paper, s))


@lru_cache(maxsize=64)
def card(text: str, W: int, paper: float = 0.0, dark: bool = False) -> Sprite:
    s = W / 1080
    size, lines = fit_size(text.upper(), int(34 * s), int(W * 0.62), int(20 * s), 2)
    tw = max(text_size(ln, size)[0] for ln in lines)
    hh = size * 1.2 * len(lines) + 26 * s
    w = tw + 50 * s
    p = Pen((-w / 2 - 8, -hh / 2 - 8, w / 2 + 8, hh / 2 + 12), 1.0, ss=2)
    bg = (250, 248, 240) if not dark else (60, 110, 80)
    p.rect(-w / 2, -hh / 2, w / 2, hh / 2, bg, r=10 * s)
    _text_layer(p, 0, 1 * s, lines, size, (60, 50, 60) if not dark else (250, 250, 250))
    return pen_sprite(p, (0, 0), **_paper_kw(paper, s))


@lru_cache(maxsize=32)
def tag(text: str, W: int, paper: float = 0.0) -> Sprite:
    s = W / 1080
    size = int(32 * s)
    tw, _th = text_size(text, size)
    w, hh = tw + 34 * s, size * 1.25 + 18 * s
    p = Pen((-6, -6, w + 6, hh + 10), 1.0, ss=2)
    p.rect(0, 0, w, hh, (250, 248, 240), r=8 * s)
    p.text(w / 2, hh / 2 + 1 * s, text, size, (70, 60, 70))
    return pen_sprite(p, (0, 0), **_paper_kw(paper, s))


@lru_cache(maxsize=64)
def sticker(text: str, W: int, paper: float = 0.0, color: tuple = STICKER) -> Sprite:
    s = W / 1080
    size, lines = fit_size(text.upper(), int(40 * s), int(W * 0.34), int(22 * s), 2)
    tw = max(text_size(ln, size)[0] for ln in lines)
    r = max(tw * 0.62, size * len(lines) * 0.95) + 34 * s
    p = Pen((-r * 1.25, -r, r * 1.25, r), 1.0, ss=2)
    pts = [(x * 1.18, y * 0.82) for x, y in star_pts(0, 0, r, r * 0.8, 14, 0)]
    p.poly(pts, color)
    _text_layer(p, 0, 2 * s, lines, size, INK)
    return pen_sprite(p, (0, 0), **_paper_kw(paper, s))


@lru_cache(maxsize=64)
def bubble(text: str, W: int, paper: float = 0.0, tail_left: bool = True) -> Sprite:
    """Balão de fala. Pivô na ponta do rabicho (encosta na cabeça do personagem)."""
    s = W / 1080
    size, lines = fit_size(text, int(46 * s), int(W * 0.42), int(24 * s), 3)
    tw = max(text_size(ln, size)[0] for ln in lines)
    hh = size * 1.22 * len(lines) + 34 * s
    w = tw + 50 * s
    tx = -w * 0.25 if tail_left else w * 0.25
    p = Pen((-w / 2 - 10, -hh - 40 * s - 10, w / 2 + 10, 10), 1.0, ss=2)
    p.rect(-w / 2, -hh - 34 * s, w / 2, -34 * s, (255, 255, 255), r=24 * s)
    p.poly([(tx - 14 * s, -36 * s), (tx + 16 * s, -36 * s), (tx - 6 * s, 0)], (255, 255, 255))
    _text_layer(p, 0, -hh / 2 - 34 * s, lines, size, INK)
    return pen_sprite(p, (0, 0), **_paper_kw(paper, s))


@lru_cache(maxsize=64)
def label(text: str, W: int, paper: float = 0.0) -> Sprite:
    s = W / 1080
    size = int(31 * s)
    text = text.upper()
    tw, _ = text_size(text, size)
    w, hh = tw + 30 * s, size * 1.2 + 16 * s
    p = Pen((-w / 2 - 6, -hh - 6, w / 2 + 6, 10), 1.0, ss=2)
    p.rect(-w / 2, -hh, w / 2, 0, (250, 248, 240), r=7 * s)
    p.text(0, -hh / 2 + 1 * s, text, size, (60, 50, 60))
    return pen_sprite(p, (0, -hh / 2), **_paper_kw(paper, s))


def checklist(title: str, items: tuple, done: int, W: int, paper: float = 0.0) -> Sprite:
    s = W / 1080
    size = int(40 * s)
    w = W * 0.78
    rows = [fit_size(it.upper(), size, int(w - 130 * s), int(22 * s), 2) for it in items]
    row_h = [max(sz * 1.25 * len(ln), 52 * s) + 16 * s for sz, ln in rows]
    hh = 104 * s + sum(row_h) + 24 * s
    p = Pen((-w / 2 - 8, -10, w / 2 + 8, hh + 14), 1.0, ss=2)
    p.rect(-w / 2, 0, w / 2, hh, (252, 250, 244), r=18 * s)
    if title:
        p.text(0, 54 * s, title.upper(), int(42 * s), (210, 70, 60))
    y = 104 * s
    for i, ((sz, ln), rh) in enumerate(zip(rows, row_h, strict=True)):
        cy = y + rh / 2
        x0 = -w / 2 + 44 * s
        if i < done:
            p.circle(x0 + 12 * s, cy, 22 * s, CHECK)
            p.line(
                [(x0 + 1 * s, cy), (x0 + 10 * s, cy + 9 * s), (x0 + 26 * s, cy - 10 * s)],
                6 * s,
                (255, 255, 255),
            )
        else:
            p.circle(x0 + 12 * s, cy, 22 * s, None, outline=(200, 200, 205), width=3 * s)
        col = (60, 50, 60) if i < done else (170, 166, 176)
        from .draw import font

        f = font(sz)
        asc, desc = f.getmetrics()
        lh = (asc + desc) * 1.05
        for j, line in enumerate(ln):
            ty = cy - lh * (len(ln) - 1) / 2 + j * lh
            tw, _ = text_size(line, sz)
            p.text(x0 + 54 * s + tw / 2, ty, line, sz, col)
        y += rh
    return pen_sprite(p, (0, hh / 2), **_paper_kw(paper, s))


def number_text(value: str, q: float) -> str:
    """Contagem progressiva de um número com pontos de milhar (pt-BR)."""
    m = re.search(r"\d[\d.,]*", value)
    if not m:
        return value
    raw = m.group(0)
    digits = re.sub(r"[.,]", "", raw)
    try:
        target = int(digits)
    except ValueError:
        return value
    cur = int(round(target * q))
    s = f"{cur:,}".replace(",", ".") if "." in raw or len(digits) > 3 else str(cur)
    return value[: m.start()] + s + value[m.end() :]


def counter(value: str, W: int, color=(220, 60, 50)) -> Sprite:
    s = W / 1080
    parts = value.split(" ", 1)
    num = parts[0]
    rest = parts[1] if len(parts) > 1 else ""
    size, _ = fit_size(num, int(110 * s), int(W * 0.82), int(40 * s), 1)
    img_num = text_image(
        num, size, rgb(color), stroke=int(8 * s), stroke_fill=(255, 255, 255), shadow=int(6 * s)
    )
    if not rest:
        return pil_sprite(img_num)
    img_rest = text_image(
        rest.upper(), int(44 * s), (60, 50, 60), stroke=int(6 * s), stroke_fill=(255, 255, 255)
    )
    w = max(img_num.width, img_rest.width)
    out = Image.new("RGBA", (w, img_num.height + img_rest.height - int(10 * s)), (0, 0, 0, 0))
    out.alpha_composite(img_num, ((w - img_num.width) // 2, 0))
    out.alpha_composite(img_rest, ((w - img_rest.width) // 2, img_num.height - int(10 * s)))
    return pil_sprite(out)


def chart(kind: str, q: float, W: int, paper: float = 0.0) -> Sprite:
    s = W / 1080
    w, hh = W * 0.56, W * 0.38
    p = Pen((-w / 2 - 8, -hh / 2 - 8, w / 2 + 8, hh / 2 + 12), 1.0, ss=2)
    p.rect(-w / 2, -hh / 2, w / 2, hh / 2, (252, 250, 244), r=16 * s)
    x0, y0, x1, y1 = -w / 2 + 40 * s, -hh / 2 + 30 * s, w / 2 - 30 * s, hh / 2 - 34 * s
    p.line([(x0, y0), (x0, y1), (x1, y1)], 4 * s, (70, 60, 70))
    n = 24
    pts = []
    for i in range(n + 1):
        t = i / n
        if t > q:
            break
        if kind == "up":
            v = t**1.8
        elif kind == "down":
            v = (1 - t) ** 1.6
        else:
            v = 0.5 + 0.35 * math.sin(t * 7)
        pts.append((x0 + 10 * s + (x1 - x0 - 20 * s) * t, y1 - 10 * s - (y1 - y0 - 20 * s) * v))
    col = (52, 170, 90) if kind == "up" else (220, 60, 50)
    if len(pts) >= 2:
        p.line(pts, 6 * s, col)
        p.circle(pts[-1][0], pts[-1][1], 10 * s, col)
    return pen_sprite(p, (0, 0), **_paper_kw(paper, s))


# ------------------------------------------------------------------ legenda
class Captions:
    """Legenda palavra por palavra (1 a 3 palavras por vez), com a palavra falada destacada."""

    def __init__(self, words, W: int, style: str = "highlight", color=(255, 216, 77), y: float = 0.725):
        from ..media import group_words

        self.W = W
        self.s = W / 1080
        self.style = style
        self.color = rgb(color, (255, 216, 77))
        self.y = y
        self.groups = group_words(words, max_words=3, max_gap=0.5, max_dur=1.4) if style != "none" else []
        self.size = int(76 * self.s)
        self._cache: dict = {}

    def _word(self, text: str, hl: bool, size: int) -> Image.Image:
        key = (text, hl, size)
        img = self._cache.get(key)
        if img is None:
            fill = self.color if hl else (255, 255, 255)
            img = text_image(
                text, size, fill, stroke=int(8 * self.s), stroke_fill=INK, shadow=int(6 * self.s)
            )
            self._cache[key] = img
        return img

    def frame(self, t: float):
        """Sprite e escala da legenda no instante t (ou None)."""
        for gi, g in enumerate(self.groups):
            g_end = g[-1].end + 0.12
            if not (g[0].start - 0.02 <= t <= g_end):
                continue
            cur = max(0, max((i for i, w in enumerate(g) if w.start <= t + 0.01), default=0))
            age = t - g[cur].start
            pop = 1.0 + 0.1 * max(0.0, 1 - age / 0.14) if self.style == "highlight" else 1.0
            key = ("grp", gi, cur if self.style == "highlight" else -1)
            spr = self._cache.get(key)
            if spr is not None:
                return spr, pop
            texts = [re.sub(r"[{}\\]", "", w.text.strip()).upper() for w in g]
            size = self.size
            total = sum(text_size(x, size)[0] for x in texts) + (len(texts) - 1) * size * 0.3
            while total > self.W * 0.86 and size > 30:
                size -= 4
                total = sum(text_size(x, size)[0] for x in texts) + (len(texts) - 1) * size * 0.3
            imgs = [self._word(x, self.style == "highlight" and i == cur, size) for i, x in enumerate(texts)]
            pad = int(8 * self.s) + int(6 * self.s) + 4  # margem que text_image põe em volta de cada palavra
            gap = int(size * 0.24) - 2 * pad
            w = sum(im.width for im in imgs) + gap * (len(imgs) - 1)
            h = max(im.height for im in imgs)
            out = Image.new("RGBA", (w, h), (0, 0, 0, 0))
            x = 0
            for im in imgs:
                out.alpha_composite(im, (x, (h - im.height) // 2))
                x += im.width + gap
            spr = pil_sprite(out)
            self._cache[key] = spr
            return spr, pop
        return None


def draw_text_simple(
    img: Image.Image, txt: str, xy, size: int, fill
) -> None:  # pragma: no cover - utilitário
    ImageDraw.Draw(img).text(xy, txt, fill=fill)
