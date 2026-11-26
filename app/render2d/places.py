"""Cenários 2D desenhados por código (fundo da cena), com variação de horário.

O quadro é desenhado em unidades: 100 de largura e ~178 de altura (9:16). O chão onde os
personagens pisam fica em `GROUND` (fração da altura). Interiores ignoram o céu; exteriores mudam
de cor de dia, no pôr do sol, à noite e no amanhecer.
"""

from __future__ import annotations

import math

import numpy as np
from PIL import Image

from .characters import GOLD
from .draw import Pen, apply_paper, bez, mix, rgb, shade

GROUND = 0.665  # linha do chão (fração da altura do quadro)
UW = 100.0  # largura em unidades

SKY = {
    "day": ((120, 190, 240), (205, 232, 250)),
    "sunset": ((242, 140, 110), (252, 210, 150)),
    "dawn": ((236, 170, 190), (250, 222, 200)),
    "night": ((24, 34, 74), (52, 66, 120)),
}


def _vgrad(w: int, h: int, top, bottom, y0: int = 0, y1: int | None = None) -> np.ndarray:
    y1 = h if y1 is None else y1
    t = np.clip((np.arange(h, dtype=np.float32) - y0) / max(1, y1 - y0), 0, 1)[:, None, None]
    a, b = np.array(rgb(top), np.float32), np.array(rgb(bottom), np.float32)
    img = a + (b - a) * t
    return np.broadcast_to(img, (h, w, 3)).astype(np.uint8)


class Canvas:
    """Fundo em construção: gradiente (numpy) + formas (Pillow com supersampling 2x)."""

    def __init__(self, w: int, h: int):
        self.w, self.h = w, h
        self.k = w / UW
        self.uh = UW * h / w  # altura em unidades
        self.gy = self.uh * GROUND
        self.pen = Pen((0, 0, UW, self.uh), self.k, ss=2)
        self.base: np.ndarray | None = None

    def gradient(self, top, bottom, y0: float = 0.0, y1: float | None = None) -> None:
        g = _vgrad(
            self.w, self.h, top, bottom, int(y0 * self.k), int((y1 if y1 is not None else self.uh) * self.k)
        )
        if self.base is None:
            self.base = g.copy()
        else:
            a, b = int(y0 * self.k), int((y1 if y1 is not None else self.uh) * self.k)
            self.base[a:b] = g[a:b]

    def finish(self, paper: float = 0.0, seed: int = 0) -> np.ndarray:
        if self.base is None:
            self.base = np.full((self.h, self.w, 3), 240, np.uint8)
        layer = self.pen.img.resize((self.w, self.h), Image.LANCZOS)
        bg = Image.fromarray(self.base, "RGB").convert("RGBA")
        bg.alpha_composite(layer)
        arr = np.asarray(bg.convert("RGB"), np.uint8)
        if paper > 0:
            arr = apply_paper(arr, paper * 0.8, seed)
        return np.ascontiguousarray(arr[..., ::-1])  # BGR


# ------------------------------------------------------------------ peças de cenário
def _clouds(p: Pen, ys, col, rng) -> None:
    for y in ys:
        x = float(rng.uniform(8, 92))
        s = float(rng.uniform(0.7, 1.2))
        for dx, dy, r in ((-7, 1.5, 5), (0, -1, 7), (7, 1, 5.5)):
            p.circle(x + dx * s, y + dy * s, r * s, col)
        p.rect(x - 12 * s, y + 1 * s, x + 12 * s, y + 5.5 * s, col, r=2.6 * s)


def _sun_moon(p: Pen, time: str, x: float = 80, y: float = 26) -> None:
    if time == "night":
        p.circle(x, y, 7, (250, 244, 214))
        p.circle(x - 2, y - 1.5, 1.4, (236, 228, 196))
        p.circle(x + 2.4, y + 2, 1.0, (236, 228, 196))
    elif time in ("sunset", "dawn"):
        p.soft(lambda q: q.circle(x, y + 30, 16, (255, 230, 160, 120)))
        p.circle(x, y + 30, 9, (255, 214, 120))
    else:
        p.soft(lambda q: q.circle(x, y, 13, (255, 250, 210, 90)))
        p.circle(x, y, 8, (255, 224, 110))


def _stars(p: Pen, uh: float, rng, n: int = 50, ymax: float | None = None) -> None:
    ymax = ymax or uh * 0.6
    for _ in range(n):
        x, y = float(rng.uniform(0, UW)), float(rng.uniform(0, ymax))
        r = float(rng.uniform(0.25, 0.7))
        p.circle(x, y, r, (250, 250, 230))


def _hills(p: Pen, gy: float, cols, rng, amp: float = 7.0) -> None:
    for i, col in enumerate(cols):
        base = gy - 14 + i * 6
        pts = [(0, gy + 2), (0, base)]
        for x in range(0, 101, 10):
            pts.append((x, base - amp * (0.6 + 0.4 * math.sin(x * 0.07 + i * 1.7 + rng.uniform(0, 0.3)))))
        pts += [(100, base), (100, gy + 2)]
        p.poly(pts, col)


