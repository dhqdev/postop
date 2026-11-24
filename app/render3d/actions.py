"""Ações (animações) aplicadas aos atores.

Cada ação recebe o ator, a pose em construção e o progresso dentro do seu trecho:
`p` (0..1), `lt` (segundos desde o início do trecho) e `dur` (duração do trecho).
Deslocamento, giro (yaw), escala e "sumir" persistem para as ações seguintes; o resto
(juntas, inclinação, pulo) dura só durante a ação e faz transição suave para a próxima.
"""

from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass, field

import numpy as np

from .geom import F32, back_out, bounce_out, clamp01, ease_in, ease_io, ease_out, elastic, smooth

TAU = math.tau
PI = math.pi


@dataclass
class Pose:
    pos: np.ndarray = field(default_factory=lambda: np.zeros(3, F32))
    yaw: float = 0.0
    scale: np.ndarray = field(default_factory=lambda: np.ones(3, F32))
    hidden: bool = False
    travel: float = 0.0  # distância percorrida (rodas)
    # transitórios
    pitch: float = 0.0
    roll: float = 0.0
    lift: float = 0.0
    pivot: np.ndarray = field(default_factory=lambda: np.zeros(3, F32))
    rot: dict = field(default_factory=dict)
    npos: dict = field(default_factory=dict)
    nscale: dict = field(default_factory=dict)
    emit: float = 1.0
    light: float = 1.0
    squash: float = 0.0
    fire: bool = False  # motor do foguete ligado

    def fresh(self) -> Pose:
        """Nova pose com só a parte persistente."""
        return Pose(self.pos.copy(), self.yaw, self.scale.copy(), self.hidden, self.travel)

    def j(self, name: str, rx: float = 0.0, ry: float = 0.0, rz: float = 0.0) -> None:
        cur = self.rot.get(name)
        v = np.array((rx, ry, rz), F32)
        self.rot[name] = v if cur is None else cur + v

    def blend_from(self, prev: Pose, w: float) -> None:
        """Mistura os transitórios da ação anterior (w=0 → anterior, 1 → atual)."""
        if w >= 1:
            return
        keys = set(self.rot) | set(prev.rot)
        z = np.zeros(3, F32)
        self.rot = {k: prev.rot.get(k, z) + (self.rot.get(k, z) - prev.rot.get(k, z)) * w for k in keys}
        keys = set(self.nscale) | set(prev.nscale)
        self.nscale = {
            k: prev.nscale.get(k, 1.0) + (self.nscale.get(k, 1.0) - prev.nscale.get(k, 1.0)) * w for k in keys
        }
        self.pitch = prev.pitch + (self.pitch - prev.pitch) * w
        self.roll = prev.roll + (self.roll - prev.roll) * w
        self.lift = prev.lift + (self.lift - prev.lift) * w
        self.squash = prev.squash + (self.squash - prev.squash) * w
        self.fire = self.fire or (prev.fire and w < 0.5)
        self.pivot = prev.pivot + (self.pivot - prev.pivot) * w


def fwd(yaw: float) -> np.ndarray:
    return np.array((math.sin(yaw), 0.0, math.cos(yaw)), F32)


def side(yaw: float) -> np.ndarray:
    return np.array((math.cos(yaw), 0.0, -math.sin(yaw)), F32)


# ------------------------------------------------------------------ pessoas
def _walk_legs(P: Pose, ph: float, amp: float = 0.5, knee: float = 0.75, arms: float = 0.45) -> None:
    s, c = math.sin(ph), math.cos(ph)
    P.j("hip_l", -amp * s)
    P.j("hip_r", amp * s)
    P.j("kn_l", knee * max(0.0, c) + 0.05)
    P.j("kn_r", knee * max(0.0, -c) + 0.05)
    P.j("sh_l", arms * s)
    P.j("sh_r", -arms * s)
    P.j("el_l", -0.25 - 0.15 * max(0.0, -s))
    P.j("el_r", -0.25 - 0.15 * max(0.0, s))
    P.j("spine", 0.03, 0.07 * s)
    P.lift += 0.03 * abs(c)


def _move(a, P: Pose, dist: float) -> None:
    P.pos += fwd(P.yaw) * dist
    P.travel += abs(dist)


def h_idle(a, P, p, lt, dur, t):
    ph = t * 1.4 + a.phase
    P.j("spine", 0.015 * math.sin(ph))
    P.j("sh_l", 0.04 * math.sin(ph + 1), 0, 0.03)
    P.j("sh_r", 0.04 * math.sin(ph + 2), 0, -0.03)
    P.j("el_l", -0.12)
    P.j("el_r", -0.12)
    P.j("head", 0.04 * math.sin(t * 0.7 + a.phase), 0.25 * math.sin(t * 0.45 + a.phase) * smooth(lt / 1.5))


def h_walk(a, P, p, lt, dur, t, speed=1.25, freq=1.8, run=False):
    k = a.stride
    ph = lt * TAU * freq / math.sqrt(k)
    if run:
        _walk_legs(P, ph, 0.85, 1.3, 0.9)
        P.j("spine", 0.22)
        P.j("el_l", -1.0)
        P.j("el_r", -1.0)
        P.lift += 0.04 * abs(math.cos(ph))
    else:
        _walk_legs(P, ph)
    if a.cat == "ghost":
        P.rot.clear()
        _float(a, P, lt, t)
    _move(a, P, speed * k * lt)


def h_run(a, P, p, lt, dur, t):
    h_walk(a, P, p, lt, dur, t, speed=3.4, freq=2.6, run=True)


