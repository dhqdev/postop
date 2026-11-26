"""Animação 2D: pose dos bonecos, montagem das partes e ações com duração natural.

Cada ação tem uma duração própria (pular leva ~0,8 s, acenar ~1,8 s). O tempo que sobra na cena
vira "idle" (respirar, piscar, olhar), então nada fica repetindo em loop. Deslocamento, espelho,
ajoelhar/deitar e sumir continuam valendo nas ações seguintes; o resto (braços, rosto, pulo) faz
transição suave para a próxima ação.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field, fields

import numpy as np

from .characters import Rig
from .draw import affine

PI = math.pi
TAU = math.tau

# duração natural (s); None = preenche o tempo que sobra (ações contínuas)
NATURAL: dict[str, float | None] = {
    "idle": None, "talk": None, "float": None, "glow": None, "pulse": None, "burn": None, "sway": None,
    "orbit": None, "swim": None, "blink": None, "spin_loop": None, "wag": None,
    "walk_in": 1.5, "walk_out": 1.5, "walk": 1.9, "run": 1.2, "run_in": 1.0, "run_out": 1.0, "fly": 2.0,
    "jump": 0.8, "wave": 1.8, "point": 1.9, "cheer": 1.7, "clap": 1.6, "think": 2.4, "surprised": 1.1,
    "scared": 1.7, "sad": 2.2, "cry": 2.2, "angry": 1.7, "laugh": 1.7, "bow": 1.5, "kneel": 0.8, "pray": 0.9,
    "sit": 0.7, "sleep": 0.9, "lie": 0.8, "fall": 0.8, "dance": 2.6, "look": 2.0, "nod": 1.0, "shake_head": 1.0,
    "shrug": 1.1, "hold_up": 1.8, "spin": 0.9, "appear": 0.45, "vanish": 0.45, "eat": 1.6, "hop": 1.2,
    "pop": 0.5, "drop": 1.0, "fly_in": 0.8, "fly_out": 0.8, "rise": 0.8, "shake": 0.9, "grow": 0.8,
    "shrink": 0.6, "open": 0.9, "ring": 1.4, "bounce": 1.4, "slide": 1.2, "flip": 0.8,
}  # fmt: skip
ENTRANCES = {"walk_in", "run_in", "fly_in", "drop", "rise", "appear", "pop"}
PERSISTENT = ("x", "y", "flip", "hidden", "kneel", "lie", "sit", "scale", "alpha")


@dataclass
class Pose2D:
    # persistentes
    x: float = 0.0  # deslocamento (px) a partir da base
    y: float = 0.0
    flip: bool = False
    hidden: bool = False
    kneel: float = 0.0  # 0..1
    lie: float = 0.0  # 0..1 (deitado)
    sit: float = 0.0
    scale: float = 1.0
    alpha: float = 1.0
    # transitórios
    rot: float = 0.0
    sx: float = 1.0
    sy: float = 1.0
    jump: float = 0.0  # px para cima
    torso: float = 0.0
    torso_dy: float = 0.0  # fração da altura
    head: float = 0.0
    head_dy: float = 0.0
    arm_l: tuple = (0.16, -0.08)  # (braço, antebraço) em radianos "para fora"
    arm_r: tuple = (0.16, -0.08)
    leg_l: float = 0.0
    leg_r: float = 0.0
    expr: str = "neutral"
    turn: float = 0.0  # olhar: -1 esquerda .. +1 direita (tela)
    tail: float = 0.0
    wing: float = 0.0
    mouth: bool = False
    fx: list = field(default_factory=list)  # marcas para a cena: "?", "!", "zzz", "sweat", "tears", "steam"

    def fresh(self) -> Pose2D:
        p = Pose2D()
        for k in PERSISTENT:
            setattr(p, k, getattr(self, k))
        return p

    def blend_from(self, prev: Pose2D, w: float) -> None:
        if w >= 1:
            return
        for f in ("rot", "sx", "sy", "jump", "torso", "torso_dy", "head", "head_dy", "leg_l", "leg_r", "turn",
                  "tail", "wing"):  # fmt: skip
            a, b = getattr(prev, f), getattr(self, f)
            setattr(self, f, a + (b - a) * w)
        self.arm_l = tuple(a + (b - a) * w for a, b in zip(prev.arm_l, self.arm_l, strict=True))
        self.arm_r = tuple(a + (b - a) * w for a, b in zip(prev.arm_r, self.arm_r, strict=True))
        if w < 0.5 and prev.expr not in ("talk",):
            self.expr = prev.expr


def smooth(x: float) -> float:
    x = min(max(x, 0.0), 1.0)
    return x * x * (3 - 2 * x)


def ease_out(x: float) -> float:
    x = min(max(x, 0.0), 1.0)
    return 1 - (1 - x) ** 3


def ease_in(x: float) -> float:
    x = min(max(x, 0.0), 1.0)
    return x**3


def back_out(x: float, s: float = 1.9) -> float:
    x = min(max(x, 0.0), 1.0) - 1
    return 1 + x * x * ((s + 1) * x + s)


def elastic(x: float) -> float:
    x = min(max(x, 0.0), 1.0)
    if x in (0.0, 1.0):
        return x
    return 2 ** (-9 * x) * math.sin((x * 10 - 0.75) * (TAU / 3)) + 1


def bounce_out(x: float) -> float:
    x = min(max(x, 0.0), 1.0)
    n, d = 7.5625, 2.75
    if x < 1 / d:
        return n * x * x
    if x < 2 / d:
        x -= 1.5 / d
        return n * x * x + 0.75
    if x < 2.5 / d:
        x -= 2.25 / d
        return n * x * x + 0.9375
    x -= 2.625 / d
    return n * x * x + 0.984375


# ------------------------------------------------------------------ linha do tempo
def build_segments(actions: list[str], T: float, start: float = 0.0) -> list[tuple[str, float, float]]:
    """Distribui as ações no tempo pela duração natural; o que sobra vira idle (ou ação contínua)."""
    acts = [a for a in actions if a] or ["idle"]
    avail = max(T - start, 0.2)
    known = [NATURAL.get(a, 1.2) for a in acts]
    fixed = sum(d for d in known if d is not None)
    n_fill = sum(1 for d in known if d is None)
    k = 1.0
    if fixed > avail * (0.92 if n_fill else 1.0):
        k = max(0.35, avail * (0.85 if n_fill else 1.0) / max(fixed, 1e-3))
    rest = max(0.0, avail - fixed * k)
    durs = []
    for d in known:
        durs.append(d * k if d is not None else rest / max(n_fill, 1))
    segs: list[tuple[str, float, float]] = []
    t = start
    for a, d in zip(acts, durs, strict=True):
        if d <= 0.01:
            continue
        segs.append((a, t, t + d))
        t += d
    if n_fill == 0 and T - t > 0.05:
        segs.append(("idle", t, T))
    elif segs:
        segs[-1] = (segs[-1][0], segs[-1][1], max(segs[-1][2], T))
    return segs or [("idle", start, T)]


# ------------------------------------------------------------------ montagem das partes
QUAD_ANCHORS = {"head": (0.0, -46.0), "tail": (21.0, -32.0)}
FAMILY_ANCHORS = {
    "bird": {"head": (0.0, -27.0), "wing": (10.0, -21.0)},
    "penguin": {"head": (0.0, -39.0), "wing": (14.0, -24.0)},
    "turtle": {"head": (-27.0, -6.0)},
    "snake": {"head": (26.0, -9.0)},
    "butterfly": {"head": (0.0, -16.0), "wing": (2.0, -14.0)},
    "bee": {"head": (0.0, -16.0), "wing": (3.0, -16.0)},
}


def critter_family(rig: Rig) -> str:
    from .characters import critter_family as fam

    f = fam(rig.critter)
    return "fish" if f in ("goldfish", "shark", "whale", "dolphin") else f


def _T(x: float, y: float) -> np.ndarray:
    return np.array([[1, 0, x], [0, 1, y], [0, 0, 1]], np.float64)


def _R(a: float) -> np.ndarray:
    c, s = math.cos(a), math.sin(a)
    return np.array([[c, -s, 0], [s, c, 0], [0, 0, 1]], np.float64)


def _S(sx: float, sy: float) -> np.ndarray:
    return np.array([[sx, 0, 0], [0, sy, 0], [0, 0, 1]], np.float64)


def rig_draws(rig: Rig, P: Pose2D, base_x: float, base_y: float, cam: np.ndarray, scale: float = 1.0):
    """Lista (sprite, matriz 3x3, alfa) na ordem de desenho, mais a posição da cabeça na tela."""
    out: list = []
    if P.hidden or P.alpha <= 0.01:
        return out, None
    k = rig.k
    sgn = -1.0 if P.flip else 1.0
    s = scale * P.scale
    lie = P.lie
    rot = P.rot - lie * (PI / 2) * (1 if not P.flip else -1)
    lift = lie * (rig.body.sh_w if not rig.critter else 14.0) * k * s
    M0 = cam @ _T(base_x + P.x, base_y + P.y - P.jump - lift) @ _R(rot) @ _S(sgn * s * P.sx, s * P.sy)
    a = P.alpha
    head_xy = None
    if rig.critter:
        fam = critter_family(rig)
        anchors = QUAD_ANCHORS if fam == "quad" else FAMILY_ANCHORS.get(fam, {})
        tail = rig.parts.get("tail")
        if tail is not None:
            tx, ty = anchors.get("tail", (20.0, -30.0))
            out.append((tail, M0 @ _T(tx * k, ty * k) @ _R(P.tail - 0.1), a))
        wing = rig.parts.get("wing")
        if wing is not None and fam in ("butterfly", "bee"):
            wx, wy = anchors.get("wing", (2.0, -14.0))
            fl = 0.55 + 0.45 * abs(math.cos(P.wing))
            out.append((wing, M0 @ _T(wx * k, wy * k) @ _S(fl, 1), a))
            out.append((wing, M0 @ _T(-wx * k, wy * k) @ _S(-fl, 1), a))
        out.append((rig.parts["body"], M0 @ _S(1, 1 - P.kneel * 0.25 - P.sit * 0.2), a))
        if wing is not None and fam in ("bird", "penguin"):
            wx, wy = anchors.get("wing", (10.0, -21.0))
            for side in (-1, 1):
                out.append(
                    (wing, M0 @ _T(side * wx * k, wy * k) @ _R(side * (-0.2 - P.wing)) @ _S(side, 1), a)
                )
        hx, hy = anchors.get("head", (0.0, 0.0))
        hy = hy * (1 - P.kneel * 0.25 - P.sit * 0.2)
        mirror = (P.turn < -0.25) != P.flip  # olhar para a esquerda espelha a cabeça
        Mh = M0 @ _T(hx * k, hy * k + P.head_dy * k * 10) @ _R(P.head) @ _S(-1 if mirror else 1, 1)
        out.append((rig.head(_expr(P), abs(P.turn)), Mh, a))
        head_xy = (Mh @ np.array([0, -16 * k, 1.0]))[:2]
        return out, head_xy
    bd = rig.body
    kneel = max(P.kneel, P.sit)
    hip_h = -bd.hip_y * k
    drop = kneel * hip_h * (0.62 if P.kneel >= P.sit else 0.5)
    Mbody = M0 @ _T(0, drop)
    hips_sy = max(0.2, 1 - drop / max(hip_h, 1e-3))
    # capa e asas (atrás de tudo)
    Mt = Mbody @ _T(0, bd.waist_y * k + P.torso_dy * bd.height * k) @ _R(P.torso)
    cape = rig.parts.get("cape")
    if cape is not None:
        out.append((cape, Mt @ _T(0, (bd.shoulder[1] - bd.waist_y - 2) * k) @ _R(-P.torso * 0.5), a))
    wings = rig.parts.get("wings")
    if wings is not None:
        flap = 0.08 * math.sin(P.wing)
        out.append(
            (wings, Mt @ _T(0, (bd.shoulder[1] - bd.waist_y + 3) * k) @ _S(1 + flap, 1 - flap * 0.5), a)
        )
    Mn = Mt @ _T(0, (bd.neck_y - bd.waist_y) * k) @ _R(P.head) @ _T(0, P.head_dy * k * 10)
    mirror_head = (P.turn < -0.25) != P.flip
    Mhead = Mn @ _S(-1 if mirror_head else 1, 1)
    hb = rig.parts.get("hair_back")
    if hb is not None:
        out.append((hb, Mhead, a))
    if kneel < 0.98:
        for name, side, ang in (("leg_l", -1, P.leg_l), ("leg_r", 1, P.leg_r)):
            spr = rig.parts.get(name)
            if spr is not None:
                Ml = M0 @ _T(side * 6.0 * k, bd.hip_y * k) @ _R(ang) @ _S(1, 1 - kneel)
                out.append((spr, Ml, a * (1 - kneel * 0.5)))
    out.append((rig.parts["hips"], Mbody @ _T(0, bd.hip_y * k) @ _S(1, hips_sy), a))
    out.append((rig.parts["torso"], Mt, a))
    out.append((rig.head(_expr(P), abs(P.turn)), Mhead, a))
    head_xy = (Mn @ np.array([0, -bd.head_r * 2.1 * k, 1.0]))[:2]
    up, fore = rig.parts["upper"], rig.parts["fore"]
    sx, sy = bd.shoulder
    for side, (ua, fa) in ((-1, P.arm_l), (1, P.arm_r)):
        Mu = Mt @ _T(side * sx * k, (sy - bd.waist_y) * k) @ _R(-side * ua)
        Mf = Mu @ _T(0, bd.upper * k) @ _R(-side * fa)
        out.append((up, Mu, a))
        if side == 1 and rig.parts.get("held") is not None:
            hand = Mf @ np.array([0, (bd.fore + bd.hand_r * 0.55) * k, 1.0])
            Mh = _T(hand[0], hand[1]) @ _R(rot * 0.6 + P.torso) @ _S(sgn * s * cam[0, 0], s * cam[1, 1])
            out.append((rig.parts["held"], Mh, a))
        out.append((fore, Mf, a))
    return out, head_xy


def _expr(P: Pose2D) -> str:
    if P.mouth and P.expr in ("neutral", "talk"):
        return "talk"
    if P.expr == "talk":
        return "neutral"
    return P.expr


# ------------------------------------------------------------------ ações de personagens
def _blink(a, P: Pose2D, t: float) -> None:
    if P.expr not in ("neutral", "talk"):
        return
    q = (t + a.phase * 3.1) % 3.4
    if q < 0.12:
        P.expr = "blink"


def _breathe(a, P: Pose2D, t: float, amp: float = 1.0) -> None:
    b = math.sin(t * TAU / 2.6 + a.phase)
    P.sy *= 1 + 0.012 * b * amp
    P.sx *= 1 - 0.006 * b * amp
    P.arm_l = (P.arm_l[0] + 0.03 * b * amp, P.arm_l[1])
    P.arm_r = (P.arm_r[0] + 0.03 * math.sin(t * TAU / 2.6 + a.phase + 0.8) * amp, P.arm_r[1])
    P.head += 0.025 * math.sin(t * 0.9 + a.phase) * amp
    P.tail += 0.35 * math.sin(t * 2.4 + a.phase)
    P.wing += t * 3 if a.rig.critter else 0.0


def a_idle(a, P, p, lt, dur, t):
    _breathe(a, P, t)
    P.turn = a.gaze
    if a.rig.critter and math.sin(t * 0.7 + a.phase * 2) > 0.85:
        P.head += 0.12
    _blink(a, P, t)


def a_talk(a, P, p, lt, dur, t):
    _breathe(a, P, t)
    P.turn = a.gaze
    g = math.sin(lt * 2.1 + a.phase)
    P.arm_r = (0.35 + 0.35 * max(0.0, g), -0.9 * max(0.0, g) - 0.1)
    P.head += 0.05 * math.sin(lt * 3.3)
    phase = lt * TAU * 3.4 + math.sin(lt * 5.1) * 1.4
    pause = math.sin(lt * 1.3 + a.phase) > 0.75
    P.mouth = (math.sin(phase) > -0.1) and not pause
    P.expr = "talk"
    _blink(a, P, t)


def _walk_cycle(a, P: Pose2D, lt: float, speed: float = 1.0, run: bool = False) -> None:
    f = (2.0 if not run else 3.0) * speed
    ph = lt * TAU * f
    sw = 0.42 if not run else 0.7
    P.leg_l = sw * math.sin(ph)
    P.leg_r = -sw * math.sin(ph)
    P.arm_l = (0.18 - (0.35 if not run else 0.6) * math.sin(ph), -0.2 if not run else -0.9)
    P.arm_r = (0.18 + (0.35 if not run else 0.6) * math.sin(ph), -0.2 if not run else -0.9)
    P.jump += abs(math.sin(ph)) * a.h * (0.025 if not run else 0.05)
    P.rot += (0.04 if not run else 0.12) * (-1 if P.flip else 1)
    if a.rig.critter:
        P.head += 0.06 * math.sin(ph * 2)
        P.tail += 0.5 * math.sin(ph)
        P.wing += lt * 18


def _move(a, P: Pose2D, x0: float, x1: float, q: float, run: bool = False) -> None:
    P.x = x0 + (x1 - x0) * q
    if abs(x1 - x0) > 1:
        P.flip = x1 < x0
        P.turn = 0.7 * (-1 if P.flip else 1)


def a_walk_in(a, P, p, lt, dur, t, run=False):
    side = -1 if a.base_x < a.W / 2 else 1
    x0 = side * (a.W * 0.42 + a.h * 0.4)
    q = smooth(p) if not run else ease_out(p)
    _move(a, P, x0, 0.0, q)
    if p < 0.97:
        _walk_cycle(a, P, lt, 1.0, run)
        P.flip = side > 0
        P.turn = 0.7 * (-1 if P.flip else 1)
    else:
        P.flip = False
        P.turn = a.gaze
    _blink(a, P, t)


def a_run_in(a, P, p, lt, dur, t):
    a_walk_in(a, P, p, lt, dur, t, run=True)


def a_walk_out(a, P, p, lt, dur, t, run=False):
    side = 1 if a.base_x >= a.W / 2 else -1
    x1 = side * (a.W * 0.45 + a.h * 0.4)
    _move(a, P, P.x, x1, ease_in(p) * 0.4 + p * 0.6)
    _walk_cycle(a, P, lt, 1.0, run)
    P.flip = side < 0
    P.turn = 0.7 * side
    if p >= 1:
        P.hidden = True


def a_run_out(a, P, p, lt, dur, t):
    a_walk_out(a, P, p, lt, dur, t, run=True)


def a_walk(a, P, p, lt, dur, t, run=False):
    d = (1 if a.base_x <= a.W / 2 else -1) * a.W * (0.22 if not run else 0.32)
    x0 = P.x
    _move(a, P, x0, x0 + d, smooth(p))
    if p < 0.98:
        _walk_cycle(a, P, lt, 1.0, run)
    else:
        P.turn = a.gaze
    _blink(a, P, t)


def a_run(a, P, p, lt, dur, t):
    a_walk(a, P, p, lt, dur, t, run=True)
    P.expr = "surprised" if a.cat == "person" and p < 0.95 else P.expr


def a_jump(a, P, p, lt, dur, t):
    if p < 0.22:
        c = smooth(p / 0.22)
        P.sy *= 1 - 0.12 * c
        P.sx *= 1 + 0.08 * c
        P.arm_l = (0.5 * c, -0.4)
        P.arm_r = (0.5 * c, -0.4)
    elif p < 0.8:
        u = (p - 0.22) / 0.58
        P.jump += a.h * 0.28 * math.sin(PI * u)
        P.sy *= 1 + 0.08 * math.sin(PI * u)
        P.arm_l = (2.5, 0.3)
        P.arm_r = (2.5, 0.3)
        P.leg_l, P.leg_r = -0.25, 0.25
        P.expr = "happy"
    else:
        c = 1 - smooth((p - 0.8) / 0.2)
        P.sy *= 1 - 0.1 * c
        P.sx *= 1 + 0.07 * c
    P.turn = a.gaze


def a_wave(a, P, p, lt, dur, t):
    _breathe(a, P, t, 0.5)
    up = smooth(min(p / 0.18, 1.0)) * (1 - smooth((p - 0.85) / 0.15))
    P.arm_r = (2.55 * up + 0.16 * (1 - up), (0.2 + 0.45 * math.sin(lt * TAU * 2.6)) * up - 0.08 * (1 - up))
    P.expr = "happy" if 0.15 < p < 0.85 else "neutral"
    P.head += 0.06 * up
    P.turn = a.gaze * 0.5


def a_point(a, P, p, lt, dur, t):
    _breathe(a, P, t, 0.5)
    up = smooth(min(p / 0.2, 1.0)) * (1 - smooth((p - 0.88) / 0.12))
    side = a.point_side
    arm = (1.5 * up + 0.16 * (1 - up), 0.05 * up - 0.08 * (1 - up))
    if side > 0:
        P.arm_r = arm
    else:
        P.arm_l = arm
    P.turn = 0.7 * side
    P.mouth = 0.2 < p < 0.8 and math.sin(lt * 20) > 0
    P.expr = "talk"


def a_cheer(a, P, p, lt, dur, t):
    P.arm_l = (2.7, 0.35 + 0.15 * math.sin(lt * 14))
    P.arm_r = (2.7, 0.35 + 0.15 * math.sin(lt * 14 + 1))
    P.jump += a.h * 0.07 * abs(math.sin(lt * TAU * 1.3))
    P.expr = "happy"
    P.turn = 0.0


def a_clap(a, P, p, lt, dur, t):
    c = abs(math.sin(lt * TAU * 2.6))
    P.arm_l = (0.25, -1.75 + 0.35 * c)
    P.arm_r = (0.25, -1.75 + 0.35 * c)
    P.expr = "happy"
    P.jump += a.h * 0.012 * c
    P.turn = a.gaze * 0.5


def a_think(a, P, p, lt, dur, t):
    _breathe(a, P, t, 0.5)
    P.arm_r = (-0.45, -2.55)
    P.arm_l = (0.1, -1.2)
    P.head += 0.12
    P.turn = 0.45 * (1 if a.phase > 3 else -1)
    if p > 0.15:
        P.fx.append("?")
    _blink(a, P, t)


def a_surprised(a, P, p, lt, dur, t):
    c = ease_out(min(p / 0.25, 1.0))
    P.jump += a.h * 0.08 * math.sin(PI * min(p / 0.35, 1.0))
    P.arm_l = (1.0 * c, 0.6 * c)
    P.arm_r = (1.0 * c, 0.6 * c)
    P.expr = "surprised"
    P.head -= 0.05 * c
    P.fx.append("!")
    P.turn = a.gaze


def a_scared(a, P, p, lt, dur, t):
    sh = math.sin(lt * 48) * a.h * 0.008
    P.x += sh
    P.arm_l = (0.55, -1.75)
    P.arm_r = (0.55, -1.75)
    P.expr = "scared"
    P.sy *= 0.97
    P.fx.append("sweat")
    P.turn = a.gaze


def a_sad(a, P, p, lt, dur, t, cry=False):
    _breathe(a, P, t, 0.4)
    c = smooth(min(p / 0.25, 1.0))
    P.head_dy += 0.12 * c
    P.head += 0.08 * c
    P.arm_l = (0.06, 0.0)
    P.arm_r = (0.06, 0.0)
    P.expr = "sad"
    if cry:
        P.x += math.sin(lt * 26) * a.h * 0.003
        P.fx.append("tears")
    P.turn = 0.0


def a_cry(a, P, p, lt, dur, t):
    a_sad(a, P, p, lt, dur, t, cry=True)


def a_angry(a, P, p, lt, dur, t):
    sh = math.sin(lt * 30)
    P.arm_l = (0.55, -1.5 + 0.2 * sh)
    P.arm_r = (0.55, -1.5 - 0.2 * sh)
    P.expr = "angry"
    P.jump += a.h * 0.02 * abs(sh)
    P.fx.append("steam")
    P.turn = a.gaze


def a_laugh(a, P, p, lt, dur, t):
    b = abs(math.sin(lt * TAU * 2.2))
    P.jump += a.h * 0.03 * b
    P.head -= 0.08
    P.arm_l = (0.3, -1.4)
    P.arm_r = (0.3, -1.4)
    P.expr = "happy"
    P.turn = a.gaze * 0.5


def a_bow(a, P, p, lt, dur, t):
    c = math.sin(PI * min(p / 0.9, 1.0))
    P.torso_dy += 0.08 * c
    P.head_dy += 0.1 * c
    P.arm_l = (0.1, -0.5 * c)
    P.arm_r = (0.1, -0.5 * c)
    P.expr = "blink" if c > 0.5 else "neutral"
    P.turn = 0.0


def a_kneel(a, P, p, lt, dur, t, pray=False):
    c = smooth(p)
    P.kneel = max(P.kneel, c)
    if pray:
        P.arm_l = (-0.3, -2.25 * c)
        P.arm_r = (-0.3, -2.25 * c)
        P.expr = "blink"
        P.head_dy += 0.06 * c
    else:
        P.head_dy += 0.04 * c
        P.arm_l = (0.1, -0.3)
        P.arm_r = (0.1, -0.3)
        _blink(a, P, t)
    P.turn = a.gaze * 0.5


def a_pray(a, P, p, lt, dur, t):
    a_kneel(a, P, p, lt, dur, t, pray=True)


def a_sit(a, P, p, lt, dur, t):
    P.sit = max(P.sit, smooth(p))
    _blink(a, P, t)
    P.turn = a.gaze


def a_lie(a, P, p, lt, dur, t, sleep=False, fall=False):
    q = ease_in(p) if fall else smooth(p)
    if fall and p < 0.6:
        P.expr = "surprised"
        P.arm_l = (2.0, 0.6)
        P.arm_r = (2.0, 0.6)
    P.lie = max(P.lie, q)
    if p >= 1 or not fall:
        P.expr = "sleep" if sleep else ("scared" if fall else P.expr)
    if sleep and p > 0.6:
        P.fx.append("zzz")
    P.turn = 0.0


def a_sleep(a, P, p, lt, dur, t):
    a_lie(a, P, p, lt, dur, t, sleep=True)


def a_fall(a, P, p, lt, dur, t):
    a_lie(a, P, p, lt, dur, t, fall=True)


def a_dance(a, P, p, lt, dur, t):
    b = lt * TAU * 1.2 + a.phase
    P.rot += 0.1 * math.sin(b)
    P.jump += a.h * 0.03 * abs(math.sin(b))
    P.arm_l = (1.4 + 1.0 * math.sin(b), 0.6 + 0.4 * math.sin(b * 2))
    P.arm_r = (1.4 - 1.0 * math.sin(b), 0.6 - 0.4 * math.sin(b * 2))
    P.leg_l = 0.2 * max(0.0, math.sin(b))
    P.leg_r = -0.2 * max(0.0, -math.sin(b))
    P.expr = "happy"
    P.turn = 0.4 * math.sin(b / 2)


def a_look(a, P, p, lt, dur, t):
    _breathe(a, P, t, 0.6)
    P.turn = 0.75 * (1 if math.sin(lt * 2.4) > 0 else -1)
    P.arm_r = (0.6, -2.3) if 0.15 < p < 0.85 else P.arm_r
    _blink(a, P, t)


def a_nod(a, P, p, lt, dur, t):
    _breathe(a, P, t, 0.5)
    P.head_dy += 0.05 * max(0.0, math.sin(lt * TAU * 2.2))
    P.expr = "happy"
    P.turn = a.gaze * 0.5


def a_shake_head(a, P, p, lt, dur, t):
    _breathe(a, P, t, 0.5)
    P.turn = 0.7 * math.sin(lt * TAU * 2.4)
    P.head += 0.08 * math.sin(lt * TAU * 2.4)
    P.expr = "sad"


def a_shrug(a, P, p, lt, dur, t):
    c = math.sin(PI * min(p, 1.0))
    P.arm_l = (0.7 * c + 0.1, 1.3 * c)
    P.arm_r = (0.7 * c + 0.1, 1.3 * c)
    P.head += 0.12 * c
    P.torso_dy -= 0.01 * c
    P.turn = a.gaze


def a_hold_up(a, P, p, lt, dur, t):
    up = smooth(min(p / 0.2, 1.0))
    P.arm_r = (2.2 * up + 0.16, 0.3 * up)
    P.expr = "happy" if p > 0.3 else "neutral"
    P.turn = 0.3


def a_spin(a, P, p, lt, dur, t):
    P.sx *= math.cos(TAU * smooth(p))
    P.jump += a.h * 0.04 * math.sin(PI * p)
    P.expr = "happy"


def a_float(a, P, p, lt, dur, t):
    P.jump += a.h * (0.06 + 0.035 * math.sin(t * 2.0 + a.phase))
    P.arm_l = (0.5 + 0.1 * math.sin(t * 2.2), 0.2)
    P.arm_r = (0.5 + 0.1 * math.sin(t * 2.2 + 1), 0.2)
    P.leg_l, P.leg_r = 0.1, -0.1
    P.wing += t * (4 if not a.rig.critter else 16)
    P.turn = a.gaze
    _blink(a, P, t)


def a_fly(a, P, p, lt, dur, t):
    side = 1 if a.base_x <= a.W / 2 else -1
    q = smooth(p)
    P.x = side * a.W * 0.25 * (q - 0.5) * 2 * 0.6
    P.jump += a.h * (0.45 * math.sin(PI * q) + 0.05)
    P.flip = side < 0
    P.rot += 0.35 * (1 if not P.flip else -1) * math.sin(PI * q)
    P.arm_r = (2.9, 0.1)
    P.arm_l = (0.4, 0.2)
    P.wing += lt * 20
    P.turn = 0.7 * side
    P.expr = "happy"


def a_appear(a, P, p, lt, dur, t):
    P.scale *= max(0.001, back_out(p))
    P.alpha = min(1.0, p * 3)
    a_idle(a, P, p, lt, dur, t)


def a_vanish(a, P, p, lt, dur, t):
    P.scale *= max(0.001, 1 - ease_in(p))
    if p >= 1:
        P.hidden = True


def a_eat(a, P, p, lt, dur, t):
    P.head += 0.18 * max(0.0, math.sin(lt * 7))
    P.head_dy += 0.04 * max(0.0, math.sin(lt * 7))
    P.mouth = math.sin(lt * 14) > 0
    P.expr = "happy"


def a_hop(a, P, p, lt, dur, t):
    q = (lt * 2.0) % 1.0
    P.jump += a.h * 0.12 * math.sin(PI * q)
    P.x += (1 if a.base_x <= a.W / 2 else -1) * a.W * 0.12 * smooth(p)
    P.tail += 0.6 * math.sin(lt * 10)
    P.wing += lt * 18
    P.turn = a.gaze


def a_wag(a, P, p, lt, dur, t):
    a_idle(a, P, p, lt, dur, t)
    P.tail += 0.6 * math.sin(lt * 16)
    P.expr = "happy"


def a_swim(a, P, p, lt, dur, t):
    side = 1 if a.base_x <= a.W / 2 else -1
    P.x += side * a.W * 0.18 * math.sin(lt * 0.6 + a.phase)
    P.flip = math.cos(lt * 0.6 + a.phase) * side < 0
    P.jump += a.h * 0.08 * math.sin(lt * 1.8)
    P.rot += 0.06 * math.sin(lt * 3)
    _blink(a, P, t)


CHAR_ACTIONS = {
    "idle": a_idle, "talk": a_talk, "walk_in": a_walk_in, "run_in": a_run_in, "walk_out": a_walk_out,
    "run_out": a_run_out, "walk": a_walk, "run": a_run, "jump": a_jump, "wave": a_wave, "point": a_point,
    "cheer": a_cheer, "clap": a_clap, "think": a_think, "surprised": a_surprised, "scared": a_scared, "sad": a_sad,
    "cry": a_cry, "angry": a_angry, "laugh": a_laugh, "bow": a_bow, "kneel": a_kneel, "pray": a_pray, "sit": a_sit,
    "sleep": a_sleep, "lie": a_lie, "fall": a_fall, "dance": a_dance, "look": a_look, "nod": a_nod,
    "shake_head": a_shake_head, "shrug": a_shrug, "hold_up": a_hold_up, "spin": a_spin, "float": a_float,
    "fly": a_fly, "appear": a_appear, "pop": a_appear, "vanish": a_vanish, "eat": a_eat, "hop": a_hop,
    "wag": a_wag, "swim": a_swim, "glow": a_idle,
}  # fmt: skip
CHAR_ALIASES = {"drop": "appear", "fly_in": "walk_in", "rise": "appear", "shake": "scared", "grow": "appear",
                "shrink": "vanish", "bounce": "jump", "slide": "walk", "fly_out": "walk_out", "pulse": "idle",
                "burn": "idle", "sway": "idle", "orbit": "float", "ring": "talk", "open": "surprised",
                "flip": "spin", "blink": "idle", "spin_loop": "spin"}  # fmt: skip


def char_action(name: str):
    return CHAR_ACTIONS.get(name) or CHAR_ACTIONS.get(CHAR_ALIASES.get(name, ""), a_idle)


def evaluate(a, segs, fns, t: float) -> Pose2D:
    """Pose no instante t: ações já concluídas deixam o estado persistente para as seguintes."""
    P = Pose2D(flip=a.flip0)
    prev = None
    for i, ((_name, t0, t1), fn) in enumerate(zip(segs, fns, strict=True)):
        dur = max(t1 - t0, 1e-3)
        if t >= t1 and i < len(segs) - 1:
            Q = P.fresh()
            fn(a, Q, 1.0, dur, dur, t1)
            P = Q.fresh()
            prev = Q
            continue
        lt = min(max(t - t0, 0.0), dur)
        cur = P.fresh()
        fn(a, cur, lt / dur, lt, dur, t)
        if prev is not None:
            cur.blend_from(prev, smooth(lt / min(0.28, dur * 0.5)))
        P = cur
        break
    return P


def pose_fields() -> list[str]:  # pragma: no cover - útil para depuração
    return [f.name for f in fields(Pose2D)]


__all__ = [
    "affine",
    "build_segments",
    "evaluate",
    "char_action",
    "rig_draws",
    "Pose2D",
    "NATURAL",
    "ENTRANCES",
]