def _tree(p: Pen, x: float, gy: float, s: float, col) -> None:
    p.rect(x - 1.1 * s, gy - 10 * s, x + 1.1 * s, gy, (150, 100, 60))
    for dx, dy, r in ((-4, -12, 5), (4, -12.5, 5), (0, -17, 6.4)):
        p.circle(x + dx * s, gy + dy * s, r * s, col)


def _palm(p: Pen, x: float, gy: float, s: float) -> None:
    p.line(bez((x, gy), (x - 1.5 * s, gy - 10 * s), (x + 1.5 * s, gy - 21 * s)), 2.0 * s, (176, 120, 70))
    for a in (-160, -125, -90, -55, -20, 200):
        ex = x + 1.5 * s + math.cos(math.radians(a)) * 11 * s
        ey = gy - 21 * s + math.sin(math.radians(a)) * 6 * s + 4 * s
        p.poly(bez((x + 1.5 * s, gy - 21 * s), ((x + ex) / 2, gy - 26 * s), (ex, ey), n=8)
               + bez((ex, ey), ((x + ex) / 2, gy - 22 * s), (x + 1.5 * s, gy - 20 * s), n=8),
               (88, 170, 84) if a % 2 else (66, 140, 70))  # fmt: skip


def _house(p: Pen, x: float, gy: float, w: float, h: float, wall, roof, garage: bool = False) -> None:
    p.rect(x, gy - h, x + w, gy, wall)
    p.poly([(x - 2, gy - h + 1), (x + w / 2, gy - h - w * 0.42), (x + w + 2, gy - h + 1)], roof)
    p.rect(x + w * 0.12, gy - h * 0.6, x + w * 0.42, gy - h * 0.3, (150, 206, 236), r=0.4)
    p.line([(x + w * 0.27, gy - h * 0.6), (x + w * 0.27, gy - h * 0.3)], 0.5, (250, 250, 250))
    if garage:
        p.rect(x + w * 0.52, gy - h * 0.55, x + w * 0.9, gy, (170, 170, 176))
        for i in range(5):
            y = gy - h * 0.55 + (i + 1) * h * 0.1
            p.line([(x + w * 0.52, y), (x + w * 0.9, y)], 0.35, (140, 140, 148))
    else:
        p.rect(x + w * 0.58, gy - h * 0.5, x + w * 0.82, gy, (150, 96, 60), r=0.6)


# ------------------------------------------------------------------ cenários
def _outdoor_sky(cv: Canvas, time: str, rng, clouds: bool = True) -> None:
    top, bot = SKY.get(time, SKY["day"])
    cv.gradient(top, bot, 0, cv.gy)
    p = cv.pen
    if time == "night":
        _stars(p, cv.uh, rng, 60, cv.gy * 0.7)
    _sun_moon(p, time)
    if clouds and time != "night":
        _clouds(
            p,
            (rng.uniform(18, 30), rng.uniform(38, 52)),
            (255, 255, 255) if time == "day" else (255, 236, 220),
            rng,
        )


def place_plain(cv: Canvas, time: str, rng, color=None) -> None:
    c = rgb(color, (248, 206, 214))
    cv.gradient(shade(c, 1.25), shade(c, 0.92))
    p = cv.pen
    for _ in range(14):
        x, y = float(rng.uniform(4, 96)), float(rng.uniform(6, cv.uh - 6))
        p.soft(lambda q, x=x, y=y: q.circle(x, y, float(rng.uniform(0.8, 2.2)), (*shade(c, 1.35), 120)))


def place_room(cv: Canvas, time: str, rng, color=None) -> None:
    wall = rgb(color, (246, 222, 196))
    cv.gradient(wall, shade(wall, 0.97), 0, cv.gy)
    p = cv.pen
    for i in range(0, 100, 8):
        p.rect(i, 0, i + 4, cv.gy, shade(wall, 0.95))
    cv.gradient((196, 140, 96), (176, 120, 80), cv.gy, cv.uh)
    for j in range(8):
        y = cv.gy + 3 + j * 7.5
        p.line([(0, y), (100, y)], 0.35, (150, 100, 66))
        for i in range(4):
            x = (i * 31 + j * 17) % 100
            p.line([(x, y), (x, y + 7.5)], 0.3, (150, 100, 66))
    p.rect(0, cv.gy - 1.5, 100, cv.gy + 0.8, (120, 80, 56))
    if time == "night":
        p.soft(lambda q: q.rect(0, 0, 100, cv.uh, (20, 20, 60, 70)))


def place_bedroom(cv: Canvas, time: str, rng, color=None) -> None:
    place_room(cv, time, rng, color or (246, 230, 196))
    p = cv.pen
    top, bot = SKY.get(time, SKY["day"])
    p.rect(12, 30, 40, 62, (250, 250, 250), r=1)
    p.rect(14, 32, 38, 60, top)
    p.line([(26, 32), (26, 60)], 0.8, (250, 250, 250))
    for x in (8, 38):
        p.rect(x, 26, x + 6, 66, (140, 80, 150), r=1.5)
    p.rect(62, 34, 82, 50, (236, 150, 60), r=1)
    p.circle(72, 42, 4, (250, 220, 120))