def h_jump(a, P, p, lt, dur, t):
    n = max(1, round(dur / 1.1))
    per = dur / n
    q = (lt % per) / per if lt < dur else 1.0
    h = 0.75 * a.stride
    if q < 0.22:
        c = smooth(q / 0.22)
        P.lift -= 0.12 * c
        P.j("hip_l", -0.6 * c)
        P.j("hip_r", -0.6 * c)
        P.j("kn_l", 1.1 * c)
        P.j("kn_r", 1.1 * c)
        P.j("spine", 0.3 * c)
        P.j("sh_l", 0.7 * c)
        P.j("sh_r", 0.7 * c)
    elif q < 0.78:
        u = (q - 0.22) / 0.56
        P.lift += h * math.sin(PI * u)
        P.j("sh_l", -2.6 * math.sin(PI * min(u * 1.5, 1)), 0, 0.3)
        P.j("sh_r", -2.6 * math.sin(PI * min(u * 1.5, 1)), 0, -0.3)
        P.j("hip_l", -0.3)
        P.j("hip_r", -0.3)
        P.j("kn_l", 0.6)
        P.j("kn_r", 0.6)
        P.squash = -0.06 * math.sin(PI * u)
    else:
        c = 1 - smooth((q - 0.78) / 0.22)
        P.lift -= 0.1 * c
        P.j("kn_l", 0.9 * c)
        P.j("kn_r", 0.9 * c)
        P.j("hip_l", -0.5 * c)
        P.j("hip_r", -0.5 * c)
        P.squash = 0.08 * c


def h_wave(a, P, p, lt, dur, t):
    h_idle(a, P, p, lt, dur, t)
    P.j("sh_r", -0.3, 0, -2.0)
    P.j("el_r", 0, 0, 0.55 + 0.5 * math.sin(lt * 9))
    P.j("head", 0, 0, 0.1 * math.sin(lt * 3))
    P.nscale["mouth"] = 1.6


def h_dance(a, P, p, lt, dur, t):
    b = lt * TAU * 1.1 + a.phase
    P.lift += 0.06 * abs(math.sin(b))
    P.j("spine", 0.05, 0.25 * math.sin(b / 2), 0.18 * math.sin(b))
    P.j("sh_l", -0.3, 0, 2.0 + 0.6 * math.sin(b))
    P.j("sh_r", -0.3, 0, -2.0 + 0.6 * math.sin(b + PI))
    P.j("el_l", -0.6 - 0.4 * math.sin(b))
    P.j("el_r", -0.6 - 0.4 * math.sin(b + PI))
    P.j("hip_l", -0.3 * max(0.0, math.sin(b)))
    P.j("hip_r", -0.3 * max(0.0, -math.sin(b)))
    P.j("kn_l", 0.5 * max(0.0, math.sin(b)))
    P.j("kn_r", 0.5 * max(0.0, -math.sin(b)))
    P.j("head", 0, 0, 0.2 * math.sin(b))
    P.yaw += 0.5 * math.sin(lt * 0.9 + a.phase)
    P.nscale["mouth"] = 1.8


def h_cheer(a, P, p, lt, dur, t):
    b = lt * TAU * 1.6 + a.phase
    P.lift += 0.18 * abs(math.sin(b / 2)) * a.stride
    P.j("sh_l", -0.2, 0, 2.7 + 0.15 * math.sin(b * 2))
    P.j("sh_r", -0.2, 0, -2.7 - 0.15 * math.sin(b * 2))
    P.j("el_l", 0, 0, 0.3)
    P.j("el_r", 0, 0, -0.3)
    P.j("head", -0.15)
    P.nscale["mouth"] = 2.4


def h_point(a, P, p, lt, dur, t):
    h_idle(a, P, p, lt, dur, t)
    P.j("sh_r", -1.45 - 0.05 * math.sin(lt * 2), 0.0, -0.15)
    P.j("el_r", -0.1)
    P.j("head", 0, -0.25)
    P.nscale["mouth"] = 1.4


def h_think(a, P, p, lt, dur, t):
    P.j("sh_r", -0.65, 0, 0.35)
    P.j("el_r", -2.25)
    P.j("sh_l", -0.35, 0, -0.15)
    P.j("el_l", -1.45, 0, 0.0)
    P.j("head", -0.12 + 0.04 * math.sin(lt * 1.5), 0.15, 0.15)
    P.j("spine", 0.03)


def h_scared(a, P, p, lt, dur, t):
    sh = math.sin(lt * 38) * 0.03
    P.j("sh_l", -1.1, 0, 0.5)
    P.j("sh_r", -1.1, 0, -0.5)
    P.j("el_l", -1.7)
    P.j("el_r", -1.7)
    P.j("spine", -0.15)
    P.j("head", -0.1 + sh)
    P.j("kn_l", 0.25)
    P.j("kn_r", 0.25)
    P.lift -= 0.04
    P.pos += side(P.yaw) * sh
    _move(a, P, -0.6 * ease_out(p))
    P.nscale["eye_l"] = 1.35
    P.nscale["eye_r"] = 1.35
    P.nscale["mouth"] = 2.6


def h_fall(a, P, p, lt, dur, t):
    q = clamp01(lt / min(1.0, dur * 0.6))
    f = ease_in(q)
    P.pitch = 1.5 * f
    P.lift += 0.17 * f
    P.j("sh_l", -2.6 * f, 0, 0.4 * f)
    P.j("sh_r", -2.6 * f, 0, -0.4 * f)
    P.j("hip_l", 0.2 * f)
    P.j("kn_l", 0.3 * f)
    P.nscale["eye_l"] = 1.3
    P.nscale["eye_r"] = 1.3
    P.nscale["mouth"] = 2.0


def h_sit(a, P, p, lt, dur, t):
    c = smooth(lt / 0.6)
    P.lift -= 0.62 * c
    P.j("hip_l", -1.45 * c, 0, 0.12 * c)
    P.j("hip_r", -1.45 * c, 0, -0.12 * c)
    P.j("kn_l", 0.4 * c)
    P.j("kn_r", 0.4 * c)
    P.j("sh_l", -0.5 * c)
    P.j("sh_r", -0.5 * c)
    P.j("el_l", -0.4 * c)
    P.j("el_r", -0.4 * c)
    P.j("spine", -0.1 * c)
    P.j("head", 0, 0.3 * math.sin(t * 0.5 + a.phase))


def h_sleep(a, P, p, lt, dur, t):
    c = smooth(lt / 0.8)
    P.pitch = -1.52 * c
    P.lift += 0.16 * c
    P.j("spine", 0.02 * math.sin(t * 2))
    P.j("sh_l", 0, 0, 0.1)
    P.j("sh_r", 0, 0, -0.1)
    P.j("head", 0, 0.4 * c)
    P.nscale["eye_l"] = 1 - 0.9 * c
    P.nscale["eye_r"] = 1 - 0.9 * c
    P.nscale["mouth"] = 0.6


