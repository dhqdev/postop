"""Ferramentas de desenho do motor 2D: vetor com supersampling (Pillow), sprites e compositor (OpenCV).

Tudo é desenhado por código, sem imagem pronta e sem IA: cada parte (cabeça, braço, casa, faixa...)
vira um sprite RGBA com pivô. No quadro, os sprites são posicionados com uma matriz afim
(posição, giro, escala, espelho) e misturados no fundo com alfa pré-multiplicado.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

SS = 3  # supersampling dos desenhos vetoriais (bordas suaves)
FONT_PATH = Path(__file__).resolve().parent.parent / "assets" / "fonts" / "Poppins-Bold.ttf"
INK = (34, 30, 38)  # contorno/sombra dos textos


# ------------------------------------------------------------------ cores
def rgb(value, default=(200, 200, 200)) -> tuple[int, int, int]:
    """Aceita '#rrggbb', '#rgb', (r, g, b) em 0..1 ou 0..255."""
    if value is None or value == "":
        return tuple(default)  # type: ignore[return-value]
    if isinstance(value, str):
        s = value.strip().lstrip("#")
        if len(s) == 3:
            s = "".join(c * 2 for c in s)
        if len(s) == 6:
            try:
                return int(s[0:2], 16), int(s[2:4], 16), int(s[4:6], 16)
            except ValueError:
                return tuple(default)  # type: ignore[return-value]
        return tuple(default)  # type: ignore[return-value]
    try:
        c = [float(x) for x in value][:3]
    except (TypeError, ValueError):
        return tuple(default)  # type: ignore[return-value]
    if len(c) != 3:
        return tuple(default)  # type: ignore[return-value]
    if max(c) <= 1.0:
        c = [x * 255 for x in c]
    return tuple(int(max(0, min(255, round(x)))) for x in c)  # type: ignore[return-value]


def shade(c, k: float) -> tuple[int, int, int]:
    """k < 1 escurece, k > 1 clareia (mistura com branco)."""
    c = rgb(c)
    if k <= 1:
        return tuple(int(x * k) for x in c)  # type: ignore[return-value]
    t = min(k - 1, 1.0)
    return tuple(int(x + (255 - x) * t) for x in c)  # type: ignore[return-value]


def mix(a, b, t: float) -> tuple[int, int, int]:
    a, b = rgb(a), rgb(b)
    return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))  # type: ignore[return-value]


def rgba(c, a: float = 1.0) -> tuple[int, int, int, int]:
    r, g, b = rgb(c)
    return r, g, b, int(max(0, min(255, a * 255)))


# ------------------------------------------------------------------ curvas
def bez(p0, p1, p2, p3=None, n: int = 14) -> list[tuple[float, float]]:
    """Pontos de uma curva de Bézier quadrática (3 pontos) ou cúbica (4 pontos)."""
    out = []
    for i in range(n + 1):
        t = i / n
        u = 1 - t
        if p3 is None:
            x = u * u * p0[0] + 2 * u * t * p1[0] + t * t * p2[0]
            y = u * u * p0[1] + 2 * u * t * p1[1] + t * t * p2[1]
        else:
            x = u**3 * p0[0] + 3 * u * u * t * p1[0] + 3 * u * t * t * p2[0] + t**3 * p3[0]
            y = u**3 * p0[1] + 3 * u * u * t * p1[1] + 3 * u * t * t * p2[1] + t**3 * p3[1]
        out.append((x, y))
    return out


def arc_pts(cx, cy, rx, ry, a0: float, a1: float, n: int = 24) -> list[tuple[float, float]]:
    """Pontos de um arco de elipse (ângulos em graus, 0 = direita, sentido horário na tela)."""
    return [
        (
            cx + rx * math.cos(math.radians(a0 + (a1 - a0) * i / n)),
            cy + ry * math.sin(math.radians(a0 + (a1 - a0) * i / n)),
        )
        for i in range(n + 1)
    ]


def star_pts(cx, cy, r_out, r_in, n: int = 5, rot: float = -90) -> list[tuple[float, float]]:
    pts = []
    for i in range(n * 2):
        r = r_out if i % 2 == 0 else r_in
        a = math.radians(rot + i * 180 / n)
        pts.append((cx + r * math.cos(a), cy + r * math.sin(a)))
    return pts


# ------------------------------------------------------------------ caneta
class Pen:
    """Canvas RGBA em "unidades" (o desenho é feito em `k` px por unidade × supersampling)."""

    def __init__(self, box: tuple[float, float, float, float], k: float, ss: int = SS):
        self.box = box
        self.k = k
        self.ss = ss
        self.kk = k * ss
        w = max(1, int(math.ceil((box[2] - box[0]) * self.kk)))
        h = max(1, int(math.ceil((box[3] - box[1]) * self.kk)))
        self.img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        self.d = ImageDraw.Draw(self.img)

    # coordenadas
    def p(self, x: float, y: float) -> tuple[float, float]:
        return (x - self.box[0]) * self.kk, (y - self.box[1]) * self.kk

    def pts(self, points) -> list[tuple[float, float]]:
        return [self.p(x, y) for x, y in points]

    def u(self, v: float) -> float:
        return v * self.kk

    # formas
    def ellipse(self, cx, cy, rx, ry, fill, outline=None, width: float = 0) -> None:
        x0, y0 = self.p(cx - rx, cy - ry)
        x1, y1 = self.p(cx + rx, cy + ry)
        self.d.ellipse(
            (x0, y0, x1, y1),
            fill=_c(fill),
            outline=_c(outline) if outline else None,
            width=int(round(self.u(width))) if outline else 0,
        )

    def circle(self, cx, cy, r, fill, outline=None, width: float = 0) -> None:
        self.ellipse(cx, cy, r, r, fill, outline, width)

    def rect(self, x0, y0, x1, y1, fill, r: float = 0, outline=None, width: float = 0) -> None:
        a, b = self.p(min(x0, x1), min(y0, y1))
        c, d = self.p(max(x0, x1), max(y0, y1))
        if r > 0:
            self.d.rounded_rectangle(
                (a, b, c, d),
                radius=self.u(min(r, abs(x1 - x0) / 2, abs(y1 - y0) / 2)),
                fill=_c(fill),
                outline=_c(outline) if outline else None,
                width=int(round(self.u(width))) if outline else 0,
            )
        else:
            self.d.rectangle(
                (a, b, c, d),
                fill=_c(fill),
                outline=_c(outline) if outline else None,
                width=int(round(self.u(width))) if outline else 0,
            )

    def poly(self, points, fill, outline=None, width: float = 0) -> None:
        if len(points) < 3:
            return
        self.d.polygon(self.pts(points), fill=_c(fill))
        if outline:
            self.line(list(points) + [points[0]], width, outline)

    def line(self, points, width: float, fill, round_caps: bool = True) -> None:
        if len(points) < 2:
            return
        pp = self.pts(points)
        w = max(1, int(round(self.u(width))))
        self.d.line(pp, fill=_c(fill), width=w, joint="curve")
        if round_caps:
            r = w / 2
            for x, y in (pp[0], pp[-1]):
                self.d.ellipse((x - r, y - r, x + r, y + r), fill=_c(fill))

    def capsule(self, x0, y0, x1, y1, r, fill) -> None:
        """Bastão com pontas redondas (braços, pernas, troncos)."""
        self.line([(x0, y0), (x1, y1)], r * 2, fill)

    def arc(self, cx, cy, rx, ry, a0, a1, width, fill) -> None:
        self.line(arc_pts(cx, cy, rx, ry, a0, a1), width, fill)

    def pie(self, cx, cy, rx, ry, a0, a1, fill) -> None:
        x0, y0 = self.p(cx - rx, cy - ry)
        x1, y1 = self.p(cx + rx, cy + ry)
        self.d.pieslice((x0, y0, x1, y1), a0, a1, fill=_c(fill))

    def chord(self, cx, cy, rx, ry, a0, a1, fill) -> None:
        x0, y0 = self.p(cx - rx, cy - ry)
        x1, y1 = self.p(cx + rx, cy + ry)
        self.d.chord((x0, y0, x1, y1), a0, a1, fill=_c(fill))

    def star(self, cx, cy, r_out, r_in, fill, n: int = 5, rot: float = -90) -> None:
        self.poly(star_pts(cx, cy, r_out, r_in, n, rot), fill)

    def text(self, cx, cy, txt: str, size: float, fill, stroke: float = 0, stroke_fill=None) -> None:
        f = font(max(4, int(self.u(size))))
        x, y = self.p(cx, cy)
        self.d.text(
            (x, y),
            txt,
            font=f,
            fill=_c(fill),
            anchor="mm",
            stroke_width=int(round(self.u(stroke))),
            stroke_fill=_c(stroke_fill) if stroke_fill else None,
        )

    # camadas (para transparência e recorte)
    def layer(self) -> Pen:
        return Pen(self.box, self.k, self.ss)

    def paste(self, other: Pen, clip: Pen | None = None, opacity: float = 1.0) -> None:
        """Mistura outra camada por cima (com recorte opcional pelo alfa de `clip`)."""
        top = other.img
        if clip is not None or opacity < 1:
            a = np.asarray(top.split()[-1], np.float32)
            if clip is not None:
                a *= np.asarray(clip.img.split()[-1], np.float32) / 255
            a *= opacity
            top = top.copy()
            top.putalpha(Image.fromarray(np.clip(a, 0, 255).astype(np.uint8)))
        self.img.alpha_composite(top)

    def soft(self, draw_fn, opacity: float = 1.0, clip: Pen | None = None) -> None:
        """Desenha numa camada à parte e mistura (cores com transparência sem "furar" o desenho)."""
        lay = self.layer()
        draw_fn(lay)
        self.paste(lay, clip, opacity)


def _c(c):
    if c is None:
        return None
    if isinstance(c, tuple) and len(c) == 4:
        return c
    r, g, b = rgb(c)
    return r, g, b, 255


# ------------------------------------------------------------------ sprites
@dataclass
class Sprite:
    img: np.ndarray  # H x W x 4, BGRA uint8 com cor pré-multiplicada pelo alfa
    px: float  # pivô (pixels do sprite)
    py: float

    @property
    def w(self) -> int:
        return self.img.shape[1]

    @property
    def h(self) -> int:
        return self.img.shape[0]


def paper_texture(size: int = 512, seed: int = 5) -> np.ndarray:
    """Textura de papel (fibras e granulado suave), em torno de 1.0."""
    rng = np.random.default_rng(seed)
    base = rng.normal(0, 1, (size // 4, size // 4)).astype(np.float32)
    base = cv2.resize(base, (size, size), interpolation=cv2.INTER_CUBIC)
    fine = rng.normal(0, 1, (size, size)).astype(np.float32)
    fiber = cv2.GaussianBlur(rng.normal(0, 1, (size, size)).astype(np.float32), (0, 0), sigmaX=6, sigmaY=0.6)
    t = base * 0.012 + fine * 0.01 + fiber * 0.05
    return np.clip(1.0 + t, 0.9, 1.08).astype(np.float32)


@lru_cache(maxsize=1)
def _paper() -> np.ndarray:
    return paper_texture()


def apply_paper(arr: np.ndarray, amount: float = 1.0, seed: int = 0) -> np.ndarray:
    """Multiplica a textura de papel (repetida) nas cores de um array RGB(A) uint8."""
    tex = _paper()
    h, w = arr.shape[:2]
    oy, ox = (seed * 97) % tex.shape[0], (seed * 61) % tex.shape[1]
    reps = (math.ceil((h + oy) / tex.shape[0]), math.ceil((w + ox) / tex.shape[1]))
    t = np.tile(tex, reps)[oy : oy + h, ox : ox + w]
    t = 1 + (t - 1) * amount
    out = arr.copy()
    out[..., :3] = np.clip(arr[..., :3].astype(np.float32) * t[..., None], 0, 255).astype(np.uint8)
    return out


def to_sprite(
    img: Image.Image,
    pivot: tuple[float, float],
    ss: int = SS,
    shadow: float = 0.0,
    shadow_off: tuple[float, float] = (0.0, 0.0),
    paper: float = 0.0,
    seed: int = 0,
) -> Sprite:
    """Reduz o desenho supersampled, aplica papel/sombra e devolve o sprite pré-multiplicado.

    `pivot` em pixels do desenho já reduzido; `shadow` = opacidade da sombra projetada (papel recortado).
    """
    if ss > 1:
        img = img.resize((max(1, img.width // ss), max(1, img.height // ss)), Image.LANCZOS)
    arr = np.asarray(img, dtype=np.uint8).copy()
    if paper > 0:
        arr = apply_paper(arr, paper, seed)
    px, py = pivot
    if shadow > 0:
        dx, dy = shadow_off
        blur = max(1.0, (abs(dx) + abs(dy)) * 0.55)
        m = int(math.ceil(blur * 2.5 + max(abs(dx), abs(dy)))) + 1
        h, w = arr.shape[:2]
        big = np.zeros((h + 2 * m, w + 2 * m, 4), np.uint8)
        big[m : m + h, m : m + w] = arr
        a = big[..., 3].astype(np.float32)
        sh = cv2.GaussianBlur(a, (0, 0), blur)
        M = np.float32([[1, 0, dx], [0, 1, dy]])
        sh = cv2.warpAffine(sh, M, (sh.shape[1], sh.shape[0])) * shadow
        top = big[..., 3:4].astype(np.float32) / 255
        out = np.empty_like(big)
        sha = sh[..., None] / 255
        alpha = top + sha * (1 - top)
        col = big[..., :3].astype(np.float32) * top  # sombra preta: só o alfa conta
        out[..., :3] = np.where(alpha > 1e-4, col / np.maximum(alpha, 1e-4), 0).clip(0, 255).astype(np.uint8)
        out[..., 3] = (alpha[..., 0] * 255).clip(0, 255).astype(np.uint8)
        arr = out
        px, py = px + m, py + m
    a = arr[..., 3:4].astype(np.uint16)
    pre = np.empty_like(arr)
    pre[..., :3] = ((arr[..., :3].astype(np.uint16) * a + 127) // 255).astype(np.uint8)[..., ::-1]
    pre[..., 3] = arr[..., 3]
    return Sprite(np.ascontiguousarray(pre), float(px), float(py))


def pen_sprite(pen: Pen, pivot_units: tuple[float, float], **kw) -> Sprite:
    """Sprite de uma caneta, com o pivô dado em unidades do desenho."""
    px = (pivot_units[0] - pen.box[0]) * pen.k
    py = (pivot_units[1] - pen.box[1]) * pen.k
    k = kw.pop("shadow_scale", 1.0)
    if kw.get("shadow"):
        kw.setdefault("shadow_off", (3.0 * k, 4.0 * k))
    return to_sprite(pen.img, (px, py), pen.ss, **kw)


# ------------------------------------------------------------------ texto
@lru_cache(maxsize=64)
def font(size: int) -> ImageFont.FreeTypeFont:
    try:
        return ImageFont.truetype(str(FONT_PATH), size)
    except OSError:  # pragma: no cover - fonte ausente: usa a do sistema
        for p in ("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",):
            if Path(p).exists():
                return ImageFont.truetype(p, size)
        return ImageFont.load_default()


def text_size(txt: str, size: int, stroke: int = 0) -> tuple[int, int]:
    box = font(size).getbbox(txt, stroke_width=stroke)
    return box[2] - box[0], box[3] - box[1]


def wrap(txt: str, size: int, max_w: int, max_lines: int = 3) -> list[str]:
    words = txt.split()
    lines: list[str] = []
    cur = ""
    for w in words:
        test = (cur + " " + w).strip()
        if not cur or text_size(test, size)[0] <= max_w:
            cur = test
        else:
            lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    if len(lines) > max_lines:
        lines = lines[: max_lines - 1] + [" ".join(lines[max_lines - 1 :])]
    return lines


def fit_size(
    txt: str, size: int, max_w: int, min_size: int = 18, max_lines: int = 2
) -> tuple[int, list[str]]:
    """Maior fonte (até `size`) em que o texto cabe em `max_lines` linhas de `max_w` px."""
    s = size
    while s > min_size:
        lines = wrap(txt, s, max_w, 99)
        if len(lines) <= max_lines and all(text_size(ln, s)[0] <= max_w for ln in lines):
            return s, lines
        s -= 2
    return min_size, wrap(txt, min_size, max_w, max_lines)


def text_image(
    txt: str, size: int, fill, stroke: int = 0, stroke_fill=INK, shadow: int = 0, spacing: float = 1.05
) -> Image.Image:
    """Texto (uma ou mais linhas, centralizado) numa imagem RGBA justa, com contorno e sombra."""
    lines = txt.split("\n")
    f = font(size)
    asc, desc = f.getmetrics()
    lh = int((asc + desc) * spacing)
    widths = [text_size(ln, size, stroke)[0] for ln in lines]
    pad = stroke + shadow + 4
    w = max(widths or [1]) + pad * 2
    h = lh * len(lines) + pad * 2
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    for i, ln in enumerate(lines):
        x = w / 2
        y = pad + i * lh + lh / 2
        if shadow:
            d.text((x + shadow * 0.4, y + shadow), ln, font=f, anchor="mm", fill=(0, 0, 0, 110),
                   stroke_width=stroke, stroke_fill=(0, 0, 0, 110))  # fmt: skip
        d.text((x, y), ln, font=f, anchor="mm", fill=_c(fill), stroke_width=stroke,
               stroke_fill=_c(stroke_fill) if stroke else None)  # fmt: skip
    if shadow:
        img = img.filter(ImageFilter.GaussianBlur(0.4))
    return img


# ------------------------------------------------------------------ compositor
def affine(x: float, y: float, rot: float = 0.0, sx: float = 1.0, sy: float = 1.0) -> np.ndarray:
    """Matriz 3x3: escala, depois giro (radianos, horário na tela), depois translação."""
    c, s = math.cos(rot), math.sin(rot)
    return np.array([[c * sx, -s * sy, x], [s * sx, c * sy, y], [0, 0, 1]], np.float64)


def sprite_matrix(spr: Sprite, M: np.ndarray, scale: float = 1.0) -> np.ndarray:
    """Matriz pixel do sprite -> tela: leva o pivô à origem, aplica escala do sprite e depois M."""
    P = np.array([[scale, 0, -spr.px * scale], [0, scale, -spr.py * scale], [0, 0, 1]], np.float64)
    return M @ P


def blit(dst: np.ndarray, spr: Sprite, M: np.ndarray, alpha: float = 1.0) -> None:
    """Desenha o sprite em `dst` (BGR uint8) com a matriz 3x3 `M` (pixel do sprite -> pixel da tela)."""
    if alpha <= 0.004:
        return
    h, w = spr.img.shape[:2]
    H, W = dst.shape[:2]
    a, b, tx = M[0]
    c, d, ty = M[1]
    xs = (tx, a * w + tx, b * h + tx, a * w + b * h + tx)
    ys = (ty, c * w + ty, d * h + ty, c * w + d * h + ty)
    x0, x1 = max(int(math.floor(min(xs))), 0), min(int(math.ceil(max(xs))), W)
    y0, y1 = max(int(math.floor(min(ys))), 0), min(int(math.ceil(max(ys))), H)
    if x1 - x0 < 1 or y1 - y0 < 1:
        return
    if abs(a - 1) < 1e-6 and abs(d - 1) < 1e-6 and abs(b) < 1e-6 and abs(c) < 1e-6:
        ix, iy = round(tx), round(ty)
        if abs(tx - ix) < 0.05 and abs(ty - iy) < 0.05:  # só translação inteira: recorte direto
            sx0, sy0 = x0 - ix, y0 - iy
            patch = spr.img[sy0 : sy0 + (y1 - y0), sx0 : sx0 + (x1 - x0)]
            _blend(dst[y0:y1, x0:x1], patch, alpha)
            return
    Mo = np.float64([[a, b, tx - x0], [c, d, ty - y0]])
    patch = cv2.warpAffine(
        spr.img, Mo, (x1 - x0, y1 - y0), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT, borderValue=0
    )
    _blend(dst[y0:y1, x0:x1], patch, alpha)


def _blend(roi: np.ndarray, patch: np.ndarray, alpha: float) -> None:
    if patch.shape[:2] != roi.shape[:2] or not patch.size:
        return
    if alpha < 0.996:
        patch = cv2.convertScaleAbs(patch, alpha=alpha)
    a = patch[:, :, 3]
    inv = cv2.bitwise_not(a)
    inv3 = cv2.merge((inv, inv, inv))
    col = cv2.cvtColor(patch, cv2.COLOR_BGRA2BGR)
    tmp = cv2.multiply(roi, inv3, scale=1.0 / 255)
    cv2.add(tmp, col, dst=tmp)
    roi[:] = tmp


def fill_alpha(dst: np.ndarray, color, alpha: float) -> None:
    """Cobre o quadro inteiro com uma cor translúcida (escurecer, flash)."""
    if alpha <= 0.004:
        return
    over = np.empty_like(dst)
    over[:] = rgb(color)[::-1]
    cv2.addWeighted(dst, 1 - alpha, over, alpha, 0, dst=dst)


def pil_sprite(img: Image.Image, pivot: tuple[float, float] | None = None) -> Sprite:
    """Sprite de uma imagem PIL já no tamanho final (sem supersampling)."""
    if pivot is None:
        pivot = (img.width / 2, img.height / 2)
    return to_sprite(img, pivot, ss=1)