def place_living(cv: Canvas, time: str, rng, color=None) -> None:
    place_room(cv, time, rng, color or (232, 236, 214))
    p = cv.pen
    p.rect(30, 40, 70, 62, (90, 120, 170), r=1)
    p.rect(32, 42, 68, 60, (150, 196, 230))
    p.rect(84, cv.gy - 16, 90, cv.gy, (120, 90, 70))
    p.circle(87, cv.gy - 20, 6, (88, 170, 84))


def place_office(cv: Canvas, time: str, rng, color=None) -> None:
    wall = rgb(color, (226, 232, 240))
    cv.gradient(wall, shade(wall, 0.95), 0, cv.gy)
    cv.gradient((170, 176, 190), (150, 156, 170), cv.gy, cv.uh)
    p = cv.pen
    top, bot = SKY.get(time, SKY["day"])
    p.rect(14, 26, 86, 70, (250, 250, 250), r=1)
    p.rect(16, 28, 84, 68, top)
    for i in range(8):
        x = 16 + i * 8.5
        hh = float(rng.uniform(12, 30))
        p.rect(x, 68 - hh, x + 7, 68, (120, 140, 176) if time != "night" else (40, 50, 80))
    for x in (38, 62):
        p.line([(x, 28), (x, 68)], 1.0, (250, 250, 250))
    p.rect(0, cv.gy - 1, 100, cv.gy + 0.6, (120, 126, 140))


def place_classroom(cv: Canvas, time: str, rng, color=None) -> None:
    place_room(cv, time, rng, color or (240, 230, 200))
    p = cv.pen
    p.rect(14, 30, 86, 70, (130, 90, 60), r=1)
    p.rect(16, 32, 84, 68, (52, 100, 80))
    p.line([(22, 42), (50, 42)], 0.7, (230, 236, 230))
    p.line([(22, 50), (44, 50)], 0.7, (230, 236, 230))


def place_lab(cv: Canvas, time: str, rng, color=None) -> None:
    wall = rgb(color, (214, 232, 240))
    cv.gradient(wall, shade(wall, 0.96), 0, cv.gy)
    cv.gradient((190, 200, 210), (176, 186, 196), cv.gy, cv.uh)
    p = cv.pen
    for y in (40, 62):
        p.rect(6, y, 94, y + 1.6, (170, 178, 190))
        for i in range(10):
            x = 9 + i * 9
            col = [(236, 90, 100), (90, 200, 120), (80, 150, 230), (250, 190, 60), (170, 110, 220)][i % 5]
            hh = 6 + (i % 3) * 2
            p.rect(x, y - hh, x + 3.4, y, (230, 240, 250), r=0.6)
            p.rect(x, y - hh * 0.55, x + 3.4, y, col, r=0.6)
    for j in range(7):
        for i in range(10):
            p.rect(
                i * 10,
                cv.gy + j * 9,
                i * 10 + 9.6,
                cv.gy + j * 9 + 8.6,
                (198, 208, 218) if (i + j) % 2 else (184, 194, 206),
            )


def place_church(cv: Canvas, time: str, rng, color=None) -> None:
    wall = rgb(color, (236, 214, 186))
    cv.gradient(wall, shade(wall, 0.95), 0, cv.gy)
    cv.gradient((190, 140, 100), (170, 120, 86), cv.gy, cv.uh)
    p = cv.pen
    for x in (10, 72):
        p.chord(x + 9, 40, 9, 9, 180, 360, (120, 90, 70))
        p.rect(x, 40, x + 18, 74, (120, 90, 70))
        p.chord(x + 9, 41, 7.4, 7.4, 180, 360, (90, 150, 210))
        p.rect(x + 1.6, 41, x + 16.4, 72.4, (90, 150, 210))
        p.rect(x + 1.6, 56, x + 16.4, 72.4, (110, 180, 110))
        p.line([(x + 9, 33), (x + 9, 72)], 0.9, (120, 90, 70))
        p.line([(x + 1.6, 56), (x + 16.4, 56)], 0.9, (120, 90, 70))
    p.rect(0, cv.gy - 1.2, 100, cv.gy + 0.6, (130, 90, 60))


def place_palace(cv: Canvas, time: str, rng, color=None) -> None:
    wall = rgb(color, (92, 70, 140))
    cv.gradient(shade(wall, 1.1), wall, 0, cv.gy)
    p = cv.pen
    cv.gradient((170, 44, 60), (150, 36, 50), cv.gy, cv.uh)
    for x in (6, 84):
        p.rect(x, 18, x + 10, cv.gy, GOLD)
        p.rect(x - 2, 14, x + 12, 20, shade(GOLD, 0.9))
        p.rect(x - 2, cv.gy - 5, x + 12, cv.gy, shade(GOLD, 0.9))
    p.rect(0, 10, 100, 14, shade(GOLD, 0.9))
    for x in (30, 60):
        p.poly([(x, 20), (x + 10, 20), (x + 10, 54), (x + 5, 50), (x, 54)], (200, 50, 60))
        p.star(x + 5, 30, 2.6, 1.2, GOLD)
    p.poly([(36, cv.gy), (64, cv.gy), (80, cv.uh), (20, cv.uh)], (210, 60, 70))
    p.line([(36, cv.gy), (20, cv.uh)], 0.8, GOLD)
    p.line([(64, cv.gy), (80, cv.uh)], 0.8, GOLD)