def h_talk(a, P, p, lt, dur, t):
    h_idle(a, P, p, lt, dur, t)
    P.j("head", 0.07 * math.sin(lt * 5), 0.1 * math.sin(lt * 1.3))
    P.j("sh_r", -0.55 + 0.25 * math.sin(lt * 2.5), 0, -0.1)
    P.j("el_r", -1.0 + 0.4 * math.sin(lt * 3.1))
    P.j("sh_l", -0.2 + 0.15 * math.sin(lt * 1.7 + 1))
    P.j("el_l", -0.5)
    P.nscale["mouth"] = 1 + 1.6 * abs(math.sin(lt * 11))


def h_fly(a, P, p, lt, dur, t):
    up = smooth(lt / 1.0)
    P.lift += (1.8 * up + 0.12 * math.sin(lt * 2.5)) * a.stride
    P.pitch = 1.25 * up
    P.pivot = np.array((0, 0.9, 0), F32)
    P.j("sh_r", -2.9 * up, 0, -0.2)
    P.j("sh_l", -0.2 * up, 0, 0.25)
    P.j("hip_l", 0.15 * up)
    P.j("hip_r", 0.05 * up)
    P.j("cape", 1.2 * up + 0.15 * math.sin(lt * 14))
    _move(a, P, 2.6 * lt * a.stride)


def h_swim(a, P, p, lt, dur, t):
    P.pitch = 1.35
    P.pivot = np.array((0, 0.9, 0), F32)
    P.lift += 0.2 + 0.05 * math.sin(lt * 3)
    P.j("sh_l", -(lt * 5 % TAU))
    P.j("sh_r", -((lt * 5 + PI) % TAU))
    P.j("hip_l", 0.25 * math.sin(lt * 9))
    P.j("hip_r", -0.25 * math.sin(lt * 9))
    _move(a, P, 0.9 * lt)


def h_look(a, P, p, lt, dur, t):
    P.j("head", -0.05, 0.75 * math.sin(lt * 1.3), 0)
    P.j("sh_r", -2.3, 0, -0.3)
    P.j("el_r", -1.3)
    P.j("spine", 0, 0.2 * math.sin(lt * 1.3))
    P.j("el_l", -0.15)


def h_clap(a, P, p, lt, dur, t):
    c = abs(math.sin(lt * 8))
    P.j("sh_l", -1.15, 0, -0.45 + 0.3 * c)
    P.j("sh_r", -1.15, 0, 0.45 - 0.3 * c)
    P.j("el_l", -0.7)
    P.j("el_r", -0.7)
    P.lift += 0.03 * abs(math.sin(lt * 4))
    P.nscale["mouth"] = 1.8


def h_bow(a, P, p, lt, dur, t):
    c = math.sin(PI * clamp01(lt / min(dur, 2.0)))
    P.j("spine", 0.9 * c)
    P.j("head", 0.2 * c)
    P.j("sh_r", -0.5 * c, 0, 0.3 * c)
    P.j("el_r", -1.3 * c)
    P.j("sh_l", 0.3 * c)


def h_spin(a, P, p, lt, dur, t):
    P.yaw += TAU * 2 * ease_io(p)
    P.j("sh_l", 0, 0, 1.3)
    P.j("sh_r", 0, 0, -1.3)
    P.lift += 0.05 * math.sin(PI * p)


def h_attack(a, P, p, lt, dur, t):
    per = 0.9
    q = (lt % per) / per
    sw = ease_in(q / 0.4) if q < 0.4 else 1 - smooth((q - 0.4) / 0.6)
    P.j("sh_r", -2.8 + 2.5 * sw, 0, -0.2)
    P.j("el_r", -0.4)
    P.j("spine", 0.25 * sw, -0.3 * sw)
    P.j("hip_l", -0.4)
    P.j("kn_r", 0.3)
    _move(a, P, 0.3 * ease_out(p))
    P.nscale["mouth"] = 1.5


def h_push(a, P, p, lt, dur, t):
    _walk_legs(P, lt * TAU * 1.1, 0.35, 0.5, 0.0)
    P.j("spine", 0.35)
    P.j("sh_l", -1.35)
    P.j("sh_r", -1.35)
    P.j("el_l", -0.3)
    P.j("el_r", -0.3)
    _move(a, P, 0.5 * lt)


def h_kneel(a, P, p, lt, dur, t):
    c = smooth(lt / 0.6)
    P.lift -= 0.4 * c
    P.j("hip_l", -1.5 * c)
    P.j("kn_l", 1.5 * c)
    P.j("hip_r", 0.1 * c)
    P.j("kn_r", 1.55 * c)
    P.j("head", 0.35 * c)
    P.j("sh_l", -0.6 * c)
    P.j("el_l", -1.2 * c)
    P.j("sh_r", -0.6 * c)
    P.j("el_r", -1.2 * c)


def h_climb(a, P, p, lt, dur, t):
    b = lt * TAU * 1.2
    P.lift += 0.5 * lt * a.stride
    P.j("sh_l", -2.8 + 0.5 * math.sin(b))
    P.j("sh_r", -2.8 - 0.5 * math.sin(b))
    P.j("hip_l", -0.6 * max(0.0, math.sin(b)))
    P.j("hip_r", -0.6 * max(0.0, -math.sin(b)))
    P.j("kn_l", 0.9 * max(0.0, math.sin(b)))
    P.j("kn_r", 0.9 * max(0.0, -math.sin(b)))


def _float(a, P, lt, t):
    P.lift += a.model.hover * 0.6 + 0.12 * math.sin(t * 2.0 + a.phase)
    P.j("sh_l", 0, 0, 0.3 * math.sin(t * 2.2 + a.phase))
    P.j("sh_r", 0, 0, -0.3 * math.sin(t * 2.2 + a.phase + 1))
    P.roll += 0.06 * math.sin(t * 1.3 + a.phase)


def h_scare(a, P, p, lt, dur, t):
    _float(a, P, lt, t)
    c = ease_out(p)
    P.pos += fwd(P.yaw) * 1.6 * c
    P.scale *= 1 + 0.25 * c
    P.j("sh_l", 0, 0, 1.6 * c)
    P.j("sh_r", 0, 0, -1.6 * c)
    P.nscale["mouth"] = 1 + 1.8 * c
    P.nscale["eye_l"] = 1 + 0.4 * c
    P.nscale["eye_r"] = 1 + 0.4 * c


