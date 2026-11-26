"""Objetos 2D desenhados por código (casas, árvores, celular, coroa, dinheiro, ícones...).

Cada objeto é desenhado numa caixa de 100 unidades de altura. `h` é a altura padrão como fração
da altura do vídeo; `anchor` diz se o objeto fica no chão (pivô embaixo) ou flutua (pivô no centro).
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from .characters import GOLD
from .draw import Pen, Sprite, bez, pen_sprite, rgb, shade

WOOD = (160, 104, 62)
WOOD_D = (118, 74, 44)
LEAF = (88, 170, 84)
LEAF_D = (62, 136, 66)
ROOF = (222, 96, 64)
WALL = (246, 226, 192)
GLASS = (150, 206, 236)
STONE = (196, 190, 182)
METAL = (176, 184, 198)
RED = (226, 64, 60)
INKC = (44, 40, 50)


@dataclass(frozen=True)
class PropDef:
    fn: object
    h: float  # altura padrão (fração da altura do quadro)
    anchor: str  # ground | center
    box: tuple
    sky: bool = False
    big: bool = False  # construção grande (fica no fundo)


PROPS: dict[str, PropDef] = {}


def prop(name: str, h: float, anchor: str = "ground", box=None, sky: bool = False, big: bool = False):
    if box is None:
        box = (-60, -104, 60, 4) if anchor == "ground" else (-60, -60, 60, 60)

    def deco(fn):
        PROPS[name] = PropDef(fn, h, anchor, box, sky, big)
        return fn

    return deco


def draw_prop(name: str, height_px: float, color=None, paper: float = 0.0, seed: int = 0) -> Sprite:
    d = PROPS.get(name) or PROPS["box"]
    k = height_px / 100.0
    p = Pen(d.box, k)
    d.fn(p, rgb(color, (0, 0, 0)) if color is not None else None)
    pivot = (0.0, 0.0)
    return pen_sprite(
        p, pivot, shadow=0.24 * (paper > 0), paper=paper, seed=seed, shadow_scale=max(0.6, k / 3)
    )


def _c(c, default):
    return c if c is not None else default


# ------------------------------------------------------------------ natureza
@prop("tree", 0.34)
def _tree(p: Pen, c):
    p.poly([(-7, 0), (-5, -42), (5, -42), (7, 0)], WOOD)
    col = _c(c, LEAF)
    for x, y, r in ((-20, -52, 22), (20, -54, 21), (0, -72, 27), (-12, -82, 18), (14, -84, 17)):
        p.circle(x, y, r, shade(col, 0.88))
    for x, y, r in ((-16, -58, 18), (16, -60, 17), (0, -76, 22)):
        p.circle(x, y, r, col)
    p.soft(lambda q: q.circle(-8, -82, 9, (255, 255, 255, 50)))


@prop("pine", 0.34)
def _pine(p: Pen, c):
    p.rect(-5, -16, 5, 0, WOOD)
    col = _c(c, (60, 140, 90))
    for i, (w, y) in enumerate(((34, -14), (28, -40), (21, -64))):
        p.poly([(-w, y), (0, y - 36), (w, y)], shade(col, 1 - i * 0.05))


@prop("palm", 0.38, box=(-70, -104, 70, 4))
def _palm(p: Pen, c):
    p.line(bez((4, 0), (-2, -40), (8, -82)), 9, (176, 120, 70))
    for i in range(5):
        p.line([(-3 + i * 0.5, -10 - i * 15), (11 + i * 0.5, -12 - i * 15)], 1.2, (140, 90, 50))
    col = _c(c, LEAF)
    for a in (-160, -125, -90, -55, -20, 200):
        ex = 8 + math.cos(math.radians(a)) * 42
        ey = -84 + math.sin(math.radians(a)) * 24 + 16
        p.poly(bez((8, -84), ((8 + ex) / 2, -100), (ex, ey), n=10) + bez((ex, ey), ((8 + ex) / 2, -86), (8, -80), n=10),
               col if a % 2 else shade(col, 0.85))  # fmt: skip
    for s in (-1, 1):
        p.circle(8 + s * 4, -80, 4, (130, 86, 50))


@prop("bush", 0.1, box=(-60, -104, 60, 4))
def _bush(p: Pen, c):
    col = _c(c, LEAF)
    for x, r in ((-26, 30), (0, 40), (26, 30)):
        p.circle(x, -r * 0.9, r, col)
    p.rect(-52, -10, 52, 2, shade(col, 0.85), r=4)


@prop("flower", 0.07)
def _flower(p: Pen, c):
    p.line([(0, 0), (0, -60)], 4, LEAF_D)
    p.ellipse(10, -30, 10, 4, LEAF)
    col = _c(c, (240, 100, 150))
    for i in range(6):
        a = math.radians(i * 60)
        p.circle(math.cos(a) * 14, -72 + math.sin(a) * 14, 11, col)
    p.circle(0, -72, 9, (250, 210, 60))


@prop("rock", 0.08)
def _rock(p: Pen, c):
    col = _c(c, STONE)
    p.poly(bez((-50, 0), (-46, -70), (30, -80), (50, 0), 16), col)
    p.poly(bez((10, -4), (30, -50), (46, -40), (48, 0), 10), shade(col, 0.85))


@prop("cactus", 0.2)
def _cactus(p: Pen, c):
    col = _c(c, (80, 160, 90))
    p.capsule(0, 0, 0, -88, 12, col)
    p.line([(-12, -40), (-26, -40), (-26, -64)], 9, col)
    p.line([(12, -54), (24, -54), (24, -74)], 9, col)


@prop("mushroom", 0.07)
def _mush(p: Pen, c):
    p.rect(-12, -40, 12, 0, (250, 240, 220), r=6)
    col = _c(c, RED)
    p.chord(0, -40, 40, 40, 180, 360, col)
    for x, y in ((-18, -56), (8, -66), (22, -48)):
        p.circle(x, y, 6, (250, 250, 250))


@prop("grass", 0.05)
def _grass(p: Pen, c):
    col = _c(c, LEAF)
    for i in range(7):
        x = -36 + i * 12
        p.poly([(x - 5, 0), (x + (4 if i % 2 else -4), -60 - (i % 3) * 14), (x + 5, 0)], col)


@prop("dead_tree", 0.32)
def _dead(p: Pen, c):
    col = _c(c, (90, 70, 66))
    p.poly([(-8, 0), (-5, -60), (5, -60), (8, 0)], col)
    p.line([(0, -58), (-22, -86), (-30, -90)], 5, col)
    p.line([(0, -58), (18, -84)], 5, col)
    p.line([(-12, -72), (-2, -96)], 4, col)


@prop("mountain", 0.3, box=(-70, -104, 70, 4), big=True)
def _mountain(p: Pen, c):
    col = _c(c, (120, 130, 170))
    p.poly([(-68, 0), (-6, -96), (68, 0)], col)
    p.poly([(-6, -96), (68, 0), (20, 0)], shade(col, 0.85))
    p.poly([(-6, -96), (-24, -68), (-14, -72), (-6, -64), (4, -74), (12, -70)], (250, 250, 250))


@prop("volcano", 0.32, box=(-70, -104, 70, 4), big=True)
def _volcano(p: Pen, c):
    p.poly([(-66, 0), (-16, -78), (16, -78), (66, 0)], _c(c, (120, 90, 80)))
    p.poly([(-16, -78), (-6, -60), (4, -70), (16, -78)], (250, 120, 40))
    for x, y, r in ((-6, -90, 10), (6, -98, 8), (0, -104, 6)):
        p.circle(x, y, r, (150, 140, 140))


@prop("cloud", 0.1, anchor="center", sky=True)
def _cloud(p: Pen, c):
    col = _c(c, (250, 250, 252))
    for x, y, r in ((-28, 6, 20), (0, -6, 28), (28, 4, 22)):
        p.circle(x, y, r, col)
    p.rect(-48, 6, 48, 24, col, r=12)


@prop("sun", 0.16, anchor="center", sky=True)
def _sun(p: Pen, c):
    col = _c(c, (255, 206, 70))
    for i in range(12):
        a = math.radians(i * 30)
        p.poly([(math.cos(a - 0.12) * 38, math.sin(a - 0.12) * 38), (math.cos(a) * 54, math.sin(a) * 54),
                (math.cos(a + 0.12) * 38, math.sin(a + 0.12) * 38)], shade(col, 1.05))  # fmt: skip
    p.circle(0, 0, 36, col)


@prop("moon", 0.14, anchor="center", sky=True)
def _moon(p: Pen, c):
    col = _c(c, (250, 240, 200))
    p.circle(0, 0, 44, col)
    for x, y, r in ((-14, -10, 8), (12, 12, 6), (16, -16, 4)):
        p.circle(x, y, r, shade(col, 0.9))


@prop("star", 0.08, anchor="center", sky=True)
def _star(p: Pen, c):
    p.star(0, 4, 50, 22, _c(c, (255, 210, 60)))
    p.soft(lambda q: q.star(-6, -2, 16, 7, (255, 255, 255, 90)))


@prop("rainbow", 0.2, anchor="center", sky=True, box=(-70, -60, 70, 30))
def _rainbow(p: Pen, c):
    cols = [(231, 76, 60), (243, 156, 18), (241, 196, 15), (46, 174, 96), (52, 120, 219), (155, 89, 182)]
    for i, col in enumerate(cols):
        p.arc(0, 20, 64 - i * 7, 64 - i * 7, 180, 360, 7.2, col)


# ------------------------------------------------------------------ construções
@prop("house", 0.26, box=(-70, -104, 70, 4), big=True)
def _house(p: Pen, c):
    wall = _c(c, WALL)
    p.rect(-50, -60, 50, 0, wall)
    p.poly([(-62, -56), (0, -100), (62, -56)], ROOF)
    p.poly([(-62, -56), (62, -56), (58, -50), (-58, -50)], shade(ROOF, 0.8))
    p.rect(-14, -40, 10, 0, (150, 96, 60), r=2)
    p.circle(5, -18, 1.6, GOLD)
    for x in (-40, 22):
        p.rect(x, -44, x + 18, -26, GLASS, r=1)
        p.line([(x + 9, -44), (x + 9, -26)], 1.4, (250, 250, 250))
        p.line([(x, -35), (x + 18, -35)], 1.4, (250, 250, 250))
    p.rect(-50, -4, 50, 0, shade(wall, 0.85))


@prop("building", 0.42, box=(-50, -104, 50, 4), big=True)
def _building(p: Pen, c):
    col = _c(c, (120, 150, 190))
    p.rect(-38, -100, 38, 0, col)
    p.rect(20, -100, 38, 0, shade(col, 0.88))
    for r in range(8):
        for q in range(3):
            p.rect(
                -30 + q * 18,
                -92 + r * 11,
                -20 + q * 18,
                -85 + r * 11,
                (250, 236, 170) if (r + q) % 3 == 0 else GLASS,
            )
    p.rect(-10, -12, 10, 0, shade(col, 0.6))


@prop("church", 0.36, box=(-60, -104, 60, 4), big=True)
def _church(p: Pen, c):
    wall = _c(c, (250, 246, 236))
    p.rect(-40, -50, 40, 0, wall)
    p.poly([(-46, -48), (0, -74), (46, -48)], (200, 80, 70))
    p.rect(-10, -86, 10, -50, wall)
    p.poly([(-13, -84), (0, -98), (13, -84)], (200, 80, 70))
    p.line([(0, -104), (0, -96)], 2, GOLD)
    p.line([(-3, -101), (3, -101)], 2, GOLD)
    p.chord(0, -16, 9, 12, 180, 360, (150, 96, 60))
    p.rect(-9, -16, 9, 0, (150, 96, 60))
    for x in (-28, 20):
        p.chord(x + 4, -34, 4.5, 6, 180, 360, GLASS)
        p.rect(x - 0.5, -34, x + 8.5, -24, GLASS)


@prop("castle", 0.42, box=(-60, -104, 60, 4), big=True)
def _castle(p: Pen, c):
    col = _c(c, (190, 190, 205))
    p.rect(-36, -60, 36, 0, col)
    for x in (-50, 34):
        p.rect(x, -84, x + 16, 0, shade(col, 0.95))
        p.poly([(x - 3, -84), (x + 8, -104), (x + 19, -84)], (90, 110, 200))
    for i in range(6):
        p.rect(-36 + i * 13, -66, -30 + i * 13, -60, col)
    p.chord(0, -18, 11, 14, 180, 360, (110, 80, 60))
    p.rect(-11, -18, 11, 0, (110, 80, 60))


@prop("tower", 0.4, box=(-40, -104, 40, 4), big=True)
def _tower(p: Pen, c):
    col = _c(c, STONE)
    p.poly([(-20, 0), (-16, -86), (16, -86), (20, 0)], col)
    for i in range(4):
        p.rect(-20 + i * 11, -94, -14 + i * 11, -86, col)
    p.rect(-5, -60, 5, -48, (60, 60, 70), r=4)


@prop("pyramid", 0.3, box=(-70, -104, 70, 4), big=True)
def _pyramid(p: Pen, c):
    col = _c(c, (226, 190, 120))
    p.poly([(-66, 0), (0, -96), (66, 0)], col)
    p.poly([(0, -96), (66, 0), (16, 0)], shade(col, 0.85))
    for i in range(1, 6):
        y = -i * 16
        x = 66 * (1 + y / 96)
        p.line([(-x, y), (x * 0.25, y)], 1, shade(col, 0.88))


@prop("temple", 0.32, box=(-64, -104, 64, 4), big=True)
def _temple(p: Pen, c):
    col = _c(c, (246, 240, 226))
    p.rect(-56, -8, 56, 0, shade(col, 0.9))
    p.rect(-52, -14, 52, -8, col)
    for i in range(5):
        x = -42 + i * 21
        p.rect(x - 5, -72, x + 5, -14, col)
        p.line([(x - 2, -70), (x - 2, -16)], 1, shade(col, 0.88))
    p.rect(-54, -80, 54, -72, col)
    p.poly([(-56, -80), (0, -100), (56, -80)], shade(col, 0.95))


@prop("tent", 0.2, box=(-60, -104, 60, 4))
def _tent(p: Pen, c):
    col = _c(c, (230, 190, 120))
    p.poly([(-56, 0), (0, -90), (56, 0)], col)
    p.poly([(0, -90), (56, 0), (20, 0)], shade(col, 0.88))
    p.poly([(-12, 0), (0, -40), (12, 0)], shade(col, 0.6))


@prop("hut", 0.22, box=(-60, -104, 60, 4))
def _hut(p: Pen, c):
    p.rect(-40, -50, 40, 0, (190, 140, 90))
    p.poly([(-54, -46), (0, -96), (54, -46)], _c(c, (226, 190, 110)))
    p.rect(-10, -30, 10, 0, (110, 70, 40), r=2)


@prop("barn", 0.28, box=(-64, -104, 64, 4), big=True)
def _barn(p: Pen, c):
    col = _c(c, (196, 60, 50))
    p.rect(-46, -56, 46, 0, col)
    p.poly([(-54, -54), (-30, -86), (30, -86), (54, -54)], shade(col, 0.8))
    p.rect(-16, -36, 16, 0, (250, 250, 250))
    p.line([(-16, -36), (16, 0)], 2.4, col)
    p.line([(16, -36), (-16, 0)], 2.4, col)


@prop("statue", 0.36, box=(-40, -104, 40, 4), big=True)
def _statue(p: Pen, c):
    g = _c(c, (226, 170, 60))
    p.rect(-26, -12, 26, 0, shade(g, 0.8))
    p.rect(-20, -20, 20, -12, shade(g, 0.9))
    p.poly([(-16, -20), (-18, -60), (18, -60), (16, -20)], g)
    p.poly([(-18, -60), (-24, -56), (-22, -30), (-16, -30)], shade(g, 0.9))
    p.poly([(18, -60), (24, -56), (22, -30), (16, -30)], shade(g, 0.9))
    p.circle(0, -72, 14, g)
    p.rect(-12, -96, 12, -84, shade(g, 1.1), r=2)
    p.line([(-7, -74), (-3, -73)], 1.6, shade(g, 0.6))
    p.line([(7, -74), (3, -73)], 1.6, shade(g, 0.6))
    p.line([(-8, -78), (-2, -76)], 1.4, shade(g, 0.55))
    p.line([(8, -78), (2, -76)], 1.4, shade(g, 0.55))
    p.arc(0, -64, 4, 2, 200, 340, 1.2, shade(g, 0.6))
    p.soft(lambda q: q.poly([(-10, -58), (-6, -58), (-8, -24), (-12, -24)], (255, 255, 255, 60)))


@prop("throne", 0.24, box=(-50, -104, 50, 4))
def _throne(p: Pen, c):
    col = _c(c, (196, 50, 60))
    p.rect(-30, -96, 30, -40, GOLD, r=10)
    p.rect(-22, -88, 22, -42, col, r=8)
    p.rect(-36, -44, 36, -30, GOLD, r=4)
    p.rect(-30, -34, 30, -26, col, r=3)
    for x in (-30, 26):
        p.rect(x, -30, x + 4, 0, shade(GOLD, 0.85))


@prop("furnace", 0.3, box=(-60, -104, 60, 4), big=True)
def _furnace(p: Pen, c):
    col = _c(c, (186, 96, 70))
    p.chord(0, -40, 50, 56, 180, 360, col)
    p.rect(-50, -40, 50, 0, col)
    for r in range(6):
        for q in range(7):
            x = -46 + q * 14 + (7 if r % 2 else 0)
            y = -8 - r * 12
            if abs(x) < 50:
                p.rect(x - 6, y - 5, x + 6, y + 5, shade(col, 0.9 + 0.08 * ((r + q) % 2)), r=1)
    p.chord(0, -18, 26, 34, 180, 360, (60, 30, 30))
    p.rect(-26, -18, 26, 0, (60, 30, 30))
    for x, h, col2 in ((-12, 34, (250, 120, 40)), (8, 40, (250, 150, 40)), (0, 26, (255, 220, 90))):
        p.poly(bez((x - 12, 0), (x - 10, -h * 0.6), (x, -h), (x + 12, 0), 12), col2)


@prop("well", 0.18, box=(-50, -104, 50, 4))
def _well(p: Pen, c):
    p.rect(-34, -36, 34, 0, _c(c, STONE), r=4)
    p.rect(-38, -42, 38, -34, shade(STONE, 0.9), r=3)
    for x in (-30, 26):
        p.rect(x, -90, x + 4, -40, WOOD)
    p.poly([(-40, -86), (0, -104), (40, -86)], ROOF)


@prop("manger", 0.12, box=(-60, -104, 60, 4))
def _manger(p: Pen, c):
    for x in (-40, 30):
        p.line([(x, 0), (x + 10, -50)], 4, WOOD_D)
        p.line([(x + 10, 0), (x, -50)], 4, WOOD_D)
    p.poly([(-50, -50), (50, -50), (40, -24), (-40, -24)], WOOD)
    for i in range(10):
        p.line([(-40 + i * 9, -50), (-36 + i * 9, -60)], 2, (236, 200, 100))
    p.ellipse(4, -60, 26, 14, (250, 246, 236))
    p.circle(-16, -64, 11, (246, 205, 170))
    p.arc(-18, -64, 3, 2, 20, 160, 1, (60, 40, 40))
    p.arc(-12, -64, 3, 2, 20, 160, 1, (60, 40, 40))


@prop("stable", 0.32, box=(-64, -104, 64, 4), big=True)
def _stable(p: Pen, c):
    col = _c(c, WOOD)
    for x in (-50, 44):
        p.rect(x, -70, x + 6, 0, shade(col, 0.85))
    p.poly([(-62, -66), (0, -96), (62, -66), (58, -60), (0, -88), (-58, -60)], col)
    p.rect(-50, -66, 50, -60, shade(col, 0.8))
    p.rect(-44, -60, 44, 0, (80, 52, 34))


@prop("column", 0.32, box=(-30, -104, 30, 4), big=True)
def _column(p: Pen, c):
    col = _c(c, (240, 234, 220))
    p.rect(-18, -8, 18, 0, shade(col, 0.9))
    p.rect(-12, -92, 12, -8, col)
    for x in (-6, 0, 6):
        p.line([(x, -90), (x, -10)], 1.2, shade(col, 0.88))
    p.rect(-18, -100, 18, -92, shade(col, 0.9))


@prop("fence", 0.1, box=(-70, -104, 70, 4))
def _fence(p: Pen, c):
    col = _c(c, (250, 250, 248))
    for i in range(6):
        x = -60 + i * 24
        p.poly([(x - 6, 0), (x - 6, -80), (x, -92), (x + 6, -80), (x + 6, 0)], col)
    for y in (-60, -24):
        p.rect(-66, y - 5, 66, y + 5, shade(col, 0.9))


@prop("lamp_post", 0.3, box=(-30, -104, 30, 4))
def _lamp(p: Pen, c):
    p.rect(-3, -90, 3, 0, (60, 64, 76))
    p.rect(-12, -100, 12, -88, _c(c, (250, 230, 140)), r=3)
    p.rect(-14, -102, 14, -98, (60, 64, 76), r=2)


@prop("tombstone", 0.1)
def _tomb(p: Pen, c):
    col = _c(c, (150, 150, 162))
    p.chord(0, -60, 34, 30, 180, 360, col)
    p.rect(-34, -60, 34, 0, col)
    p.line([(0, -76), (0, -36)], 5, shade(col, 0.75))
    p.line([(-12, -62), (12, -62)], 5, shade(col, 0.75))


@prop("cross", 0.24, box=(-40, -104, 40, 4))
def _cross(p: Pen, c):
    col = _c(c, WOOD)
    p.rect(-6, -100, 6, 0, col)
    p.rect(-30, -78, 30, -66, col)
    p.rect(-6, -100, -1, 0, shade(col, 1.1))


@prop("sign", 0.16, box=(-60, -104, 60, 4))
def _sign(p: Pen, c):
    p.rect(-4, -70, 4, 0, WOOD_D)
    p.poly([(-50, -98), (40, -98), (54, -84), (40, -70), (-50, -70)], _c(c, WOOD))


@prop("door", 0.24, box=(-40, -104, 40, 4))
def _door(p: Pen, c):
    col = _c(c, (150, 96, 60))
    p.rect(-30, -100, 30, 0, shade(col, 0.8), r=2)
    p.rect(-26, -96, 26, 0, col, r=2)
    p.rect(-20, -88, 20, -56, shade(col, 0.9), r=2)
    p.rect(-20, -48, 20, -10, shade(col, 0.9), r=2)
    p.circle(18, -50, 3, GOLD)


# ------------------------------------------------------------------ casa e objetos
@prop("table", 0.12, box=(-64, -104, 64, 4))
def _table(p: Pen, c):
    col = _c(c, WOOD)
    p.rect(-60, -70, 60, -58, col, r=3)
    for x in (-52, 44):
        p.rect(x, -58, x + 8, 0, shade(col, 0.85))


@prop("chair", 0.14, box=(-40, -104, 40, 4))
def _chair(p: Pen, c):
    col = _c(c, WOOD)
    p.rect(-24, -100, 24, -50, col, r=6)
    p.rect(-28, -54, 28, -44, shade(col, 0.9), r=3)
    for x in (-26, 20):
        p.rect(x, -44, x + 6, 0, shade(col, 0.8))


@prop("bed", 0.14, box=(-70, -104, 70, 4))
def _bed(p: Pen, c):
    col = _c(c, (90, 140, 220))
    p.rect(-64, -96, -52, 0, WOOD)
    p.rect(52, -64, 64, 0, WOOD)
    p.rect(-56, -50, 56, -24, (250, 250, 250), r=4)
    p.rect(-30, -56, 58, -22, col, r=6)
    p.rect(-52, -64, -26, -48, (250, 250, 250), r=6)
    p.rect(-60, -24, 60, -14, WOOD_D)


@prop("sofa", 0.14, box=(-70, -104, 70, 4))
def _sofa(p: Pen, c):
    col = _c(c, (200, 80, 90))
    p.rect(-60, -80, 60, -40, shade(col, 0.88), r=10)
    p.rect(-66, -54, -48, -12, col, r=8)
    p.rect(48, -54, 66, -12, col, r=8)
    p.rect(-50, -46, 50, -16, col, r=6)
    for x in (-56, 50):
        p.rect(x, -12, x + 6, 0, WOOD_D)


@prop("tv", 0.16, box=(-64, -104, 64, 4))
def _tv(p: Pen, c):
    p.rect(-60, -100, 60, -28, (40, 40, 50), r=6)
    p.rect(-54, -94, 54, -34, _c(c, (90, 160, 220)), r=3)
    p.rect(-48, -92, -28, -86, RED, r=1)
    p.rect(-6, -28, 6, -10, (60, 60, 70))
    p.rect(-26, -10, 26, -4, (60, 60, 70), r=2)


@prop("computer", 0.12, box=(-60, -104, 60, 4))
def _computer(p: Pen, c):
    p.rect(-50, -100, 50, -36, (50, 54, 66), r=5)
    p.rect(-44, -94, 44, -42, _c(c, (110, 180, 240)), r=2)
    p.rect(-6, -36, 6, -14, (70, 74, 86))
    p.rect(-24, -14, 24, -8, (70, 74, 86), r=2)


@prop("laptop", 0.1, box=(-60, -104, 60, 4))
def _laptop(p: Pen, c):
    p.rect(-44, -90, 44, -24, (60, 64, 76), r=4)
    p.rect(-38, -84, 38, -30, _c(c, (110, 180, 240)), r=2)
    p.poly([(-54, -20), (54, -20), (60, 0), (-60, 0)], (150, 156, 170))


@prop("car", 0.11, box=(-70, -104, 70, 4))
def _car(p: Pen, c, police=False, taxi=False):
    col = _c(c, (52, 120, 219)) if not police else (40, 44, 56)
    if taxi:
        col = (250, 200, 40)
    p.poly(bez((-64, -20), (-60, -52), (60, -52), (66, -20), 12), col)
    p.poly([(-40, -50), (-28, -84), (28, -84), (44, -50)], col)
    p.poly([(-34, -52), (-24, -78), (-2, -78), (-2, -52)], GLASS)
    p.poly([(4, -52), (4, -78), (24, -78), (36, -52)], GLASS)
    if police:
        p.rect(-64, -40, 66, -26, (250, 250, 250))
        p.rect(-12, -94, 0, -84, RED, r=2)
        p.rect(0, -94, 12, -84, (52, 120, 219), r=2)
    for x in (-38, 38):
        p.circle(x, -14, 14, (40, 40, 48))
        p.circle(x, -14, 6, (180, 180, 190))
    p.rect(56, -36, 66, -28, (250, 230, 120), r=2)


@prop("police_car", 0.11, box=(-70, -104, 70, 4))
def _police(p: Pen, c):
    _car(p, c, police=True)


@prop("taxi", 0.11, box=(-70, -104, 70, 4))
def _taxi(p: Pen, c):
    _car(p, c, taxi=True)


@prop("bus", 0.15, box=(-70, -104, 70, 4))
def _bus(p: Pen, c):
    col = _c(c, (250, 190, 40))
    p.rect(-66, -96, 66, -16, col, r=8)
    for i in range(5):
        p.rect(-58 + i * 24, -86, -40 + i * 24, -60, GLASS, r=2)
    p.rect(-66, -50, 66, -44, shade(col, 0.8))
    for x in (-40, 40):
        p.circle(x, -14, 13, (40, 40, 48))
        p.circle(x, -14, 5, (180, 180, 190))


@prop("truck", 0.14, box=(-70, -104, 70, 4))
def _truck(p: Pen, c):
    p.rect(-66, -96, 20, -18, _c(c, (230, 230, 236)), r=4)
    p.rect(22, -70, 66, -18, RED, r=6)
    p.rect(30, -64, 56, -46, GLASS, r=2)
    for x in (-44, -20, 44):
        p.circle(x, -14, 12, (40, 40, 48))


@prop("boat", 0.12, box=(-70, -104, 70, 4))
def _boat(p: Pen, c):
    p.poly([(-64, -40), (64, -40), (44, 0), (-44, 0)], _c(c, (200, 70, 60)))
    p.rect(-64, -46, 64, -40, (250, 250, 250))
    p.line([(0, -40), (0, -100)], 3, WOOD_D)
    p.poly([(4, -96), (48, -48), (4, -48)], (250, 250, 250))


@prop("ship", 0.24, box=(-70, -104, 70, 4), big=True)
def _ship(p: Pen, c):
    p.poly([(-66, -40), (66, -40), (52, 0), (-50, 0)], _c(c, (60, 60, 72)))
    p.rect(-66, -40, 66, -32, RED)
    p.rect(-40, -64, 40, -40, (250, 250, 250))
    for i in range(6):
        p.circle(-30 + i * 12, -52, 3.4, GLASS)
    for x in (-14, 14):
        p.rect(x - 7, -92, x + 7, -64, (240, 150, 40))
        p.rect(x - 7, -92, x + 7, -84, (40, 40, 48))


@prop("chest", 0.1, box=(-60, -104, 60, 4))
def _chest(p: Pen, c):
    col = _c(c, (150, 96, 56))
    p.rect(-50, -54, 50, 0, col, r=4)
    p.chord(0, -54, 50, 30, 180, 360, shade(col, 1.08))
    for x in (-40, 34):
        p.rect(x, -80, x + 6, 0, GOLD)
    p.rect(-8, -62, 8, -44, GOLD, r=2)
    for x, y in ((-20, -84), (10, -88), (26, -80)):
        p.circle(x, y, 8, (255, 210, 60))


@prop("treasure", 0.1, box=(-60, -104, 60, 4))
def _treasure(p: Pen, c):
    _chest(p, c)


@prop("box", 0.1, box=(-60, -104, 60, 4))
def _box(p: Pen, c):
    col = _c(c, (206, 160, 100))
    p.rect(-46, -80, 46, 0, col, r=2)
    p.rect(-46, -80, 46, -64, shade(col, 1.08))
    p.rect(-6, -80, 6, 0, shade(col, 0.85))


@prop("gift", 0.09, box=(-60, -104, 60, 4))
def _gift(p: Pen, c):
    col = _c(c, (231, 76, 60))
    p.rect(-40, -70, 40, 0, col, r=3)
    p.rect(-46, -80, 46, -64, shade(col, 1.1), r=3)
    p.rect(-6, -80, 6, 0, GOLD)
    for s in (-1, 1):
        p.ellipse(s * 14, -88, 14, 9, GOLD)


@prop("candle", 0.08, box=(-30, -104, 30, 4))
def _candle(p: Pen, c):
    p.rect(-10, -70, 10, 0, _c(c, (250, 246, 230)), r=3)
    p.poly(bez((0, -100), (12, -82), (0, -70), (-12, -82), 12), (255, 170, 40))
    p.poly(bez((0, -90), (6, -80), (0, -72), (-6, -80), 10), (255, 236, 120))


@prop("advent_wreath", 0.11, box=(-70, -104, 70, 4))
def _wreath(p: Pen, c):
    p.ellipse(0, -22, 64, 18, (60, 140, 80))
    for i in range(14):
        a = math.radians(i * 360 / 14)
        p.circle(math.cos(a) * 56, -22 + math.sin(a) * 14, 9, (80, 170, 90) if i % 2 else (50, 120, 70))
    for x, col in ((-36, (140, 80, 190)), (-12, (140, 80, 190)), (12, (240, 140, 180)), (36, (140, 80, 190))):
        p.rect(x - 6, -70, x + 6, -24, col, r=2)
        p.poly(bez((x, -90), (x + 6, -78), (x, -70), (x - 6, -78), 10), (255, 180, 50))
    _ = c


@prop("campfire", 0.1, box=(-60, -104, 60, 4))
def _campfire(p: Pen, c):
    p.line([(-40, -6), (40, -18)], 9, WOOD_D)
    p.line([(-40, -18), (40, -6)], 9, WOOD)
    for x, h, col in ((-12, 70, (250, 120, 40)), (10, 84, (250, 150, 40)), (0, 50, (255, 220, 90))):
        p.poly(bez((x - 20, -10), (x - 18, -h * 0.6), (x, -h), (x + 20, -10), 12), col)


@prop("bench", 0.08, box=(-64, -104, 64, 4))
def _bench(p: Pen, c):
    col = _c(c, WOOD)
    for y in (-80, -60):
        p.rect(-60, y, 60, y + 10, col, r=2)
    p.rect(-60, -40, 60, -30, col, r=2)
    for x in (-50, 44):
        p.rect(x, -30, x + 6, 0, (60, 64, 76))


@prop("snowman", 0.18, box=(-50, -104, 50, 4))
def _snowman(p: Pen, c):
    p.circle(0, -26, 26, (250, 250, 252))
    p.circle(0, -64, 19, (250, 250, 252))
    p.poly([(0, -64), (16, -60), (0, -58)], (250, 140, 40))
    for s in (-1, 1):
        p.circle(s * 6, -70, 2.4, INKC)
    p.rect(-14, -100, 14, -82, _c(c, (40, 40, 48)))
    p.rect(-20, -84, 20, -80, _c(c, (40, 40, 48)))


@prop("rocket", 0.3, box=(-40, -104, 40, 4))
def _rocket(p: Pen, c):
    col = _c(c, (250, 250, 250))
    p.poly(bez((-16, -14), (-20, -60), (0, -100), n=12) + bez((0, -100), (20, -60), (16, -14), n=12), col)
    p.poly([(-16, -30), (-30, -6), (-14, -14)], RED)
    p.poly([(16, -30), (30, -6), (14, -14)], RED)
    p.circle(0, -60, 8, GLASS)
    p.circle(0, -60, 8, None, outline=(150, 156, 170), width=2)
    p.poly([(-10, -14), (10, -14), (0, 4)], (255, 170, 40))


@prop("airplane", 0.1, anchor="center", sky=True, box=(-64, -40, 64, 40))
def _plane(p: Pen, c):
    col = _c(c, (250, 250, 250))
    p.poly([(-56, 0), (40, -6), (56, 0), (40, 6)], col)
    p.poly([(-10, -2), (16, -2), (0, -34)], shade(col, 0.9))
    p.poly([(-10, 2), (16, 2), (0, 34)], shade(col, 0.9))
    p.poly([(-56, 0), (-46, -18), (-40, 0)], RED)
    for i in range(5):
        p.circle(-18 + i * 9, -1, 2, GLASS)


@prop("trophy", 0.12, box=(-50, -104, 50, 4))
def _trophy(p: Pen, c):
    g = _c(c, GOLD)
    p.rect(-24, -14, 24, 0, (110, 70, 40), r=2)
    p.rect(-6, -36, 6, -14, g)
    p.chord(0, -88, 30, 52, 0, 180, g)
    p.rect(-30, -96, 30, -88, g, r=2)
    for s in (-1, 1):
        p.arc(s * 30, -76, 10, 12, 270 if s > 0 else 90, 450 if s > 0 else 270, 4, g)
    p.star(0, -70, 10, 4, shade(g, 1.2))


@prop("globe", 0.16, box=(-50, -104, 50, 4))
def _globe(p: Pen, c):
    p.rect(-20, -8, 20, 0, WOOD_D, r=2)
    p.rect(-3, -20, 3, -8, WOOD_D)
    p.circle(0, -58, 38, (80, 160, 230))
    for x, y, r in ((-14, -70, 12), (10, -50, 14), (-6, -40, 8)):
        p.ellipse(x, y, r, r * 0.7, (90, 180, 90))
    p.arc(0, -58, 44, 44, 120, 300, 3, WOOD_D)


# ------------------------------------------------------------------ ícones (flutuam)
@prop("heart", 0.09, anchor="center")
def _heart(p: Pen, c):
    col = _c(c, (236, 64, 92))
    p.poly(
        bez((0, 46), (-60, 4), (-46, -46), (0, -24), 16) + bez((0, -24), (46, -46), (60, 4), (0, 46), 16), col
    )
    p.soft(lambda q: q.ellipse(-22, -18, 9, 6, (255, 255, 255, 110)))


@prop("broken_heart", 0.09, anchor="center")
def _bheart(p: Pen, c):
    _heart(p, c)
    p.line([(0, -24), (-8, -6), (6, 6), (-4, 20), (0, 44)], 4, (250, 250, 250))


@prop("coin", 0.07, anchor="center")
def _coin(p: Pen, c):
    col = _c(c, GOLD)
    p.circle(0, 0, 46, shade(col, 0.85))
    p.circle(-3, -3, 42, col)
    p.text(-3, -3, "$", 52, shade(col, 0.7))


@prop("money", 0.07, anchor="center", box=(-64, -40, 64, 40))
def _money(p: Pen, c):
    col = _c(c, (120, 196, 110))
    p.rect(-60, -34, 60, 34, shade(col, 0.85), r=4)
    p.rect(-54, -28, 54, 28, col, r=3)
    p.circle(0, 0, 18, shade(col, 0.85))
    p.text(0, -1, "$", 26, shade(col, 0.6))


@prop("money_bag", 0.1, anchor="center")
def _bag(p: Pen, c):
    col = _c(c, (206, 170, 110))
    p.poly(
        bez((-16, -30), (-56, 0), (-50, 48), (0, 48), 14) + bez((0, 48), (50, 48), (56, 0), (16, -30), 14),
        col,
    )
    p.poly([(-14, -30), (-22, -48), (22, -48), (14, -30)], shade(col, 0.9))
    p.rect(-18, -34, 18, -26, shade(col, 0.7), r=2)
    p.text(0, 12, "$", 40, shade(col, 0.6))


@prop("gem", 0.08, anchor="center")
def _gem(p: Pen, c):
    col = _c(c, (90, 200, 240))
    p.poly([(-40, -16), (-22, -38), (22, -38), (40, -16), (0, 40)], col)
    p.poly([(-40, -16), (40, -16), (0, 40)], shade(col, 0.85))
    p.poly([(-22, -38), (0, -16), (22, -38)], shade(col, 1.15))


@prop("crown", 0.08, anchor="center")
def _crown(p: Pen, c):
    g = _c(c, GOLD)
    p.poly([(-46, 30), (-50, -26), (-24, 0), (0, -36), (24, 0), (50, -26), (46, 30)], g)
    p.rect(-46, 18, 46, 32, shade(g, 0.85), r=3)
    for x, col in ((-24, RED), (0, (52, 120, 219)), (24, (46, 174, 96))):
        p.circle(x, 25, 5, col)


@prop("ring", 0.08, anchor="center")
def _ring(p: Pen, c):
    p.circle(0, 12, 30, None, outline=_c(c, GOLD), width=9)
    p.poly([(-14, -18), (-8, -34), (8, -34), (14, -18), (0, -6)], (180, 230, 250))
    p.poly([(-8, -34), (0, -18), (8, -34)], (230, 250, 255))


@prop("ring_box", 0.12, anchor="center")
def _ringbox(p: Pen, c):
    col = _c(c, (196, 50, 70))
    p.rect(-40, 6, 40, 46, col, r=6)
    p.rect(-40, 0, 40, 12, shade(col, 0.8), r=4)
    p.circle(0, -14, 20, None, outline=GOLD, width=6)
    p.poly([(-10, -36), (-5, -48), (5, -48), (10, -36), (0, -28)], (190, 235, 250))


@prop("phone", 0.16, anchor="center", box=(-40, -64, 60, 64))
def _phone(p: Pen, c):
    p.rect(-30, -58, 30, 58, (34, 34, 44), r=10)
    p.rect(-25, -48, 25, 48, _c(c, (240, 244, 250)), r=4)
    p.rect(-25, -48, 25, -36, (70, 160, 90), r=4)
    for i, (w, side) in enumerate(((30, -1), (22, 1), (34, -1), (18, 1), (26, -1))):
        y = -28 + i * 14
        x0 = -21 if side < 0 else 21 - w
        p.rect(x0, y, x0 + w, y + 9, (230, 230, 236) if side < 0 else (120, 200, 120), r=4)
    p.circle(30, -56, 13, RED)
    p.text(30, -57, "99+", 10, (250, 250, 250))


@prop("book", 0.09, anchor="center")
def _book(p: Pen, c):
    col = _c(c, (52, 120, 219))
    p.rect(-40, -46, 40, 46, shade(col, 0.8), r=4)
    p.rect(-36, -46, 40, 40, col, r=4)
    p.rect(-30, -40, 34, -34, (250, 245, 230))
    p.rect(-20, -16, 24, 6, shade(col, 1.15), r=2)


@prop("bible", 0.09, anchor="center")
def _bible(p: Pen, c):
    col = _c(c, (120, 60, 40))
    p.rect(-38, -46, 38, 46, shade(col, 0.8), r=4)
    p.rect(-34, -46, 38, 40, col, r=4)
    p.rect(-2, -26, 6, 20, GOLD)
    p.rect(-14, -14, 18, -6, GOLD)


@prop("scroll", 0.1, anchor="center")
def _scroll(p: Pen, c):
    p.rect(-34, -40, 34, 40, _c(c, (246, 232, 196)))
    for y in (-44, 44):
        p.rect(-40, y - 6, 40, y + 6, (216, 190, 140), r=6)
    for i in range(5):
        p.line([(-24, -24 + i * 12), (24 - (i % 2) * 10, -24 + i * 12)], 2.2, (180, 150, 110))


@prop("tablets", 0.16, anchor="center", box=(-64, -60, 64, 60))
def _tablets(p: Pen, c):
    col = _c(c, STONE)
    for x in (-28, 28):
        p.chord(x, -24, 26, 26, 180, 360, col)
        p.rect(x - 26, -24, x + 26, 50, col)
        for i in range(5):
            p.line([(x - 16, -16 + i * 13), (x + 16, -16 + i * 13)], 2.2, shade(col, 0.75))


@prop("letter", 0.08, anchor="center", box=(-64, -44, 64, 44))
def _letter(p: Pen, c):
    col = _c(c, (250, 240, 230))
    p.rect(-56, -38, 56, 38, col, r=3)
    p.poly([(-56, -38), (0, 6), (56, -38)], shade(col, 0.92))
    p.circle(0, 4, 9, RED)


@prop("newspaper", 0.12, anchor="center")
def _news(p: Pen, c):
    p.rect(-40, -50, 40, 50, (246, 246, 240))
    p.rect(-32, -42, 32, -28, (60, 60, 70))
    p.rect(-32, -20, 0, 10, (180, 190, 200))
    for i in range(6):
        p.line([(6, -18 + i * 7), (32, -18 + i * 7)], 2, (150, 150, 160))
        p.line([(-32, 18 + i * 5), (32, 18 + i * 5)], 1.6, (170, 170, 176))


@prop("lightbulb", 0.1, anchor="center")
def _bulb(p: Pen, c):
    col = _c(c, (255, 220, 80))
    p.circle(0, -12, 34, col)
    p.poly([(-16, 14), (16, 14), (12, 30), (-12, 30)], col)
    p.rect(-14, 30, 14, 46, (150, 156, 170), r=3)
    p.soft(lambda q: q.circle(-12, -24, 10, (255, 255, 255, 140)))
    p.line([(-8, 10), (-6, -10), (0, 0), (6, -10), (8, 10)], 2, shade(col, 0.7))


@prop("question", 0.1, anchor="center")
def _question(p: Pen, c):
    p.text(0, 0, "?", 110, _c(c, (255, 210, 50)), stroke=6, stroke_fill=INKC)


@prop("exclamation", 0.1, anchor="center")
def _excl(p: Pen, c):
    p.text(0, 0, "!", 110, _c(c, (236, 64, 60)), stroke=6, stroke_fill=INKC)


@prop("check", 0.09, anchor="center")
def _check(p: Pen, c):
    col = _c(c, (52, 180, 90))
    p.circle(0, 0, 46, col)
    p.line([(-22, 2), (-6, 18), (24, -16)], 11, (250, 250, 250))


@prop("x_mark", 0.09, anchor="center")
def _xmark(p: Pen, c):
    col = _c(c, (226, 64, 60))
    p.line([(-36, -36), (36, 36)], 16, col)
    p.line([(36, -36), (-36, 36)], 16, col)


@prop("clock", 0.1, anchor="center")
def _clock(p: Pen, c):
    p.circle(0, 0, 46, _c(c, (236, 80, 70)))
    p.circle(0, 0, 38, (250, 250, 250))
    for i in range(12):
        a = math.radians(i * 30)
        p.circle(math.cos(a) * 31, math.sin(a) * 31, 2.4, INKC)
    p.line([(0, 0), (0, -24)], 4, INKC)
    p.line([(0, 0), (16, 6)], 4, INKC)


@prop("hourglass", 0.12, anchor="center")
def _hourglass(p: Pen, c):
    p.rect(-34, -50, 34, -42, WOOD, r=2)
    p.rect(-34, 42, 34, 50, WOOD, r=2)
    p.poly([(-26, -42), (26, -42), (4, 0), (26, 42), (-26, 42), (-4, 0)], (220, 236, 250))
    p.poly([(-16, -26), (16, -26), (0, -4)], _c(c, (236, 190, 100)))
    p.poly([(-20, 42), (20, 42), (0, 22)], _c(c, (236, 190, 100)))


@prop("calendar", 0.1, anchor="center")
def _calendar(p: Pen, c):
    p.rect(-40, -38, 40, 44, (250, 250, 250), r=5)
    p.rect(-40, -38, 40, -16, _c(c, RED), r=5)
    for r in range(3):
        for q in range(4):
            p.rect(-30 + q * 16, -6 + r * 15, -20 + q * 16, 3 + r * 15, (200, 200, 210), r=1)


@prop("magnifier", 0.1, anchor="center")
def _magn(p: Pen, c):
    p.line([(16, 16), (44, 44)], 12, WOOD_D)
    p.circle(-8, -8, 30, None, outline=_c(c, (90, 90, 100)), width=8)
    p.soft(lambda q: q.circle(-8, -8, 26, (190, 230, 255, 120)))


@prop("key", 0.08, anchor="center", box=(-64, -40, 64, 40))
def _key(p: Pen, c):
    g = _c(c, GOLD)
    p.circle(-34, 0, 20, None, outline=g, width=9)
    p.rect(-16, -5, 50, 5, g)
    p.rect(30, 5, 38, 18, g)
    p.rect(42, 5, 50, 14, g)


@prop("lock", 0.09, anchor="center")
def _lock(p: Pen, c):
    p.arc(0, -14, 22, 26, 180, 360, 8, (150, 156, 170))
    p.rect(-32, -14, 32, 40, _c(c, GOLD), r=6)
    p.circle(0, 8, 6, INKC)
    p.rect(-2.4, 8, 2.4, 22, INKC)


@prop("dna", 0.16, anchor="center", box=(-50, -64, 50, 64))
def _dna(p: Pen, c):
    a, b = _c(c, (236, 80, 110)), (70, 140, 230)
    for i in range(13):
        y = -56 + i * 9.3
        x = math.sin(i * 0.65) * 26
        p.line([(x, y), (-x, y)], 3, (200, 200, 210))
        p.circle(x, y, 6, a)
        p.circle(-x, y, 6, b)


@prop("atom", 0.12, anchor="center")
def _atom(p: Pen, c):
    col = _c(c, (70, 170, 230))
    for ang in (0, 60, 120):
        pts = []
        for i in range(41):
            t = math.radians(i * 9)
            x, y = math.cos(t) * 46, math.sin(t) * 16
            r = math.radians(ang)
            pts.append((x * math.cos(r) - y * math.sin(r), x * math.sin(r) + y * math.cos(r)))
        p.line(pts, 3, col)
    p.circle(0, 0, 10, (236, 80, 80))


@prop("flask", 0.12, anchor="center")
def _flask(p: Pen, c):
    p.rect(-10, -48, 10, -14, (220, 236, 250))
    p.poly([(-10, -16), (10, -16), (40, 40), (-40, 40)], (220, 236, 250))
    p.poly([(-24, 12), (24, 12), (40, 40), (-40, 40)], _c(c, (110, 210, 120)))
    for x, y, r in ((-6, 0, 4), (6, -8, 3), (0, -20, 2.4)):
        p.circle(x, y, r, _c(c, (110, 210, 120)))


@prop("pill", 0.07, anchor="center", box=(-64, -40, 64, 40))
def _pill(p: Pen, c):
    p.capsule(-30, 0, 0, 0, 22, _c(c, (236, 80, 80)))
    p.capsule(0, 0, 30, 0, 22, (250, 250, 250))


@prop("brain", 0.11, anchor="center")
def _brain(p: Pen, c):
    col = _c(c, (246, 160, 180))
    for x, y, r in ((-20, -12, 22), (6, -20, 24), (24, -2, 20), (-12, 14, 20), (12, 16, 20)):
        p.circle(x, y, r, col)
    for pts in (
        ((-30, -10), (-16, -4), (-20, 10)),
        ((4, -34), (8, -16), (0, 0)),
        ((22, -16), (30, 2), (18, 14)),
    ):
        p.line(list(pts), 3, shade(col, 0.8))


@prop("camera", 0.09, anchor="center")
def _camera(p: Pen, c):
    p.rect(-46, -26, 46, 34, _c(c, (60, 64, 76)), r=8)
    p.rect(-18, -38, 12, -26, (60, 64, 76), r=3)
    p.circle(0, 4, 20, (40, 40, 48))
    p.circle(0, 4, 12, (90, 150, 210))
    p.circle(32, -16, 4, RED)


@prop("microphone", 0.11, anchor="center")
def _mic(p: Pen, c):
    p.rect(-8, 6, 8, 46, (60, 64, 76), r=3)
    p.capsule(0, -30, 0, -6, 20, _c(c, (150, 156, 170)))
    p.arc(0, -4, 26, 20, 0, 180, 4, (60, 64, 76))


@prop("megaphone", 0.1, anchor="center", box=(-64, -50, 64, 50))
def _megaphone(p: Pen, c):
    p.poly([(-40, -14), (30, -40), (30, 40), (-40, 14)], _c(c, (236, 80, 70)))
    p.rect(-50, -16, -36, 16, (60, 64, 76), r=3)
    p.ellipse(30, 0, 8, 40, shade(_c(c, (236, 80, 70)), 0.8))


@prop("music_note", 0.08, anchor="center")
def _note(p: Pen, c):
    col = _c(c, INKC)
    p.ellipse(-16, 30, 16, 12, col)
    p.rect(-4, -40, 4, 30, col)
    p.poly([(-4, -40), (34, -28), (34, -12), (4, -24)], col)


@prop("medal", 0.1, anchor="center")
def _medal(p: Pen, c):
    p.poly([(-24, -50), (-6, -50), (6, -6), (-10, -6)], (52, 120, 219))
    p.poly([(24, -50), (6, -50), (-6, -6), (10, -6)], RED)
    p.circle(0, 18, 26, _c(c, GOLD))
    p.star(0, 18, 14, 6, shade(_c(c, GOLD), 1.2))


@prop("bomb", 0.1, anchor="center")
def _bomb(p: Pen, c):
    p.circle(-4, 8, 36, _c(c, (40, 40, 48)))
    p.rect(-4, -36, 14, -24, (90, 90, 100), r=2)
    p.line(bez((6, -36), (14, -50), (28, -44)), 3, WOOD)
    p.star(30, -46, 10, 4, (255, 190, 40))


@prop("fire", 0.14, anchor="center")
def _fire(p: Pen, c):
    for x, h, col in ((-14, 80, (240, 90, 40)), (12, 96, (250, 130, 40)), (0, 60, (255, 210, 80))):
        p.poly(bez((x - 30, 46), (x - 32, 46 - h * 0.6), (x, 46 - h), (x + 30, 46), 14), col)


@prop("lightning", 0.14, anchor="center")
def _lightning(p: Pen, c):
    p.poly([(10, -56), (-30, 8), (-4, 8), (-14, 56), (30, -12), (4, -12)], _c(c, (255, 214, 50)))


@prop("explosion", 0.16, anchor="center")
def _boom(p: Pen, c):
    p.star(0, 0, 56, 30, (255, 160, 40), n=12)
    p.star(0, 0, 40, 22, _c(c, (255, 220, 70)), n=12)


@prop("skull", 0.1, anchor="center")
def _skull(p: Pen, c):
    col = _c(c, (246, 244, 236))
    p.circle(0, -8, 38, col)
    p.rect(-20, 18, 20, 40, col, r=6)
    for s in (-1, 1):
        p.ellipse(s * 14, -6, 10, 12, INKC)
    p.poly([(0, 6), (-5, 16), (5, 16)], INKC)


@prop("pin", 0.08, anchor="center")
def _pin(p: Pen, c):
    col = _c(c, (236, 64, 60))
    p.poly(
        bez((0, 50), (-40, -6), (-30, -46), (0, -46), 14) + bez((0, -46), (30, -46), (40, -6), (0, 50), 14),
        col,
    )
    p.circle(0, -18, 12, (250, 250, 250))


@prop("target", 0.1, anchor="center")
def _target(p: Pen, c):
    for i, col in enumerate((RED, (250, 250, 250), RED, (250, 250, 250), RED)):
        p.circle(0, 0, 46 - i * 9, col)


@prop("gear", 0.1, anchor="center")
def _gear(p: Pen, c):
    col = _c(c, (150, 156, 170))
    p.star(0, 0, 48, 36, col, n=10, rot=0)
    p.circle(0, 0, 38, col)
    p.circle(0, 0, 14, (250, 250, 250))


@prop("shield", 0.12, anchor="center")
def _shield(p: Pen, c):
    col = _c(c, (52, 120, 219))
    p.poly(bez((-40, -44), (-40, 20), (0, 50), n=10) + bez((0, 50), (40, 20), (40, -44), n=10), col)
    p.poly([(-40, -44), (40, -44), (0, -36)], shade(col, 1.1))
    p.star(0, 0, 18, 8, GOLD)


@prop("sword", 0.16, anchor="center", box=(-40, -64, 40, 64))
def _sword(p: Pen, c):
    p.poly([(-5, 30), (5, 30), (5, -50), (0, -60), (-5, -50)], (220, 225, 235))
    p.rect(-18, 28, 18, 36, GOLD, r=2)
    p.rect(-4, 36, 4, 56, WOOD_D, r=2)


@prop("cup", 0.08, anchor="center")
def _cup(p: Pen, c):
    col = _c(c, GOLD)
    p.chord(0, -26, 30, 40, 0, 180, col)
    p.rect(-4, 10, 4, 30, col)
    p.rect(-20, 30, 20, 38, col, r=3)


@prop("bread", 0.08, anchor="center", box=(-64, -40, 64, 40))
def _bread(p: Pen, c):
    col = _c(c, (214, 150, 80))
    p.ellipse(0, 0, 56, 30, col)
    for x in (-24, 0, 24):
        p.line([(x - 6, -14), (x + 6, 6)], 3, shade(col, 0.8))


@prop("apple", 0.07, anchor="center")
def _apple(p: Pen, c):
    col = _c(c, (226, 54, 60))
    p.circle(-12, 6, 30, col)
    p.circle(12, 6, 30, col)
    p.line([(0, -24), (4, -42)], 4, WOOD_D)
    p.ellipse(16, -38, 12, 6, LEAF)


@prop("pizza", 0.08, anchor="center")
def _pizza(p: Pen, c):
    p.poly([(-40, -36), (40, -36), (0, 46)], (250, 210, 100))
    p.rect(-44, -46, 44, -32, (214, 150, 80), r=6)
    for x, y in ((-14, -18), (12, -12), (0, 12)):
        p.circle(x, y, 7, (220, 60, 60))


@prop("burger", 0.08, anchor="center")
def _burger(p: Pen, c):
    p.chord(0, -6, 44, 34, 180, 360, (214, 150, 80))
    p.rect(-46, -6, 46, 4, (90, 180, 80), r=3)
    p.rect(-44, 4, 44, 18, (120, 70, 40), r=5)
    p.rect(-44, 18, 44, 30, (214, 150, 80), r=6)


@prop("cake", 0.09, anchor="center")
def _cake(p: Pen, c):
    col = _c(c, (246, 170, 190))
    p.rect(-40, -10, 40, 40, col, r=4)
    p.rect(-40, -10, 40, 4, (250, 250, 250), r=4)
    for x in (-20, 0, 20):
        p.rect(x - 3, -34, x + 3, -10, (250, 246, 230))
        p.poly(bez((x, -48), (x + 5, -40), (x, -34), (x - 5, -40), 8), (255, 180, 50))


@prop("coffee", 0.08, anchor="center")
def _coffee(p: Pen, c):
    p.rect(-30, -20, 26, 40, _c(c, (250, 250, 250)), r=8)
    p.arc(26, 8, 12, 14, 270, 450, 6, _c(c, (250, 250, 250)))
    p.rect(-26, -20, 22, -10, (120, 70, 40))
    for x in (-12, 4):
        p.line(bez((x, -30), (x + 6, -40), (x - 2, -52)), 3, (200, 200, 210))


@prop("balloon", 0.12, anchor="center", box=(-40, -64, 40, 64))
def _balloon(p: Pen, c):
    p.line(bez((0, 26), (8, 40), (-4, 60)), 1.6, (90, 90, 90))
    p.ellipse(0, -14, 30, 38, _c(c, (236, 64, 92)))
    p.poly([(-5, 24), (5, 24), (0, 30)], _c(c, (236, 64, 92)))
    p.soft(lambda q: q.ellipse(-10, -26, 7, 11, (255, 255, 255, 110)))


@prop("ball", 0.07, anchor="center")
def _ball(p: Pen, c):
    p.circle(0, 0, 44, (250, 250, 250))
    p.poly([(0, -16), (15, -5), (9, 13), (-9, 13), (-15, -5)], INKC)
    for a in range(5):
        r = math.radians(-90 + a * 72)
        p.circle(math.cos(r) * 38, math.sin(r) * 38, 8, INKC)


@prop("earth", 0.2, anchor="center", sky=True)
def _earth(p: Pen, c):
    p.circle(0, 0, 50, (70, 150, 230))
    for x, y, rx, ry in ((-18, -20, 18, 12), (16, 4, 20, 16), (-20, 22, 12, 9), (24, -28, 8, 6)):
        p.ellipse(x, y, rx, ry, (90, 186, 96))
    p.soft(lambda q: q.circle(-16, -18, 22, (255, 255, 255, 50)))


@prop("planet", 0.16, anchor="center", sky=True, box=(-70, -60, 70, 60))
def _planet(p: Pen, c):
    col = _c(c, (236, 170, 90))
    p.circle(0, 0, 40, col)
    p.line([(-30, -14), (30, -18)], 6, shade(col, 0.88))
    p.line([(-36, 10), (34, 6)], 5, shade(col, 0.9))
    p.ellipse(0, 4, 66, 14, None, outline=shade(col, 1.15), width=5)


@prop("comet", 0.12, anchor="center", sky=True, box=(-70, -50, 70, 50))
def _comet(p: Pen, c):
    p.soft(lambda q: q.poly([(30, -10), (-66, -30), (-60, 0), (30, 12)], (255, 230, 160, 130)))
    p.circle(32, 0, 16, _c(c, (255, 236, 170)))


@prop("ufo", 0.12, anchor="center", sky=True, box=(-70, -50, 70, 50))
def _ufo(p: Pen, c):
    p.chord(0, -6, 26, 24, 180, 360, (170, 230, 250))
    p.ellipse(0, 4, 60, 16, _c(c, (150, 156, 170)))
    for i in range(5):
        p.circle(-36 + i * 18, 6, 4, (255, 220, 80))


@prop("eye", 0.08, anchor="center", box=(-64, -40, 64, 40))
def _eye(p: Pen, c):
    p.ellipse(0, 0, 56, 30, (250, 250, 250))
    p.circle(0, 0, 22, _c(c, (90, 150, 220)))
    p.circle(0, 0, 10, INKC)
    p.circle(6, -6, 4, (250, 250, 250))


@prop("thumbs_up", 0.1, anchor="center")
def _thumb(p: Pen, c):
    col = _c(c, (52, 120, 219))
    p.circle(0, 0, 46, col)
    p.rect(-20, -6, 20, 26, (250, 250, 250), r=6)
    p.rect(-6, -32, 8, -2, (250, 250, 250), r=5)


@prop("chat", 0.1, anchor="center", box=(-64, -50, 64, 50))
def _chat(p: Pen, c):
    col = _c(c, (250, 250, 250))
    p.rect(-56, -40, 56, 24, col, r=14)
    p.poly([(-30, 20), (-40, 44), (-12, 22)], col)
    for x in (-24, 0, 24):
        p.circle(x, -8, 6, (150, 156, 170))


@prop("arrow", 0.08, anchor="center", box=(-64, -40, 64, 40))
def _arrow(p: Pen, c):
    p.poly([(-56, -12), (16, -12), (16, -32), (56, 0), (16, 32), (16, 12), (-56, 12)], _c(c, RED))


PROP_NAMES = tuple(PROPS)
SKY_PROPS = {k for k, d in PROPS.items() if d.sky}
BIG_PROPS = {k for k, d in PROPS.items() if d.big}
GROUND_PROPS = {k for k, d in PROPS.items() if d.anchor == "ground"}