def place_street(cv: Canvas, time: str, rng, color=None) -> None:
    _outdoor_sky(cv, time, rng)
    p = cv.pen
    gy = cv.gy
    walls = [(246, 214, 170), (250, 236, 210), (236, 200, 160)]
    for i, x in enumerate((-6, 30, 66)):
        _house(p, x, gy - 4, 34, 24, walls[i % 3], (222, 96, 64), garage=i == 1)
    for x in (8, 58, 98):
        p.rect(x, gy - 46, x + 1.2, gy - 4, (110, 100, 96))
    p.line(bez((0, gy - 42), (30, gy - 38), (60, gy - 42)), 0.3, (60, 60, 60))
    p.line(bez((40, gy - 42), (70, gy - 37), (100, gy - 42)), 0.3, (60, 60, 60))
    cv.gradient((200, 200, 204), (190, 190, 196), gy - 4, gy + 4)
    cv.gradient((96, 98, 108), (84, 86, 96), gy + 4, cv.uh)
    for i in range(6):
        p.rect(4 + i * 18, gy + 22, 12 + i * 18, gy + 23.6, (250, 250, 250))
    if time == "night":
        p.soft(lambda q: q.rect(0, 0, 100, cv.uh, (10, 10, 40, 80)))


def place_city(cv: Canvas, time: str, rng, color=None) -> None:
    _outdoor_sky(cv, time, rng)
    p = cv.pen
    gy = cv.gy
    night = time == "night"
    for col, hmin, hmax in (((150, 170, 200), 30, 60), ((110, 130, 170), 20, 46)):
        x = -2
        while x < 102:
            w = float(rng.uniform(9, 16))
            hh = float(rng.uniform(hmin, hmax))
            c = col if not night else shade(col, 0.4)
            p.rect(x, gy - hh, x + w, gy, c)
            for r in range(int(hh // 6)):
                for q in range(int(w // 4)):
                    lit = night and rng.random() < 0.4
                    p.rect(x + 1.5 + q * 4, gy - hh + 2 + r * 6, x + 3.5 + q * 4, gy - hh + 4.5 + r * 6,
                           (250, 220, 130) if lit else shade(c, 1.12))  # fmt: skip
            x += w + float(rng.uniform(0.5, 2))
    cv.gradient((96, 98, 108), (84, 86, 96), gy, cv.uh)
    for i in range(6):
        p.rect(4 + i * 18, gy + 20, 12 + i * 18, gy + 21.6, (250, 250, 250))


def place_ancient(cv: Canvas, time: str, rng, color=None) -> None:
    top, bot = {"day": ((246, 222, 186), (250, 236, 210))}.get(time, SKY.get(time, SKY["day"]))
    cv.gradient(top, bot, 0, cv.gy)
    p = cv.pen
    gy = cv.gy
    if time == "night":
        _stars(p, cv.uh, rng, 40, gy * 0.6)
    for x, w, h in ((14, 20, 24), (40, 24, 32), (70, 18, 20)):
        col = (226, 200, 160)
        p.rect(x, gy - 14 - h, x + w, gy - 14, col)
        p.rect(x + 3, gy - 14 - h - 7, x + w - 3, gy - 14 - h, shade(col, 1.05))
        p.rect(x + w * 0.4, gy - 14 - h - 12, x + w * 0.6, gy - 14 - h - 7, shade(col, 1.08))
    wall = rgb(color, (52, 92, 170))
    p.rect(0, gy - 16, 100, gy - 3, wall)
    for i in range(14):
        p.rect(i * 7.4, gy - 19, i * 7.4 + 4, gy - 16, wall)
    p.rect(0, gy - 6, 100, gy - 4.8, GOLD)
    for i in range(6):
        p.chord(8 + i * 17, gy - 9, 3.4, 2, 180, 360, (250, 236, 200))
    for x in (4, 92):
        _palm(p, x, gy - 2, 1.0)
    cv.gradient((236, 208, 160), (226, 194, 146), gy - 3, cv.uh)
    p.line([(0, gy + 30), (100, gy + 30)], 0.4, (214, 184, 140))


def place_desert(cv: Canvas, time: str, rng, color=None) -> None:
    _outdoor_sky(cv, time, rng, clouds=False)
    p = cv.pen
    gy = cv.gy
    _hills(p, gy, [(236, 200, 140), (226, 186, 126)], rng, 6)
    cv.gradient((236, 204, 150), (224, 190, 136), gy, cv.uh)
    p.rect(8, gy - 12, 10, gy, (80, 160, 90))
    p.line([(8, gy - 7), (5.5, gy - 7), (5.5, gy - 10)], 1.6, (80, 160, 90))


def place_egypt(cv: Canvas, time: str, rng, color=None) -> None:
    _outdoor_sky(cv, time, rng, clouds=False)
    p = cv.pen
    gy = cv.gy
    for x, s in ((26, 1.0), (60, 1.3), (86, 0.8)):
        col = (226, 190, 120)
        p.poly([(x - 18 * s, gy), (x, gy - 22 * s), (x + 18 * s, gy)], col)
        p.poly([(x, gy - 22 * s), (x + 18 * s, gy), (x + 4 * s, gy)], shade(col, 0.85))
    cv.gradient((236, 204, 150), (224, 190, 136), gy, cv.uh)


def place_village(cv: Canvas, time: str, rng, color=None) -> None:
    _outdoor_sky(cv, time, rng)
    p = cv.pen
    gy = cv.gy
    _hills(p, gy, [(150, 200, 120), (120, 184, 100)], rng)
    for x, s in ((6, 0.8), (78, 0.9)):
        _house(p, x, gy - 3, 20 * s, 14 * s, (246, 226, 192), (222, 96, 64))
    for x in (34, 60, 96):
        _tree(p, x, gy - 2, 1.0, (88, 170, 84))
    cv.gradient((130, 196, 104), (110, 176, 90), gy - 2, cv.uh)
    p.poly([(44, gy), (56, gy), (70, cv.uh), (30, cv.uh)], (214, 190, 140))


def place_farm(cv: Canvas, time: str, rng, color=None) -> None:
    _outdoor_sky(cv, time, rng)
    p = cv.pen
    gy = cv.gy
    _hills(p, gy, [(160, 206, 120)], rng)
    p.rect(64, gy - 26, 90, gy - 2, (196, 60, 50))
    p.poly([(62, gy - 25), (77, gy - 36), (92, gy - 25)], (150, 46, 40))
    p.rect(72, gy - 14, 82, gy - 2, (250, 250, 250))
    for i in range(10):
        x = 2 + i * 6
        p.rect(x, gy - 9, x + 1.6, gy - 1, (250, 250, 248))
    p.rect(0, gy - 7, 60, gy - 6, (250, 250, 248))
    cv.gradient((140, 200, 100), (120, 180, 86), gy - 2, cv.uh)


def place_forest(cv: Canvas, time: str, rng, color=None) -> None:
    _outdoor_sky(cv, time, rng)
    p = cv.pen
    gy = cv.gy
    for i, col in enumerate(((100, 170, 110), (76, 150, 90))):
        for j in range(8):
            x = j * 14 + (7 if i else 0) + float(rng.uniform(-2, 2))
            _tree(p, x, gy - 6 + i * 4, 1.3 + i * 0.25, col if time != "night" else shade(col, 0.5))
    cv.gradient((110, 180, 96), (90, 160, 80), gy - 2, cv.uh)
    p.poly([(44, gy - 2), (56, gy - 2), (72, cv.uh), (28, cv.uh)], (190, 160, 110))
    for _ in range(12):
        x, y = float(rng.uniform(2, 98)), float(rng.uniform(gy + 4, cv.uh - 4))
        p.circle(x, y, 0.8, (250, 240, 120) if rng.random() < 0.5 else (250, 140, 170))


def place_park(cv: Canvas, time: str, rng, color=None) -> None:
    _outdoor_sky(cv, time, rng)
    p = cv.pen
    gy = cv.gy
    _hills(p, gy, [(150, 210, 130)], rng, 4)
    for x in (10, 88):
        _tree(p, x, gy - 1, 1.5, (88, 170, 84))
    p.rect(60, gy - 6, 78, gy - 5, (150, 100, 60))
    p.rect(60, gy - 9, 78, gy - 8, (150, 100, 60))
    cv.gradient((140, 206, 110), (120, 190, 96), gy - 1, cv.uh)
    p.poly([(40, gy - 1), (60, gy - 1), (80, cv.uh), (20, cv.uh)], (214, 200, 170))


def place_hills(cv: Canvas, time: str, rng, color=None) -> None:
    _outdoor_sky(cv, time, rng)
    p = cv.pen
    gy = cv.gy
    _hills(p, gy, [(170, 214, 140), (140, 200, 120), (116, 184, 100)], rng, 8)
    cv.gradient((120, 190, 100), (100, 170, 86), gy, cv.uh)
    for _ in range(10):
        x, y = float(rng.uniform(2, 98)), float(rng.uniform(gy + 6, cv.uh - 6))
        p.circle(x, y, 0.9, (250, 250, 250))


def place_beach(cv: Canvas, time: str, rng, color=None) -> None:
    _outdoor_sky(cv, time, rng)
    p = cv.pen
    gy = cv.gy
    cv.gradient((70, 160, 220), (90, 190, 230), gy - 22, gy)
    for i in range(5):
        y = gy - 20 + i * 4
        p.line([(float(rng.uniform(0, 40)), y), (float(rng.uniform(50, 100)), y)], 0.35, (250, 250, 250))
    cv.gradient((246, 222, 170), (236, 206, 150), gy, cv.uh)
    p.line(bez((0, gy + 1), (50, gy - 1), (100, gy + 1)), 1.0, (250, 250, 250))
    _palm(p, 90, gy + 6, 1.2)


def place_underwater(cv: Canvas, time: str, rng, color=None) -> None:
    cv.gradient((40, 150, 200), (16, 70, 130))
    p = cv.pen
    gy = cv.gy
    for i in range(5):
        x = 10 + i * 20
        p.soft(lambda q, x=x: q.poly([(x, 0), (x + 6, 0), (x + 14, gy), (x + 2, gy)], (255, 255, 255, 26)))
    cv.gradient((226, 206, 160), (206, 186, 140), gy + 4, cv.uh)
    p.line(bez((0, gy + 5), (50, gy + 2), (100, gy + 5)), 1.6, (236, 216, 170))
    for x in (8, 22, 80, 94):
        h = float(rng.uniform(14, 26))
        p.line([(x + math.sin(i) * 2, gy + 5 - i * h / 6) for i in range(7)], 2.2, (60, 160, 90))
    for x, col in ((40, (240, 120, 120)), (64, (250, 170, 90))):
        for i in range(4):
            p.circle(x + i * 2.4 - 3, gy + 2 - (i % 2) * 2, 2.4, col)


def place_space(cv: Canvas, time: str, rng, color=None) -> None:
    cv.gradient((14, 18, 46), (34, 30, 80))
    p = cv.pen
    _stars(p, cv.uh, rng, 110, cv.uh)
    p.soft(lambda q: q.circle(78, 30, 16, (120, 90, 200, 50)))
    p.circle(14, 150, 12, (236, 170, 90))
    p.ellipse(14, 150, 20, 4, None, outline=(250, 210, 150), width=1.2)


def place_sky(cv: Canvas, time: str, rng, color=None) -> None:
    top, bot = SKY.get(time, SKY["day"]) if time != "day" else ((150, 206, 246), (250, 240, 210))
    cv.gradient(top, bot)
    p = cv.pen
    for i in range(10):
        a = math.radians(-90 + (i - 4.5) * 16)
        p.soft(lambda q, a=a: q.poly([(50, -6), (50 + math.cos(a - 0.05) * 200, -6 + math.sin(a - 0.05) * -200),
                                      (50 + math.cos(a + 0.05) * 200, -6 + math.sin(a + 0.05) * -200)], (255, 255, 230, 40)))  # fmt: skip
    _clouds(p, (30, 60, 100, 140), (255, 255, 255), rng)
    for x in (18, 50, 82):
        for dx, r in ((-8, 6), (0, 8), (8, 6)):
            p.circle(x + dx, cv.gy + 6, r, (255, 255, 255))
    p.rect(0, cv.gy + 6, 100, cv.uh, (255, 255, 255))


def place_night(cv: Canvas, time: str, rng, color=None) -> None:
    cv.gradient((20, 24, 60), (60, 50, 100), 0, cv.gy)
    p = cv.pen
    gy = cv.gy
    _stars(p, cv.uh, rng, 70, gy * 0.8)
    _sun_moon(p, "night", 76, 24)
    x = -2
    while x < 102:
        w = float(rng.uniform(8, 14))
        hh = float(rng.uniform(16, 40))
        p.rect(x, gy - hh, x + w, gy, (34, 34, 60))
        for r in range(int(hh // 6)):
            for q in range(int(w // 4)):
                if rng.random() < 0.3:
                    p.rect(
                        x + 1.5 + q * 4,
                        gy - hh + 2 + r * 6,
                        x + 3.4 + q * 4,
                        gy - hh + 4.3 + r * 6,
                        (250, 214, 120),
                    )
        x += w + 1
    cv.gradient((44, 44, 70), (30, 30, 52), gy, cv.uh)


def place_graveyard(cv: Canvas, time: str, rng, color=None) -> None:
    cv.gradient((40, 30, 70), (90, 70, 110), 0, cv.gy)
    p = cv.pen
    gy = cv.gy
    _stars(p, cv.uh, rng, 40, gy * 0.6)
    _sun_moon(p, "night", 72, 26)
    p.line([(10, gy), (12, gy - 30), (4, gy - 40)], 2, (40, 34, 50))
    p.line([(12, gy - 22), (22, gy - 34)], 1.6, (40, 34, 50))
    for x in (30, 52, 74, 92):
        h = float(rng.uniform(9, 13))
        p.chord(x, gy - h + 3, 4.6, 4, 180, 360, (130, 130, 150))
        p.rect(x - 4.6, gy - h + 3, x + 4.6, gy, (130, 130, 150))
    cv.gradient((60, 70, 70), (40, 50, 52), gy, cv.uh)
    p.soft(lambda q: q.rect(0, gy - 8, 100, gy + 10, (200, 200, 230, 50)))


def place_cave(cv: Canvas, time: str, rng, color=None) -> None:
    cv.gradient((70, 60, 70), (40, 34, 44))
    p = cv.pen
    gy = cv.gy
    for i in range(9):
        x = i * 12 + float(rng.uniform(-2, 2))
        p.poly([(x - 6, 0), (x, float(rng.uniform(10, 26))), (x + 6, 0)], (60, 52, 62))
    cv.gradient((80, 70, 76), (60, 52, 58), gy, cv.uh)
    for _ in range(14):
        x, y = float(rng.uniform(0, 100)), float(rng.uniform(gy, cv.uh))
        p.ellipse(x, y, float(rng.uniform(2, 5)), 1.2, (96, 86, 92))


def place_mountains(cv: Canvas, time: str, rng, color=None) -> None:
    _outdoor_sky(cv, time, rng)
    p = cv.pen
    gy = cv.gy
    for x, w, h, col in (
        (20, 34, 40, (130, 140, 180)),
        (60, 40, 54, (110, 120, 166)),
        (92, 30, 36, (130, 140, 180)),
    ):
        p.poly([(x - w, gy), (x, gy - h), (x + w, gy)], col)
        p.poly([(x, gy - h), (x - w * 0.25, gy - h * 0.72), (x - w * 0.1, gy - h * 0.78), (x + w * 0.05, gy - h * 0.7),
                (x + w * 0.22, gy - h * 0.76)], (250, 250, 250))  # fmt: skip
    for i in range(8):
        x = 4 + i * 13
        p.poly([(x - 4, gy), (x, gy - 12), (x + 4, gy)], (60, 140, 90))
    cv.gradient((120, 186, 110), (100, 166, 96), gy, cv.uh)


def place_snow(cv: Canvas, time: str, rng, color=None) -> None:
    _outdoor_sky(cv, time, rng)
    p = cv.pen
    gy = cv.gy
    _hills(p, gy, [(236, 242, 250), (222, 232, 246)], rng)
    for i in range(6):
        x = 6 + i * 18
        p.poly([(x - 5, gy - 1), (x, gy - 16), (x + 5, gy - 1)], (60, 130, 100))
        p.poly([(x - 3, gy - 8), (x, gy - 16), (x + 3, gy - 8)], (250, 250, 250))
    cv.gradient((246, 248, 252), (226, 234, 246), gy, cv.uh)


def place_fire(cv: Canvas, time: str, rng, color=None) -> None:
    cv.gradient((140, 26, 18), (226, 96, 36), 0, cv.gy)
    p = cv.pen
    gy = cv.gy
    for i in range(10):  # labaredas atrás (do chão para cima)
        x = i * 11 - 2
        h = float(rng.uniform(46, 96))
        col = [(236, 90, 40), (248, 136, 40), (255, 190, 70)][i % 3]
        p.poly(bez((x - 10, gy + 2), (x - 9, gy - h * 0.6), (x + 2, gy - h), (x + 10, gy + 2), 10), col)
    for i in range(10):
        x = i * 11 + 3
        h = float(rng.uniform(22, 50))
        p.poly(bez((x - 7, 0), (x - 6, h * 0.6), (x + 2, h), (x + 7, 0), 8), (210, 60, 30))
    cv.gradient((96, 30, 24), (70, 22, 18), gy, cv.uh)
    for _ in range(14):  # brasas no chão
        x, y = float(rng.uniform(0, 100)), float(rng.uniform(gy + 6, cv.uh - 4))
        p.ellipse(x, y, float(rng.uniform(1.5, 4)), 0.9, (230, 110, 40))
    for i in range(9):  # chamas baixas na frente, só na borda de baixo
        x = i * 12 + 2
        h = float(rng.uniform(8, 16))
        p.poly(
            bez((x - 6, cv.uh), (x - 5, cv.uh - h * 0.6), (x + 1, cv.uh - h), (x + 6, cv.uh), 8),
            (250, 140, 40),
        )


def place_stage(cv: Canvas, time: str, rng, color=None) -> None:
    cv.gradient((40, 30, 60), (20, 16, 34), 0, cv.gy)
    p = cv.pen
    gy = cv.gy
    curtain = rgb(color, (40, 46, 90))
    for i in range(10):
        x = i * 10
        p.rect(x, 0, x + 10, gy, curtain if i % 2 else shade(curtain, 0.85))
    p.soft(lambda q: q.poly([(38, 0), (62, 0), (82, gy + 20), (18, gy + 20)], (255, 250, 220, 50)))
    cv.gradient((90, 60, 50), (70, 46, 40), gy, cv.uh)
    p.soft(lambda q: q.ellipse(50, gy + 8, 26, 6, (255, 250, 220, 70)))


def place_stable(cv: Canvas, time: str, rng, color=None) -> None:
    t = "night" if time == "day" else time
    _outdoor_sky(cv, t, rng, clouds=False)
    p = cv.pen
    gy = cv.gy
    p.star(50, 22, 4.6, 1.8, (255, 236, 150))
    p.soft(lambda q: q.circle(50, 22, 10, (255, 236, 150, 60)))
    p.poly(
        [(6, gy - 40), (50, gy - 58), (94, gy - 40), (90, gy - 36), (50, gy - 52), (10, gy - 36)],
        (150, 100, 60),
    )
    p.rect(12, gy - 38, 88, gy, (80, 52, 34))
    for x in (12, 84):
        p.rect(x, gy - 40, x + 4, gy, (130, 86, 52))
    cv.gradient((200, 160, 90), (180, 140, 80), gy, cv.uh)
    for _ in range(30):
        x, y = float(rng.uniform(0, 100)), float(rng.uniform(gy, gy + 20))
        p.line([(x, y), (x + float(rng.uniform(-3, 3)), y - 2)], 0.4, (236, 200, 110))


def place_temple(cv: Canvas, time: str, rng, color=None) -> None:
    _outdoor_sky(cv, time, rng)
    p = cv.pen
    gy = cv.gy
    col = (246, 240, 226)
    p.rect(4, gy - 6, 96, gy, shade(col, 0.9))
    for i in range(6):
        x = 10 + i * 16
        p.rect(x - 3.5, gy - 44, x + 3.5, gy - 6, col)
    p.rect(2, gy - 50, 98, gy - 44, col)
    p.poly([(2, gy - 50), (50, gy - 64), (98, gy - 50)], shade(col, 0.95))
    cv.gradient((226, 214, 190), (210, 198, 174), gy, cv.uh)


def place_castle(cv: Canvas, time: str, rng, color=None) -> None:
    _outdoor_sky(cv, time, rng)
    p = cv.pen
    gy = cv.gy
    _hills(p, gy, [(150, 200, 120)], rng)
    col = (190, 190, 205)
    p.rect(30, gy - 34, 70, gy - 4, col)
    for x in (22, 70):
        p.rect(x, gy - 46, x + 9, gy - 4, shade(col, 0.95))
        p.poly([(x - 2, gy - 46), (x + 4.5, gy - 58), (x + 11, gy - 46)], (90, 110, 200))
    for i in range(6):
        p.rect(30 + i * 7, gy - 37, 33 + i * 7, gy - 34, col)
    p.chord(50, gy - 12, 5, 6, 180, 360, (110, 80, 60))
    p.rect(45, gy - 12, 55, gy - 4, (110, 80, 60))
    cv.gradient((130, 196, 104), (110, 176, 90), gy - 4, cv.uh)


def place_jungle(cv: Canvas, time: str, rng, color=None) -> None:
    cv.gradient((120, 200, 160), (60, 140, 100), 0, cv.gy)
    p = cv.pen
    gy = cv.gy
    for i in range(16):
        x = float(rng.uniform(-5, 105))
        y = float(rng.uniform(10, gy))
        a = float(rng.uniform(-1, 1))
        col = [(50, 130, 80), (70, 160, 90), (40, 110, 70)][i % 3]
        p.poly(bez((x, y), (x + 14 * math.cos(a) - 6, y - 12), (x + 26 * math.cos(a), y + 6 * math.sin(a)), n=10)
               + bez((x + 26 * math.cos(a), y + 6 * math.sin(a)), (x + 14, y + 8), (x, y), n=10), col)  # fmt: skip
    cv.gradient((90, 150, 80), (70, 130, 66), gy, cv.uh)


PLACES = {
    "plain": place_plain, "room": place_room, "bedroom": place_bedroom, "living_room": place_living,
    "office": place_office, "classroom": place_classroom, "lab": place_lab, "church": place_church,
    "palace": place_palace, "street": place_street, "city": place_city, "ancient_city": place_ancient,
    "desert": place_desert, "egypt": place_egypt, "village": place_village, "farm": place_farm,
    "forest": place_forest, "park": place_park, "hills": place_hills, "beach": place_beach,
    "underwater": place_underwater, "space": place_space, "sky": place_sky, "night_city": place_night,
    "graveyard": place_graveyard, "cave": place_cave, "mountains": place_mountains, "snow": place_snow,
    "fire": place_fire, "stage": place_stage, "stable": place_stable, "temple": place_temple,
    "castle": place_castle, "jungle": place_jungle,
}  # fmt: skip
INDOOR = {
    "room",
    "bedroom",
    "living_room",
    "office",
    "classroom",
    "lab",
    "church",
    "palace",
    "stage",
    "fire",
    "cave",
}
FLOATING = {"plain", "space", "sky", "underwater"}  # sem chão visível (personagens ganham sombra suave)
TIMES2D = ("day", "sunset", "night", "dawn")


def draw_place(
    name: str, time: str, w: int, h: int, paper: float = 0.0, seed: int = 0, color=None
) -> np.ndarray:
    fn = PLACES.get(name, place_plain)
    rng = np.random.default_rng(seed)
    cv = Canvas(w, h)
    fn(cv, time if time in TIMES2D else "day", rng, color)
    return cv.finish(paper, seed)


def ground_color(name: str, time: str) -> tuple:
    """Cor aproximada do chão (para sombras e fundo das legendas)."""
    return {
        "room": (186, 130, 88), "palace": (160, 40, 56), "street": (90, 92, 102), "city": (90, 92, 102),
        "ancient_city": (230, 200, 154), "beach": (240, 214, 160), "space": (24, 24, 60),
    }.get(name, mix((120, 180, 100), (40, 40, 60), 0.6 if time == "night" else 0.0))  # fmt: skip