# ------------------------------------------------------------------ quadrúpedes
def q_idle(a, P, p, lt, dur, t):
    ph = t + a.phase
    P.j("neck", 0.06 * math.sin(ph * 0.8))
    P.j("head", 0.0, 0.35 * math.sin(ph * 0.5) * smooth(lt / 1.5), 0.08 * math.sin(ph * 0.7))
    P.j("tail1", 0.0, 0.35 * math.sin(ph * 2.2))
    P.j("tail2", 0.0, 0.25 * math.sin(ph * 2.2 - 0.6))
    P.scale *= np.array((1, 1 + 0.012 * math.sin(ph * 3), 1), F32)
    P.j("trunk1", 0.15 * math.sin(ph * 1.3))
    P.j("trunk2", 0.25 * math.sin(ph * 1.3 - 0.5))


def q_walk(a, P, p, lt, dur, t, run=False):
    leg = a.model.height * 0.4
    freq = (1.5 if not run else 2.4) / math.sqrt(max(a.stride * leg, 0.08) / 0.25)
    ph = lt * TAU * freq
    amp = 0.4 if not run else 0.75
    phases = (
        {"fl": 0.0, "br": 0.0, "fr": PI, "bl": PI}
        if not run
        else {"fl": 0.0, "fr": 0.5, "bl": PI, "br": PI + 0.5}
    )
    for k, off in phases.items():
        s = math.sin(ph + off)
        P.j(f"leg_{k}", -amp * s)
        P.j(f"knee_{k}", 0.55 * max(0.0, math.cos(ph + off)) * (1 if k[0] == "f" else -0.7))
    P.lift += (0.02 if not run else 0.06) * abs(math.cos(ph)) * a.stride
    if run:
        P.pitch = 0.06 * math.sin(ph)
    P.j("neck", 0.05 * math.sin(ph * 2))
    P.j("tail1", 0.0, 0.3 * math.sin(ph))
    P.j("trunk1", 0.2 * math.sin(ph))
    speed = (leg * 2.6 if not run else leg * 6.5) * a.stride
    _move(a, P, speed * lt)


def q_run(a, P, p, lt, dur, t):
    q_walk(a, P, p, lt, dur, t, run=True)


def q_jump(a, P, p, lt, dur, t):
    n = max(1, round(dur / 1.2))
    per = dur / n
    q = (lt % per) / per if lt < dur else 1.0
    if q < 0.25:
        c = smooth(q / 0.25)
        P.lift -= 0.08 * c * a.stride
        for k in ("fl", "fr", "bl", "br"):
            P.j(f"knee_{k}", 0.5 * c * (1 if k[0] == "f" else -1))
    elif q < 0.8:
        u = (q - 0.25) / 0.55
        P.lift += a.model.height * 0.6 * math.sin(PI * u) * a.stride
        P.pitch = -0.3 * math.cos(PI * u)
        P.j("leg_fl", -0.9)
        P.j("leg_fr", -0.9)
        P.j("leg_bl", 0.9)
        P.j("leg_br", 0.9)
        P.j("tail1", -0.5)
        _move(a, P, a.model.radius * 1.2 * (u if lt < dur else 1.0) / n)
    else:
        c = 1 - smooth((q - 0.8) / 0.2)
        P.lift -= 0.05 * c


def q_sit(a, P, p, lt, dur, t):
    c = smooth(lt / 0.7)
    L = a.model.radius
    P.pivot = np.array((0, 0, L * 0.5), F32)
    P.pitch = -0.5 * c
    P.j("leg_fl", 0.5 * c)
    P.j("leg_fr", 0.5 * c)
    P.j("leg_bl", -1.3 * c)
    P.j("leg_br", -1.3 * c)
    P.j("knee_bl", 1.8 * c)
    P.j("knee_br", 1.8 * c)
    P.j("neck", -0.25 * c)
    P.j("head", 0.25 * c, 0.3 * math.sin(t * 0.6 + a.phase))
    P.j("tail1", 0, 0.4 * math.sin(t * 2.5))


def q_sleep(a, P, p, lt, dur, t):
    c = smooth(lt / 0.8)
    P.lift -= a.model.height * 0.32 * c
    for k in ("fl", "fr"):
        P.j(f"leg_{k}", -1.3 * c)
        P.j(f"knee_{k}", 1.0 * c)
    for k in ("bl", "br"):
        P.j(f"leg_{k}", -1.2 * c)
        P.j(f"knee_{k}", 1.6 * c)
    P.j("neck", 0.6 * c)
    P.j("head", -0.3 * c)
    P.scale *= np.array((1, 1 + 0.03 * math.sin(t * 2), 1), F32)
    P.j("tail1", 0.5 * c, 0.6 * c)


def q_wag(a, P, p, lt, dur, t):
    q_idle(a, P, p, lt, dur, t)
    P.j("tail1", -0.3, 0.8 * math.sin(lt * 16))
    P.j("tail2", 0, 0.5 * math.sin(lt * 16 - 0.8))
    P.lift += 0.03 * abs(math.sin(lt * 5)) * a.stride
    P.j("head", 0, 0, 0.25 * math.sin(lt * 2))


def q_eat(a, P, p, lt, dur, t):
    P.j("neck", 0.9 + 0.12 * math.sin(lt * 6))
    P.j("head", 0.2)
    P.j("tail1", 0, 0.3 * math.sin(lt * 2))


def q_look(a, P, p, lt, dur, t):
    P.j("head", -0.1, 0.8 * math.sin(lt * 1.2), 0.1)
    P.j("neck", -0.15)


def q_howl(a, P, p, lt, dur, t):
    c = smooth(lt / 0.6)
    P.j("neck", -0.8 * c)
    P.j("head", -0.4 * c + 0.05 * math.sin(lt * 10))
    P.pitch = -0.15 * c


# ------------------------------------------------------------------ aves, peixes, criaturas
def _flap(P, lt, speed=14.0, amp=0.9):
    s = math.sin(lt * speed)
    P.j("wing_l", 0, 0, amp * s)
    P.j("wing_r", 0, 0, -amp * s)


