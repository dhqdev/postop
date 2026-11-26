"""Cena 2D: monta cenário, personagens, objetos, efeitos e textos e desenha cada quadro.

Layout automático (protagonista no centro, dupla frente a frente, multidão em fileiras, objetos
grandes no fundo, ícones flutuando), câmera suave (zoom, pan, punch, tremida) e linha do tempo
de cada elemento pela duração natural das ações.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field, replace

import cv2
import numpy as np

from . import overlays as ov
from .anim import (
    ENTRANCES,
    Pose2D,
    back_out,
    bounce_out,
    build_segments,
    char_action,
    ease_in,
    ease_out,
    evaluate,
    rig_draws,
    smooth,
)
from .characters import CRITTERS, PALETTE, Look, Rig, body_for, build_rig, critter_height, make_look
from .draw import (
    Pen,
    Sprite,
    affine,
    blit,
    fill_alpha,
    pen_sprite,
    pil_sprite,
    sprite_matrix,
    star_pts,
    text_image,
)
from .places import FLOATING, GROUND, INDOOR, draw_place
from .props import BIG_PROPS, PROPS, SKY_PROPS, draw_prop

TAU = math.tau
PI = math.pi


@dataclass
class Element2D:
    kind: str = "char"  # char | prop
    type: str = "person"
    ref: str = ""  # id do elenco
    look: Look | None = None
    count: int = 1
    at: str = ""
    actions: list = field(default_factory=lambda: ["idle"])
    size: float = 1.0
    label: str = ""
    say: str = ""
    color: tuple | None = None
    facing: str = ""


@dataclass
class SceneSpec2D:
    place: str = "plain"
    time: str = "day"
    elements: list = field(default_factory=list)
    banner: str = ""
    card: str = ""
    tag: str = ""
    sticker: str = ""
    items: list = field(default_factory=list)
    items_title: str = ""
    number: str = ""
    chart: str = ""
    fx: str = ""
    camera: str = ""
    color: tuple | None = None  # cor do fundo liso
    banner_color: int = 0
    narration: str = ""
    keep: list = field(default_factory=list)  # ids que já estavam na cena anterior (sem "pop")


POS = {
    "center": (0.5, 0.0, 1.0), "left": (0.27, 0.0, 1.0), "right": (0.73, 0.0, 1.0),
    "far_left": (0.13, 0.0, 0.95), "far_right": (0.87, 0.0, 0.95),
    "back": (0.5, -0.045, 0.84), "back_left": (0.28, -0.045, 0.84), "back_right": (0.72, -0.045, 0.84),
    "front": (0.5, 0.055, 1.1), "front_left": (0.3, 0.055, 1.08), "front_right": (0.7, 0.055, 1.08),
    "sky": (0.5, -0.34, 1.0), "sky_left": (0.24, -0.33, 1.0), "sky_right": (0.76, -0.33, 1.0),
    "top": (0.5, -0.42, 1.0),
}  # fmt: skip
CHAR_H = 0.235  # altura de um adulto (fração da altura do quadro)
CAMERAS = ("zoom_in", "zoom_out", "pan_left", "pan_right", "static", "punch", "shake")
FX = ("confetti", "hearts", "notes", "stars", "sparkles", "money", "coins", "rain", "snow", "leaves", "bubbles",
      "embers", "smoke", "zzz", "question", "lightning", "rays", "spotlight", "flash", "fire")  # fmt: skip
VEHICLES = {"car", "police_car", "taxi", "bus", "truck", "boat", "ship", "airplane", "rocket", "ufo"}


# ------------------------------------------------------------------ ações de objetos
def p_idle(a, P, p, lt, dur, t):
    if a.floating:
        P.jump += a.h * 0.035 * math.sin(t * 2.0 + a.phase)
        P.rot += 0.03 * math.sin(t * 1.3 + a.phase)
    elif a.ptype in ("tree", "palm", "pine", "flower", "grass", "bush"):
        P.rot += 0.012 * math.sin(t * 1.2 + a.phase)


def p_pop(a, P, p, lt, dur, t):
    P.scale *= max(0.001, back_out(p))
    P.alpha = min(1.0, p * 3)
    p_idle(a, P, p, lt, dur, t)


def p_drop(a, P, p, lt, dur, t):
    P.jump += (a.base_y + a.h * 1.2) * (1 - bounce_out(p))
    P.alpha = 1.0


def p_fly_in(a, P, p, lt, dur, t):
    side = -1 if a.base_x < a.W / 2 else 1
    q = ease_out(p)
    P.x = side * (a.W * 0.6) * (1 - q)
    if a.ptype in VEHICLES:
        P.flip = side > 0
        P.jump += abs(math.sin(lt * 20)) * a.h * 0.01 * (1 - q)
    P.rot += 0.15 * side * (1 - q) if a.floating else 0.0


def p_fly_out(a, P, p, lt, dur, t):
    side = 1 if a.base_x >= a.W / 2 else -1
    P.x = side * (a.W * 0.6) * ease_in(p)
    if a.ptype in VEHICLES:
        P.flip = side < 0
    if p >= 1:
        P.hidden = True


def p_rise(a, P, p, lt, dur, t):
    if a.ptype == "rocket":
        P.jump += a.H * 0.9 * ease_in(p)
        P.fx.append("smoke")
        return
    P.jump -= a.H * 0.25 * (1 - ease_out(p))
    P.alpha = min(1.0, p * 2)


def p_float(a, P, p, lt, dur, t):
    P.jump += a.h * (0.08 + 0.05 * math.sin(t * 1.8 + a.phase))
    P.rot += 0.05 * math.sin(t * 1.1 + a.phase)


def p_spin(a, P, p, lt, dur, t):
    P.sx *= math.cos(TAU * smooth(p)) if not a.floating else 1.0
    if a.floating:
        P.rot += TAU * smooth(p)


def p_spin_loop(a, P, p, lt, dur, t):
    P.rot += lt * 1.4
    p_idle(a, P, p, lt, dur, t)


def p_shake(a, P, p, lt, dur, t):
    P.rot += 0.14 * math.sin(lt * 34) * (1 - 0.6 * p)


def p_pulse(a, P, p, lt, dur, t):
    P.sx *= 1 + 0.07 * math.sin(lt * 6.5)
    P.sy *= 1 + 0.07 * math.sin(lt * 6.5)
    p_idle(a, P, p, lt, dur, t)


def p_grow(a, P, p, lt, dur, t):
    P.scale *= 1 + 0.35 * back_out(p, 1.2)


def p_shrink(a, P, p, lt, dur, t):
    P.scale *= 1 - 0.4 * smooth(p)


def p_vanish(a, P, p, lt, dur, t):
    P.scale *= max(0.001, 1 - ease_in(p))
    if p >= 1:
        P.hidden = True


def p_glow(a, P, p, lt, dur, t):
    p_pulse(a, P, p, lt, dur, t)
    P.fx.append("rays")


def p_burn(a, P, p, lt, dur, t):
    p_idle(a, P, p, lt, dur, t)
    P.fx.append("fire")


def p_ring(a, P, p, lt, dur, t):
    P.rot += 0.12 * math.sin(lt * 42) * (1 if (lt % 0.7) < 0.45 else 0.2)
    P.fx.append("ring")


def p_bounce(a, P, p, lt, dur, t):
    q = (lt * 1.6) % 1.0
    P.jump += a.h * 0.3 * math.sin(PI * q)
    edge = min(q, 1 - q)
    P.sy *= 1 - 0.12 * max(0.0, 1 - edge / 0.12)


def p_slide(a, P, p, lt, dur, t):
    side = 1 if a.base_x <= a.W / 2 else -1
    P.x = side * a.W * 0.25 * smooth(p)
    if a.ptype in VEHICLES:
        P.flip = side < 0


def p_open(a, P, p, lt, dur, t):
    P.sy *= 1 - 0.12 * math.sin(PI * min(p * 1.4, 1.0))
    if p > 0.4:
        P.fx.append("sparkle")


def p_orbit(a, P, p, lt, dur, t):
    P.x += math.cos(lt * 1.5 + a.phase) * a.W * 0.12
    P.jump += math.sin(lt * 1.5 + a.phase) * a.h * 0.3


def p_sway(a, P, p, lt, dur, t):
    P.rot += 0.05 * math.sin(t * 1.5 + a.phase)


def p_blink(a, P, p, lt, dur, t):
    P.alpha = 0.45 + 0.55 * (math.sin(lt * 9) > 0)


def p_flip(a, P, p, lt, dur, t):
    P.sx *= math.cos(TAU * smooth(p))


PROP_ACTIONS = {
    "idle": p_idle, "pop": p_pop, "appear": p_pop, "drop": p_drop, "fly_in": p_fly_in, "fly_out": p_fly_out,
    "rise": p_rise, "float": p_float, "spin": p_spin, "spin_loop": p_spin_loop, "shake": p_shake,
    "pulse": p_pulse, "grow": p_grow, "shrink": p_shrink, "vanish": p_vanish, "glow": p_glow, "burn": p_burn,
    "ring": p_ring, "bounce": p_bounce, "slide": p_slide, "open": p_open, "orbit": p_orbit, "sway": p_sway,
    "blink": p_blink, "flip": p_flip,
}  # fmt: skip
PROP_ALIASES = {
    "walk": "slide", "run": "slide", "walk_in": "fly_in", "run_in": "fly_in", "walk_out": "fly_out",
    "run_out": "fly_out", "fly": "float", "jump": "bounce", "cheer": "bounce", "dance": "bounce",
    "scared": "shake", "angry": "shake", "surprised": "pop", "talk": "pulse", "wave": "sway", "point": "pulse",
    "think": "idle", "sad": "idle", "laugh": "bounce", "hold_up": "grow", "fall": "drop", "sleep": "idle",
    "kneel": "idle", "pray": "idle", "sit": "idle", "lie": "idle", "look": "idle", "clap": "bounce",
    "bow": "idle", "nod": "bounce", "shake_head": "shake", "shrug": "idle", "cry": "idle", "eat": "pulse",
    "hop": "bounce", "wag": "sway", "swim": "orbit",
}  # fmt: skip


def prop_action(name: str):
    return PROP_ACTIONS.get(name) or PROP_ACTIONS.get(PROP_ALIASES.get(name, ""), p_idle)


# ------------------------------------------------------------------ atores
class Actor2D:
    def __init__(self, el: Element2D, W: int, H: int, base_x: float, base_y: float, depth: float, h: float,
                 rig: Rig | None = None, sprite: Sprite | None = None, floating: bool = False, phase: float = 0.0):  # fmt: skip
        self.el = el
        self.W, self.H = W, H
        self.base_x, self.base_y = base_x, base_y
        self.depth = depth
        self.h = h
        self.rig = rig
        self.sprite = sprite
        self.floating = floating
        self.phase = phase
        self.cat = "prop" if rig is None else ("critter" if rig.critter else "person")
        self.ptype = el.type
        self.gaze = 0.0
        self.point_side = 1
        self.flip0 = False
        self.start = 0.0
        self.segs: list = []
        self.fns: list = []
        self.layer = 1
        self.label_spr: Sprite | None = None
        self.say_spr: Sprite | None = None
        self.say_t = (0.0, 0.0)
        self.main = False

    def schedule(self, actions: list[str], T: float, start: float, pop: bool) -> None:
        acts = [a for a in actions if a] or ["idle"]
        if pop and acts[0] not in ENTRANCES:
            acts = ["appear" if self.rig is not None else "pop", *acts]
        self.start = start
        self.segs = build_segments(acts, T, start)
        fn = char_action if self.rig is not None else prop_action
        self.fns = [fn(n) for n, _a, _b in self.segs]

    def pose(self, t: float) -> Pose2D:
        if t < self.start:
            return Pose2D(hidden=True)
        return evaluate(self, self.segs, self.fns, t)

    def draws(self, P: Pose2D, cam: np.ndarray):
        if self.rig is not None:
            return rig_draws(self.rig, P, self.base_x, self.base_y, cam, self.depth)
        if P.hidden or P.alpha <= 0.01 or self.sprite is None:
            return [], None
        sgn = -1.0 if P.flip else 1.0
        s = P.scale
        M = cam @ affine(self.base_x + P.x, self.base_y + P.y - P.jump, P.rot, sgn * s * P.sx, s * P.sy)
        top = (M @ np.array([0, -self.h * (1.0 if not self.floating else 0.5), 1.0]))[:2]
        return [(self.sprite, M, P.alpha)], top


# ------------------------------------------------------------------ partículas
class Particles:
    def __init__(self, sprites: list[Sprite], n: int, mode: str, W: int, H: int, seed: int, region=None,
                 emitter=None, speed: float = 1.0, size: float = 1.0, start: float = 0.0, life: float = 2.2):  # fmt: skip
        rng = np.random.default_rng(seed)
        self.sprites = sprites
        self.mode = mode
        self.W, self.H = W, H
        self.region = region or (0, 0, W, H)
        self.emitter = emitter
        self.start = start
        self.life = life
        self.speed = speed
        self.items = [
            dict(
                s=int(rng.integers(0, len(sprites))),
                x=float(rng.uniform(self.region[0], self.region[2])),
                y=float(rng.uniform(self.region[1], self.region[3])),
                ph=float(rng.uniform(0, 1)),
                v=float(rng.uniform(0.7, 1.3)) * speed,
                rs=float(rng.uniform(-2.5, 2.5)),
                sc=float(rng.uniform(0.7, 1.15)) * size,
                sw=float(rng.uniform(0.5, 1.5)),
                dx=float(rng.uniform(-1, 1)),
            )
            for _ in range(n)
        ]

    def draw(self, frame: np.ndarray, t: float, cam: np.ndarray) -> None:
        if t < self.start:
            return
        tt = t - self.start
        H, W = self.H, self.W
        for it in self.items:
            spr = self.sprites[it["s"]]
            a = 1.0
            if self.mode == "fall":
                span = H * 1.25
                y = (it["y"] + tt * it["v"] * H * 0.28) % span - H * 0.12
                x = it["x"] + math.sin(tt * it["sw"] * 2 + it["ph"] * TAU) * W * 0.03
                rot = tt * it["rs"] + it["ph"] * TAU
                sc = it["sc"]
            elif self.mode == "rise":
                ex, ey = self.emitter or (W / 2, H * 0.6)
                age = (tt / self.life + it["ph"]) % 1.0
                x = ex + it["dx"] * W * 0.09 * age + math.sin(age * 6 + it["ph"] * 9) * W * 0.015
                y = ey - age * H * 0.16 * it["v"]
                a = min(1.0, age * 5) * (1 - age) ** 0.8
                rot = math.sin(age * 4 + it["ph"]) * 0.3
                sc = it["sc"] * (0.6 + 0.5 * age)
            else:  # twinkle
                x, y = it["x"], it["y"]
                a = 0.35 + 0.65 * (0.5 + 0.5 * math.sin(tt * 3 * it["sw"] + it["ph"] * TAU))
                rot = tt * 0.3 * it["rs"]
                sc = it["sc"] * (0.8 + 0.25 * math.sin(tt * 2 + it["ph"] * TAU))
            M = cam @ affine(x, y, rot, sc, sc)
            blit(frame, spr, sprite_matrix(spr, M), a)


def _confetti_sprites(k: float) -> list[Sprite]:
    out = []
    for col in (
        (231, 76, 60),
        (52, 152, 219),
        (46, 204, 113),
        (241, 196, 15),
        (155, 89, 182),
        (230, 126, 34),
    ):
        p = Pen((-6, -4, 6, 4), k)
        p.rect(-5, -2.6, 5, 2.6, col, r=0.8)
        out.append(pen_sprite(p, (0, 0)))
    return out


def _sparkle_sprite(k: float, col=(255, 236, 140)) -> Sprite:
    p = Pen((-10, -10, 10, 10), k)
    p.poly(star_pts(0, 0, 9, 2.2, 4, -90), col)
    return pen_sprite(p, (0, 0))


def _dot_sprite(k: float, col, r: float = 3.0, ring: bool = False) -> Sprite:
    p = Pen((-r - 2, -r - 2, r + 2, r + 2), k)
    if ring:
        p.circle(0, 0, r, None, outline=col, width=r * 0.25)
        p.soft(lambda q: q.circle(-r * 0.35, -r * 0.35, r * 0.25, (255, 255, 255, 180)))
    else:
        p.circle(0, 0, r, col)
    return pen_sprite(p, (0, 0))


def _drop_sprite(k: float) -> Sprite:
    p = Pen((-2, -8, 2, 8), k)
    p.line([(0, -6), (0, 6)], 1.2, (170, 200, 240, 200))
    return pen_sprite(p, (0, 0))


def _text_sprite(txt: str, size: int, col) -> Sprite:
    return pil_sprite(text_image(txt, size, col, stroke=max(2, size // 10)))


def _rays_sprite(R: float, col=(255, 240, 170)) -> Sprite:
    p = Pen((-R, -R, R, R), 1.0, ss=1)
    n = 14
    for i in range(n):
        a0 = TAU * i / n
        a1 = a0 + TAU / n * 0.5
        p.soft(lambda q, a0=a0, a1=a1: q.poly([(0, 0), (math.cos(a0) * R, math.sin(a0) * R),
                                               (math.cos(a1) * R, math.sin(a1) * R)], (*col, 90)))  # fmt: skip
    return pen_sprite(p, (0, 0))


# ------------------------------------------------------------------ cena
class Scene2D:
    def __init__(self, spec: SceneSpec2D, seconds: float, style: str = "papel", seed: int = 0, index: int = 0,
                 W: int = 1080, H: int = 1920, words=None, caption_style: str = "highlight",
                 caption_color=(255, 216, 77)):  # fmt: skip
        self.spec = spec
        self.T = max(float(seconds), 0.5)
        self.W, self.H = W, H
        self.s = W / 1080
        self.style = style
        self.paper = 1.0 if style == "papel" else 0.0
        self.rng = np.random.default_rng(seed)
        self.index = index
        self.events: list[tuple[float, str, dict]] = []
        self.bg = draw_place(spec.place, spec.time, W, H, self.paper, seed, spec.color)
        self.gy = H * GROUND
        self.has_list = bool(spec.items) or bool(spec.chart)
        self.actors: list[Actor2D] = []
        self._build_actors()
        self._build_overlays()
        self._build_fx()
        self.captions = ov.Captions(words or [], W, caption_style, caption_color) if words else None
        self._camera_setup()
        self._shadow = self._shadow_sprite()
        self._fx_cache: dict = {}

    # -------------------------------------------------------------- elementos
    def _char_height(self, el: Element2D) -> float:
        base = CHAR_H * self.H * float(np.clip(el.size or 1.0, 0.4, 2.2))
        if el.type in CRITTERS:
            return base * critter_height(el.type) / 100.0
        age = el.look.age if el.look is not None else "adult"
        return base * body_for(age).height / 100.0

    def _build_actors(self) -> None:
        spec = self.spec
        W, H = self.W, self.H
        chars = [e for e in spec.elements if e.kind == "char"]
        props = [e for e in spec.elements if e.kind == "prop"]
        n_chars = len(chars)
        defaults = {1: ["center"], 2: ["left", "right"], 3: ["left", "center", "right"],
                    4: ["far_left", "left", "right", "far_right"]}.get(n_chars, ["far_left", "left", "center", "right", "far_right"])  # fmt: skip
        used = {e.at for e in spec.elements if e.at}
        auto = [p for p in defaults if p not in used] + [
            p for p in POS if p not in used and p not in defaults
        ]
        shrink = 0.82 if self.has_list or spec.number else 1.0
        if n_chars >= 4 or sum(e.count for e in chars) > 4:
            shrink *= 0.88
        k_auto = 0
        order = 0
        main_char: Actor2D | None = None
        for e in chars:
            pos = e.at
            if not pos or pos in ("above", "sky", "sky_left", "sky_right", "top"):
                pos = auto[k_auto % len(auto)] if auto else "center"
                k_auto += 1
            fx, fy, depth = POS.get(pos, POS["center"])
            h = self._char_height(e) * shrink
            n = max(1, int(e.count))
            per_row = n if n <= 6 else math.ceil(n / 2)  # multidão grande: duas fileiras
            inst_scale = 1.0 if n == 1 else (0.86 if n <= 6 else 0.78)
            spacing = h * inst_scale * (0.42 if n > 1 else 0)
            if per_row > 1:
                spacing = min(spacing, W * 0.86 / (per_row - 1))
            cx = float(
                np.clip(fx * W, W * 0.1 + spacing * (per_row - 1) / 2, W * 0.9 - spacing * (per_row - 1) / 2)
            )
            if spacing * (per_row - 1) > W * 0.8:
                cx = W / 2
            for i in range(n):
                row, col = divmod(i, per_row)
                x = cx + (col - (per_row - 1) / 2) * spacing + (row % 2) * spacing * 0.5
                y = self.gy + fy * H - row * h * 0.1 + (col % 2) * h * 0.012 * (n > 2)
                d = depth * inst_scale * (1 - row * 0.08)
                look = e.look if (i == 0 or e.ref) else make_look(e.type, f"{e.type}{i}{self.index}", e.color)
                if n > 1 and not e.ref and e.color is None and look is not None:
                    look = replace(look, top=PALETTE[(i * 5 + self.index * 3) % len(PALETTE)])
                rig = build_rig(look, h, self.paper, seed=order * 7 + i, color=e.color)
                act = Actor2D(
                    e, W, H, x, y, d, h * inst_scale, rig=rig, phase=float(self.rng.uniform(0, TAU))
                )
                act.z = (1 - row) * 10 + y * 0.001 + depth
                act.group_i, act.group_n = i, n
                if main_char is None:
                    main_char = act
                    act.main = True
                self.actors.append(act)
            order += 1
        self.main = main_char
        self.glow_actor = None
        # objetos
        hero = n_chars == 0 and len(props) >= 1
        for j, e in enumerate(props):
            d = PROPS.get(e.type) or PROPS["box"]
            pos = e.at
            floating = d.anchor == "center"
            n = max(1, int(e.count))
            size = float(np.clip(e.size or 1.0, 0.4, 3.0))
            h = d.h * H * size
            if hero and n == 1 and not pos:
                h *= 2.3 if floating else (1.25 if d.big else 1.8)
                pos = "hero"
                if len(props) > 1:
                    h *= 0.72
            if not pos:
                if e.type in SKY_PROPS:
                    pos = "sky_right" if "sky" in used else "sky"
                elif d.big:
                    pos = "back_right" if (main_char is None or main_char.base_x <= W / 2) else "back_left"
                    if pos in used:
                        pos = "back_left" if pos == "back_right" else "back_right"
                elif floating and main_char is not None and n == 1:
                    pos = "above"
                else:
                    free = [p for p in ("right", "left", "front_right", "front_left") if p not in used]
                    pos = free[0] if free else "front"
                used.add(pos)
            for i in range(n):
                x, y, depth, layer = self._prop_slot(e, pos, i, n, h, floating, len(props), j)
                spr = draw_prop(e.type, h * depth, e.color, self.paper, seed=j * 11 + i)
                act = Actor2D(e, W, H, x, y, 1.0, h * depth, sprite=spr, floating=floating,
                              phase=float(self.rng.uniform(0, TAU)))  # fmt: skip
                act.layer = layer
                act.z = layer * 100 + (y * 0.001 if layer else -50)
                act.group_i, act.group_n = i, n
                self.actors.append(act)
        if self.main is None:
            props_actors = [a for a in self.actors if a.rig is None]
            if props_actors:
                self.main = props_actors[0]
                props_actors[0].main = True
        for a in self.actors:
            if (
                self.glow_actor is None
                and any(x in ("glow", "appear", "fly") for x in a.el.actions)
                and (a.el.type in ("angel", "jesus") or "glow" in a.el.actions)
            ):
                self.glow_actor = a
        self._gazes()
        self._timeline()
        self._labels()
        self.actors.sort(key=lambda a: getattr(a, "z", 0))

    def _prop_slot(self, e, pos, i, n, h, floating, n_props, j):
        W, H = self.W, self.H
        rng = self.rng
        if pos == "hero":
            if n_props == 1:
                return W / 2, (H * 0.45 if floating else self.gy + H * 0.02), 1.0, 1
            x = W * (0.3 + 0.4 * (j % 2)) if n_props == 2 else W * (0.2 + 0.3 * (j % 3))
            return x, (H * 0.45 if floating else self.gy), 1.0, 1
        if pos == "above" and self.main is not None:
            m = self.main
            if n == 1:
                return m.base_x + W * 0.02, m.base_y - m.h * 1.18 - h * 0.35, 1.0, 1
            crowd = [a for a in self.actors if a.rig is not None]
            if len(crowd) >= n:
                a = crowd[i]
                return a.base_x, a.base_y - a.h * a.depth * 1.15 - h * 0.4, 0.75, 1
            return m.base_x + (i - (n - 1) / 2) * h * 1.2, m.base_y - m.h * 1.2 - h * 0.4, 0.9, 1
        fx, fy, depth = POS.get(pos, POS["center"])
        if pos.startswith("sky") or pos == "top":
            if n == 1:
                return fx * W, self.gy + fy * H, 1.0, 0
            return (
                float(rng.uniform(0.1, 0.9)) * W,
                float(rng.uniform(0.12, 0.36)) * H,
                float(rng.uniform(0.6, 1.0)),
                0,
            )
        layer = 0 if e.type in BIG_PROPS else 1
        if n == 1:
            x = fx * W
            if floating:
                y = self.gy + fy * H - h * 0.75
            else:
                y = self.gy + fy * H
            return x, y, depth, layer
        if floating:
            ang = TAU * i / n + 0.4
            r = W * 0.22
            return fx * W + math.cos(ang) * r, self.gy - H * 0.16 + math.sin(ang) * r * 0.55, 0.8, 1
        spacing = min(W * 0.86 / max(n - 1, 1), h * 0.9)
        x = W / 2 + (i - (n - 1) / 2) * spacing if fx == 0.5 else fx * W + (i - (n - 1) / 2) * spacing
        return x, self.gy + fy * H - (i % 2) * H * 0.01, depth * (0.92 if i % 2 else 1.0), layer

    def _gazes(self) -> None:
        chars = [a for a in self.actors if a.rig is not None]
        main = (
            self.main
            if (self.main is not None and self.main.rig is not None)
            else (chars[0] if chars else None)
        )
        if main is None:
            return
        others = [a for a in chars if a.el is not main.el]
        for a in chars:
            f = a.el.facing
            if a is main or a.el is main.el:
                tgt = others[0].base_x if others else None
                g = 0.0 if tgt is None else 0.5 * (1 if tgt > a.base_x else -1)
                if a.el is main.el and a is not main and a.group_n > 1:
                    g = float(self.rng.uniform(-0.3, 0.3))
            else:
                g = 0.5 * (1 if main.base_x > a.base_x else -1)
                if a.group_n > 3:
                    g *= float(self.rng.uniform(0.3, 1.0))
            if f in ("left",):
                g = -0.7
            elif f in ("right",):
                g = 0.7
            elif f in ("camera", "front"):
                g = 0.0
            elif f == "center":
                g = 0.5 * (1 if a.base_x < self.W / 2 else -1)
            a.gaze = g
            a.point_side = 1 if (g > 0 or (g == 0 and a.base_x <= self.W / 2)) else -1

    def _timeline(self) -> None:
        T = self.T
        keep = set(self.spec.keep)
        k = 0
        for a in self.actors:
            pop = not (a.el.ref and a.el.ref in keep)
            start = (
                0.0
                if not pop
                else min(0.08 + k * 0.14 + (a.group_i * 0.05 if a.group_n > 1 else 0), T * 0.35)
            )
            if a.group_i == 0:
                k += 1
            acts = list(a.el.actions)
            if a.group_n > 1 and a.rig is not None:
                start += float(self.rng.uniform(0, 0.12))
            a.schedule(acts, T, start, pop)
            for name, t0, t1 in a.segs:
                self._action_sound(a, name, t0, t1)

    def _action_sound(self, a: Actor2D, name: str, t0: float, t1: float) -> None:
        first = a.group_i == 0
        if not first and name not in ("walk_in", "walk", "run"):
            return
        ev = self.events.append
        if name in ("appear", "pop"):
            ev((t0 + 0.02, "pop", {"g": 0.6 if a.rig is None else 0.45}))
        elif name == "drop":
            ev((t0 + 0.3, "thud", {"g": 0.7}))
            ev((t0, "whoosh_down", {"g": 0.4}))
        elif name in ("fly_in", "fly_out", "walk_out", "run_out"):
            ev((t0, "whoosh_up", {"g": 0.45}))
        elif name in ("walk_in", "walk", "run", "run_in"):
            step = 0.25 if "run" in name else 0.34
            t = t0 + 0.1
            while t < min(t1, t0 + 2.4):
                ev((t, "step", {"g": 0.25, "soft": True}))
                t += step
        elif name in ("jump", "bounce", "hop"):
            ev((t0 + 0.15, "boing", {"g": 0.5}))
        elif name in ("cheer", "clap"):
            ev((t0, "applause", {"sec": min(2.0, t1 - t0), "g": 0.35}))
        elif name in ("surprised", "scared"):
            ev((t0, "sting", {"g": 0.35}))
        elif name in ("fall", "lie"):
            ev((t0 + (t1 - t0) * 0.8, "thud", {"g": 0.6}))
        elif name in ("glow", "hold_up", "grow"):
            ev((t0, "sparkle", {"g": 0.45}))
        elif name == "ring":
            ev((t0, "rattle", {"g": 0.5}))
        elif name in ("vanish", "shrink"):
            ev((t0, "unpop", {"g": 0.5}))
        elif name == "rise" and a.ptype == "rocket":
            ev((t0, "rocket", {"sec": t1 - t0, "g": 0.5}))
        if (
            a.rig is None
            and name in ("pop", "appear", "drop")
            and a.ptype in ("coin", "money", "money_bag", "treasure", "chest")
        ):
            ev((t0 + 0.1, "coin", {"g": 0.5}))

    def _labels(self) -> None:
        for a in self.actors:
            if a.group_i != 0:
                continue
            if a.el.label:
                a.label_spr = ov.label(a.el.label, self.W, self.paper)
            if a.el.say:
                a.say_spr = ov.bubble(a.el.say, self.W, self.paper, tail_left=a.base_x < self.W * 0.55)
                t0 = max(a.start + 0.45, 0.35)
                a.say_t = (t0, min(self.T, t0 + max(2.5, len(a.el.say) * 0.07)))
                self.events.append((t0, "pop", {"g": 0.4}))

    # -------------------------------------------------------------- textos
    def _build_overlays(self) -> None:
        spec, W, H = self.spec, self.W, self.H
        self.ovl: list[tuple] = []  # (sprite, x, y, t_in, kind)
        y = H * 0.205
        if spec.tag:
            self.ovl.append((ov.tag(spec.tag[:28], W, self.paper), W * 0.055, H * 0.112, 0.0, "tag"))
        if spec.banner:
            col = ov.BANNER_COLORS[spec.banner_color % len(ov.BANNER_COLORS)]
            spr = ov.banner(spec.banner[:48], W, col, self.paper)
            self.ovl.append((spr, W / 2, y, 0.12, "banner"))
            self.events.append((0.12, "whoosh_up", {"g": 0.35}))
            y += spr.h / 2 + H * 0.004
        if spec.card:
            spr = ov.card(spec.card[:60], W, self.paper)
            cy = y + spr.h / 2 if spec.banner else H * 0.205
            self.ovl.append((spr, W / 2, cy, 0.38, "card"))
            self.events.append((0.38, "pop", {"g": 0.3}))
            y = cy + spr.h / 2
        self.list_top = max(y + H * 0.01, H * 0.25)
        if spec.sticker:
            m = self.main
            spr = ov.sticker(spec.sticker[:32], W, self.paper)
            chars = [a for a in self.actors if a.rig is not None] or ([m] if m is not None else [])
            if chars:
                top = min(a.base_y - a.h * a.depth * 1.12 for a in chars)
                xs = [a.base_x for a in chars]
                gap_r, gap_l = W - max(xs), min(xs)
                sx = float(np.clip((max(xs) + W) / 2 if gap_r > gap_l else min(xs) / 2, W * 0.26, W * 0.74))
                if len(chars) >= 3:
                    sx = W * 0.5
                sy = float(np.clip(top - spr.h * 0.5 - H * 0.075, max(y + spr.h * 0.5, H * 0.24), H * 0.52))
            else:
                sx, sy = W * 0.68, H * 0.4
            t_s = float(min(max(0.65, self.T * 0.28), max(0.3, self.T - 0.9)))
            self.ovl.append((spr, sx, sy, t_s, "sticker"))
            self.events.append((t_s, "pop", {"g": 0.55}))
        self.items = list(spec.items)[:5]
        if self.items:
            n = len(self.items)
            t0 = 0.45
            span = max(0.6, (self.T - t0 - 0.6))
            self.item_times = [t0 + 0.35 + span * (i + 0.2) / n for i in range(n)]
            for tt in self.item_times:
                self.events.append((tt, "ding", {"g": 0.4}))
        if spec.number:
            self.events.append((0.3, "tick", {"g": 0.3}))
            self.events.append((1.45, "ding", {"g": 0.35}))

    # -------------------------------------------------------------- efeitos
    def _build_fx(self) -> None:
        spec, W, H = self.spec, self.W, self.H
        k = self.s * 3.2
        self.particles: list[Particles] = []
        self.rays: Sprite | None = None
        self.spot: np.ndarray | None = None
        self.flash_times: list[float] = []
        self.shake = 0.0
        fx = spec.fx
        m = self.main
        mx = m.base_x if m is not None else W / 2
        my = (m.base_y - m.h * 0.7) if m is not None else H * 0.5
        seed = int(self.rng.integers(0, 1 << 30))
        if fx == "confetti":
            self.particles.append(Particles(_confetti_sprites(k), 70, "fall", W, H, seed, speed=1.4))
            self.events.append((0.1, "chime", {"g": 0.4}))
        elif fx in ("hearts", "notes", "stars", "question", "zzz"):
            if fx == "hearts":
                sprs = [draw_prop("heart", H * 0.04, None), draw_prop("heart", H * 0.03, (250, 120, 160))]
            elif fx == "notes":
                sprs = [draw_prop("music_note", H * 0.04, c) for c in ((60, 50, 70), (200, 60, 90))]
            elif fx == "stars":
                sprs = [draw_prop("star", H * 0.035, None), _sparkle_sprite(k)]
            elif fx == "zzz":
                sprs = [_text_sprite("Z", int(54 * self.s), (90, 120, 220))]
            else:
                sprs = [draw_prop("question", H * 0.05, None)]
            self.particles.append(Particles(sprs, 9, "rise", W, H, seed, emitter=(mx, my), life=2.4))
        elif fx == "sparkles":
            self.particles.append(Particles([_sparkle_sprite(k), _sparkle_sprite(k * 0.7, (255, 255, 255))], 26,
                                            "twinkle", W, H, seed, region=(W * 0.08, H * 0.1, W * 0.92, H * 0.7)))  # fmt: skip
            self.events.append((0.2, "sparkle", {"g": 0.45}))
        elif fx in ("money", "coins"):
            sprs = (
                [draw_prop("money", H * 0.05, None)]
                if fx == "money"
                else [draw_prop("coin", H * 0.035, None)]
            )
            if fx == "money":
                sprs.append(draw_prop("coin", H * 0.03, None))
            self.particles.append(Particles(sprs, 30, "fall", W, H, seed, speed=1.1))
            self.events.append((0.2, "coin", {"g": 0.45}))
        elif fx == "rain":
            self.particles.append(Particles([_drop_sprite(k * 1.4)], 110, "fall", W, H, seed, speed=5.0))
        elif fx == "snow":
            self.particles.append(
                Particles([_dot_sprite(k, (255, 255, 255), 2.4)], 70, "fall", W, H, seed, speed=0.6)
            )
        elif fx == "leaves":
            sprs = [_dot_sprite(k, c, 3) for c in ((230, 140, 40), (200, 80, 40), (120, 170, 60))]
            self.particles.append(Particles(sprs, 26, "fall", W, H, seed, speed=0.7))
        elif fx == "bubbles":
            self.particles.append(Particles([_dot_sprite(k, (230, 245, 255), 4, ring=True)], 22, "rise", W, H, seed,
                                            emitter=(W / 2, H * 0.9), life=3.5, size=1.3))  # fmt: skip
            for it in self.particles[-1].items:
                it["dx"] *= 4
        elif fx in ("embers", "fire"):
            self.particles.append(Particles([_dot_sprite(k, (255, 170, 60), 1.8), _dot_sprite(k, (255, 230, 120), 1.2)],
                                            30, "rise", W, H, seed, emitter=(W / 2, H * 0.95), life=3.0))  # fmt: skip
            for it in self.particles[-1].items:
                it["dx"] *= 5
            self.events.append((0.0, "crackle", {"sec": self.T, "g": 0.4}))
        elif fx == "smoke":
            self.particles.append(Particles([_dot_sprite(k, (200, 200, 205), 8)], 12, "rise", W, H, seed,
                                            emitter=(mx, my), life=2.8, size=1.6))  # fmt: skip
        elif fx == "lightning":
            self.flash_times = [0.25, min(0.75, self.T * 0.5)]
            self.events.append((0.27, "thunder_soft", {"g": 0.6}))
        elif fx == "rays":
            self.rays = _rays_sprite(W * 0.75)
        elif fx == "spotlight":
            self.spot = self._spot_mask(mx, my)
        elif fx == "flash":
            self.flash_times = [0.0]
        if fx == "shake" or spec.camera == "shake":
            self.shake = 1.0
        self.ambient: list[Particles] = []
        place, time = spec.place, spec.time
        if place in ("space",) or (time == "night" and place not in INDOOR):
            self.ambient.append(Particles([_sparkle_sprite(k * 0.6, (255, 255, 230))], 14, "twinkle", W, H, seed + 1,
                                          region=(0, 0, W, self.gy * 0.7)))  # fmt: skip
        elif place == "underwater":
            self.ambient.append(Particles([_dot_sprite(k, (230, 245, 255), 3, ring=True)], 14, "rise", W, H, seed + 2,
                                          emitter=(W / 2, H * 0.85), life=4.0))  # fmt: skip
            for it in self.ambient[-1].items:
                it["dx"] *= 5
        elif place == "fire":
            self.ambient.append(Particles([_dot_sprite(k, (255, 200, 90), 1.6)], 24, "rise", W, H, seed + 3,
                                          emitter=(W / 2, H * 0.98), life=2.6))  # fmt: skip
            for it in self.ambient[-1].items:
                it["dx"] *= 6
        self.clouds: list[tuple[Sprite, float, float, float]] = []
        if (
            place not in INDOOR
            and place not in FLOATING
            and time in ("day", "sunset", "dawn")
            and place not in ("fire", "stable")
        ):
            for i in range(2):
                spr = draw_prop(
                    "cloud", H * float(self.rng.uniform(0.05, 0.075)), None, self.paper * 0.5, seed=i
                )
                self.clouds.append((spr, float(self.rng.uniform(0, W)), H * float(self.rng.uniform(0.07, 0.2)),
                                    float(self.rng.uniform(6, 14)) * self.s))  # fmt: skip

    def _spot_mask(self, x: float, y: float) -> np.ndarray:
        W, H = self.W, self.H
        yy, xx = np.mgrid[0:H:4, 0:W:4].astype(np.float32)
        d = np.sqrt(((xx - x) / (W * 0.32)) ** 2 + ((yy - y) / (H * 0.24)) ** 2)
        m = np.clip(0.38 + 0.62 * (1 - np.clip((d - 0.6) / 0.6, 0, 1)), 0, 1)
        m = cv2.resize(m, (W, H), interpolation=cv2.INTER_LINEAR)
        m8 = (m * 255).astype(np.uint8)
        return cv2.merge((m8, m8, m8))

    def _shadow_sprite(self) -> Sprite:
        p = Pen((-60, -16, 60, 16), 2.0 * self.s, ss=2)
        p.soft(lambda q: q.ellipse(0, 0, 54, 11, (0, 0, 0, 255)))
        spr = pen_sprite(p, (0, 0))
        spr.img = cv2.GaussianBlur(spr.img, (0, 0), 4 * self.s)
        return spr

    # -------------------------------------------------------------- câmera
    def _camera_setup(self) -> None:
        cam = self.spec.camera if self.spec.camera in CAMERAS else ""
        if not cam:
            cam = ("zoom_in", "static", "pan_right", "zoom_out", "punch", "static", "pan_left")[
                self.index % 7
            ]
        self.cam_kind = cam
        m = self.main
        fx = m.base_x if m is not None else self.W / 2
        fy = (m.base_y - m.h * 0.6) if m is not None else self.H * 0.5
        self.focus = (
            float(np.clip(fx, self.W * 0.3, self.W * 0.7)),
            float(np.clip(fy, self.H * 0.35, self.H * 0.62)),
        )

    def camera(self, t: float) -> np.ndarray:
        u = smooth(t / self.T)
        k, px = 1.0, 0.0
        c = self.cam_kind
        if c == "zoom_in":
            k = 1.0 + 0.075 * u
        elif c == "zoom_out":
            k = 1.075 - 0.075 * u
        elif c in ("pan_left", "pan_right"):
            k = 1.08
            px = (u - 0.5) * self.W * 0.06 * (1 if c == "pan_left" else -1)
        elif c == "punch":
            k = 1.0 + 0.11 * (1 - ease_out(min(t / 0.55, 1.0))) + 0.03 * u
        elif c == "shake":
            k = 1.05
        else:
            k = 1.0 + 0.025 * u
        fx, fy = self.focus
        sx = sy = 0.0
        if self.shake:
            amp = self.W * 0.008 * (0.35 + 0.65 * max(0.0, 1 - t / 0.8))
            sx = math.sin(t * 37) * amp
            sy = math.cos(t * 29) * amp
            k = max(k, 1.04)
        M = np.array([[k, 0, fx - k * fx + px + sx], [0, k, fy - k * fy + sy], [0, 0, 1]], np.float64)
        # nunca mostrar fora do cenário
        M[0, 2] = min(0.0, max(M[0, 2], self.W - k * self.W))
        M[1, 2] = min(0.0, max(M[1, 2], self.H - k * self.H))
        return M

    # -------------------------------------------------------------- quadro
    def frame(self, t: float) -> np.ndarray:
        W, H = self.W, self.H
        cam = self.camera(t)
        if abs(cam[0, 0] - 1) < 1e-4 and abs(cam[0, 2]) < 0.5 and abs(cam[1, 2]) < 0.5:
            img = self.bg.copy()
        else:
            img = cv2.warpAffine(
                self.bg, cam[:2], (W, H), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT
            )
        for spr, x0, y0, v in self.clouds:
            x = (x0 + t * v) % (W + spr.w) - spr.w / 2
            blit(img, spr, sprite_matrix(spr, cam @ affine(x, y0)), 0.95)
        for p in self.ambient:
            p.draw(img, t, cam)
        poses = [(a, a.pose(t)) for a in self.actors]
        if self.rays is not None and self.main is not None:
            m = self.glow_actor or self.main
            P = poses[self.actors.index(m)][1]
            if not P.hidden:
                cx = m.base_x + P.x
                cy = m.base_y - (m.h * 0.55 if m.rig is not None else (0 if m.floating else m.h * 0.5))
                M = cam @ affine(cx, cy, t * 0.25, 1, 1)
                blit(img, self.rays, sprite_matrix(self.rays, M), min(1.0, t * 3))
        # sombras no chão
        for a, P in poses:
            if P.hidden or a.floating or a.layer == 0 or P.alpha < 0.05:
                continue
            w = (
                a.h * 0.28
                if a.rig is not None
                else (a.sprite.w if a.sprite is not None else 50) * 0.42 / max(self.s, 0.1)
            )
            k = (w / (54 * 2.0 * self.s)) * P.scale * (1 - min(P.jump / max(a.h, 1), 0.6) * 0.6)
            if a.rig is not None:
                k *= a.depth
            M = cam @ affine(a.base_x + P.x, a.base_y + P.y + 2 * self.s, 0, k * (1 + P.lie * 1.4), k * 0.9)
            blit(img, self._shadow, sprite_matrix(self._shadow, M), 0.22 * P.alpha)
        heads: dict[int, tuple] = {}
        prop_marks: list = []
        for a, P in poses:
            draws, head = a.draws(P, cam)
            for spr, M, alpha in draws:
                blit(img, spr, sprite_matrix(spr, M), alpha)
            if head is not None:
                heads[id(a)] = (head, P)
            if a.rig is None and P.fx and not P.hidden:
                prop_marks.append((a, P, head))
        self._marks(img, t, heads, prop_marks, cam)
        for p in self.particles:
            p.draw(img, t, np.eye(3))
        if self.spot is not None:
            cv2.multiply(img, self.spot, dst=img, scale=1 / 255)
        self._bubbles(img, t, heads)
        self._overlays(img, t)
        if self.captions is not None:
            cap = self.captions.frame(t)
            if cap is not None:
                spr, pop = cap
                blit(img, spr, sprite_matrix(spr, affine(W / 2, H * self.captions.y, 0, pop, pop)))
        for ft in self.flash_times:
            d = t - ft
            if 0 <= d < 0.32:
                fill_alpha(img, (255, 255, 255), 0.75 * (1 - d / 0.32))
        return img

    def _marks(self, img, t, heads, prop_marks, cam) -> None:
        """Ícones sobre a cabeça (?, !, zzz, suor, fumaça) e efeitos dos objetos (raios, fogo, vibração)."""
        s = self.s
        for (hx, hy), P in heads.values():
            for mk in set(P.fx):
                key = mk
                spr = self._fx_cache.get(key)
                if spr is None:
                    spr = {
                        "?": draw_prop("question", self.H * 0.06, None),
                        "!": draw_prop("exclamation", self.H * 0.06, None),
                        "zzz": _text_sprite("Z", int(48 * s), (90, 120, 220)),
                        "steam": _dot_sprite(3.2 * s, (230, 230, 236), 5),
                        "sweat": _dot_sprite(3.2 * s, (140, 200, 250), 2.4),
                        "tears": _dot_sprite(3.2 * s, (120, 190, 250), 1.6),
                        "smoke": _dot_sprite(3.2 * s, (210, 210, 216), 8),
                    }.get(mk)
                    if spr is None:
                        continue
                    self._fx_cache[key] = spr
                if mk in ("?", "!"):
                    bob = math.sin(t * 5) * 6 * s
                    blit(
                        img,
                        spr,
                        sprite_matrix(spr, affine(hx + 28 * s, hy - 30 * s + bob, 0.15 * math.sin(t * 3))),
                    )
                elif mk in ("zzz", "steam"):
                    for i in range(3):
                        age = (t * 0.6 + i / 3) % 1.0
                        sc = 0.6 + age * 0.6
                        x = hx + 30 * s + age * 40 * s * (1 if mk == "zzz" else math.sin(i * 2))
                        blit(img, spr, sprite_matrix(spr, affine(x, hy - age * 90 * s, 0, sc, sc)), 1 - age)
        for a, P, top in prop_marks:
            if top is None:
                continue
            for mk in set(P.fx):
                if mk == "fire":
                    for i in range(3):
                        age = (t * 1.6 + i / 3) % 1.0
                        spr = self._fx_cache.setdefault("ember", _dot_sprite(3.2 * s, (255, 170, 60), 3))
                        blit(
                            img,
                            spr,
                            sprite_matrix(spr, affine(top[0] + (i - 1) * 16 * s, top[1] - age * 60 * s)),
                            1 - age,
                        )
                elif mk == "ring":
                    spr = self._fx_cache.setdefault("ringarc", _text_sprite(")", int(50 * s), (60, 60, 70)))
                    for side in (-1, 1):
                        blit(img, spr, sprite_matrix(spr, affine(top[0] + side * a.h * 0.32, top[1] + a.h * 0.3, 0,
                                                                 side, 1)), 0.6 + 0.4 * math.sin(t * 20))  # fmt: skip
                elif mk == "sparkle":
                    spr = self._fx_cache.setdefault("spk", _sparkle_sprite(3.2 * s))
                    for i in range(4):
                        ang = t * 2 + i * TAU / 4
                        blit(img, spr, sprite_matrix(spr, affine(top[0] + math.cos(ang) * a.h * 0.5,
                                                                 top[1] + a.h * 0.3 + math.sin(ang) * a.h * 0.3)))  # fmt: skip

    def _bubbles(self, img, t, heads) -> None:
        W, H = self.W, self.H
        for a in self.actors:
            info = heads.get(id(a))
            if info is None:
                continue
            (hx, hy), P = info
            if a.label_spr is not None and not P.hidden and t >= a.start + 0.2:
                q = back_out(min((t - a.start - 0.2) / 0.3, 1.0))
                y = hy - 22 * self.s
                x = float(np.clip(hx, a.label_spr.w / 2 + 8, W - a.label_spr.w / 2 - 8))
                blit(img, a.label_spr, sprite_matrix(a.label_spr, affine(x, y, 0, q, q)))
            if a.say_spr is not None and a.say_t[0] <= t <= a.say_t[1]:
                q = back_out(min((t - a.say_t[0]) / 0.28, 1.0))
                side = 1 if a.base_x < W * 0.55 else -1
                x = float(np.clip(hx + side * 30 * self.s, a.say_spr.w * 0.25, W - a.say_spr.w * 0.25))
                y = float(max(hy - 18 * self.s, a.say_spr.h + H * 0.1))
                blit(img, a.say_spr, sprite_matrix(a.say_spr, affine(x, y, 0, q, q)))

    def _overlays(self, img, t) -> None:
        W, H = self.W, self.H
        for spr, x, y, t_in, kind in self.ovl:
            if t < t_in:
                continue
            age = t - t_in
            if kind == "tag":
                blit(img, spr, sprite_matrix(spr, affine(x, y)), min(1.0, age * 4 + 0.3))
                continue
            if kind == "banner":
                q = back_out(min(age / 0.38, 1.0), 2.2)
                M = affine(x, y - (1 - min(age / 0.25, 1.0)) * 40 * self.s, -0.025, q, q)
            elif kind == "card":
                q = back_out(min(age / 0.3, 1.0))
                M = affine(x, y, 0.012, q, q)
            else:  # sticker
                q = back_out(min(age / 0.3, 1.0), 2.6)
                M = affine(x, y, -0.08 + 0.05 * math.sin(age * 4.5), q, q)
            blit(img, spr, sprite_matrix(spr, M))
        spec = self.spec
        if self.items and t >= 0.45:
            done = sum(1 for tt in self.item_times if t >= tt)
            key = ("list", done)
            spr = self._fx_cache.get(key)
            if spr is None:
                spr = ov.checklist(spec.items_title, tuple(self.items), done, W, self.paper)
                self._fx_cache[key] = spr
            q = back_out(min((t - 0.45) / 0.35, 1.0))
            y = self.list_top + spr.h / 2
            blit(img, spr, sprite_matrix(spr, affine(W / 2, y, 0, q, q)))
        elif spec.chart and t >= 0.3:
            q = min((t - 0.3) / 1.3, 1.0)
            key = ("chart", round(q, 2))
            spr = self._fx_cache.get(key)
            if spr is None:
                spr = ov.chart(spec.chart, q, W, self.paper)
                self._fx_cache[key] = spr
            pop = back_out(min((t - 0.3) / 0.3, 1.0))
            blit(img, spr, sprite_matrix(spr, affine(W / 2, self.list_top + spr.h / 2, 0, pop, pop)))
        if spec.number and t >= 0.25:
            q = ease_out(min((t - 0.25) / 1.2, 1.0))
            txt = ov.number_text(spec.number, q)
            key = ("num", txt)
            spr = self._fx_cache.get(key)
            if spr is None:
                spr = ov.counter(txt, W)
                self._fx_cache[key] = spr
            pop = back_out(min((t - 0.25) / 0.3, 1.0))
            y = self.list_top + spr.h / 2 if not (self.items or spec.chart) else H * 0.56
            blit(img, spr, sprite_matrix(spr, affine(W / 2, y, 0, pop, pop)))


def draw_rig_static(img: np.ndarray, rig: Rig, x: float, y: float, expr: str = "neutral") -> None:
    """Desenha um personagem parado (prévia/inspeção)."""
    P = Pose2D(expr=expr)
    draws, _ = rig_draws(rig, P, x, y, np.eye(3), 1.0)
    for spr, M, a in draws:
        blit(img, spr, sprite_matrix(spr, M), a)