def b_idle(a, P, p, lt, dur, t):
    if "flies" in a.model.tags and a.model.hover > 0.5:
        return b_fly(a, P, p, lt, dur, t, travel=False)
    P.j("head", 0.15 * max(0.0, math.sin(t * 2.3 + a.phase)) ** 8, 0.4 * math.sin(t * 0.9 + a.phase))
    if math.sin(t * 0.8 + a.phase) > 0.92:
        _flap(P, lt, 20, 0.5)


def b_fly(a, P, p, lt, dur, t, travel=True):
    if "walker" in a.model.tags and a.cat == "bird":
        return b_hop(a, P, p, lt, dur, t)
    up = smooth(lt / 0.8) if a.base[1] < 0.5 else 1.0
    P.lift += (2.2 * up + 0.25 * math.sin(lt * 2.5 + a.phase)) * (1 if a.cat != "insect" else 0.6)
    P.pitch = -0.12 * math.cos(lt * 2.5)
    _flap(P, lt, 13 if a.cat == "bird" else 30, 0.95)
    P.j("leg_l", 0.9)
    P.j("leg_r", 0.9)
    if travel:
        _move(a, P, 3.0 * lt * max(a.stride, 0.4))


def b_circle(a, P, p, lt, dur, t):
    r = max(1.6, a.model.radius * 4)
    ang = lt * 1.1 + a.phase
    P.pos += np.array((math.cos(ang) * r, 0, math.sin(ang) * r), F32)
    P.yaw = -ang
    if a.cat in ("bird", "insect", "person") or "flies" in a.model.tags:
        P.lift += 2.4 + 0.2 * math.sin(lt * 3)
        _flap(P, lt, 13, 0.8)
        P.roll = -0.3
    if a.cat in ("fish", "creature"):
        P.j("tail1", 0, 0.45 * math.sin(lt * 9))
        _tentacles(a, P, t, 1.0)
    if "wheels" in a.model.tags:
        P.travel += r * lt * 1.1


def b_hop(a, P, p, lt, dur, t):
    q = (lt * 2.2) % 1.0
    P.lift += 0.12 * math.sin(PI * q) * a.stride
    _move(a, P, 0.5 * lt * a.stride)
    P.j("head", 0.1 * math.sin(lt * 9))
    P.roll = 0.08 * math.sin(lt * 4.4 * PI / 2)


def b_peck(a, P, p, lt, dur, t):
    q = (lt * 2.0) % 1.0
    P.pitch = 0.45 * max(0.0, math.sin(TAU * q)) ** 2
    P.j("head", 0.2 * max(0.0, math.sin(TAU * q)))


def f_swim(a, P, p, lt, dur, t, travel=True):
    P.lift += a.model.hover + 0.15 * math.sin(lt * 1.5 + a.phase)
    P.j("tail1", 0, 0.45 * math.sin(lt * 8 + a.phase))
    P.yaw += 0.06 * math.sin(lt * 8 + a.phase + 1)
    P.roll = 0.05 * math.sin(lt * 1.5)
    _tentacles(a, P, t, 1.0)
    for i in range(12):
        P.j(f"seg{i}", 0, 0.45 * math.sin(lt * 5 - i * 0.7) if i else 0.15 * math.sin(lt * 5))
    if "glow" in a.model.tags:
        k = 0.5 + 0.5 * math.sin(lt * 3)
        P.scale *= np.array((1 + 0.12 * k, 1 - 0.1 * k, 1 + 0.12 * k), F32)
    if travel:
        speed = 1.2 * max(a.stride, 0.3) if a.cat != "snake" else 0.8
        _move(a, P, speed * lt)


def f_idle(a, P, p, lt, dur, t):
    f_swim(a, P, p, lt, dur, t, travel=False)


def f_jump(a, P, p, lt, dur, t):
    """Peixe/golfinho salta em arco."""
    n = max(1, round(dur / 1.6))
    per = dur / n
    q = (lt % per) / per if lt < dur else 1.0
    h = max(1.2, a.model.radius * 1.6)
    P.lift += h * math.sin(PI * q) - 0.2
    P.pitch = -1.1 * math.cos(PI * q)
    P.j("tail1", 0, 0.4 * math.sin(lt * 10))
    _move(a, P, a.model.radius * 2.2 * (q if lt < dur else 1.0) / n + 0.0)


def _tentacles(a, P, t, amp):
    for i in range(8):
        w = math.sin(t * 2.2 + i * 0.8 + a.phase) * 0.25 * amp
        P.j(f"tent{i}a", w, 0, w)
        P.j(f"tent{i}b", w * 1.3, 0, 0)
        P.j(f"tent{i}c", w * 1.6, 0, 0)


# ------------------------------------------------------------------ objetos (genéricas)
def o_idle(a, P, p, lt, dur, t):
    if a.cat == "person":
        return h_idle(a, P, p, lt, dur, t)
    if a.cat == "ghost":
        return _float(a, P, lt, t)
    if a.cat == "animal":
        return q_idle(a, P, p, lt, dur, t)
    if a.cat in ("bird", "insect"):
        return b_idle(a, P, p, lt, dur, t)
    if a.cat in ("fish", "creature", "snake"):
        return f_idle(a, P, p, lt, dur, t)
    if a.model.hover > 0.2 and "planet" not in a.model.tags:
        P.lift += 0.08 * math.sin(t * 1.6 + a.phase)
        P.yaw += 0.15 * math.sin(t * 0.6 + a.phase)


def o_spin(a, P, p, lt, dur, t):
    P.yaw += lt * (2.2 if a.model.height < 3 else 0.5)
    o_idle_hover(a, P, t)


def o_idle_hover(a, P, t):
    if a.model.hover > 0.2:
        P.lift += 0.06 * math.sin(t * 1.6 + a.phase)


def o_bounce(a, P, p, lt, dur, t):
    per = 0.75
    q = (lt % per) / per
    h = max(0.5, a.model.height * 0.9)
    P.lift += h * 4 * q * (1 - q)
    edge = min(q, 1 - q)
    P.squash = 0.22 * max(0.0, 1 - edge / 0.09) - 0.08 * math.sin(PI * q) ** 2
    if a.cat == "person":
        h_jump(a, P, p, lt, dur, t)


def o_float(a, P, p, lt, dur, t):
    up = smooth(lt / 1.2)
    P.lift += (0.6 + max(0.0, a.model.hover * 0.3)) * up + 0.15 * math.sin(t * 1.8 + a.phase)
    P.yaw += 0.4 * lt
    P.roll = 0.08 * math.sin(t * 1.3 + a.phase)
    if a.cat == "person":
        P.j("sh_l", 0, 0, 0.6 * up)
        P.j("sh_r", 0, 0, -0.6 * up)
        P.j("hip_l", -0.2 * up)
        P.j("kn_l", 0.4 * up)


def o_fall(a, P, p, lt, dur, t):
    """Cai do céu, quica e assenta."""
    q = clamp01(lt / min(dur, 1.6))
    h0 = 7.0 + a.model.height
    P.lift += h0 * (1 - bounce_out(q))
    impact = (1 - q) * 0.25 if q > 0.35 else 0.0
    P.squash = impact * abs(math.sin(q * 18))
    P.roll += (1 - q) * 0.8 * math.sin(a.phase + 1)


def o_grow(a, P, p, lt, dur, t):
    P.scale *= max(0.001, back_out(clamp01(lt / min(dur, 1.2))))


def o_pop(a, P, p, lt, dur, t):
    P.scale *= max(0.001, elastic(clamp01(lt / min(dur, 0.9))))
    o_idle(a, P, p, lt, dur, t)


def o_shrink(a, P, p, lt, dur, t):
    q = clamp01(lt / min(dur, 1.0))
    P.scale *= max(0.001, 1 - ease_in(q))
    if q >= 1:
        P.hidden = True


def o_vanish(a, P, p, lt, dur, t):
    q = clamp01(lt / min(dur, 1.0))
    P.scale *= max(0.001, 1 - ease_in(q))
    P.yaw += 6 * ease_in(q)
    P.lift += 0.6 * q
    P.emit = 1 + 3 * q
    if q >= 1:
        P.hidden = True


def o_appear(a, P, p, lt, dur, t):
    q = clamp01(lt / min(dur, 1.0))
    P.scale *= max(0.001, back_out(q))
    P.yaw += 4 * (1 - ease_out(q))
    o_idle(a, P, p, lt, dur, t)


def o_shake(a, P, p, lt, dur, t):
    k = 0.06 * (1 - 0.3 * p)
    P.pos += np.array((math.sin(lt * 47) * k, 0, math.cos(lt * 39) * k * 0.6), F32)
    P.roll += math.sin(lt * 31) * 0.06
    o_idle(a, P, p, lt, dur, t)


def o_pulse(a, P, p, lt, dur, t):
    s = 1 + 0.12 * math.sin(lt * 6)
    P.scale *= np.array((s, s, s), F32)
    P.emit = 1 + 0.8 * max(0.0, math.sin(lt * 6))
    o_idle(a, P, p, lt, dur, t)


def o_wobble(a, P, p, lt, dur, t):
    P.roll += 0.25 * math.sin(lt * 9) * math.exp(-lt * 0.6)
    P.pitch += 0.12 * math.sin(lt * 7) * math.exp(-lt * 0.6)


def o_orbit(a, P, p, lt, dur, t):
    r = max(1.5, a.model.radius * 2.5)
    ang = lt * 1.3 + a.phase
    P.pos += np.array((math.cos(ang) * r, 0, math.sin(ang) * r), F32)
    P.yaw += lt * 2
    P.lift += 0.4 * math.sin(ang)


def o_roll(a, P, p, lt, dur, t):
    speed = 1.6
    d = speed * lt
    P.pos += side(P.yaw) * d
    r = max(0.2, a.model.height / 2)
    P.pivot = np.array((0, r, 0), F32)
    P.roll = -d / r


def o_tumble(a, P, p, lt, dur, t):
    """Caixa tomba de face em face."""
    size = max(0.3, a.model.height)
    per = 0.6
    n = lt / per
    k = int(n)
    q = ease_io(n - k)
    P.pos += side(P.yaw) * size * k
    P.pivot = np.array((size / 2, 0, 0), F32)
    P.roll = -PI / 2 * q
    P.lift += 0.0


def o_slide(a, P, p, lt, dur, t):
    P.pos += side(P.yaw) * 2.5 * ease_io(p)
    P.roll = -0.15 * math.sin(PI * p)


def o_rise(a, P, p, lt, dur, t):
    P.lift += 3.0 * ease_io(p)
    P.yaw += 0.6 * p
    if "rocket" in a.model.tags:
        o_launch(a, P, p, lt, dur, t)


def o_sink(a, P, p, lt, dur, t):
    P.lift -= (a.model.height + 0.3) * ease_in(p)
    P.roll += 0.1 * math.sin(lt * 6) * p


def o_fly(a, P, p, lt, dur, t):
    if a.cat in ("bird", "insect"):
        return b_fly(a, P, p, lt, dur, t)
    if a.cat == "person":
        return h_fly(a, P, p, lt, dur, t)
    if a.cat == "animal" and "flies" in a.model.tags:
        up = smooth(lt / 1.0)
        P.lift += 2.5 * up + 0.2 * math.sin(lt * 2)
        _flap(P, lt, 6, 0.7)
        for k in ("fl", "fr", "bl", "br"):
            P.j(f"leg_{k}", 0.6 * up)
        _move(a, P, 3.5 * lt)
        return None
    P.lift += max(2.5, a.model.hover) + 0.2 * math.sin(lt * 2)
    P.fire = True
    _move(a, P, 4.0 * lt)
    P.roll = -0.1 * math.sin(lt)
    return None


def o_approach(a, P, p, lt, dur, t):
    P.yaw = a.face_cam
    if a.cat == "person":
        return h_walk(a, P, p, lt, dur, t)
    if a.cat == "animal":
        return q_walk(a, P, p, lt, dur, t)
    if a.cat in ("fish", "creature", "snake"):
        return f_swim(a, P, p, lt, dur, t)
    o_idle(a, P, p, lt, dur, t)
    P.pos += fwd(P.yaw) * 2.2 * ease_io(p)
    return None


def o_retreat(a, P, p, lt, dur, t):
    P.yaw = a.face_cam + PI
    return o_approach(a, P, p, lt, dur, t) if a.cat in ("person", "animal") else _retreat_obj(a, P, p)


def _retreat_obj(a, P, p):
    P.pos += fwd(P.yaw) * 2.5 * ease_io(p)
    P.scale *= 1 - 0.3 * p


def o_swing(a, P, p, lt, dur, t):
    P.pivot = np.array((0, a.model.height, 0), F32)
    P.roll = 0.5 * math.sin(lt * 2.8)


def o_flip(a, P, p, lt, dur, t):
    q = clamp01(lt / min(dur, 1.2))
    P.lift += a.model.height * 1.2 * math.sin(PI * q)
    P.pivot = np.array((0, a.model.height / 2, 0), F32)
    P.pitch = -TAU * ease_io(q)


def o_glow(a, P, p, lt, dur, t):
    P.emit = 1.5 + 1.5 * (0.5 + 0.5 * math.sin(lt * 4))
    P.light = P.emit
    o_idle(a, P, p, lt, dur, t)


def o_open(a, P, p, lt, dur, t):
    c = ease_io(clamp01(lt / min(dur, 1.4)))
    P.j("door", 0, -1.6 * c, 0)
    P.j("lid", -1.7 * c)
    P.npos["door_l"] = np.array((-0.72 * c, 0, 0), F32)
    P.npos["door_r"] = np.array((0.72 * c, 0, 0), F32)
    P.light = 1 + 3 * c


def o_drive(a, P, p, lt, dur, t):
    if a.cat != "prop":
        return o_approach(a, P, p, lt, dur, t) if a.cat != "person" else h_walk(a, P, p, lt, dur, t)
    speed = 5.0 if "wheels" in a.model.tags else 3.0
    _move(a, P, speed * lt)
    P.lift += 0.02 * math.sin(lt * 17)
    if "boat" in a.model.tags:
        P.roll = 0.08 * math.sin(lt * 1.6)
        P.pitch = 0.05 * math.sin(lt * 1.3)
    return None


def o_launch(a, P, p, lt, dur, t):
    q = clamp01(lt / dur)
    P.fire = True
    shake = 0.03 * (1 - q) if q < 0.3 else 0.0
    P.pos += np.array((math.sin(lt * 60) * shake, 0, 0), F32)
    if q > 0.15:
        u = (q - 0.15) / 0.85
        P.lift += 40 * u * u


def o_explode(a, P, p, lt, dur, t):
    """Sozinho: treme, incha e some num estouro de faíscas. Em grupo: as peças voam."""
    q = clamp01(lt / dur)
    if a.gn > 1:
        return g_explode(a, P, p, lt, dur, t)
    if q < 0.35:
        k = q / 0.35
        P.pos += np.array((math.sin(lt * 50) * 0.04 * k, 0, 0), F32)
        P.scale *= 1 + 0.15 * k
    elif q < 0.45:
        P.scale *= 1.15 + (q - 0.35) * 6
        P.emit = 3
    else:
        P.hidden = True
    return None


def o_sway(a, P, p, lt, dur, t):
    P.pivot = np.zeros(3, F32)
    P.roll = 0.06 * math.sin(t * 1.4 + a.phase)
    P.pitch = 0.04 * math.sin(t * 1.1 + a.phase)


def o_blink(a, P, p, lt, dur, t):
    P.emit = 0.2 if math.sin(lt * 9) > 0 else 2.0
    o_idle(a, P, p, lt, dur, t)


# ------------------------------------------------------------------ grupos
def g_stack(a, P, p, lt, dur, t):
    """As peças caem uma a uma formando a torre/pirâmide (posição final = formação)."""
    n = max(a.gn, 1)
    start = dur * 0.8 * a.gi / n
    q = clamp01((lt - start) / min(0.9, dur * 0.35))
    if lt < start:
        P.scale *= 0.001
        return
    P.lift += 6.0 * (1 - bounce_out(q))
    P.squash = 0.18 * (1 - q) * (q > 0.36)
    P.yaw += (1 - ease_out(q)) * 1.5 * math.sin(a.phase)


def g_build(a, P, p, lt, dur, t):
    n = max(a.gn, 1)
    start = dur * 0.75 * a.gi / n
    q = ease_io(clamp01((lt - start) / min(1.1, dur * 0.4)))
    off = a.scatter
    P.pos += off * (1 - q)
    P.lift += 3.5 * math.sin(PI * q) * (1 - q) + (1 - q) * 2.0
    P.yaw += (1 - q) * 3.0
    P.roll += (1 - q) * 1.5
    if lt < start:
        P.scale *= 0.001


def g_domino(a, P, p, lt, dur, t):
    start = dur * 0.15 + a.gi * min(0.22, dur * 0.7 / max(a.gn, 1))
    q = clamp01((lt - start) / 0.35)
    P.pivot = np.array((0, 0, -0.05), F32)  # quina de trás: tomba para longe, em cima da próxima peça
    P.pitch = -(PI / 2 - 0.35) * ease_in(q)


def g_explode(a, P, p, lt, dur, t):
    t_boom = dur * 0.35
    if lt < t_boom:
        k = lt / t_boom
        P.pos += np.array((math.sin(lt * 50 + a.phase) * 0.03 * k, 0, 0), F32)
        return
    s = lt - t_boom
    v = a.scatter / max(np.linalg.norm(a.scatter), 1e-3) * (4.0 + 2.0 * math.sin(a.phase * 3))
    up = 5.5 + 2.5 * math.cos(a.phase * 2)
    y_base = a.base[1]
    y = y_base + up * s - 4.9 * s * s
    land = y < 0
    if land:
        tl = (up + math.sqrt(up * up + 19.6 * y_base)) / 9.8
        s = tl
        y = 0.0
    P.pos += v * s
    P.lift += y - y_base
    P.yaw += s * 4
    P.roll += s * 3 * math.sin(a.phase)


def g_wave(a, P, p, lt, dur, t):
    ph = lt * 4.0 - a.slot[0] * 1.2 - a.slot[2] * 0.8
    P.lift += max(0.0, math.sin(ph)) * max(0.4, a.model.height * 0.6)
    if a.cat == "person":
        P.j("sh_l", 0, 0, 2.6 * max(0.0, math.sin(ph)))
        P.j("sh_r", 0, 0, -2.6 * max(0.0, math.sin(ph)))


def g_rain(a, P, p, lt, dur, t):
    per = 1.6
    q = ((lt + a.phase * 0.5) % per) / per
    P.pos += a.scatter * 0.6
    P.lift += 8 * (1 - q)
    P.yaw += lt * 3 + a.phase
    P.roll += lt * 2


def g_scatter(a, P, p, lt, dur, t):
    q = ease_io(p)
    P.pos += a.scatter * q
    P.lift += 1.5 * math.sin(PI * q)
    P.yaw += 2 * q


def g_assemble(a, P, p, lt, dur, t):
    q = ease_io(clamp01(lt / min(dur * 0.8, 2.5)))
    P.pos += a.scatter * (1 - q)
    P.lift += 1.5 * math.sin(PI * q)
    P.yaw += 2 * (1 - q)


def g_circle(a, P, p, lt, dur, t):
    rel = a.slot.copy()
    rel[1] = 0
    ang = lt * 0.8
    c, s = math.cos(ang), math.sin(ang)
    nx, nz = rel[0] * c - rel[2] * s, rel[0] * s + rel[2] * c
    P.pos += np.array((nx - rel[0], 0, nz - rel[2]), F32)
    P.yaw -= ang
    o_idle(a, P, p, lt, dur, t)


ActionFn = Callable[..., None]

# ação → {categoria: função}. "*" vale para qualquer categoria sem função específica.
ACTIONS: dict[str, dict[str, ActionFn]] = {
    "idle": {"*": o_idle},
    "walk": {
        "person": h_walk,
        "ghost": h_walk,
        "animal": q_walk,
        "bird": b_hop,
        "insect": b_hop,
        "fish": f_swim,
        "creature": f_swim,
        "snake": f_swim,
        "*": o_drive,
    },
    "run": {
        "person": h_run,
        "animal": q_run,
        "bird": b_fly,
        "insect": b_fly,
        "fish": f_swim,
        "creature": f_swim,
        "snake": f_swim,
        "*": o_drive,
    },
    "jump": {"person": h_jump, "animal": q_jump, "fish": f_jump, "bird": b_hop, "*": o_bounce},
    "wave": {"person": h_wave, "ghost": h_wave, "animal": q_wag, "*": o_wobble},
    "dance": {"person": h_dance, "ghost": h_dance, "animal": q_wag, "*": o_bounce},
    "cheer": {"person": h_cheer, "animal": q_wag, "*": o_bounce},
    "point": {"person": h_point, "*": o_idle},
    "think": {"person": h_think, "*": o_idle},
    "scared": {"person": h_scared, "animal": q_look, "*": o_shake},
    "fall": {"person": h_fall, "*": o_fall},
    "sit": {"person": h_sit, "animal": q_sit, "*": o_idle},
    "sleep": {"person": h_sleep, "animal": q_sleep, "*": o_idle},
    "talk": {"person": h_talk, "ghost": h_talk, "animal": q_look, "*": o_wobble},
    "fly": {"*": o_fly},
    "swim": {"person": h_swim, "*": f_swim},
    "look": {"person": h_look, "animal": q_look, "*": o_idle},
    "clap": {"person": h_clap, "*": o_bounce},
    "bow": {"person": h_bow, "*": o_wobble},
    "attack": {"person": h_attack, "animal": q_jump, "*": o_shake},
    "push": {"person": h_push, "*": o_slide},
    "kneel": {"person": h_kneel, "*": o_idle},
    "climb": {"person": h_climb, "*": o_rise},
    "scare": {"ghost": h_scare, "person": h_scared, "*": o_approach},
    "wag": {"animal": q_wag, "*": o_wobble},
    "eat": {"animal": q_eat, "bird": b_peck, "*": o_wobble},
    "howl": {"animal": q_howl, "*": o_idle},
    "circle": {"*": b_circle},
    "spin": {"person": h_spin, "ghost": h_spin, "*": o_spin},
    "bounce": {"*": o_bounce},
    "float": {"ghost": o_idle, "*": o_float},
    "drop": {"*": o_fall},
    "grow": {"*": o_grow},
    "pop": {"*": o_pop},
    "appear": {"*": o_appear},
    "shrink": {"*": o_shrink},
    "vanish": {"*": o_vanish},
    "shake": {"*": o_shake},
    "pulse": {"*": o_pulse},
    "wobble": {"*": o_wobble},
    "orbit": {"*": o_orbit},
    "roll": {"*": o_roll},
    "tumble": {"*": o_tumble},
    "slide": {"*": o_slide},
    "rise": {"*": o_rise},
    "sink": {"*": o_sink},
    "approach": {"*": o_approach},
    "retreat": {"*": o_retreat},
    "swing": {"*": o_swing},
    "flip": {"*": o_flip},
    "glow": {"*": o_glow},
    "open": {"*": o_open},
    "drive": {"*": o_drive},
    "launch": {"*": o_launch},
    "explode": {"*": o_explode},
    "sway": {"*": o_sway},
    "blink": {"*": o_blink},
    # grupos
    "stack": {"*": g_stack},
    "build": {"*": g_build},
    "domino": {"*": g_domino},
    "group_wave": {"*": g_wave},
    "rain": {"*": g_rain},
    "scatter": {"*": g_scatter},
    "assemble": {"*": g_assemble},
    "carousel": {"*": g_circle},
}

GROUP_ACTIONS = {"stack", "build", "domino", "group_wave", "rain", "scatter", "assemble", "carousel"}
MOVING = {
    "walk",
    "run",
    "fly",
    "swim",
    "drive",
    "push",
    "approach",
    "retreat",
    "roll",
    "tumble",
    "slide",
    "attack",
    "jump",
}

CAT_ALIAS = {
    "statue": "prop",
    "building": "prop",
    "vehicle": "prop",
    "nature": "prop",
    "symbol": "prop",
    "space": "prop",
    "science": "prop",
    "food": "prop",
    "block": "prop",
    "ball": "prop",
}


def resolve(action: str, cat: str) -> ActionFn:
    table = ACTIONS.get(action) or ACTIONS["idle"]
    return table.get(cat) or table.get(CAT_ALIAS.get(cat, ""), None) or table["*"]
