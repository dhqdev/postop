"""Biblioteca de modelos 3D montados por código.

Cada modelo é uma hierarquia de nós (juntas) com malhas. As animações giram/deslocam os nós
pelo nome (ex.: "sh_l" = ombro esquerdo), então qualquer pessoa, robô ou fantasma usa as mesmas
ações. Personagens olham para +Z e ficam com os pés em y = 0.
"""

from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass

import numpy as np

from .geom import (
    F32,
    Mesh,
    bolt_points,
    box,
    capsule,
    chamfer_box,
    cone,
    cylinder,
    ellipsoid,
    extrude,
    gear_points,
    heart_points,
    lathe,
    mat4,
    mix_rgb,
    plane,
    sphere,
    star_points,
    torus,
)

PI = math.pi

# paleta base
WHITE = (0.95, 0.95, 0.95)
BLACK = (0.06, 0.06, 0.07)
DARK = (0.16, 0.14, 0.15)
GOLD = (1.0, 0.78, 0.25)
SILVER = (0.78, 0.8, 0.84)
WOOD = (0.55, 0.36, 0.2)
WOOD_DARK = (0.35, 0.22, 0.12)
LEAF = (0.24, 0.6, 0.28)
STONE = (0.6, 0.6, 0.62)
RED = (0.88, 0.2, 0.2)
SKINS = [(1.0, 0.84, 0.7), (0.95, 0.74, 0.58), (0.8, 0.57, 0.4), (0.6, 0.4, 0.27), (0.42, 0.28, 0.19)]
HAIRS = [(0.18, 0.12, 0.08), (0.08, 0.06, 0.05), (0.55, 0.32, 0.14), (0.85, 0.65, 0.3), (0.55, 0.15, 0.08)]
VIVID = [
    (0.95, 0.3, 0.3),
    (1.0, 0.62, 0.2),
    (1.0, 0.85, 0.25),
    (0.35, 0.8, 0.4),
    (0.25, 0.65, 0.95),
    (0.6, 0.4, 0.92),
    (0.95, 0.45, 0.7),
    (0.25, 0.8, 0.8),
]


class Model:
    """Hierarquia de nós. `build()` junta as malhas em um único buffer de vértices."""

    def __init__(self, kind: str = "prop", height: float = 1.0, radius: float = 0.5):
        self.kind = kind
        self.height = height
        self.radius = radius
        self.names: list[str] = []
        self.parent: list[int] = []
        self.pos: list[np.ndarray] = []
        self.rot: list[np.ndarray] = []
        self.parts: list[list[Mesh]] = []
        self.lights: list[tuple[str, tuple, tuple, float, float, bool]] = []
        self.flicker: set[str] = set()
        self.tags: set[str] = set()
        self.hover = 0.0  # altura padrão acima do chão (peixes, fantasmas, naves)
        self.mesh: Mesh | None = None
        self.slices: list[tuple[int, int]] = []
        self.fslices: list[tuple[int, int]] = []

    def node(self, name: str, parent: str | None = None, pos=(0, 0, 0), rot=(0, 0, 0), *meshes: Mesh) -> str:
        self.names.append(name)
        self.parent.append(self.names.index(parent) if parent else -1)
        self.pos.append(np.asarray(pos, F32))
        self.rot.append(np.asarray(rot, F32))
        self.parts.append([m for m in meshes if m is not None])
        return name

    def add(self, name: str, *meshes: Mesh) -> None:
        self.parts[self.names.index(name)].extend(m for m in meshes if m is not None)

    def light(self, node: str, pos, color, power=1.0, radius=4.0, flicker=False) -> None:
        self.lights.append((node, tuple(pos), tuple(color), power, radius, flicker))

    def has(self, name: str) -> bool:
        return name in self.names

    def build(self) -> Model:
        meshes, vs, fs = [], 0, 0
        self.slices, self.fslices = [], []
        for parts in self.parts:
            m = Mesh.merge(*parts)
            meshes.append(m)
            self.slices.append((vs, vs + len(m.v)))
            self.fslices.append((fs, fs + len(m.f)))
            vs += len(m.v)
            fs += len(m.f)
        self.mesh = Mesh.merge(*meshes)
        return self

    def pose(self, root: np.ndarray, rot_off: dict, pos_off: dict, scl_off: dict) -> tuple[np.ndarray, list]:
        """Vértices no mundo para a pose dada (offsets por nome de nó)."""
        assert self.mesh is not None
        V = self.mesh.v
        out = np.empty_like(V)
        mats: list[np.ndarray] = []
        for i, name in enumerate(self.names):
            rr = self.rot[i]
            ro = rot_off.get(name)
            if ro is not None:
                rr = rr + ro
            pp = self.pos[i]
            po = pos_off.get(name)
            if po is not None:
                pp = pp + po
            local = mat4(pp, rr, scl_off.get(name, 1.0))
            p = self.parent[i]
            m = (root if p < 0 else mats[p]) @ local
            mats.append(m)
            s, e = self.slices[i]
            if e > s:
                out[s:e] = V[s:e] @ m[:3, :3].T + m[:3, 3]
        return out, mats


# =================================================================== pessoas
@dataclass
class HumanStyle:
    skin: tuple = SKINS[1]
    shirt: tuple = (0.25, 0.55, 0.9)
    pants: tuple = (0.2, 0.22, 0.3)
    shoes: tuple = (0.15, 0.12, 0.1)
    hair: tuple = HAIRS[0]
    hair_style: str = "short"  # short, long, ponytail, bun, spiky, curly, bald
    hat: str = ""  # cap, tophat, wizard, crown, helmet, astronaut, straw, chef, tiara, hardhat, safari
    hat_color: tuple = (0.85, 0.2, 0.2)
    outfit: str = ""  # dress, robe, coat, armor, suit
    outfit_color: tuple | None = None
    cape: tuple | None = None
    beard: bool = False
    long_sleeves: bool = True
    eye: tuple = (0.12, 0.09, 0.07)
    body: str = "human"  # human, robot, ghost, zombie
    glow: float = 0.0


def humanoid(st: HumanStyle) -> Model:
    if st.body == "robot":
        return robot(st)
    if st.body == "ghost":
        return ghost(st)
    m = Model("person", height=1.75, radius=0.32)
    skin, shirt, pants = st.skin, st.shirt, st.pants
    torso_col = st.outfit_color if st.outfit in ("armor", "suit", "robe") and st.outfit_color else shirt
    spec_t = 0.9 if st.outfit == "armor" else 0.15
    m.node(
        "hips", None, (0, 0.81, 0), (0, 0, 0), ellipsoid(0.15, 0.1, 0.105, pants, nu=12, nv=6).at((0, 0.0, 0))
    )
    m.node(
        "spine",
        "hips",
        (0, 0.06, 0),
        (0, 0, 0),
        lathe(
            [(0.168, -0.07), (0.17, 0.12), (0.19, 0.3), (0.175, 0.41), (0.08, 0.47)],
            torso_col,
            12,
            squash=0.72,
            spec=spec_t,
        ),
    )
    if st.outfit == "coat":
        m.add(
            "spine",
            lathe([(0.21, -0.38), (0.19, 0.0), (0.16, 0.1)], st.outfit_color or WHITE, 12, squash=0.75),
        )
    if st.outfit == "suit":
        m.add("spine", box(0.06, 0.26, 0.02, RED).at((0, 0.26, 0.135), (0.15, 0, 0)))  # gravata
    m.node("neck", "spine", (0, 0.45, 0), (0, 0, 0), cylinder(0.055, 0.08, skin, 8))
    head = [
        ellipsoid(0.17, 0.18, 0.165, skin, nu=14, nv=9).at((0, 0.16, 0)),
        ellipsoid(0.022, 0.026, 0.024, mix_rgb(skin, (0.6, 0.3, 0.2), 0.12), nu=6, nv=4).at((0, 0.13, 0.168)),
        ellipsoid(0.03, 0.045, 0.02, skin, nu=6, nv=4).at((0.168, 0.15, 0)),
        ellipsoid(0.03, 0.045, 0.02, skin, nu=6, nv=4).at((-0.168, 0.15, 0)),
    ]
    m.node("head", "neck", (0, 0.06, 0), (0, 0, 0), *head)
    eye = [
        ellipsoid(0.034, 0.042, 0.02, WHITE, nu=8, nv=5, spec=0.6),
        ellipsoid(0.02, 0.025, 0.012, st.eye, nu=8, nv=5, spec=0.9).at((0, -0.003, 0.014)),
        sphere(0.006, WHITE, nu=4, nv=3, emit=0.6).at((0.007, 0.007, 0.024)),
    ]
    m.node("eye_l", "head", (0.062, 0.18, 0.148), (0, 0.12, 0), *eye)
    m.node("eye_r", "head", (-0.062, 0.18, 0.148), (0, -0.12, 0), *eye)
    m.node(
        "mouth",
        "head",
        (0, 0.085, 0.152),
        (0.25, 0, 0),
        ellipsoid(0.035, 0.012, 0.012, (0.45, 0.12, 0.12), nu=8, nv=4),
    )
    _hair(m, st)
    _hat(m, st)
    if st.beard:
        m.add("head", ellipsoid(0.13, 0.15, 0.09, st.hair, nu=10, nv=6).at((0, 0.04, 0.1)))
    sleeve = shirt if st.long_sleeves else skin
    arm_col = st.outfit_color if st.outfit == "armor" and st.outfit_color else shirt
    for side, sx in (("l", 1), ("r", -1)):
        m.node(f"sh_{side}", "spine", (0.2 * sx, 0.39, 0), (0, 0, 0.1 * sx), capsule(0.056, 0.24, arm_col, 8))
        m.node(
            f"el_{side}",
            f"sh_{side}",
            (0, -0.26, 0),
            (0, 0, 0),
            capsule(0.048, 0.2, sleeve, 8, r2=0.034),
            sphere(0.06, (0.75, 0.75, 0.78) if st.hat == "astronaut" else skin, nu=8, nv=6).at(
                (0, -0.25, 0.005)
            ),
        )
        m.node(f"hip_{side}", "hips", (0.088 * sx, -0.02, 0), (0, 0, 0), capsule(0.068, 0.33, pants, 8))
        m.node(
            f"kn_{side}",
            f"hip_{side}",
            (0, -0.37, 0),
            (0, 0, 0),
            capsule(0.06, 0.31, pants, 8),
            chamfer_box(0.11, 0.08, 0.22, 0.025, st.shoes).at((0, -0.38, 0.04)),
        )
    if st.outfit == "dress":
        m.add("hips", lathe([(0.29, -0.45), (0.23, -0.2), (0.16, 0.0)], st.outfit_color or shirt, 14))
    if st.outfit == "robe":
        m.add("hips", lathe([(0.3, -0.79), (0.24, -0.4), (0.16, 0.0)], st.outfit_color or shirt, 14))
    if st.cape:
        m.node(
            "cape",
            "spine",
            (0, 0.42, -0.14),
            (0.12, 0, 0),
            plane(0.44, 0.95, st.cape, 1, 3).at((0, -0.475, 0), (PI / 2, 0, 0)),
        )
    if st.glow:
        for parts in m.parts:
            for p in parts:
                p.e[:] = np.maximum(p.e, st.glow)
    return m.build()


def _hair(m: Model, st: HumanStyle) -> None:
    hc = st.hair
    hs = st.hair_style
    if hs == "bald" or st.hat in ("astronaut", "helmet"):
        return
    cap = ellipsoid(0.178, 0.19, 0.175, hc, nu=14, nv=6, v0=0, v1=0.47).at((0, 0.168, -0.008))
    fringe = ellipsoid(0.15, 0.05, 0.06, hc, nu=10, nv=4).at((0, 0.29, 0.11), (0.5, 0, 0))
    parts = [cap, fringe]
    if hs == "long":
        parts.append(ellipsoid(0.175, 0.27, 0.11, hc, nu=12, nv=6).at((0, 0.08, -0.075)))
    elif hs == "ponytail":
        parts += [
            sphere(0.06, hc, nu=8, nv=5).at((0, 0.2, -0.18)),
            ellipsoid(0.055, 0.16, 0.055, hc, nu=8, nv=5).at((0, 0.06, -0.21)),
        ]
    elif hs == "bun":
        parts.append(sphere(0.085, hc, nu=10, nv=6).at((0, 0.35, -0.06)))
    elif hs == "spiky":
        for k in range(7):
            a = -0.9 + k * 0.3
            parts.append(
                cone(0.05, 0.13, hc, 5).at(
                    (math.sin(a) * 0.12, 0.3, -0.02 + math.cos(a) * 0.03), (-0.3, 0, -a * 0.8)
                )
            )
    elif hs == "curly":
        parts = [
            ellipsoid(0.24, 0.235, 0.22, hc, nu=14, nv=8, v0=0, v1=0.62).at((0, 0.2, -0.03)).vary(0.08, 3)
        ]
    m.add("head", *parts)


def _hat(m: Model, st: HumanStyle) -> None:
    h, c = st.hat, st.hat_color
    if not h:
        return
    top = 0.34
    parts: list[Mesh] = []
    if h == "cap":
        parts = [
            ellipsoid(0.182, 0.13, 0.18, c, nu=14, nv=5, v0=0, v1=0.5).at((0, 0.2, 0)),
            box(0.2, 0.015, 0.14, c).at((0, 0.205, 0.2)),
        ]
    elif h == "tophat":
        parts = [cylinder(0.25, 0.02, c, 16).at((0, 0.28, 0)), cylinder(0.14, 0.26, c, 14).at((0, 0.28, 0))]
    elif h in ("wizard", "witch"):
        parts = [
            cylinder(0.33, 0.02, c, 16).at((0, 0.27, 0)),
            cone(0.2, 0.55, c, 12).at((0, 0.27, 0), (-0.15, 0, 0)),
        ]
        parts.append(extrude(star_points(5, 0.05, 0.022), 0.01, GOLD, emit=0.4).at((0, 0.45, 0.13)))
    elif h in ("crown", "tiara"):
        k = 0.7 if h == "tiara" else 1.0
        parts = [cylinder(0.14 * k + 0.02, 0.07 * k, GOLD, 14, spec=1.2).at((0, 0.3, 0))]
        for i in range(6 if h == "crown" else 3):
            a = i / 6 * 2 * PI if h == "crown" else (i - 1) * 0.5 + PI / 2
            parts.append(
                cone(0.035, 0.09 * k, GOLD, 5, spec=1.2).at(
                    (math.cos(a) * 0.14 * k, 0.3 + 0.07 * k, math.sin(a) * 0.14 * k)
                )
            )
        parts.append(sphere(0.025, RED, nu=6, nv=4, emit=0.3).at((0, 0.34, 0.15 * k)))
    elif h == "helmet":
        parts = [
            ellipsoid(0.2, 0.22, 0.2, SILVER, nu=14, nv=9, spec=1.3).at((0, 0.16, 0)),
            box(0.22, 0.025, 0.05, BLACK).at((0, 0.18, 0.19)),
            cone(0.03, 0.12, RED, 5).at((0, 0.36, -0.02)),
        ]
    elif h == "astronaut":
        parts = [
            sphere(0.27, WHITE, nu=16, nv=10, spec=0.6).at((0, 0.16, 0)),
            ellipsoid(0.2, 0.15, 0.08, (0.08, 0.1, 0.18), nu=12, nv=7, spec=2.0).at((0, 0.18, 0.22)),
        ]
    elif h in ("straw", "safari", "cowboy"):
        c2 = (0.9, 0.78, 0.45) if h == "straw" else (0.75, 0.62, 0.4) if h == "safari" else (0.45, 0.28, 0.15)
        parts = [
            cylinder(0.32, 0.02, c2, 16).at((0, 0.26, 0)),
            cylinder(0.16, 0.13, c2, 12, r_top=0.14).at((0, 0.26, 0)),
        ]
    elif h == "chef":
        parts = [
            cylinder(0.15, 0.12, WHITE, 12).at((0, 0.27, 0)),
            ellipsoid(0.2, 0.13, 0.2, WHITE, nu=12, nv=6).at((0, 0.43, 0)),
        ]
    elif h == "hardhat":
        parts = [
            ellipsoid(0.19, 0.15, 0.19, (1, 0.8, 0.1), nu=12, nv=5, v0=0, v1=0.5).at((0, 0.2, 0)),
            cylinder(0.23, 0.015, (1, 0.8, 0.1), 14).at((0, 0.2, 0.02)),
        ]
    elif h == "headband":
        parts = [cylinder(0.175, 0.04, c, 14).at((0, 0.22, 0))]
    elif h == "halo":
        parts = [torus(0.13, 0.015, GOLD, 16, 6, emit=0.8).at((0, top + 0.12, 0))]
    m.add("head", *parts)
    if h == "astronaut":
        m.add("spine", chamfer_box(0.3, 0.38, 0.14, 0.04, WHITE).at((0, 0.25, -0.17)))


def robot(st: HumanStyle) -> Model:
    m = Model("person", height=1.75, radius=0.34)
    body = st.shirt
    metal = st.pants
    eye = (0.3, 0.95, 1.0)
    m.node("hips", None, (0, 0.81, 0), (0, 0, 0), chamfer_box(0.3, 0.14, 0.2, 0.03, metal, spec=1.2))
    m.node(
        "spine",
        "hips",
        (0, 0.06, 0),
        (0, 0, 0),
        chamfer_box(0.44, 0.44, 0.28, 0.06, body, spec=1.2).at((0, 0.24, 0)),
        box(0.18, 0.12, 0.02, (0.1, 0.12, 0.15)).at((0, 0.28, 0.14)),
        sphere(0.025, (1, 0.3, 0.3), nu=6, nv=4, emit=0.9).at((0.05, 0.3, 0.155)),
    )
    m.node("neck", "spine", (0, 0.46, 0), (0, 0, 0), cylinder(0.05, 0.08, metal, 8))
    m.node(
        "head",
        "neck",
        (0, 0.07, 0),
        (0, 0, 0),
        chamfer_box(0.34, 0.28, 0.28, 0.05, body, spec=1.2).at((0, 0.15, 0)),
        cylinder(0.012, 0.14, metal, 5).at((0, 0.29, 0)),
        sphere(0.035, (1, 0.3, 0.3), nu=8, nv=5, emit=0.9).at((0, 0.44, 0)),
    )
    m.node("eye_l", "head", (0.075, 0.17, 0.142), (0, 0, 0), box(0.07, 0.045, 0.02, eye, emit=0.95))
    m.node("eye_r", "head", (-0.075, 0.17, 0.142), (0, 0, 0), box(0.07, 0.045, 0.02, eye, emit=0.95))
    m.node("mouth", "head", (0, 0.07, 0.142), (0, 0, 0), box(0.14, 0.02, 0.02, (0.1, 0.1, 0.12)))
    for side, sx in (("l", 1), ("r", -1)):
        m.node(
            f"sh_{side}",
            "spine",
            (0.27 * sx, 0.4, 0),
            (0, 0, 0.08 * sx),
            sphere(0.07, metal, nu=8, nv=5, spec=1.2),
            cylinder(0.045, 0.26, metal, 8).at((0, -0.26, 0)),
        )
        m.node(
            f"el_{side}",
            f"sh_{side}",
            (0, -0.27, 0),
            (0, 0, 0),
            cylinder(0.04, 0.22, body, 8, spec=1.2).at((0, -0.22, 0)),
            chamfer_box(0.09, 0.1, 0.06, 0.015, metal).at((0, -0.27, 0)),
        )
        m.node(
            f"hip_{side}",
            "hips",
            (0.09 * sx, -0.03, 0),
            (0, 0, 0),
            cylinder(0.055, 0.35, metal, 8, spec=1.2).at((0, -0.36, 0)),
        )
        m.node(
            f"kn_{side}",
            f"hip_{side}",
            (0, -0.37, 0),
            (0, 0, 0),
            cylinder(0.05, 0.33, body, 8, spec=1.2).at((0, -0.35, 0)),
            chamfer_box(0.13, 0.08, 0.22, 0.02, metal).at((0, -0.39, 0.03)),
        )
    m.tags.add("metal")
    return m.build()


def ghost(st: HumanStyle) -> Model:
    m = Model("ghost", height=1.6, radius=0.35)
    col = st.shirt if st.shirt != HumanStyle().shirt else (0.93, 0.95, 1.0)
    prof = [(0.36, 0.0), (0.34, 0.25), (0.3, 0.6), (0.3, 0.9), (0.25, 1.15), (0.13, 1.33), (0.0, 1.38)]
    body = lathe(prof, col, 18, emit=0.35)
    v = body.v
    hem = v[:, 1] < 0.05
    v[hem, 1] += 0.06 * np.sin(np.arctan2(v[hem, 2], v[hem, 0]) * 6)
    m.node("hips", None, (0, 0.0, 0), (0, 0, 0), body)
    m.node("spine", "hips", (0, 0.5, 0), (0, 0, 0))
    m.node("neck", "spine", (0, 0.4, 0), (0, 0, 0))
    m.node("head", "neck", (0, 0.0, 0), (0, 0, 0))
    m.node("eye_l", "head", (0.1, 0.25, 0.25), (0, 0.2, 0), ellipsoid(0.05, 0.075, 0.02, BLACK, nu=8, nv=5))
    m.node("eye_r", "head", (-0.1, 0.25, 0.25), (0, -0.2, 0), ellipsoid(0.05, 0.075, 0.02, BLACK, nu=8, nv=5))
    m.node("mouth", "head", (0, 0.07, 0.28), (0.2, 0, 0), ellipsoid(0.05, 0.06, 0.02, BLACK, nu=8, nv=5))
    for side, sx in (("l", 1), ("r", -1)):
        m.node(
            f"sh_{side}",
            "spine",
            (0.28 * sx, 0.25, 0),
            (0, 0, 0.5 * sx),
            capsule(0.07, 0.18, col, 8, emit=0.35),
        )
        m.node(f"el_{side}", f"sh_{side}", (0, -0.2, 0), (0, 0, 0))
    m.hover = 0.35
    m.tags.add("floats")
    return m.build()


HUMANS: dict[str, dict] = {
    "person": {},
    "man": {"hair_style": "short"},
    "woman": {"hair_style": "long", "outfit": "dress"},
    "girl": {"hair_style": "ponytail", "outfit": "dress", "child": True},
    "boy": {"hair_style": "spiky", "child": True},
    "child": {"hair_style": "short", "child": True},
    "baby": {"hair_style": "bald", "child": True, "baby": True},
    "old_man": {"hair_style": "bald", "hair": (0.85, 0.85, 0.85), "beard": True, "old": True},
    "old_woman": {"hair_style": "bun", "hair": (0.85, 0.85, 0.85), "outfit": "dress", "old": True},
    "astronaut": {
        "hat": "astronaut",
        "shirt": WHITE,
        "pants": WHITE,
        "shoes": (0.6, 0.6, 0.65),
        "body": "astronaut",
    },
    "robot": {"body": "robot", "shirt": (0.7, 0.74, 0.8), "pants": (0.38, 0.4, 0.45)},
    "ghost": {"body": "ghost"},
    "wizard": {
        "hat": "wizard",
        "hat_color": (0.3, 0.2, 0.65),
        "outfit": "robe",
        "outfit_color": (0.3, 0.2, 0.65),
        "beard": True,
        "hair": (0.9, 0.9, 0.9),
        "hair_style": "long",
    },
    "witch": {
        "hat": "witch",
        "hat_color": (0.12, 0.1, 0.14),
        "outfit": "robe",
        "outfit_color": (0.15, 0.1, 0.2),
        "hair_style": "long",
        "skin": (0.75, 0.88, 0.7),
    },
    "knight": {
        "hat": "helmet",
        "outfit": "armor",
        "outfit_color": SILVER,
        "shirt": SILVER,
        "pants": (0.5, 0.52, 0.56),
        "cape": (0.7, 0.12, 0.12),
    },
    "king": {
        "hat": "crown",
        "outfit": "robe",
        "outfit_color": (0.65, 0.1, 0.15),
        "cape": (0.65, 0.1, 0.15),
        "beard": True,
    },
    "queen": {
        "hat": "crown",
        "outfit": "dress",
        "outfit_color": (0.5, 0.2, 0.6),
        "hair_style": "long",
        "cape": (0.45, 0.15, 0.55),
    },
    "princess": {
        "hat": "tiara",
        "outfit": "dress",
        "outfit_color": (1.0, 0.6, 0.78),
        "shirt": (1.0, 0.6, 0.78),
        "hair_style": "long",
        "hair": HAIRS[3],
    },
    "scientist": {"outfit": "coat", "outfit_color": WHITE, "shirt": WHITE, "hair_style": "curly"},
    "doctor": {"outfit": "coat", "outfit_color": WHITE, "shirt": (0.4, 0.75, 0.75)},
    "chef": {"hat": "chef", "shirt": WHITE, "pants": (0.2, 0.2, 0.22)},
    "farmer": {"hat": "straw", "shirt": (0.85, 0.25, 0.2), "pants": (0.2, 0.35, 0.6)},
    "explorer": {"hat": "safari", "shirt": (0.75, 0.68, 0.45), "pants": (0.55, 0.45, 0.3)},
    "cowboy": {"hat": "cowboy", "shirt": (0.7, 0.3, 0.2), "pants": (0.25, 0.3, 0.45)},
    "worker": {"hat": "hardhat", "shirt": (1.0, 0.55, 0.1), "pants": (0.2, 0.3, 0.5)},
    "superhero": {
        "shirt": (0.15, 0.35, 0.85),
        "pants": (0.15, 0.35, 0.85),
        "shoes": (0.8, 0.1, 0.1),
        "cape": (0.85, 0.12, 0.12),
        "hair_style": "short",
    },
    "businessman": {
        "outfit": "suit",
        "outfit_color": (0.18, 0.2, 0.28),
        "shirt": (0.18, 0.2, 0.28),
        "pants": (0.18, 0.2, 0.28),
        "shoes": BLACK,
    },
    "athlete": {
        "shirt": (0.95, 0.85, 0.2),
        "pants": (0.15, 0.15, 0.2),
        "long_sleeves": False,
        "hat": "headband",
        "hat_color": RED,
    },
    "ninja": {
        "shirt": (0.1, 0.1, 0.12),
        "pants": (0.1, 0.1, 0.12),
        "hat": "headband",
        "hat_color": RED,
        "hair_style": "spiky",
    },
    "pirate": {
        "hat": "tophat",
        "hat_color": (0.12, 0.1, 0.1),
        "shirt": (0.9, 0.9, 0.85),
        "pants": (0.25, 0.2, 0.15),
        "beard": True,
    },
    "vampire": {
        "cape": (0.08, 0.05, 0.08),
        "shirt": (0.1, 0.08, 0.1),
        "pants": (0.1, 0.08, 0.1),
        "skin": (0.9, 0.9, 0.92),
        "hair": BLACK,
        "eye": (0.7, 0.05, 0.05),
    },
    "zombie": {
        "skin": (0.55, 0.7, 0.45),
        "shirt": (0.4, 0.38, 0.45),
        "pants": (0.3, 0.28, 0.25),
        "hair_style": "spiky",
        "eye": (0.6, 0.1, 0.1),
    },
    "angel": {
        "hat": "halo",
        "outfit": "dress",
        "outfit_color": WHITE,
        "shirt": WHITE,
        "hair_style": "curly",
        "hair": HAIRS[3],
        "glow": 0.2,
    },
    "student": {"shirt": (0.95, 0.95, 0.95), "pants": (0.2, 0.25, 0.45), "hair_style": "short"},
    "statue": {"statue": True},
    "doll": {
        "outfit": "dress",
        "outfit_color": (0.8, 0.75, 0.85),
        "shirt": (0.8, 0.75, 0.85),
        "skin": (0.98, 0.92, 0.9),
        "hair_style": "long",
        "hair": (0.95, 0.85, 0.5),
        "child": True,
    },
    "caveman": {
        "shirt": (0.55, 0.4, 0.25),
        "pants": (0.55, 0.4, 0.25),
        "hair_style": "curly",
        "beard": True,
        "long_sleeves": False,
    },
    "diver": {"hat": "astronaut", "shirt": (0.95, 0.75, 0.15), "pants": (0.15, 0.15, 0.2)},
    "fisherman": {"hat": "straw", "shirt": (0.3, 0.5, 0.35), "pants": (0.35, 0.3, 0.25), "beard": True},
    "driver": {
        "hat": "cap",
        "hat_color": (0.2, 0.3, 0.6),
        "shirt": (0.5, 0.15, 0.15),
        "pants": (0.25, 0.3, 0.45),
    },
    "musician": {"shirt": (0.12, 0.12, 0.14), "pants": (0.12, 0.12, 0.14), "hair_style": "long"},
    "policeman": {
        "hat": "cap",
        "hat_color": (0.1, 0.15, 0.35),
        "shirt": (0.15, 0.22, 0.45),
        "pants": (0.1, 0.12, 0.25),
    },
    "nurse": {"shirt": (0.55, 0.8, 0.9), "pants": (0.55, 0.8, 0.9), "hair_style": "bun"},
    "alien": {
        "skin": (0.55, 0.85, 0.5),
        "hair_style": "bald",
        "shirt": (0.75, 0.78, 0.82),
        "pants": (0.6, 0.62, 0.66),
        "eye": BLACK,
    },
    "saci": {
        "child": True,
        "hat": "wizard",
        "hat_color": RED,
        "skin": SKINS[4],
        "shirt": RED,
        "pants": RED,
        "long_sleeves": False,
        "hair_style": "bald",
    },
    "curupira": {
        "child": True,
        "hair_style": "spiky",
        "hair": (1.0, 0.35, 0.08),
        "skin": SKINS[3],
        "shirt": (0.35, 0.55, 0.25),
        "pants": (0.35, 0.55, 0.25),
    },
    "mermaid": {
        "outfit": "dress",
        "outfit_color": (0.15, 0.7, 0.6),
        "shirt": (0.95, 0.6, 0.7),
        "hair_style": "long",
        "hair": HAIRS[1],
    },
}


def build_human(kind: str, color, rng: np.random.Generator) -> tuple[Model, float]:
    """Retorna (modelo, escala). A escala diminui crianças e bebês."""
    o = dict(HUMANS.get(kind, {}))
    child, baby, old, statue = (
        o.pop("child", False),
        o.pop("baby", False),
        o.pop("old", False),
        o.pop("statue", False),
    )
    style = HumanStyle()
    style.skin = SKINS[int(rng.integers(0, len(SKINS)))]
    style.hair = HAIRS[int(rng.integers(0, len(HAIRS)))]
    style.shirt = VIVID[int(rng.integers(0, len(VIVID)))]
    style.pants = [(0.2, 0.25, 0.45), (0.22, 0.22, 0.25), (0.45, 0.35, 0.25), (0.15, 0.3, 0.55)][
        int(rng.integers(0, 4))
    ]
    if kind in ("person", "man", "woman", "child", "boy", "girl"):
        style.hair_style = (
            str(rng.choice(["short", "short", "spiky", "curly"]))
            if kind in ("person", "man", "boy")
            else style.hair_style
        )
    for k, v in o.items():
        setattr(style, k, v)
    if style.body == "ghost":
        style.shirt = (0.93, 0.95, 1.0)
    if style.body == "astronaut":
        style.body = "human"
    if color is not None:
        if style.body == "ghost":
            style.shirt = color
        elif style.outfit in ("dress", "robe", "armor", "suit") and kind not in ("person",):
            style.outfit_color = color
            style.shirt = color
        else:
            style.shirt = color
    if statue:
        stone = (0.82, 0.8, 0.76)
        style = HumanStyle(
            skin=stone,
            shirt=stone,
            pants=stone,
            shoes=stone,
            hair=stone,
            eye=stone,
            outfit="robe",
            outfit_color=stone,
        )
    model = humanoid(style)
    if statue:
        model.mesh.s[:] = 0.4
        model.kind = "statue"
    scale = 1.0
    if child:
        scale = 0.68
        _scale_subtree(model, "head", 1.25)  # cabeça proporcionalmente maior
    if baby:
        scale = 0.45
        _scale_subtree(model, "head", 1.35)
    if old:
        model.rot[model.names.index("spine")] = np.asarray((0.18, 0, 0), F32)
    return model, scale


def _scale_subtree(model: Model, name: str, k: float) -> None:
    """Escala um nó e todos os filhos em torno do pivô do nó."""
    stack = [model.names.index(name)]
    while stack:
        j = stack.pop()
        s, e = model.slices[j]
        model.mesh.v[s:e] *= k
        for c, p in enumerate(model.parent):
            if p == j:
                model.pos[c] = model.pos[c] * k
                stack.append(c)


def night_windows(mesh: Mesh, rng: np.random.Generator) -> Mesh:
    """Acende parte das janelas (prédios e casas) à noite."""
    out = mesh.copy()
    win = (np.abs(out.c - np.asarray((0.35, 0.45, 0.6), F32)).sum(axis=1) < 0.03) | (
        np.abs(out.c - np.asarray((0.55, 0.75, 0.9), F32)).sum(axis=1) < 0.03
    )
    lit = win & (rng.random(len(out.c)) < 0.65)
    out.c[lit] = (1.0, 0.82, 0.48)
    out.e[lit] = 0.95
    return out


def subset(mesh: Mesh, keep: np.ndarray) -> Mesh:
    out = mesh.copy()
    out.f, out.c, out.e, out.s, out.d = out.f[keep], out.c[keep], out.e[keep], out.s[keep], out.d[keep]
    return out


# =================================================================== animais
@dataclass
class QuadStyle:
    length: float = 0.5
    height: float = 0.22
    width: float = 0.22
    leg: float = 0.25
    leg_r: float = 0.045
    head: float = 0.14
    snout: float = 0.06
    neck: float = 0.06
    neck_up: float = 0.5
    ears: str = "pointy"  # pointy, floppy, round, long, horns, none, big
    tail: str = "long"  # long, short, bushy, curly, none, hair
    color: tuple = (0.9, 0.6, 0.25)
    belly: tuple | None = None
    nose: tuple = BLACK
    extra: str = ""  # mane, shell, horn, antlers, trunk, spots, fluffy, wings, panda, stripes
    eye_size: float = 1.0


QUADS: dict[str, QuadStyle] = {
    "cat": QuadStyle(
        0.46,
        0.2,
        0.2,
        0.24,
        0.04,
        0.13,
        0.03,
        color=(0.95, 0.6, 0.25),
        belly=(1, 0.9, 0.8),
        nose=(0.9, 0.45, 0.5),
    ),
    "dog": QuadStyle(
        0.6,
        0.26,
        0.24,
        0.32,
        0.055,
        0.16,
        0.09,
        ears="floppy",
        tail="short",
        color=(0.8, 0.55, 0.3),
        belly=(0.95, 0.85, 0.7),
    ),
    "fox": QuadStyle(
        0.55,
        0.22,
        0.2,
        0.3,
        0.04,
        0.14,
        0.1,
        ears="big",
        tail="bushy",
        color=(0.95, 0.45, 0.12),
        belly=(1, 0.95, 0.9),
    ),
    "wolf": QuadStyle(
        0.8,
        0.32,
        0.28,
        0.45,
        0.06,
        0.18,
        0.12,
        ears="pointy",
        tail="bushy",
        color=(0.5, 0.52, 0.56),
        belly=(0.8, 0.8, 0.8),
    ),
    "jaguar": QuadStyle(
        0.9,
        0.34,
        0.3,
        0.42,
        0.07,
        0.2,
        0.06,
        ears="round",
        tail="long",
        color=(0.95, 0.7, 0.25),
        belly=(1, 0.92, 0.8),
        extra="spots",
    ),
    "tiger": QuadStyle(
        1.0,
        0.38,
        0.32,
        0.45,
        0.08,
        0.22,
        0.07,
        ears="round",
        tail="long",
        color=(1.0, 0.55, 0.15),
        belly=(1, 0.95, 0.9),
        extra="stripes",
    ),
    "lion": QuadStyle(
        1.0,
        0.4,
        0.34,
        0.48,
        0.08,
        0.22,
        0.08,
        ears="round",
        tail="long",
        color=(0.9, 0.7, 0.35),
        extra="mane",
    ),
    "horse": QuadStyle(
        1.3,
        0.5,
        0.36,
        0.85,
        0.07,
        0.2,
        0.25,
        0.45,
        0.9,
        ears="pointy",
        tail="hair",
        color=(0.55, 0.33, 0.18),
        extra="mane",
    ),
    "unicorn": QuadStyle(
        1.3,
        0.5,
        0.36,
        0.85,
        0.07,
        0.2,
        0.25,
        0.45,
        0.9,
        ears="pointy",
        tail="hair",
        color=(0.97, 0.95, 1.0),
        extra="mane,horn",
    ),
    "cow": QuadStyle(
        1.4,
        0.6,
        0.5,
        0.62,
        0.09,
        0.24,
        0.14,
        0.15,
        0.2,
        ears="horns",
        tail="long",
        color=(0.96, 0.96, 0.94),
        nose=(0.95, 0.6, 0.65),
        extra="spots_black",
    ),
    "pig": QuadStyle(
        0.8,
        0.42,
        0.38,
        0.28,
        0.06,
        0.2,
        0.06,
        ears="floppy",
        tail="curly",
        color=(1.0, 0.68, 0.72),
        nose=(0.95, 0.5, 0.55),
    ),
    "sheep": QuadStyle(
        0.8,
        0.45,
        0.42,
        0.4,
        0.05,
        0.15,
        0.06,
        ears="floppy",
        tail="short",
        color=(0.97, 0.96, 0.92),
        nose=(0.2, 0.18, 0.18),
        extra="fluffy",
    ),
    "capybara": QuadStyle(
        0.85, 0.42, 0.38, 0.28, 0.07, 0.2, 0.12, 0.05, 0.1, ears="round", tail="none", color=(0.6, 0.42, 0.26)
    ),
    "bear": QuadStyle(
        1.2, 0.6, 0.55, 0.55, 0.12, 0.26, 0.1, ears="round", tail="short", color=(0.45, 0.28, 0.16)
    ),
    "panda": QuadStyle(
        1.1,
        0.58,
        0.52,
        0.5,
        0.12,
        0.27,
        0.07,
        ears="round",
        tail="short",
        color=(0.97, 0.97, 0.95),
        extra="panda",
    ),
    "rabbit": QuadStyle(
        0.32,
        0.2,
        0.2,
        0.15,
        0.04,
        0.12,
        0.03,
        ears="long",
        tail="short",
        color=(0.92, 0.9, 0.88),
        nose=(0.95, 0.55, 0.6),
    ),
    "mouse": QuadStyle(
        0.18,
        0.1,
        0.1,
        0.07,
        0.02,
        0.07,
        0.03,
        ears="big",
        tail="long",
        color=(0.6, 0.6, 0.62),
        nose=(0.95, 0.55, 0.6),
    ),
    "elephant": QuadStyle(
        2.0,
        1.1,
        0.95,
        1.1,
        0.2,
        0.5,
        0.0,
        0.05,
        0.1,
        ears="elephant",
        tail="short",
        color=(0.55, 0.55, 0.58),
        extra="trunk",
    ),
    "deer": QuadStyle(
        1.0,
        0.4,
        0.3,
        0.75,
        0.05,
        0.17,
        0.12,
        0.3,
        0.9,
        ears="pointy",
        tail="short",
        color=(0.65, 0.42, 0.24),
        belly=(0.9, 0.8, 0.65),
        extra="antlers",
    ),
    "dinosaur": QuadStyle(
        2.4,
        1.0,
        0.8,
        1.0,
        0.18,
        0.28,
        0.1,
        1.4,
        1.0,
        ears="none",
        tail="dino",
        color=(0.35, 0.62, 0.35),
        belly=(0.7, 0.8, 0.5),
    ),
    "dragon": QuadStyle(
        1.8,
        0.8,
        0.7,
        0.75,
        0.14,
        0.3,
        0.2,
        0.8,
        0.8,
        ears="horns",
        tail="dino",
        color=(0.75, 0.15, 0.12),
        belly=(1.0, 0.75, 0.3),
        extra="wings,spikes",
    ),
    "turtle": QuadStyle(
        0.6,
        0.18,
        0.5,
        0.12,
        0.06,
        0.1,
        0.05,
        0.12,
        0.2,
        ears="none",
        tail="short",
        color=(0.5, 0.65, 0.35),
        extra="shell",
    ),
    "frog": QuadStyle(
        0.3,
        0.16,
        0.26,
        0.1,
        0.04,
        0.12,
        0.0,
        0.0,
        0.0,
        ears="none",
        tail="none",
        color=(0.35, 0.75, 0.3),
        belly=(0.85, 0.9, 0.6),
        eye_size=1.8,
    ),
    "monkey": QuadStyle(
        0.42,
        0.28,
        0.24,
        0.32,
        0.05,
        0.16,
        0.05,
        0.08,
        0.6,
        ears="round",
        tail="curly",
        color=(0.5, 0.33, 0.2),
        belly=(0.85, 0.7, 0.55),
    ),
    "camel": QuadStyle(
        1.4,
        0.55,
        0.4,
        1.0,
        0.08,
        0.2,
        0.25,
        0.6,
        0.9,
        ears="round",
        tail="short",
        color=(0.82, 0.65, 0.4),
        extra="hump",
    ),
    "goat": QuadStyle(
        0.8, 0.36, 0.3, 0.5, 0.05, 0.16, 0.1, 0.2, 0.7, ears="horns", tail="short", color=(0.92, 0.9, 0.85)
    ),
}


def quadruped(st: QuadStyle, color=None) -> Model:
    col = color or st.color
    belly = st.belly or col
    L, Hh, Wd, leg = st.length, st.height, st.width, st.leg
    m = Model("animal", height=leg + Hh * 1.4 + st.head, radius=max(L, Wd) * 0.6)
    y0 = leg + Hh * 0.2
    body = [ellipsoid(Wd / 2, Hh / 2, L / 2, col, nu=14, nv=8).at((0, 0, 0))]
    if belly != col:
        body.append(ellipsoid(Wd / 2.2, Hh / 3, L / 2.4, belly, nu=12, nv=6).at((0, -Hh * 0.2, 0)))
    ex = st.extra
    if "shell" in ex:
        body = [
            ellipsoid(Wd / 1.7, Hh * 1.6, L / 1.6, (0.45, 0.35, 0.2), nu=14, nv=7, v0=0, v1=0.5)
            .vary(0.12, 2)
            .at((0, -Hh * 0.1, 0)),
            ellipsoid(Wd / 1.8, Hh / 3, L / 1.8, (0.75, 0.7, 0.45), nu=12, nv=5).at((0, -Hh * 0.15, 0)),
        ]
    if "fluffy" in ex:
        rng = np.random.default_rng(5)
        body = [
            sphere(Hh * 0.33, col, nu=8, nv=6).at(
                (
                    rng.uniform(-Wd / 2.5, Wd / 2.5),
                    rng.uniform(-Hh / 3, Hh / 3),
                    rng.uniform(-L / 2.3, L / 2.3),
                )
            )
            for _ in range(14)
        ]
    if "hump" in ex:
        body.append(ellipsoid(Wd / 2.4, Hh * 0.55, L / 4, col, nu=10, nv=6).at((0, Hh * 0.5, 0)))
    if "spikes" in ex:
        for i in range(5):
            body.append(cone(0.07, 0.18, belly, 5).at((0, Hh * 0.45, L * (0.3 - i * 0.15))))
    m.node("hips", None, (0, y0, 0), (0, 0, 0), *body)
    if "spots" in ex or "stripes" in ex or "panda" in ex:
        _pattern(m.parts[0][0], ex)
    # pescoço e cabeça
    nk = st.neck
    neck_rot = (PI / 2 - st.neck_up, 0, 0)
    m.node(
        "neck",
        "hips",
        (0, Hh * 0.2, L * 0.42),
        neck_rot,
        capsule(st.head * 0.55, nk, col, 10, down=False) if nk > 0.02 else None,
    )
    hz = st.head
    head = [ellipsoid(hz * 0.95, hz * 0.9, hz, col, nu=12, nv=8)]
    if st.snout > 0.01:
        head.append(
            ellipsoid(
                hz * 0.55, hz * 0.45, st.snout + hz * 0.3, belly if belly != col else col, nu=10, nv=6
            ).at((0, -hz * 0.25, hz * 0.75))
        )
    nose_z = hz * 0.95 + st.snout + hz * 0.05
    head.append(
        ellipsoid(hz * 0.18, hz * 0.13, hz * 0.1, st.nose, nu=6, nv=4, spec=0.9).at((0, -hz * 0.12, nose_z))
    )
    es = 0.2 * st.eye_size
    for sx in (1, -1):
        head.append(
            ellipsoid(hz * es, hz * es * 1.1, hz * es * 0.5, BLACK, nu=8, nv=5, spec=1.0).at(
                (sx * hz * 0.45, hz * 0.2, hz * 0.8)
            )
        )
        head.append(
            sphere(hz * es * 0.3, WHITE, nu=4, nv=3, emit=0.6).at(
                (sx * hz * 0.45 + hz * 0.04, hz * 0.28, hz * 0.88)
            )
        )
        e = st.ears
        if e == "pointy":
            head.append(
                cone(hz * 0.32, hz * 0.6, col, 4).at((sx * hz * 0.5, hz * 0.6, -hz * 0.1), (0, 0, -sx * 0.3))
            )
        elif e == "big":
            head.append(
                cone(hz * 0.45, hz * 0.9, col, 4).at(
                    (sx * hz * 0.55, hz * 0.6, -hz * 0.1), (0, 0, -sx * 0.35)
                )
            )
        elif e == "floppy":
            head.append(
                ellipsoid(hz * 0.22, hz * 0.5, hz * 0.12, mix_rgb(col, BLACK, 0.25), nu=8, nv=5).at(
                    (sx * hz * 0.85, hz * 0.05, -hz * 0.1), (0, 0, sx * 0.3)
                )
            )
        elif e == "round":
            head.append(
                sphere(hz * 0.28, col if "panda" not in ex else BLACK, nu=8, nv=5).at(
                    (sx * hz * 0.6, hz * 0.65, -hz * 0.15)
                )
            )
        elif e == "long":
            head.append(
                ellipsoid(hz * 0.2, hz * 0.9, hz * 0.1, col, nu=8, nv=5).at(
                    (sx * hz * 0.3, hz * 1.4, -hz * 0.15), (0, 0, -sx * 0.15)
                )
            )
        elif e == "horns":
            head.append(
                cone(hz * 0.12, hz * 0.6, (0.92, 0.88, 0.75), 6).at(
                    (sx * hz * 0.5, hz * 0.6, -hz * 0.1), (0, 0, -sx * 0.7)
                )
            )
        elif e == "elephant":
            head.append(
                ellipsoid(hz * 0.08, hz * 0.8, hz * 0.65, col, nu=10, nv=6).at(
                    (sx * hz * 0.95, 0, -hz * 0.3), (0, sx * 0.5, 0)
                )
            )
    if "panda" in ex:
        for sx in (1, -1):
            head.append(
                ellipsoid(hz * 0.25, hz * 0.3, hz * 0.1, BLACK, nu=8, nv=5).at(
                    (sx * hz * 0.42, hz * 0.15, hz * 0.78)
                )
            )
    if "mane" in ex:
        if st.neck > 0.2:  # cavalo: crina
            m.add(
                "neck",
                *[
                    ellipsoid(0.04, 0.12, 0.08, mix_rgb(col, BLACK, 0.5), nu=6, nv=4).at(
                        (0, nk * k / 4, -0.05)
                    )
                    for k in range(1, 5)
                ],
            )
        else:
            head.append(
                torus(hz * 1.0, hz * 0.45, mix_rgb(col, (0.5, 0.25, 0.05), 0.6), 14, 6).at(
                    (0, 0, -hz * 0.15), (PI / 2, 0, 0)
                )
            )
    if "horn" in ex:
        head.append(cone(hz * 0.15, hz * 1.3, GOLD, 8, emit=0.3).at((0, hz * 0.75, hz * 0.4), (0.6, 0, 0)))
    if "antlers" in ex:
        for sx in (1, -1):
            head.append(cylinder(0.015, 0.35, WOOD, 5).at((sx * hz * 0.3, hz * 0.6, 0), (0, 0, -sx * 0.4)))
            head.append(cylinder(0.012, 0.18, WOOD, 5).at((sx * hz * 0.55, hz * 1.0, 0), (0.6, 0, -sx * 0.2)))
    m.node("head", "neck", (0, nk, 0), (st.neck_up - PI / 2, 0, 0), *[h.at((0, 0, hz * 0.4)) for h in head])
    if "trunk" in ex:
        m.node("trunk1", "head", (0, -hz * 0.3, hz * 1.25), (0.3, 0, 0), capsule(hz * 0.2, hz * 0.6, col, 8))
        m.node("trunk2", "trunk1", (0, -hz * 0.65, 0), (0.2, 0, 0), capsule(hz * 0.15, hz * 0.55, col, 8))
    # pernas
    up, lo = leg * 0.52, leg * 0.48
    paw = mix_rgb(col, BLACK, 0.25) if "panda" not in ex else BLACK
    leg_col = col if "panda" not in ex else BLACK
    for name, sx, sz in (("fl", 1, 1), ("fr", -1, 1), ("bl", 1, -1), ("br", -1, -1)):
        m.node(
            f"leg_{name}",
            "hips",
            (sx * Wd * 0.3, -Hh * 0.2, sz * L * 0.32),
            (0, 0, 0),
            capsule(st.leg_r * 1.15, up, leg_col, 8),
        )
        m.node(
            f"knee_{name}",
            f"leg_{name}",
            (0, -up, 0),
            (0, 0, 0),
            capsule(st.leg_r, lo - st.leg_r, leg_col, 8),
            ellipsoid(st.leg_r * 1.3, st.leg_r * 0.8, st.leg_r * 1.6, paw, nu=8, nv=5).at(
                (0, -lo + st.leg_r * 0.8, st.leg_r * 0.4)
            ),
        )
    # cauda
    t = st.tail
    if t != "none":
        tail_col = col if t != "hair" else mix_rgb(col, BLACK, 0.5)
        seg = {
            "long": (st.leg_r * 0.8, L * 0.35),
            "short": (st.leg_r * 0.9, L * 0.12),
            "bushy": (st.leg_r * 2.2, L * 0.3),
            "curly": (st.leg_r * 0.5, L * 0.12),
            "hair": (st.leg_r * 1.3, L * 0.3),
            "dino": (Hh * 0.28, L * 0.35),
        }[t]
        r0, ln = seg
        dino = t == "dino"
        m.node(
            "tail1",
            "hips",
            (0, Hh * 0.15, -L * 0.48),
            (1.4 if dino else 2.0, 0, 0),
            capsule(r0, ln, tail_col, 8),
        )
        m.node(
            "tail2",
            "tail1",
            (0, -ln, 0),
            (0.08 if dino else 0.3 if t != "curly" else 1.6, 0, 0),
            capsule(r0 * (0.8 if t != "bushy" else 1.1), ln, tail_col, 8),
        )
        if t in ("dino", "long"):
            m.node(
                "tail3",
                "tail2",
                (0, -ln, 0),
                (0.08 if dino else 0.2, 0, 0),
                capsule(r0 * 0.55, ln * 0.9, tail_col, 8),
            )
    if "wings" in ex:
        wc = mix_rgb(col, BLACK, 0.3)
        for side, sx in (("l", 1), ("r", -1)):
            wing = extrude([(0, 0), (1.2, 0.3), (1.6, -0.1), (1.1, -0.35), (0.6, -0.25), (0, -0.2)], 0.03, wc)
            m.node(
                f"wing_{side}",
                "hips",
                (sx * Wd * 0.4, Hh * 0.35, 0.05),
                (0, 0, sx * 0.7),
                wing.at((0, 0, 0), (PI / 2, 0, 0), (sx * L * 0.7, L * 0.7, L * 0.7)).paint(double=True),
            )
        m.tags.add("flies")
    m.tags.add("quad")
    return m.build()


def _pattern(mesh: Mesh, ex: str) -> None:
    cen = mesh.v[mesh.f].mean(axis=1)
    if "spots" in ex:
        rng = np.random.default_rng(4)
        pts = rng.uniform(-1, 1, (14, 3)) * (np.abs(mesh.v).max(axis=0))
        d = np.min(np.linalg.norm(cen[:, None, :] - pts[None], axis=2), axis=1)
        dark = (0.12, 0.1, 0.08) if "black" in ex else (0.45, 0.28, 0.1)
        mesh.c[d < np.abs(mesh.v).max() * 0.22] = dark
    if "stripes" in ex:
        z = cen[:, 2]
        mesh.c[(np.sin(z * 28) > 0.55) & (cen[:, 1] > -0.05)] = (0.1, 0.08, 0.06)
    if "panda" in ex:
        mesh.c[np.abs(cen[:, 2]) < np.abs(mesh.v[:, 2]).max() * 0.25] = BLACK


# ------------------------------------------------------------------ aves
BIRDS: dict[str, dict] = {
    "bird": dict(color=(0.3, 0.6, 0.95), belly=(0.95, 0.9, 0.7), size=0.25),
    "parrot": dict(color=(0.15, 0.75, 0.3), belly=(1.0, 0.85, 0.2), wing=(0.2, 0.35, 0.9), size=0.32),
    "owl": dict(color=(0.55, 0.4, 0.25), belly=(0.85, 0.75, 0.6), size=0.32, round=True),
    "eagle": dict(color=(0.35, 0.22, 0.12), head=(0.97, 0.97, 0.95), beak=(1, 0.8, 0.2), size=0.5),
    "penguin": dict(color=(0.1, 0.1, 0.12), belly=(0.97, 0.97, 0.97), size=0.5, walker=True),
    "chicken": dict(color=(0.97, 0.95, 0.9), size=0.32, comb=True, walker=True),
    "duck": dict(color=(0.95, 0.85, 0.2), size=0.28, walker=True),
    "bat": dict(color=(0.18, 0.14, 0.16), size=0.2, batwing=True),
    "pigeon": dict(color=(0.55, 0.58, 0.65), belly=(0.65, 0.65, 0.72), size=0.25, walker=True),
    "flamingo": dict(color=(1.0, 0.55, 0.65), size=0.45, long_legs=True),
    "toucan": dict(
        color=(0.08, 0.08, 0.1), belly=(1.0, 0.95, 0.85), beak=(1.0, 0.55, 0.1), size=0.3, big_beak=True
    ),
}


def bird(kind: str, color=None) -> Model:
    o = BIRDS.get(kind, BIRDS["bird"])
    s = o["size"]
    col = color or o["color"]
    belly = o.get("belly", col)
    leg_h = s * (1.6 if o.get("long_legs") else 0.55)
    m = Model("bird", height=leg_h + s * 1.6, radius=s * 0.8)
    m.tags.add("bird")
    body = [
        ellipsoid(s * 0.42, s * 0.42, s * 0.6 if not o.get("round") else s * 0.45, col, nu=12, nv=8),
        ellipsoid(s * 0.34, s * 0.34, s * 0.45, belly, nu=10, nv=6).at((0, -s * 0.08, s * 0.1)),
    ]
    body.append(
        cone(s * 0.18, s * 0.45, col, 4).at((0, s * 0.05, -s * 0.5), (-PI / 2 - 0.3, 0, 0), (1, 1, 0.35))
    )
    m.node("hips", None, (0, leg_h + s * 0.4, 0), (0, 0, 0), *body)
    hc = o.get("head", col)
    beak = o.get("beak", (1, 0.65, 0.15))
    head = [sphere(s * 0.3, hc, nu=10, nv=7)]
    if o.get("big_beak"):
        head.append(
            cone(s * 0.15, s * 0.55, beak, 8).at((0, -s * 0.02, s * 0.2), (PI / 2, 0, 0), (1, 1.3, 1))
        )
    else:
        head.append(cone(s * 0.08, s * 0.22, beak, 6).at((0, -s * 0.03, s * 0.25), (PI / 2, 0, 0)))
    es = s * (0.09 if o.get("round") else 0.055)
    for sx in (1, -1):
        if o.get("round"):
            head.append(
                ellipsoid(es * 1.4, es * 1.4, es * 0.4, WHITE, nu=8, nv=5).at(
                    (sx * s * 0.12, s * 0.07, s * 0.24)
                )
            )
        head.append(sphere(es, BLACK, nu=6, nv=4, spec=1.0).at((sx * s * 0.13, s * 0.08, s * 0.25)))
    if o.get("comb"):
        head.append(ellipsoid(s * 0.04, s * 0.12, s * 0.12, RED, nu=6, nv=4).at((0, s * 0.3, 0.02)))
    m.node("neck", "hips", (0, s * 0.35, s * 0.3), (0, 0, 0))
    m.node("head", "neck", (0, s * 0.1, 0.0), (0, 0, 0), *head)
    wc = o.get("wing", mix_rgb(col, BLACK, 0.15))
    for side, sx in (("l", 1), ("r", -1)):
        if o.get("batwing"):
            w = extrude(
                [(0, 0), (0.7, 0.3), (1.0, 0.1), (0.85, -0.1), (0.6, 0.0), (0.4, -0.15), (0, -0.1)], 0.02, wc
            )
            w = w.at((0, 0, 0), (PI / 2, 0, 0), (sx * s * 1.6, s * 1.6, s * 1.6)).paint(double=True)
        else:
            w = ellipsoid(s * 0.5, s * 0.05, s * 0.3, wc, nu=10, nv=5).at(
                (sx * s * 0.45, 0, -s * 0.05), (0, sx * 0.25, 0)
            )
        m.node(f"wing_{side}", "hips", (sx * s * 0.32, s * 0.12, 0), (0, 0, 0), w)
        m.node(
            f"leg_{side}",
            "hips",
            (sx * s * 0.14, -s * 0.3, 0.02),
            (0, 0, 0),
            cylinder(s * 0.03, leg_h + s * 0.1, beak, 5).at((0, -leg_h - s * 0.1, 0)),
            chamfer_box(s * 0.16, s * 0.03, s * 0.18, s * 0.01, beak).at((0, -leg_h - s * 0.1, s * 0.05)),
        )
    if o.get("walker"):
        m.tags.add("walker")
    else:
        m.tags.add("flies")
    return m.build()


# ------------------------------------------------------------------ peixes e criaturas
FISH: dict[str, dict] = {
    "fish": dict(color=(1.0, 0.55, 0.15), size=0.35, stripes=True),
    "shark": dict(color=(0.5, 0.56, 0.64), belly=(0.92, 0.92, 0.95), size=2.2, dorsal=True),
    "whale": dict(color=(0.25, 0.35, 0.55), belly=(0.85, 0.87, 0.9), size=6.0, flat_tail=True),
    "dolphin": dict(
        color=(0.55, 0.62, 0.72), belly=(0.92, 0.92, 0.95), size=1.8, dorsal=True, flat_tail=True
    ),
    "pink_dolphin": dict(
        color=(1.0, 0.62, 0.7), belly=(1.0, 0.85, 0.88), size=1.8, dorsal=True, flat_tail=True
    ),
    "clownfish": dict(color=(1.0, 0.45, 0.1), size=0.25, stripes=True),
    "goldfish": dict(color=(1.0, 0.7, 0.15), size=0.2),
    "piranha": dict(color=(0.5, 0.55, 0.6), belly=(0.9, 0.25, 0.2), size=0.3),
}


def fish(kind: str, color=None) -> Model:
    o = FISH.get(kind, FISH["fish"])
    s = o["size"]
    col = color or o["color"]
    belly = o.get("belly", mix_rgb(col, WHITE, 0.4))
    m = Model("fish", height=s * 0.5, radius=s * 0.6)
    body = [
        ellipsoid(s * 0.17, s * 0.22, s * 0.5, col, nu=12, nv=8),
        ellipsoid(s * 0.15, s * 0.12, s * 0.42, belly, nu=10, nv=6).at((0, -s * 0.09, 0.02 * s)),
    ]
    for sx in (1, -1):
        body.append(sphere(s * 0.04, BLACK, nu=6, nv=4, spec=1.2).at((sx * s * 0.12, s * 0.06, s * 0.34)))
        body.append(sphere(s * 0.012, WHITE, nu=4, nv=3, emit=0.7).at((sx * s * 0.15, s * 0.075, s * 0.36)))
        body.append(
            ellipsoid(s * 0.12, s * 0.02, s * 0.07, mix_rgb(col, BLACK, 0.2), nu=6, nv=4).at(
                (sx * s * 0.17, -s * 0.06, s * 0.1), (0, sx * 0.6, sx * 0.5)
            )
        )
    if o.get("dorsal"):
        body.append(
            extrude([(0, 0), (0.25, 0), (-0.05, 0.3)], 0.04, col).at((0, s * 0.18, 0), (0, -PI / 2, 0), s)
        )
    elif not o.get("flat_tail"):
        body.append(
            extrude([(0, 0), (0.3, 0), (0.05, 0.15)], 0.02, mix_rgb(col, BLACK, 0.15)).at(
                (0, s * 0.17, 0.05 * s), (0, -PI / 2, 0), s
            )
        )
    if o.get("stripes"):
        bm = body[0]
        z = bm.v[bm.f].mean(axis=1)[:, 2]
        bm.c[np.abs(np.sin(z / s * 9)) < 0.25] = WHITE
    m.node("hips", None, (0, 0, 0), (0, 0, 0), *body)
    if o.get("flat_tail"):
        tail = extrude([(0, 0), (0.25, -0.12), (0.3, 0.0), (0.25, 0.12)], 0.03, col).at(
            (0, 0, 0), (PI / 2, PI / 2, 0), s
        )
    else:
        tail = extrude([(0, 0), (0.25, -0.17), (0.2, 0), (0.25, 0.17)], 0.025, mix_rgb(col, BLACK, 0.1)).at(
            (0, 0, 0), (0, PI / 2, 0), s
        )
    m.node("tail1", "hips", (0, 0, -s * 0.45), (0, 0, 0), tail.paint(double=True))
    m.hover = max(0.8, s * 0.6)
    m.tags.add("swims")
    return m.build()


def octopus(color=None) -> Model:
    col = color or (0.85, 0.3, 0.45)
    m = Model("creature", height=1.2, radius=0.7)
    m.node(
        "hips",
        None,
        (0, 0.7, 0),
        (0, 0, 0),
        ellipsoid(0.32, 0.38, 0.32, col, nu=14, nv=9).at((0, 0.25, -0.05)),
        *[sphere(0.06, WHITE, nu=8, nv=5).at((sx * 0.13, 0.12, 0.26)) for sx in (1, -1)],
        *[sphere(0.035, BLACK, nu=6, nv=4).at((sx * 0.13, 0.12, 0.31)) for sx in (1, -1)],
    )
    for i in range(8):
        a = i / 8 * 2 * PI
        n = f"tent{i}"
        m.node(
            n + "a",
            "hips",
            (math.cos(a) * 0.2, -0.02, math.sin(a) * 0.2),
            (-math.sin(a) * 0.7, 0, math.cos(a) * 0.7),
            capsule(0.065, 0.28, col, 6),
        )
        m.node(
            n + "b",
            n + "a",
            (0, -0.3, 0),
            (-math.sin(a) * 0.3, 0, math.cos(a) * 0.3),
            capsule(0.05, 0.25, col, 6),
        )
        m.node(
            n + "c",
            n + "b",
            (0, -0.27, 0),
            (-math.sin(a) * 0.3, 0, math.cos(a) * 0.3),
            capsule(0.035, 0.2, col, 6),
        )
    m.hover = 0.3
    m.tags |= {"swims", "tentacles"}
    return m.build()


def jellyfish(color=None) -> Model:
    col = color or (0.95, 0.55, 0.85)
    m = Model("creature", height=1.0, radius=0.4)
    m.node(
        "hips",
        None,
        (0, 0.9, 0),
        (0, 0, 0),
        ellipsoid(0.35, 0.28, 0.35, col, nu=14, nv=6, v0=0, v1=0.5, emit=0.55),
    )
    for i in range(6):
        a = i / 6 * 2 * PI
        m.node(
            f"tent{i}a",
            "hips",
            (math.cos(a) * 0.2, -0.02, math.sin(a) * 0.2),
            (0, 0, 0),
            capsule(0.015, 0.35, col, 5, emit=0.6),
        )
        m.node(f"tent{i}b", f"tent{i}a", (0, -0.36, 0), (0, 0, 0), capsule(0.012, 0.3, col, 5, emit=0.6))
    m.hover = 0.4
    m.tags |= {"swims", "tentacles", "glow"}
    return m.build()


def snake(color=None, fire=False) -> Model:
    col = color or ((1.0, 0.55, 0.1) if fire else (0.35, 0.6, 0.25))
    emit = 0.85 if fire else 0.0
    m = Model("snake", height=0.4, radius=1.2)
    n = 12
    seg = 0.2
    parent = None
    for i in range(n):
        r = 0.09 * (1 - i / n * 0.6)
        name = f"seg{i}"
        c = col if i % 2 == 0 or fire else mix_rgb(col, (0.95, 0.85, 0.3), 0.4)
        mesh = sphere(r, c, nu=10, nv=6, emit=emit)
        m.node(
            name,
            parent,
            (0, 0.09, 0.9) if parent is None else (0, 0, -seg),
            (0, 0, 0),
            mesh,
            cylinder(r * 0.95, seg, c, 8, emit=emit).at((0, 0, 0), (-PI / 2, 0, 0)),
        )
        parent = name
    head = [ellipsoid(0.12, 0.08, 0.16, col, nu=10, nv=6, emit=emit).at((0, 0.01, 0.1))]
    for sx in (1, -1):
        head.append(
            sphere(0.025, (1.0, 0.9, 0.2) if fire else BLACK, nu=6, nv=4, emit=0.9 if fire else 0).at(
                (sx * 0.07, 0.05, 0.17)
            )
        )
    head.append(box(0.015, 0.005, 0.1, RED).at((0, -0.01, 0.3)))
    m.add("seg0", *head)
    m.tags.add("snake")
    if fire:
        m.tags.add("fire")
        m.flicker |= {f"seg{i}" for i in range(n)}
        m.light("seg0", (0, 0.2, 0), (1.0, 0.55, 0.15), 1.4, 4.0, True)
    return m.build()


def insect(kind: str, color=None) -> Model:
    m = Model("insect", height=0.2, radius=0.2)
    if kind == "butterfly":
        col = color or (0.95, 0.55, 0.15)
        m.node(
            "hips",
            None,
            (0, 0.8, 0),
            (0, 0, 0),
            capsule(0.02, 0.18, DARK, 6, down=False).at((0, -0.09, 0), (PI / 2, 0, 0)),
        )
        for side, sx in (("l", 1), ("r", -1)):
            w = extrude(
                [(0, 0), (0.25, 0.2), (0.35, 0.05), (0.2, -0.05), (0.28, -0.22), (0.05, -0.1)], 0.01, col
            )
            w = w.at((0, 0, 0), (PI / 2, 0, 0), (sx, 1, 1)).paint(double=True)
            m.node(f"wing_{side}", "hips", (0, 0, 0), (0, 0, 0), w)
        m.hover = 0.8
        m.tags.add("flies")
        return m.build()
    col = color or {
        "ant": (0.15, 0.08, 0.06),
        "bee": (1.0, 0.8, 0.1),
        "ladybug": RED,
        "spider": (0.12, 0.1, 0.1),
    }.get(kind, DARK)
    s = 0.3 if kind != "spider" else 0.35
    body = [
        sphere(s * 0.25, col, nu=10, nv=6).at((0, 0, -s * 0.3)),
        sphere(s * 0.17, col, nu=8, nv=5),
        sphere(s * 0.15, DARK if kind == "bee" else col, nu=8, nv=5).at((0, s * 0.02, s * 0.25)),
    ]
    if kind == "ladybug":
        body = [
            ellipsoid(s * 0.32, s * 0.25, s * 0.4, RED, nu=12, nv=6, v0=0, v1=0.5),
            sphere(s * 0.14, BLACK, nu=8, nv=5).at((0, 0.0, s * 0.35)),
        ]
        for sx, sz in ((1, 0.1), (-1, 0.1), (1, -0.15), (-1, -0.15)):
            body.append(sphere(s * 0.06, BLACK, nu=6, nv=4).at((sx * s * 0.15, s * 0.2, sz * s)))
    if kind == "bee":
        body.append(sphere(s * 0.255, BLACK, nu=10, nv=6).at((0, 0, -s * 0.3), scale=(1, 1, 0.3)))
        for side, sx in (("l", 1), ("r", -1)):
            m.node(
                f"wing_{side}",
                None,
                (sx * s * 0.1, s * 0.45, 0),
                (0, 0, 0),
                ellipsoid(s * 0.25, s * 0.02, s * 0.12, (0.9, 0.95, 1.0), nu=8, nv=4, emit=0.2).at(
                    (sx * s * 0.2, 0, 0)
                ),
            )
        m.hover = 0.8
        m.tags.add("flies")
    m.node("hips", None, (0, s * 0.2, 0), (0, 0, 0), *body)
    legs = 8 if kind == "spider" else 6
    for i in range(legs):
        sx = 1 if i % 2 == 0 else -1
        z = (i // 2 - (legs / 4 - 0.5)) * s * 0.15
        m.add("hips", cylinder(0.008, s * 0.45, DARK, 4).at((sx * s * 0.1, 0, z), (0, 0, -sx * 1.9)))
    m.tags.add("insect")
    return m.build()


# =================================================================== objetos
def _single(
    kind: str, height: float, *meshes: Mesh, radius: float | None = None, hover: float = 0.0
) -> Model:
    m = Model(kind, height=height, radius=radius or height * 0.5)
    m.node("body", None, (0, 0, 0), (0, 0, 0), *meshes)
    m.hover = hover
    return m


def _tree(col, rng) -> list[Mesh]:
    h = rng.uniform(1.3, 1.9)
    parts = [cylinder(0.14, h, WOOD, 7, r_top=0.1)]
    for k in range(3):
        a = k * 2.1 + rng.uniform(0, 1)
        parts.append(
            sphere(rng.uniform(0.6, 0.8), col, nu=9, nv=6)
            .vary(0.08, int(rng.integers(0, 99)))
            .jitter(0.06, k)
            .at((math.cos(a) * 0.35, h + 0.35 + k * 0.25, math.sin(a) * 0.35))
        )
    return parts


def build_prop(kind: str, color, rng: np.random.Generator) -> Model:
    """Objetos estáticos ou com partes móveis simples."""
    c = color
    pick = VIVID[int(rng.integers(0, len(VIVID)))]
    k = kind
    if k == "block":
        return _single(
            "block", 0.8, chamfer_box(0.8, 0.8, 0.8, 0.07, c or pick, base=True, spec=0.45)
        ).build()
    if k == "brick":
        col = c or pick
        parts = [chamfer_box(1.0, 0.45, 0.5, 0.03, col, base=True, spec=0.5)]
        for i in range(4):
            for j in range(2):
                parts.append(
                    cylinder(0.08, 0.08, col, 10, spec=0.5).at((-0.375 + i * 0.25, 0.45, -0.125 + j * 0.25))
                )
        return _single("block", 0.5, *parts, radius=0.55).build()
    if k == "domino":
        return _single(
            "block",
            0.6,
            chamfer_box(0.3, 0.6, 0.1, 0.02, c or WHITE, base=True, spec=0.5),
            *[sphere(0.025, BLACK, nu=5, nv=3).at((0, y, 0.05)) for y in (0.15, 0.45)],
            box(0.26, 0.01, 0.012, BLACK).at((0, 0.3, 0.05)),
        ).build()
    if k == "dice":
        parts = [chamfer_box(0.6, 0.6, 0.6, 0.08, c or WHITE, base=True, spec=0.6)]
        for x, y in ((0, 0.3), (-0.15, 0.15), (0.15, 0.45)):
            parts.append(sphere(0.05, RED, nu=6, nv=4).at((x, y, 0.3)))
        return _single("block", 0.6, *parts).build()
    if k == "ball":
        b = sphere(0.35, c or pick, nu=16, nv=10, spec=0.7)
        if c is None:  # bola de praia
            cen = b.v[b.f].mean(axis=1)
            ang = (np.arctan2(cen[:, 2], cen[:, 0]) + PI) / (2 * PI) * 6
            for i in range(6):
                b.c[(ang.astype(int) % 6) == i] = [
                    RED,
                    WHITE,
                    (0.2, 0.5, 0.95),
                    WHITE,
                    (1, 0.85, 0.2),
                    WHITE,
                ][i]
        return _single("ball", 0.7, b.at((0, 0.35, 0))).build()
    if k == "marble":
        return _single("ball", 0.3, sphere(0.15, c or pick, nu=12, nv=8, spec=1.8).at((0, 0.15, 0))).build()
    if k == "pyramid_block":
        return _single("block", 0.8, cone(0.6, 0.8, c or pick, 4, spec=0.4)).build()
    if k == "cylinder":
        return _single("block", 0.8, cylinder(0.4, 0.8, c or pick, 16, spec=0.4)).build()
    if k == "star":
        return _single(
            "symbol",
            1.0,
            extrude(star_points(5, 0.5, 0.22), 0.18, c or GOLD, emit=0.35, spec=1.0).at((0, 0.5, 0)),
            hover=0.6,
        ).build()
    if k == "heart":
        return _single(
            "symbol",
            1.0,
            extrude(heart_points(0.5), 0.2, c or (0.95, 0.2, 0.35), emit=0.25, spec=0.8).at((0, 0.5, 0)),
            hover=0.6,
        ).build()
    if k == "coin":
        return _single(
            "symbol",
            0.6,
            cylinder(0.3, 0.06, c or GOLD, 18, spec=1.5, center=True).at((0, 0.3, 0), (PI / 2, 0, 0)),
            cylinder(0.22, 0.07, mix_rgb(c or GOLD, WHITE, 0.15), 18, spec=1.5, center=True).at(
                (0, 0.3, 0), (PI / 2, 0, 0)
            ),
        ).build()
    if k == "gem":
        gem = lathe(
            [(0.0, 0.0), (0.3, 0.35), (0.2, 0.5), (0.0, 0.52)], c or (0.3, 0.85, 1.0), 8, emit=0.35, spec=2.0
        )
        return _single("symbol", 0.52, gem, hover=0.4).build()
    if k == "crystal":
        rng2 = np.random.default_rng(1)
        parts = [
            lathe(
                [(0, 0), (0.12, 0.05), (0.1, 0.6), (0, 0.8)], c or (0.6, 0.4, 1.0), 6, emit=0.5, spec=1.5
            ).at(
                (rng2.uniform(-0.2, 0.2), 0, rng2.uniform(-0.2, 0.2)),
                (rng2.uniform(-0.4, 0.4), 0, rng2.uniform(-0.4, 0.4)),
                rng2.uniform(0.6, 1.3),
            )
            for _ in range(5)
        ]
        m = _single("nature", 1.0, *parts)
        m.light("body", (0, 0.6, 0), c or (0.6, 0.4, 1.0), 0.8, 3.0)
        return m.build()
    if k == "gear":
        g = extrude(gear_points(12, 0.5, 0.4), 0.15, c or GOLD, spec=1.3)
        return _single(
            "symbol",
            1.0,
            g.at((0, 0.5, 0)),
            cylinder(0.12, 0.2, DARK, 10, center=True).at((0, 0.5, 0), (PI / 2, 0, 0)),
        ).build()
    if k == "ring":
        return _single(
            "symbol", 1.0, torus(0.38, 0.1, c or GOLD, 22, 8, spec=1.4).at((0, 0.5, 0), (PI / 2, 0, 0))
        ).build()
    if k == "balloon":
        col = c or pick
        return _single(
            "symbol",
            1.6,
            ellipsoid(0.3, 0.36, 0.3, col, nu=12, nv=8, spec=1.0).at((0, 1.3, 0)),
            cone(0.05, 0.08, col, 6).at((0, 0.9, 0)),
            cylinder(0.005, 0.9, WHITE, 3),
            hover=0.0,
        ).build()
    if k == "gift":
        col = c or RED
        return _single(
            "prop",
            0.75,
            chamfer_box(0.7, 0.6, 0.7, 0.03, col, base=True),
            box(0.72, 0.62, 0.12, GOLD, base=True),
            box(0.12, 0.62, 0.72, GOLD, base=True),
            torus(0.1, 0.035, GOLD, 10, 5).at((0.08, 0.66, 0), (PI / 2, 0.5, 0)),
            torus(0.1, 0.035, GOLD, 10, 5).at((-0.08, 0.66, 0), (PI / 2, -0.5, 0)),
        ).build()
    # ---- natureza
    if k == "tree":
        return _single("nature", 3.0, *_tree(c or LEAF, rng), radius=1.0).build()
    if k == "pine":
        parts = [cylinder(0.12, 0.6, WOOD, 6)]
        for i in range(3):
            parts.append(
                cone(0.85 - i * 0.2, 1.2, c or (0.15, 0.45, 0.28), 8).vary(0.06, i).at((0, 0.5 + i * 0.6, 0))
            )
        return _single("nature", 3.0, *parts, radius=0.9).build()
    if k == "palm":
        parts = []
        for i in range(6):
            parts.append(
                cylinder(0.12 - i * 0.008, 0.55, (0.6, 0.45, 0.28), 7).at(
                    (i * i * 0.012, i * 0.53, 0), (0, 0, -i * 0.04)
                )
            )
        top = (0.36, 3.2)
        for i in range(7):
            a = i / 7 * 2 * PI
            leaf = (
                extrude([(0, 0), (0.6, 0.18), (1.5, 0.0), (0.6, -0.18)], 0.02, c or (0.22, 0.62, 0.25))
                .paint(double=True)
                .at(rot=(PI / 2, 0, 0))
            )
            parts.append(leaf.at((top[0], top[1], 0), (0, a, -0.45)))
        parts.append(sphere(0.12, (0.45, 0.3, 0.15), nu=6, nv=4).at((top[0] + 0.1, top[1] - 0.1, 0.05)))
        return _single("nature", 3.4, *parts, radius=1.0).build()
    if k == "dead_tree":
        parts = [cylinder(0.14, 1.8, (0.3, 0.25, 0.22), 6, r_top=0.08)]
        for i in range(5):
            parts.append(
                cylinder(0.05, 0.8, (0.3, 0.25, 0.22), 5, r_top=0.01).at(
                    (0, 0.9 + i * 0.22, 0), (0.3 * (i % 2 * 2 - 1), i * 1.3, 0.9 * (1 if i % 2 else -1))
                )
            )
        return _single("nature", 2.5, *parts, radius=0.8).build()
    if k == "bush":
        return _single(
            "nature",
            0.8,
            *[
                sphere(rng.uniform(0.3, 0.45), c or (0.2, 0.52, 0.22), nu=8, nv=6)
                .vary(0.1, i)
                .at((rng.uniform(-0.35, 0.35), 0.3, rng.uniform(-0.25, 0.25)))
                for i in range(4)
            ],
            radius=0.6,
        ).build()
    if k == "flower":
        col = c or pick
        parts = [
            cylinder(0.02, 0.45, (0.25, 0.6, 0.25), 5),
            sphere(0.06, (1, 0.85, 0.2), nu=8, nv=5).at((0, 0.48, 0.02)),
        ]
        for i in range(6):
            a = i / 6 * 2 * PI
            parts.append(
                ellipsoid(0.07, 0.025, 0.04, col, nu=6, nv=4).at(
                    (math.cos(a) * 0.08, 0.48 + math.sin(a) * 0.08, 0), (PI / 2, 0, a)
                )
            )
        parts.append(
            ellipsoid(0.08, 0.015, 0.04, (0.25, 0.6, 0.25), nu=6, nv=3).at((0.06, 0.2, 0), (0, 0, 0.5))
        )
        return _single("nature", 0.55, *parts, radius=0.15).build()
    if k == "mushroom":
        col = c or RED
        parts = [
            cylinder(0.08, 0.25, (0.95, 0.92, 0.85), 8, r_top=0.06),
            ellipsoid(0.24, 0.16, 0.24, col, nu=12, nv=6, v0=0, v1=0.5).at((0, 0.25, 0)),
        ]
        for i in range(5):
            a = i * 1.3
            parts.append(sphere(0.03, WHITE, nu=5, nv=3).at((math.cos(a) * 0.12, 0.36, math.sin(a) * 0.12)))
        return _single("nature", 0.42, *parts, radius=0.25).build()
    if k == "rock":
        return _single(
            "nature",
            0.6,
            sphere(0.45, c or STONE, nu=7, nv=5)
            .jitter(0.1, int(rng.integers(0, 99)))
            .vary(0.08, 1)
            .at((0, 0.2, 0), scale=(1.2, 0.7, 1.0)),
            radius=0.55,
        ).build()
    if k == "cactus":
        col = c or (0.3, 0.6, 0.3)
        return _single(
            "nature",
            1.8,
            capsule(0.2, 1.4, col, 10, down=False),
            capsule(0.12, 0.35, col, 8, down=False).at((0.3, 0.7, 0)),
            capsule(0.12, 0.3, col, 8, down=False).at((-0.3, 0.9, 0)),
            cylinder(0.1, 0.3, col, 8).at((0.05, 0.7, 0), (0, 0, -PI / 2)),
            cylinder(0.1, 0.3, col, 8).at((-0.05, 0.9, 0), (0, 0, PI / 2)),
            radius=0.5,
        ).build()
    if k == "log":
        return _single(
            "nature",
            0.4,
            cylinder(0.2, 1.4, WOOD, 9, center=True).at((0, 0.2, 0), (0, 0, PI / 2)),
            radius=0.7,
        ).build()
    if k == "seaweed":
        m = Model("nature", height=1.6, radius=0.3)
        parent = None
        for i in range(4):
            name = f"sw{i}"
            m.node(
                name,
                parent,
                (0, 0 if parent is None else 0.4, 0),
                (0, 0, 0),
                ellipsoid(0.09, 0.24, 0.04, c or (0.2, 0.55, 0.3), nu=6, nv=4).at((0, 0.2, 0)),
            )
            parent = name
        m.tags.add("sway")
        return m.build()
    if k == "coral":
        col = c or (1.0, 0.45, 0.5)
        return _single(
            "nature",
            0.9,
            *[
                capsule(0.06, 0.5, col, 6, down=False).at(
                    (math.cos(i * 1.3) * 0.15, 0, math.sin(i * 1.3) * 0.15),
                    (math.cos(i) * 0.5, 0, math.sin(i * 1.3) * 0.5),
                )
                for i in range(6)
            ],
            radius=0.4,
        ).build()
    if k == "mountain":
        h = 8.0
        mtn = cone(6.0, h, c or (0.45, 0.47, 0.5), 9).jitter(0.35, int(rng.integers(0, 99))).vary(0.06, 2)
        cen = mtn.v[mtn.f].mean(axis=1)
        mtn.c[cen[:, 1] > h * 0.66] = (0.96, 0.97, 1.0)
        return _single("nature", h, mtn, radius=6.0).build()
    if k == "volcano":
        h = 7.0
        mtn = (
            lathe([(6.5, 0), (4.5, 2.5), (1.6, h), (1.1, h - 0.3)], c or (0.32, 0.26, 0.24), 12)
            .jitter(0.25, 3)
            .vary(0.08, 1)
        )
        m = _single(
            "nature",
            h,
            mtn,
            cylinder(1.15, 0.05, (1.0, 0.45, 0.1), 12, emit=1.0).at((0, h - 0.32, 0)),
            radius=6.5,
        )
        m.light("body", (0, h + 0.5, 0), (1.0, 0.45, 0.1), 2.5, 9.0, True)
        m.tags.add("fire")
        return m.build()
    if k == "cloud":
        col = c or WHITE
        return _single(
            "nature",
            1.2,
            *[
                sphere(rng.uniform(0.5, 0.8), col, nu=9, nv=6, emit=0.25).at(
                    (i * 0.6 - 0.9, rng.uniform(0, 0.3), rng.uniform(-0.2, 0.2))
                )
                for i in range(4)
            ],
            radius=1.5,
            hover=4.0,
        ).build()
    if k == "rainbow":
        cols = [
            (0.95, 0.25, 0.25),
            (1, 0.6, 0.2),
            (1, 0.9, 0.25),
            (0.35, 0.85, 0.35),
            (0.3, 0.6, 1.0),
            (0.55, 0.35, 0.9),
        ]
        parts = [
            torus(3.0 - i * 0.22, 0.11, cc, 30, 5, arc=0.5, emit=0.45).at((0, 0, 0), (-PI / 2, 0, 0))
            for i, cc in enumerate(cols)
        ]
        return _single("nature", 3.0, *parts, radius=3.0).build()
    if k == "grass":
        return _single(
            "nature",
            0.3,
            *[
                cone(0.04, rng.uniform(0.2, 0.35), c or (0.3, 0.65, 0.25), 3).at(
                    (rng.uniform(-0.15, 0.15), 0, rng.uniform(-0.15, 0.15)),
                    (rng.uniform(-0.3, 0.3), 0, rng.uniform(-0.3, 0.3)),
                )
                for _ in range(6)
            ],
            radius=0.2,
        ).build()
    if k == "snowman":
        return _single(
            "prop",
            1.6,
            sphere(0.45, WHITE, nu=12, nv=8).at((0, 0.42, 0)),
            sphere(0.33, WHITE, nu=12, nv=8).at((0, 1.0, 0)),
            sphere(0.24, WHITE, nu=12, nv=8).at((0, 1.45, 0)),
            cone(0.04, 0.2, (1, 0.5, 0.1), 6).at((0, 1.45, 0.22), (PI / 2, 0, 0)),
            *[sphere(0.03, BLACK, nu=5, nv=3).at((sx * 0.08, 1.52, 0.21)) for sx in (1, -1)],
            cylinder(0.18, 0.25, BLACK, 10).at((0, 1.62, 0)),
            cylinder(0.26, 0.02, BLACK, 12).at((0, 1.62, 0)),
        ).build()
    return build_structure(k, c, rng)


def build_structure(k: str, c, rng: np.random.Generator) -> Model:
    if k == "house":
        wall = (
            c
            or [(0.95, 0.88, 0.72), (0.85, 0.65, 0.5), (0.75, 0.85, 0.95), (1.0, 0.95, 0.85)][
                int(rng.integers(0, 4))
            ]
        )
        roof = extrude([(-1.9, 0), (1.9, 0), (0, 1.4)], 3.3, (0.7, 0.25, 0.2))
        win = (0.55, 0.75, 0.9)
        parts = [
            chamfer_box(3.4, 2.4, 3.0, 0.05, wall, base=True, seg=2),
            roof.at((0, 2.4, 0)),
            box(0.7, 1.3, 0.06, WOOD_DARK, base=True).at((0, 0, 1.51)),
            sphere(0.05, GOLD, nu=5, nv=3).at((0.22, 0.65, 1.55)),
            box(0.6, 0.6, 0.06, win, base=True, emit=0.1, spec=1.5).at((-1.05, 1.1, 1.51)),
            box(0.6, 0.6, 0.06, win, base=True, emit=0.1, spec=1.5).at((1.05, 1.1, 1.51)),
            box(0.4, 1.0, 0.4, (0.55, 0.3, 0.25), base=True).at((1.0, 2.8, -0.5)),
        ]
        m = _single("building", 3.8, *parts, radius=2.0)
        m.tags.add("windows")
        return m.build()
    if k == "building":
        h = float(rng.uniform(8, 16))
        col = (
            c
            or [(0.6, 0.65, 0.72), (0.72, 0.68, 0.62), (0.45, 0.5, 0.58), (0.8, 0.78, 0.75)][
                int(rng.integers(0, 4))
            ]
        )
        parts = [box(3.2, h, 3.2, col, base=True, seg=3)]
        win = []
        for fz in (1.61, -1.61):
            for iy in range(int(h / 1.4)):
                for ix in range(3):
                    win.append(
                        box(0.55, 0.7, 0.04, (0.95, 0.85, 0.5), emit=0.0, spec=1.5).at(
                            (-1.0 + ix * 1.0, 0.9 + iy * 1.4, fz)
                        )
                    )
        for fx in (1.61, -1.61):
            for iy in range(int(h / 1.4)):
                for iz in range(3):
                    win.append(
                        box(0.04, 0.7, 0.55, (0.95, 0.85, 0.5), emit=0.0, spec=1.5).at(
                            (fx, 0.9 + iy * 1.4, -1.0 + iz * 1.0)
                        )
                    )
        wm = Mesh.merge(*win)
        wm.c[:] = (0.35, 0.45, 0.6)
        m = _single("building", h, *parts, wm, radius=2.3)
        m.tags.add("windows")
        return m.build()
    if k == "tower":
        col = c or STONE
        parts = [
            cylinder(1.0, 6, col, 12).vary(0.05, 1),
            cylinder(1.2, 0.5, col, 12).at((0, 6, 0)),
            cone(1.3, 2.2, (0.55, 0.2, 0.2), 12).at((0, 6.5, 0)),
        ]
        parts.append(box(0.3, 0.7, 0.1, BLACK).at((0, 4.5, 1.0)))
        return _single("building", 8.7, *parts, radius=1.3).build()
    if k == "castle":
        col = c or (0.72, 0.7, 0.66)
        parts = [
            box(8, 4, 0.8, col, base=True, seg=3).at((0, 0, 3)),
            box(0.8, 4, 6, col, base=True, seg=3).at((-4, 0, 0)),
            box(0.8, 4, 6, col, base=True, seg=3).at((4, 0, 0)),
            box(8, 4, 0.8, col, base=True, seg=3).at((0, 0, -3)),
            box(2.2, 3, 0.2, WOOD_DARK, base=True).at((0, 0, 3.41)),
        ]
        for x in (-4, 4):
            for z in (-3, 3):
                parts += [
                    cylinder(1.0, 6, col, 10).at((x, 0, z)),
                    cone(1.2, 2.2, (0.3, 0.35, 0.65), 10).at((x, 6, z)),
                ]
        for i in range(8):
            parts.append(box(0.5, 0.5, 0.82, col, base=True).at((-3.5 + i, 4, 3)))
        parts += [
            cylinder(1.6, 8, col, 12).at((0, 0, 0)),
            cone(1.9, 3, (0.3, 0.35, 0.65), 12).at((0, 8, 0)),
            cylinder(0.03, 1.2, DARK, 4).at((0, 11, 0)),
            box(0.7, 0.4, 0.02, RED).at((0.35, 11.9, 0)),
        ]
        return _single("building", 11, *parts, radius=5.0).build()
    if k == "temple":
        col = c or (0.93, 0.9, 0.84)
        parts = [box(7, 0.6, 5, col, base=True, seg=2), box(6.4, 0.3, 4.4, col, base=True).at((0, 0.6, 0))]
        for x in range(6):
            for z in (-1.8, 1.8):
                parts.append(cylinder(0.25, 3.5, col, 10).at((-2.7 + x * 1.08, 0.9, z)))
        parts += [
            box(6.8, 0.5, 4.8, col, base=True).at((0, 4.4, 0)),
            extrude([(-3.4, 0), (3.4, 0), (0, 1.1)], 4.8, col).at((0, 4.9, 0)),
        ]
        return _single("building", 6.0, *parts, radius=3.6).build()
    if k == "pyramid":
        p = cone(5.0, 6.0, c or (0.9, 0.78, 0.5), 4).vary(0.04, 2)
        return _single("building", 6.0, p, radius=5.0).build()
    if k == "column":
        col = c or (0.93, 0.9, 0.84)
        return _single(
            "building",
            3.5,
            box(0.8, 0.25, 0.8, col, base=True),
            cylinder(0.28, 3.0, col, 12).at((0, 0.25, 0)),
            box(0.8, 0.25, 0.8, col, base=True).at((0, 3.25, 0)),
            radius=0.5,
        ).build()
    if k == "hut":
        return _single(
            "building",
            3.2,
            cylinder(1.4, 1.8, c or (0.75, 0.6, 0.4), 12),
            cone(1.9, 1.5, (0.85, 0.72, 0.4), 12).at((0, 1.8, 0)),
            box(0.6, 1.1, 0.1, WOOD_DARK, base=True).at((0, 0, 1.38)),
            radius=1.9,
        ).build()
    if k == "tent":
        return _single(
            "building", 1.8, extrude([(-1.3, 0), (1.3, 0), (0, 1.8)], 2.5, c or (0.95, 0.55, 0.2)), radius=1.4
        ).build()
    if k == "barn":
        col = c or (0.72, 0.18, 0.15)
        return _single(
            "building",
            5.0,
            box(5, 3.2, 4, col, base=True, seg=2),
            extrude([(-2.7, 0), (2.7, 0), (1.5, 1.2), (0, 1.8), (-1.5, 1.2)], 4.2, (0.35, 0.3, 0.3)).at(
                (0, 3.2, 0)
            ),
            box(1.8, 2.2, 0.06, WHITE, base=True).at((0, 0, 2.01)),
            box(1.5, 1.9, 0.07, col, base=True).at((0, 0.1, 2.02)),
            radius=2.8,
        ).build()
    if k == "lighthouse":
        parts = [lathe([(1.2, 0), (0.75, 8)], WHITE, 14)]
        cen = parts[0].v[parts[0].f].mean(axis=1)
        parts[0].c[(cen[:, 1] % 2.0) < 1.0] = RED
        parts += [
            cylinder(0.85, 0.2, DARK, 12).at((0, 8, 0)),
            cylinder(0.6, 1.0, (1, 0.95, 0.6), 10, emit=0.9).at((0, 8.2, 0)),
            cone(0.85, 0.8, RED, 12).at((0, 9.2, 0)),
        ]
        m = _single("building", 10, *parts, radius=1.3)
        m.light("body", (0, 8.7, 0), (1.0, 0.95, 0.7), 3.0, 12.0)
        return m.build()
    if k == "windmill":
        m = Model("building", height=7, radius=2)
        m.node(
            "body",
            None,
            (0, 0, 0),
            (0, 0, 0),
            lathe([(1.3, 0), (0.9, 5.5)], c or (0.95, 0.92, 0.85), 10),
            cone(1.15, 1.2, (0.6, 0.3, 0.2), 10).at((0, 5.5, 0)),
        )
        blades = [box(0.5, 2.8, 0.05, (0.9, 0.88, 0.8)).at((0, 1.5, 0), (0, 0, i * PI / 2)) for i in range(4)]
        m.node("spin", "body", (0, 5.2, 1.0), (0, 0, 0), *blades, sphere(0.2, WOOD, nu=6, nv=4))
        m.tags.add("spinner")
        return m.build()
    if k == "fence":
        parts = [box(0.12, 1.0, 0.12, WOOD, base=True).at((x, 0, 0)) for x in (-1.5, -0.5, 0.5, 1.5)]
        parts += [box(3.2, 0.12, 0.06, WOOD).at((0, y, 0)) for y in (0.45, 0.8)]
        return _single("prop", 1.0, *parts, radius=1.6).build()
    if k == "tombstone":
        col = c or (0.55, 0.56, 0.58)
        return _single(
            "prop",
            1.1,
            chamfer_box(0.7, 0.9, 0.18, 0.03, col, base=True),
            cylinder(0.35, 0.18, col, 12, center=True).at((0, 0.9, 0), (PI / 2, 0, 0)),
            box(0.36, 0.05, 0.02, DARK).at((0, 0.75, 0.1)),
            box(0.05, 0.28, 0.02, DARK).at((0, 0.75, 0.1)),
        ).build()
    if k == "lamp":
        m = _single(
            "prop",
            3.4,
            cylinder(0.07, 3.2, DARK, 8),
            box(0.45, 0.1, 0.45, DARK, base=True).at((0, 3.2, 0)),
            sphere(0.2, (1, 0.92, 0.65), nu=8, nv=6, emit=1.0).at((0, 3.1, 0)),
            radius=0.3,
        )
        m.light("body", (0, 2.9, 0), (1.0, 0.85, 0.55), 1.3, 5.0)
        m.tags.add("light")
        return m.build()
    if k == "bench":
        return _single(
            "prop",
            0.9,
            box(1.6, 0.08, 0.5, WOOD, base=True).at((0, 0.45, 0)),
            box(1.6, 0.4, 0.06, WOOD, base=True).at((0, 0.55, -0.22), (-0.15, 0, 0)),
            *[box(0.08, 0.45, 0.45, DARK, base=True).at((x, 0, 0)) for x in (-0.7, 0.7)],
            radius=0.9,
        ).build()
    if k == "sign":
        return _single(
            "prop",
            2.2,
            cylinder(0.05, 2.0, WOOD, 6),
            chamfer_box(1.2, 0.7, 0.08, 0.03, c or (0.95, 0.85, 0.3), base=True).at((0, 1.4, 0.05)),
        ).build()
    if k == "door":
        m = Model("prop", height=2.3, radius=0.8)
        m.node(
            "body",
            None,
            (0, 0, 0),
            (0, 0, 0),
            box(0.15, 2.3, 0.2, WOOD_DARK, base=True).at((-0.62, 0, 0)),
            box(0.15, 2.3, 0.2, WOOD_DARK, base=True).at((0.62, 0, 0)),
            box(1.4, 0.15, 0.2, WOOD_DARK, base=True).at((0, 2.2, 0)),
        )
        m.node(
            "door",
            "body",
            (-0.55, 0, 0),
            (0, 0, 0),
            box(1.1, 2.15, 0.08, c or (0.55, 0.3, 0.18), base=True).at((0.55, 0, 0)),
            sphere(0.05, GOLD, nu=6, nv=4, spec=1.5).at((0.95, 1.05, 0.06)),
        )
        m.tags.add("opens")
        return m.build()
    if k == "elevator":
        m = Model("prop", height=2.6, radius=1.0)
        m.node(
            "body",
            None,
            (0, 0, 0),
            (0, 0, 0),
            box(2.2, 2.6, 0.2, SILVER, base=True, spec=1.2).at((0, 0, -0.05)),
            box(1.5, 2.1, 0.05, (0.95, 0.9, 0.7), base=True, emit=0.6).at((0, 0.05, -0.1)),
            box(0.25, 0.12, 0.05, (1, 0.3, 0.2), emit=0.9).at((0, 2.35, 0.08)),
        )
        m.node(
            "door_l",
            "body",
            (-0.37, 0.05, 0.08),
            (0, 0, 0),
            box(0.74, 2.05, 0.05, (0.7, 0.72, 0.76), base=True, spec=1.5),
        )
        m.node(
            "door_r",
            "body",
            (0.37, 0.05, 0.08),
            (0, 0, 0),
            box(0.74, 2.05, 0.05, (0.7, 0.72, 0.76), base=True, spec=1.5),
        )
        m.tags.add("slides")
        return m.build()
    return build_vehicle(k, c, rng)


def build_vehicle(k: str, c, rng: np.random.Generator) -> Model:
    pick = VIVID[int(rng.integers(0, len(VIVID)))]
    if k in ("car", "taxi", "police_car", "bus", "truck"):
        col = c or {"taxi": (1.0, 0.8, 0.15), "police_car": (0.95, 0.95, 0.97), "bus": (1.0, 0.75, 0.1)}.get(
            k, pick
        )
        L = {"bus": 7.0, "truck": 6.5}.get(k, 3.6)
        m = Model("vehicle", height=1.5 if k == "car" else 2.8, radius=L / 2)
        glass = (0.25, 0.35, 0.45)
        if k == "bus":
            parts = [chamfer_box(2.3, 2.3, L, 0.15, col, base=True, spec=0.8).at((0, 0.35, 0))]
            for i in range(6):
                for sx in (1.16, -1.16):
                    parts.append(box(0.04, 0.8, 0.85, glass, spec=1.8).at((sx, 1.75, -2.6 + i * 1.0)))
            parts.append(box(2.0, 1.0, 0.04, glass, spec=1.8).at((0, 1.7, L / 2 + 0.01)))
        elif k == "truck":
            parts = [
                chamfer_box(2.3, 2.0, 2.0, 0.15, col, base=True, spec=0.8).at((0, 0.4, 2.2)),
                box(2.0, 0.8, 0.04, glass, spec=1.8).at((0, 1.85, 3.21)),
                chamfer_box(2.4, 2.8, 4.2, 0.08, (0.9, 0.9, 0.92), base=True).at((0, 0.5, -0.9)),
                box(2.4, 0.3, 6.5, DARK, base=True).at((0, 0.35, 0)),
            ]
        else:
            parts = [
                chamfer_box(1.7, 0.6, L, 0.15, col, base=True, spec=0.9).at((0, 0.3, 0)),
                chamfer_box(1.5, 0.6, L * 0.5, 0.15, col, base=True, spec=0.9).at((0, 0.88, -0.15)),
                box(1.3, 0.45, 0.04, glass, spec=1.8).at((0, 1.15, L * 0.25 - 0.13), (-0.3, 0, 0)),
                box(1.3, 0.45, 0.04, glass, spec=1.8).at((0, 1.15, -L * 0.25 - 0.17), (0.3, 0, 0)),
                box(0.04, 0.4, 1.5, glass, spec=1.8).at((0.76, 1.15, -0.15)),
                box(0.04, 0.4, 1.5, glass, spec=1.8).at((-0.76, 1.15, -0.15)),
            ]
            if k == "taxi":
                parts.append(box(0.5, 0.15, 0.25, (1, 1, 0.8), base=True, emit=0.5).at((0, 1.48, -0.15)))
            if k == "police_car":
                parts += [
                    box(0.3, 0.15, 0.25, (1, 0.1, 0.1), base=True, emit=0.9).at((0.2, 1.48, -0.15)),
                    box(0.3, 0.15, 0.25, (0.1, 0.3, 1), base=True, emit=0.9).at((-0.2, 1.48, -0.15)),
                ]
        for sx in (1, -1):
            parts.append(sphere(0.12, (1, 0.97, 0.85), nu=6, nv=4, emit=0.9).at((sx * 0.6, 0.65, L / 2)))
            parts.append(sphere(0.1, (1, 0.15, 0.1), nu=6, nv=4, emit=0.8).at((sx * 0.65, 0.65, -L / 2)))
        m.node("body", None, (0, 0, 0), (0, 0, 0), *parts)
        wz = L * 0.33
        for i, (sx, sz) in enumerate(((1, 1), (-1, 1), (1, -1), (-1, -1))):
            m.node(
                f"wheel{i}",
                "body",
                (sx * 0.85 * (1.3 if k in ("bus", "truck") else 1), 0.38, sz * wz),
                (0, 0, 0),
                cylinder(0.38, 0.3, (0.1, 0.1, 0.1), 12, center=True).at((0, 0, 0), (0, 0, PI / 2)),
                cylinder(0.2, 0.32, SILVER, 8, center=True, spec=1.5).at((0, 0, 0), (0, 0, PI / 2)),
            )
        m.tags.add("wheels")
        return m.build()
    if k == "rocket":
        col = c or WHITE
        m = Model("vehicle", height=5.0, radius=1.0)
        body = lathe([(0.55, 0.4), (0.6, 1.0), (0.6, 3.2), (0.45, 4.0), (0.0, 5.0)], col, 14, spec=0.8)
        cen = body.v[body.f].mean(axis=1)
        body.c[cen[:, 1] > 3.6] = RED
        parts = [
            body,
            sphere(0.25, (0.3, 0.6, 0.9), nu=10, nv=6, spec=1.8, emit=0.2).at(
                (0, 3.0, 0.5), scale=(1, 1, 0.4)
            ),
            cylinder(0.4, 0.4, DARK, 10, r_top=0.5),
        ]
        fins = []
        for i in range(4):
            a = i * PI / 2 + PI / 4
            fins.append(
                extrude([(0, 0), (0.75, -0.2), (0.7, 0.4), (0, 1.3)], 0.08, RED).at(
                    (math.cos(a) * 0.5, 0.3, math.sin(a) * 0.5), (0, -a, 0)
                )
            )
        m.node("body", None, (0, 0, 0), (0, 0, 0), body, parts[1], parts[2], *fins)
        m.node(
            "flame",
            "body",
            (0, 0.05, 0),
            (PI, 0, 0),
            cone(0.38, 1.6, (1.0, 0.6, 0.15), 10, emit=1.0),
            cone(0.22, 1.1, (1.0, 0.95, 0.6), 8, emit=1.0),
        )
        m.light("body", (0, -0.5, 0), (1.0, 0.6, 0.2), 2.5, 8.0, True)
        m.flicker.add("flame")
        m.tags |= {"rocket"}
        return m.build()
    if k == "ufo":
        m = Model("vehicle", height=1.6, radius=2.2)
        col = c or SILVER
        lights = [
            sphere(0.1, VIVID[i % len(VIVID)], nu=6, nv=4, emit=1.0).at(
                (math.cos(i / 10 * 2 * PI) * 1.85, 0.0, math.sin(i / 10 * 2 * PI) * 1.85)
            )
            for i in range(10)
        ]
        m.node(
            "body",
            None,
            (0, 0, 0),
            (0, 0, 0),
            ellipsoid(2.2, 0.35, 2.2, col, nu=20, nv=8, spec=1.5),
            ellipsoid(0.9, 0.7, 0.9, (0.5, 0.9, 0.7), nu=14, nv=8, v0=0, v1=0.5, emit=0.35, spec=2.0).at(
                (0, 0.2, 0)
            ),
            *lights,
        )
        m.hover = 4.0
        m.light("body", (0, -1, 0), (0.5, 1.0, 0.7), 2.0, 7.0)
        m.tags |= {"flies", "spinner_body"}
        return m.build()
    if k == "airplane":
        col = c or WHITE
        m = Model("vehicle", height=2.0, radius=4.0)
        m.node(
            "body",
            None,
            (0, 0, 0),
            (0, 0, 0),
            capsule(0.5, 5.0, col, 12, down=False).at((0, 0, -2.5), (PI / 2, 0, 0)),
            box(9.0, 0.12, 1.3, col).at((0, -0.1, 0.2)),
            box(3.2, 0.1, 0.8, col).at((0, 0.1, -2.6)),
            extrude([(0, 0), (1.0, 0), (0.2, 1.5)], 0.1, RED).at((0, 0.3, -2.4), (0, -PI / 2, 0)),
            *[
                box(0.04, 0.3, 0.4, (0.3, 0.4, 0.55), spec=1.5).at((sx * 0.49, 0.15, 1.0 - i * 0.6))
                for sx in (1, -1)
                for i in range(6)
            ],
        )
        m.node(
            "spin", "body", (0, 0, 2.95), (0, 0, 0), box(2.0, 0.15, 0.04, DARK), sphere(0.18, RED, nu=8, nv=5)
        )
        m.hover = 5.0
        m.tags |= {"flies", "spinner"}
        return m.build()
    if k in ("boat", "ship"):
        s = 1.0 if k == "boat" else 2.2
        col = c or (0.85, 0.25, 0.2)
        hull = Mesh.merge(
            chamfer_box(1.4, 0.7, 3.6, 0.3, col, base=True),
            box(1.3, 0.05, 3.4, WOOD, base=True).at((0, 0.62, 0)),
        )
        parts = [
            hull,
            cylinder(0.06, 3.2, WOOD, 6).at((0, 0.6, 0.2)),
            extrude([(0, 0), (1.6, 0), (0, 2.6)], 0.03, WHITE)
            .at((0.05, 0.9, 0.2), (0, -PI / 2, 0))
            .paint(double=True),
        ]
        m = _single("vehicle", 3.8 * s, *[p.at((0, 0, 0), scale=s) for p in parts], radius=1.8 * s)
        m.tags.add("boat")
        return m.build()
    if k == "submarine":
        col = c or (1.0, 0.85, 0.15)
        m = Model("vehicle", height=2.0, radius=2.5)
        m.node(
            "body",
            None,
            (0, 0, 0),
            (0, 0, 0),
            capsule(0.8, 3.2, col, 14, down=False).at((0, 0, -1.6), (PI / 2, 0, 0)),
            chamfer_box(0.8, 0.8, 1.2, 0.2, col, base=True).at((0, 0.6, 0.2)),
            cylinder(0.06, 0.8, DARK, 6).at((0, 1.3, 0.4)),
            *[
                cylinder(0.22, 0.1, (0.5, 0.8, 0.9), 12, emit=0.4, spec=1.5).at(
                    (sx * 0.78, 0.1, z), (0, 0, PI / 2)
                )
                for sx in (1, -1)
                for z in (-0.6, 0.4, 1.4)
            ],
        )
        m.node(
            "spin", "body", (0, 0, -2.5), (0, 0, 0), box(1.0, 0.12, 0.05, DARK), box(0.12, 1.0, 0.05, DARK)
        )
        m.hover = 1.5
        m.tags |= {"swims", "spinner"}
        return m.build()
    if k == "satellite":
        m = _single(
            "vehicle",
            1.5,
            chamfer_box(0.8, 0.8, 1.0, 0.05, GOLD, spec=1.5),
            *[box(2.0, 0.04, 0.8, (0.15, 0.25, 0.6), spec=2.0).at((sx * 1.5, 0, 0)) for sx in (1, -1)],
            cone(0.4, 0.3, WHITE, 12).at((0, 0.4, 0)),
            hover=3.0,
            radius=2.5,
        )
        m.tags.add("flies")
        return m.build()
    if k == "train":
        col = c or (0.2, 0.45, 0.85)
        m = Model("vehicle", height=3.0, radius=4.0)
        m.node(
            "body",
            None,
            (0, 0, 0),
            (0, 0, 0),
            chamfer_box(2.2, 2.4, 6.0, 0.2, col, base=True).at((0, 0.4, 0)),
            box(2.24, 0.25, 6.0, WHITE, base=True).at((0, 1.2, 0)),
            *[
                box(0.04, 0.7, 0.8, (0.3, 0.4, 0.5), spec=1.5).at((sx * 1.1, 1.9, -2 + i * 1.3))
                for sx in (1, -1)
                for i in range(4)
            ],
            sphere(0.2, (1, 0.95, 0.7), nu=6, nv=4, emit=1.0).at((0, 1.0, 3.01)),
        )
        for i, (sx, sz) in enumerate(((1, 2), (-1, 2), (1, -2), (-1, -2))):
            m.node(
                f"wheel{i}",
                "body",
                (sx * 1.0, 0.42, sz),
                (0, 0, 0),
                cylinder(0.42, 0.2, DARK, 12, center=True).at((0, 0, 0), (0, 0, PI / 2)),
            )
        m.tags.add("wheels")
        return m.build()
    return build_space(k, c, rng)


def build_space(k: str, c, rng: np.random.Generator) -> Model:
    if k in ("planet", "earth", "mars", "jupiter", "saturn", "moon", "neptune", "venus"):
        r = {"moon": 1.2, "jupiter": 3.0, "saturn": 2.4, "mars": 1.5, "earth": 2.0}.get(k, 2.0)
        sph = sphere(r, (0.5, 0.5, 0.5), nu=28, nv=16, spec=0.3)
        cen = sph.v[sph.f].mean(axis=1)
        lat = cen[:, 1] / r
        lon = np.arctan2(cen[:, 2], cen[:, 0])
        rr = np.random.default_rng(7)
        if k == "earth" or (k == "planet" and c is None and rng.random() < 0.0):
            noise = np.sin(lon * 3 + rr.uniform(0, 6)) * np.cos(lat * 4 + 1) + np.sin(lon * 5 + lat * 3) * 0.6
            sph.c[:] = (0.12, 0.35, 0.8)
            sph.c[noise > 0.45] = (0.25, 0.6, 0.3)
            sph.c[np.abs(lat) > 0.85] = (0.95, 0.97, 1.0)
        elif k == "moon":
            sph.c[:] = (0.75, 0.75, 0.73)
            sph = sph.jitter(0.03, 2)
            for _ in range(14):
                d = rr.normal(size=3)
                d /= np.linalg.norm(d)
                cen_n = cen / r
                sph.c[(cen_n @ d) > 0.96] = (0.55, 0.55, 0.55)
        elif k == "mars":
            sph.c[:] = (0.8, 0.38, 0.2)
            sph = sph.vary(0.12, 3)
        else:
            base = np.asarray(
                c
                or [(0.85, 0.65, 0.4), (0.4, 0.6, 0.9), (0.85, 0.55, 0.75), (0.5, 0.8, 0.7)][
                    int(rng.integers(0, 4))
                ],
                F32,
            )
            if k == "jupiter":
                base = np.asarray((0.85, 0.65, 0.45), F32)
            if k == "neptune":
                base = np.asarray((0.3, 0.45, 0.95), F32)
            band = 0.75 + 0.25 * np.sin(lat * 9 + np.sin(lon * 2) * 0.4)
            sph.c[:] = np.clip(base[None] * band[:, None], 0, 1)
        parts = [sph]
        if k == "saturn" or (k == "planet" and rng.random() < 0.35):
            ring = torus(r * 1.75, r * 0.32, (0.9, 0.82, 0.62), 36, 4).at(
                (0, 0, 0), (0.35, 0, 0.15), (1, 0.06, 1)
            )
            parts.append(ring)
        if k == "earth":
            clouds = sphere(r * 1.04, WHITE, nu=20, nv=12, emit=0.15)
            parts.append(subset(clouds, np.random.default_rng(3).random(len(clouds.f)) < 0.22))
        m = Model("space", height=2 * r, radius=r * (1.8 if len(parts) > 1 and k != "earth" else 1.0))
        m.node("body", None, (0, r, 0), (0, 0, 0.3), *parts)
        m.tags.add("planet")
        return m.build()
    if k == "sun":
        m = Model("space", height=6.0, radius=3.0)
        m.node(
            "body",
            None,
            (0, 3.0, 0),
            (0, 0, 0),
            sphere(3.0, (1.0, 0.75, 0.25), nu=24, nv=14, emit=1.0).vary(0.08, 1),
        )
        m.light("body", (0, 0, 0), (1.0, 0.8, 0.5), 3.0, 30.0)
        m.tags.add("planet")
        return m.build()
    if k == "black_hole":
        m = Model("space", height=3.0, radius=4.0)
        disk = torus(2.6, 1.0, (1.0, 0.55, 0.2), 40, 6, emit=1.0).at((0, 0, 0), (0.25, 0, 0), (1, 0.12, 1))
        cen = disk.v[disk.f].mean(axis=1)
        rr = np.sqrt(cen[:, 0] ** 2 + cen[:, 2] ** 2)
        disk.c[:] = np.stack(
            [np.ones_like(rr), np.clip(1.25 - rr / 3.2, 0.3, 1), np.clip(1.1 - rr / 2.2, 0.05, 1)], axis=1
        )
        m.node(
            "body", None, (0, 2.0, 0), (0, 0, 0), sphere(1.2, (0.0, 0.0, 0.0), nu=20, nv=12, spec=0.0), disk
        )
        m.tags |= {"planet", "spinner_body"}
        return m.build()
    if k == "asteroid":
        return _single(
            "space",
            1.4,
            sphere(0.7, c or (0.45, 0.42, 0.4), nu=9, nv=6)
            .jitter(0.15, int(rng.integers(0, 99)))
            .vary(0.12, 2)
            .at((0, 0.7, 0)),
            hover=1.0,
        ).build()
    if k == "comet":
        m = _single(
            "space",
            1.4,
            sphere(0.5, (0.8, 0.85, 0.9), nu=9, nv=6).jitter(0.08, 2),
            cone(0.55, 4.0, (0.6, 0.85, 1.0), 10, emit=0.8).at((0, 0, -0.2), (-PI / 2, 0, 0)),
            hover=3.0,
        )
        return m.build()
    if k == "galaxy":
        m = Model("space", height=2.0, radius=5.0)
        parts = []
        rr = np.random.default_rng(4)
        for i in range(160):
            arm = i % 2
            t = rr.random() ** 0.7
            a = t * 7 + arm * PI + rr.normal(0, 0.25)
            dist = 0.4 + t * 4.2
            col = mix_rgb((1.0, 0.85, 0.6), (0.5, 0.6, 1.0), t)
            parts.append(
                sphere(0.08 + rr.random() * 0.08, col, nu=4, nv=3, emit=1.0).at(
                    (math.cos(a) * dist, rr.normal(0, 0.08), math.sin(a) * dist)
                )
            )
        parts.append(sphere(0.7, (1.0, 0.9, 0.7), nu=12, nv=8, emit=1.0).at((0, 0, 0), scale=(1, 0.45, 1)))
        m.node("body", None, (0, 1.5, 0), (0.45, 0, 0.1), *parts)
        m.tags |= {"planet", "spinner_body"}
        return m.build()
    return build_object(k, c, rng)


def build_object(k: str, c, rng: np.random.Generator) -> Model:
    pick = VIVID[int(rng.integers(0, len(VIVID)))]
    if k == "table":
        col = c or WOOD
        return _single(
            "prop",
            0.8,
            box(1.6, 0.08, 0.9, col, base=True).at((0, 0.75, 0)),
            *[
                box(0.08, 0.75, 0.08, col, base=True).at((sx * 0.7, 0, sz * 0.35))
                for sx in (1, -1)
                for sz in (1, -1)
            ],
            radius=0.9,
        ).build()
    if k == "chair":
        col = c or WOOD
        return _single(
            "prop",
            1.0,
            box(0.5, 0.06, 0.5, col, base=True).at((0, 0.45, 0)),
            box(0.5, 0.55, 0.06, col, base=True).at((0, 0.5, -0.22)),
            *[
                box(0.05, 0.45, 0.05, col, base=True).at((sx * 0.21, 0, sz * 0.21))
                for sx in (1, -1)
                for sz in (1, -1)
            ],
            radius=0.35,
        ).build()
    if k == "bed":
        col = c or (0.4, 0.55, 0.85)
        return _single(
            "prop",
            0.9,
            box(1.6, 0.35, 2.2, WOOD, base=True),
            box(1.5, 0.2, 2.1, WHITE, base=True).at((0, 0.35, 0)),
            box(1.5, 0.08, 1.4, col, base=True).at((0, 0.52, 0.35)),
            chamfer_box(0.6, 0.15, 0.35, 0.05, WHITE, base=True).at((0, 0.55, -0.8)),
            box(1.6, 0.9, 0.1, WOOD, base=True).at((0, 0, -1.1)),
            radius=1.2,
        ).build()
    if k == "sofa":
        col = c or (0.55, 0.3, 0.6)
        return _single(
            "prop",
            0.9,
            chamfer_box(2.0, 0.45, 0.9, 0.08, col, base=True),
            chamfer_box(2.0, 0.5, 0.25, 0.08, col, base=True).at((0, 0.45, -0.32)),
            *[chamfer_box(0.25, 0.3, 0.9, 0.08, col, base=True).at((sx * 0.9, 0.45, 0)) for sx in (1, -1)],
            radius=1.1,
        ).build()
    if k in ("tv", "screen", "computer", "laptop"):
        col = c or (0.35, 0.65, 1.0)
        if k == "laptop":
            return _single(
                "prop",
                0.35,
                box(0.6, 0.03, 0.42, SILVER, base=True),
                box(0.6, 0.4, 0.03, SILVER, base=True).at((0, 0.03, -0.2), (-0.25, 0, 0)),
                box(0.54, 0.34, 0.01, col, base=True, emit=0.9).at((0, 0.06, -0.18), (-0.25, 0, 0)),
                radius=0.4,
            ).build()
        return _single(
            "prop",
            1.3,
            box(1.4, 0.85, 0.08, DARK, base=True, spec=1.5).at((0, 0.45, 0)),
            box(1.3, 0.75, 0.01, col, base=True, emit=0.95).at((0, 0.5, 0.045)),
            cylinder(0.05, 0.45, DARK, 6),
            box(0.5, 0.04, 0.3, DARK, base=True),
            radius=0.8,
        ).build()
    if k == "phone":
        return _single(
            "prop",
            0.3,
            chamfer_box(0.16, 0.3, 0.02, 0.01, DARK, base=True, spec=1.5).at((0, 0.0, 0)),
            box(0.14, 0.26, 0.004, c or (0.35, 0.7, 1.0), base=True, emit=0.95).at((0, 0.02, 0.011)),
            hover=1.0,
            radius=0.15,
        ).build()
    if k == "book":
        col = c or pick
        return _single(
            "prop",
            0.12,
            box(0.5, 0.1, 0.7, col, base=True),
            box(0.46, 0.08, 0.66, (0.97, 0.95, 0.88), base=True).at((0.03, 0.01, 0)),
            radius=0.4,
        ).build()
    if k == "candle":
        m = Model("prop", height=0.5, radius=0.1)
        m.node(
            "body",
            None,
            (0, 0, 0),
            (0, 0, 0),
            cylinder(0.06, 0.35, c or (0.97, 0.95, 0.88), 10),
            cylinder(0.005, 0.05, DARK, 3).at((0, 0.35, 0)),
        )
        m.node(
            "flame",
            "body",
            (0, 0.38, 0),
            (0, 0, 0),
            lathe([(0, 0), (0.03, 0.03), (0.0, 0.12)], (1.0, 0.8, 0.3), 6, emit=1.0),
        )
        m.light("body", (0, 0.5, 0), (1.0, 0.7, 0.35), 0.9, 2.5, True)
        m.flicker.add("flame")
        m.tags.add("fire")
        return m.build()
    if k in ("campfire", "fire", "torch"):
        m = Model("prop", height=1.0, radius=0.6)
        if k == "torch":
            m.node(
                "body",
                None,
                (0, 0, 0),
                (0, 0, 0),
                cylinder(0.05, 1.4, WOOD, 6),
                cylinder(0.09, 0.2, DARK, 6).at((0, 1.35, 0)),
            )
            m.node(
                "flame",
                "body",
                (0, 1.55, 0),
                (0, 0, 0),
                cone(0.13, 0.45, (1.0, 0.5, 0.1), 8, emit=1.0),
                cone(0.07, 0.3, (1.0, 0.9, 0.5), 6, emit=1.0),
            )
            m.light("body", (0, 1.8, 0), (1.0, 0.6, 0.25), 1.4, 4.5, True)
        else:
            logs = [
                cylinder(0.08, 0.9, WOOD_DARK, 6, center=True).at((0, 0.08, 0), (0, a, PI / 2))
                for a in (0, 1.0, 2.1)
            ]
            stones = [
                sphere(0.1, STONE, nu=6, nv=4)
                .jitter(0.02, i)
                .at((math.cos(i * 0.7) * 0.55, 0.05, math.sin(i * 0.7) * 0.55))
                for i in range(9)
            ]
            m.node("body", None, (0, 0, 0), (0, 0, 0), *logs, *stones)
            m.node(
                "flame",
                "body",
                (0, 0.1, 0),
                (0, 0, 0),
                *[
                    cone(
                        0.24 - i * 0.06,
                        0.55 - i * 0.12,
                        [(1.0, 0.35, 0.05), (1.0, 0.6, 0.1), (1.0, 0.9, 0.4)][i],
                        7,
                        emit=1.0,
                    ).at((math.cos(i * 2) * 0.05, 0, math.sin(i * 2) * 0.05))
                    for i in range(3)
                ],
            )
            m.light("body", (0, 0.7, 0), (1.0, 0.55, 0.2), 2.2, 6.0, True)
        m.flicker.add("flame")
        m.tags.add("fire")
        return m.build()
    if k == "lantern":
        m = _single(
            "prop",
            0.5,
            cylinder(0.12, 0.05, DARK, 8),
            cylinder(0.1, 0.3, (1.0, 0.85, 0.45), 8, emit=0.95).at((0, 0.05, 0)),
            cone(0.13, 0.12, DARK, 8).at((0, 0.35, 0)),
            torus(0.06, 0.012, DARK, 8, 4).at((0, 0.5, 0), (PI / 2, 0, 0)),
            radius=0.15,
        )
        m.light("body", (0, 0.25, 0), (1.0, 0.75, 0.35), 1.1, 3.5, True)
        return m.build()
    if k == "clock":
        m = Model("prop", height=1.0, radius=0.5)
        rim = c or (0.55, 0.3, 0.18)
        m.node(
            "body",
            None,
            (0, 0.5, 0),
            (0, 0, 0),
            cylinder(0.5, 0.1, rim, 20, center=True).at((0, 0, 0), (PI / 2, 0, 0)),
            cylinder(0.44, 0.11, WHITE, 20, center=True).at((0, 0, 0.005), (PI / 2, 0, 0)),
            *[
                box(0.03, 0.08, 0.01, DARK).at(
                    (math.sin(i * PI / 6) * 0.36, math.cos(i * PI / 6) * 0.36, 0.06), (0, 0, -i * PI / 6)
                )
                for i in range(12)
            ],
        )
        m.node("hand_h", "body", (0, 0, 0.065), (0, 0, 0), box(0.04, 0.24, 0.01, DARK).at((0, 0.1, 0)))
        m.node("hand_m", "body", (0, 0, 0.075), (0, 0, 0), box(0.025, 0.36, 0.01, DARK).at((0, 0.16, 0)))
        m.tags.add("clock")
        return m.build()
    if k in ("chest", "treasure"):
        m = Model("prop", height=0.8, radius=0.6)
        col = c or WOOD
        m.node(
            "body",
            None,
            (0, 0, 0),
            (0, 0, 0),
            chamfer_box(1.0, 0.5, 0.6, 0.03, col, base=True),
            box(1.02, 0.08, 0.62, GOLD, base=True, spec=1.5).at((0, 0.2, 0)),
            box(0.9, 0.05, 0.5, GOLD, base=True, emit=0.6).at((0, 0.45, 0)),
            *[
                sphere(0.07, GOLD, nu=6, nv=4, emit=0.5, spec=1.5).at((x, 0.5, z))
                for x, z in ((-0.2, 0.1), (0.1, -0.1), (0.3, 0.12))
            ],
        )
        m.node(
            "lid",
            "body",
            (0, 0.5, -0.3),
            (0, 0, 0),
            cylinder(0.3, 1.0, col, 10, center=True).at((0, 0, 0.3), (0, 0, PI / 2), (1, 1, 1)),
            box(1.02, 0.08, 0.08, GOLD, spec=1.5).at((0, 0.0, 0.6)),
        )
        m.tags.add("opens")
        m.light("body", (0, 0.8, 0.2), GOLD, 0.0, 2.5)
        return m.build()
    if k in ("box", "crate"):
        col = c or (0.75, 0.55, 0.3)
        return _single(
            "prop",
            0.8,
            chamfer_box(0.8, 0.8, 0.8, 0.03, col, base=True),
            *[box(0.82, 0.1, 0.82, mix_rgb(col, BLACK, 0.25), base=True).at((0, y, 0)) for y in (0.05, 0.65)],
        ).build()
    if k == "barrel":
        return _single(
            "prop",
            1.0,
            lathe([(0.32, 0), (0.4, 0.5), (0.32, 1.0)], c or WOOD, 12),
            *[torus(r, 0.02, DARK, 14, 4).at((0, y, 0)) for r, y in ((0.35, 0.15), (0.35, 0.85))],
            radius=0.4,
        ).build()
    if k == "cauldron":
        m = _single(
            "prop",
            0.9,
            lathe([(0.25, 0.1), (0.5, 0.4), (0.42, 0.8), (0.45, 0.85)], DARK, 14, spec=1.2),
            cylinder(0.42, 0.02, c or (0.4, 1.0, 0.3), 14, emit=0.9).at((0, 0.78, 0)),
            radius=0.5,
        )
        m.light("body", (0, 1.0, 0), c or (0.4, 1.0, 0.3), 1.2, 3.0, True)
        m.tags.add("bubbles")
        return m.build()
    if k in ("bottle", "potion", "flask", "beaker"):
        col = c or (0.3, 0.8, 1.0)
        return _single(
            "prop",
            0.6,
            lathe([(0.18, 0), (0.2, 0.25), (0.06, 0.42), (0.06, 0.55)], (0.85, 0.92, 0.95), 10, spec=2.0),
            cylinder(0.17, 0.2, col, 10, emit=0.6).at((0, 0.02, 0)),
            cylinder(0.07, 0.07, WOOD, 8).at((0, 0.55, 0)),
            radius=0.2,
        ).build()
    if k in ("cup", "coffee", "mug"):
        col = c or WHITE
        return _single(
            "prop",
            0.3,
            lathe([(0.1, 0), (0.12, 0.25)], col, 12),
            cylinder(0.105, 0.005, (0.35, 0.2, 0.1), 12).at((0, 0.24, 0)),
            torus(0.07, 0.02, col, 10, 5).at((0.13, 0.13, 0), (PI / 2, 0, 0)),
            radius=0.15,
        ).build()
    if k in ("bulb", "lightbulb", "idea"):
        m = _single(
            "symbol",
            0.9,
            ellipsoid(0.3, 0.32, 0.3, (1.0, 0.92, 0.5), nu=14, nv=9, emit=0.95).at((0, 0.55, 0)),
            cylinder(0.14, 0.22, SILVER, 10, spec=1.5).at((0, 0.1, 0)),
            *[torus(0.145, 0.015, SILVER, 10, 4).at((0, 0.12 + i * 0.05, 0)) for i in range(3)],
            hover=0.8,
        )
        m.light("body", (0, 0.55, 0), (1.0, 0.9, 0.5), 1.6, 4.0)
        return m.build()
    if k == "tape":
        return _single(
            "prop",
            0.15,
            box(0.6, 0.1, 0.36, BLACK, base=True, spec=0.8),
            box(0.4, 0.002, 0.15, WHITE, base=True).at((0, 0.1, 0.03)),
            *[cylinder(0.06, 0.003, (0.4, 0.4, 0.42), 10).at((sx * 0.13, 0.1, -0.06)) for sx in (1, -1)],
            radius=0.35,
        ).build()
    if k == "sword":
        return _single(
            "prop",
            1.2,
            box(0.08, 0.9, 0.02, SILVER, base=True, spec=2.0).at((0, 0.3, 0)),
            cone(0.04, 0.1, SILVER, 4).at((0, 1.2, 0)),
            box(0.35, 0.05, 0.06, GOLD, base=True).at((0, 0.25, 0)),
            cylinder(0.025, 0.25, WOOD_DARK, 6),
            sphere(0.04, GOLD, nu=6, nv=4).at((0, 0, 0)),
            hover=0.3,
            radius=0.2,
        ).build()
    if k == "shield":
        return _single(
            "prop",
            0.9,
            cylinder(0.45, 0.06, c or (0.65, 0.12, 0.12), 16, center=True).at((0, 0.5, 0), (PI / 2, 0, 0)),
            torus(0.45, 0.03, GOLD, 18, 4).at((0, 0.5, 0.0), (PI / 2, 0, 0)),
            extrude(star_points(5, 0.2, 0.09), 0.08, GOLD).at((0, 0.5, 0.03)),
            radius=0.45,
        ).build()
    if k == "hammer":
        return _single(
            "prop",
            1.0,
            cylinder(0.04, 0.8, WOOD_DARK, 6),
            chamfer_box(0.45, 0.25, 0.25, 0.03, SILVER, spec=1.4).at((0, 0.85, 0)),
            hover=0.3,
            radius=0.3,
        ).build()
    if k == "crown":
        parts = [cylinder(0.3, 0.2, GOLD, 16, spec=1.5)]
        for i in range(8):
            a = i / 8 * 2 * PI
            parts.append(cone(0.07, 0.2, GOLD, 5, spec=1.5).at((math.cos(a) * 0.3, 0.2, math.sin(a) * 0.3)))
            parts.append(
                sphere(0.04, VIVID[i % len(VIVID)], nu=5, nv=3, emit=0.4).at(
                    (math.cos(a) * 0.31, 0.1, math.sin(a) * 0.31)
                )
            )
        return _single("symbol", 0.45, *parts, hover=0.5, radius=0.32).build()
    if k == "trophy":
        col = c or GOLD
        return _single(
            "symbol",
            1.0,
            box(0.4, 0.15, 0.4, DARK, base=True),
            cylinder(0.05, 0.3, col, 8, spec=1.5).at((0, 0.15, 0)),
            lathe([(0.05, 0.45), (0.25, 0.6), (0.3, 0.95)], col, 14, spec=1.6),
            *[torus(0.1, 0.025, col, 10, 4).at((sx * 0.3, 0.75, 0), (PI / 2, 0, 0)) for sx in (1, -1)],
            radius=0.35,
        ).build()
    if k == "flag":
        m = Model("prop", height=3.0, radius=0.8)
        m.node(
            "body",
            None,
            (0, 0, 0),
            (0, 0, 0),
            cylinder(0.04, 3.0, SILVER, 6),
            sphere(0.07, GOLD, nu=6, nv=4).at((0, 3.0, 0)),
        )
        col = c or RED
        parent = "body"
        for i in range(4):
            name = f"cloth{i}"
            m.node(
                name,
                parent,
                (0.0, 2.9, 0) if i == 0 else (0.3, 0, 0),
                (0, 0, 0),
                box(0.3, 0.75, 0.02, col if i % 2 == 0 else mix_rgb(col, WHITE, 0.1), seg=1)
                .at((0.15, -0.375, 0))
                .paint(double=True),
            )
            parent = name
        m.tags.add("flag")
        return m.build()
    if k == "magnifier":
        return _single(
            "prop",
            0.6,
            torus(0.2, 0.03, DARK, 16, 5).at((0, 0.45, 0), (PI / 2, 0, 0)),
            cylinder(0.19, 0.01, (0.75, 0.9, 1.0), 16, emit=0.2, spec=2.0, center=True).at(
                (0, 0.45, 0), (PI / 2, 0, 0)
            ),
            cylinder(0.03, 0.3, WOOD_DARK, 6).at((0, 0.0, 0)),
            hover=0.6,
            radius=0.25,
        ).build()
    if k == "arrow":
        return _single(
            "symbol",
            0.8,
            extrude(
                [(-0.5, -0.12), (0.1, -0.12), (0.1, -0.3), (0.5, 0), (0.1, 0.3), (0.1, 0.12), (-0.5, 0.12)],
                0.12,
                c or (1.0, 0.85, 0.2),
                emit=0.3,
            ).at((0, 0.4, 0)),
            hover=0.6,
        ).build()
    if k == "lightning":
        m = _single(
            "symbol",
            1.6,
            extrude(bolt_points(0.8), 0.12, c or (1.0, 0.92, 0.3), emit=1.0).at((0, 0.8, 0)),
            hover=0.8,
        )
        m.light("body", (0, 0.8, 0.5), (1.0, 0.95, 0.5), 1.5, 4.0, True)
        return m.build()
    if k == "atom":
        m = Model("science", height=2.0, radius=1.0)
        nuc = [
            sphere(0.12, RED if i % 2 else (0.3, 0.5, 1.0), nu=8, nv=5, spec=1.0).at(
                tuple(np.random.default_rng(i).normal(0, 0.09, 3))
            )
            for i in range(10)
        ]
        m.node("body", None, (0, 1.0, 0), (0, 0, 0), *nuc)
        for i in range(3):
            n = f"orbit{i}"
            m.node(
                n,
                "body",
                (0, 0, 0),
                (0.4 + i * 1.0, i * 1.05, 0.3 * i),
                torus(0.85, 0.012, (0.5, 0.85, 1.0), 30, 4, emit=0.9),
                sphere(0.07, (0.5, 0.9, 1.0), nu=8, nv=5, emit=1.0).at((0.85, 0, 0)),
            )
        m.tags.add("atom")
        return m.build()
    if k == "dna":
        m = Model("science", height=3.0, radius=0.6)
        parts = []
        for i in range(22):
            y = i * 0.13
            a = i * 0.5
            p1 = (math.cos(a) * 0.45, y, math.sin(a) * 0.45)
            p2 = (-p1[0], y, -p1[2])
            parts += [
                sphere(0.07, (0.3, 0.6, 1.0), nu=6, nv=4, emit=0.3).at(p1),
                sphere(0.07, (1.0, 0.4, 0.6), nu=6, nv=4, emit=0.3).at(p2),
                cylinder(0.02, 0.9, WHITE, 4, center=True).at((0, y, 0), (0, -a, PI / 2)),
            ]
        m.node("body", None, (0, 0.2, 0), (0, 0, 0), *parts)
        m.tags.add("spinner_body")
        return m.build()
    if k == "molecule":
        cols = [RED, WHITE, (0.3, 0.5, 1.0), DARK]
        rr = np.random.default_rng(3)
        parts, pts = [], [np.zeros(3)]
        for _ in range(6):
            p = pts[int(rr.integers(0, len(pts)))] + rr.normal(0, 1, 3) / 1.6
            pts.append(p)
        for i, p in enumerate(pts):
            parts.append(sphere(0.22 if i % 3 else 0.3, cols[i % 4], nu=10, nv=7, spec=1.0).at(tuple(p)))
        m = _single("science", 2.0, *parts, hover=1.0, radius=1.2)
        m.tags.add("spinner_body")
        return m.build()
    if k in ("cell", "virus", "bacteria"):
        if k == "virus":
            col = c or (0.85, 0.3, 0.35)
            parts = [sphere(0.5, col, nu=14, nv=9).vary(0.05, 1)]
            for i in range(26):
                d = np.random.default_rng(i).normal(size=3)
                d /= np.linalg.norm(d)
                ang_y = math.atan2(d[0], d[2])
                ang_x = math.acos(np.clip(d[1], -1, 1))
                parts.append(cylinder(0.03, 0.25, col, 5).at(tuple(d * 0.45), (ang_x, ang_y, 0)))
                parts.append(sphere(0.06, (1.0, 0.8, 0.3), nu=5, nv=3).at(tuple(d * 0.72)))
            return _single("science", 1.2, *parts, hover=1.0).build()
        if k == "bacteria":
            return _single(
                "science",
                0.6,
                capsule(0.25, 0.8, c or (0.45, 0.85, 0.4), 12, down=False).at(
                    (-0.4, 0.3, 0), (0, 0, -PI / 2)
                ),
                hover=1.0,
                radius=0.7,
            ).build()
        col = c or (1.0, 0.65, 0.7)
        return _single(
            "science",
            1.4,
            sphere(0.7, col, nu=16, nv=10, emit=0.1).vary(0.04, 1),
            sphere(0.3, (0.6, 0.25, 0.55), nu=12, nv=8).at((0.25, 0.2, 0.5)),
            hover=1.0,
        ).build()
    if k == "brain":
        col = c or (1.0, 0.65, 0.7)
        parts = [
            sphere(0.45, col, nu=14, nv=9).jitter(0.035, 1).at((sx * 0.24, 0, 0), scale=(0.55, 0.75, 1.0))
            for sx in (1, -1)
        ]
        return _single("science", 1.0, *parts, hover=1.0, radius=0.6).build()
    if k == "magnet":
        return _single(
            "science",
            1.0,
            torus(0.4, 0.12, RED, 16, 6, arc=0.5).at((0, 0.6, 0), (PI / 2, 0, PI)),
            box(0.24, 0.3, 0.24, SILVER).at((0.4, 0.45, 0)),
            box(0.24, 0.3, 0.24, SILVER).at((-0.4, 0.45, 0)),
            hover=0.8,
        ).build()
    # ---- comida
    if k == "pizza":
        parts = [
            cylinder(0.6, 0.06, (0.95, 0.75, 0.4), 18),
            cylinder(0.54, 0.065, (0.85, 0.2, 0.1), 18),
            cylinder(0.5, 0.07, (1.0, 0.85, 0.4), 18),
        ]
        parts += [
            cylinder(0.08, 0.075, (0.7, 0.12, 0.1), 10).at(
                (math.cos(i * 1.3) * 0.3, 0, math.sin(i * 1.3) * 0.3)
            )
            for i in range(6)
        ]
        return _single("food", 0.1, *parts, radius=0.6).build()
    if k == "cake":
        col = c or (1.0, 0.7, 0.8)
        m = Model("food", height=1.0, radius=0.6)
        parts = [
            cylinder(0.6, 0.35, col, 18),
            cylinder(0.62, 0.05, WHITE, 18).at((0, 0.33, 0)),
            cylinder(0.42, 0.3, col, 16).at((0, 0.38, 0)),
            cylinder(0.44, 0.04, WHITE, 16).at((0, 0.66, 0)),
            sphere(0.06, RED, nu=6, nv=4).at((0, 0.73, 0)),
        ]
        parts += [
            cylinder(0.02, 0.15, VIVID[i], 5).at((math.cos(i * 1.25) * 0.28, 0.68, math.sin(i * 1.25) * 0.28))
            for i in range(5)
        ]
        m.node("body", None, (0, 0, 0), (0, 0, 0), *parts)
        m.node(
            "flame",
            "body",
            (0, 0, 0),
            (0, 0, 0),
            *[
                cone(0.025, 0.07, (1, 0.8, 0.3), 5, emit=1.0).at(
                    (math.cos(i * 1.25) * 0.28, 0.84, math.sin(i * 1.25) * 0.28)
                )
                for i in range(5)
            ],
        )
        m.flicker.add("flame")
        m.light("body", (0, 1.0, 0), (1.0, 0.75, 0.4), 0.8, 2.5, True)
        return m.build()
    if k == "apple":
        return _single(
            "food",
            0.5,
            sphere(0.22, c or (0.9, 0.12, 0.12), nu=12, nv=8, spec=1.2).at((0, 0.22, 0), scale=(1, 0.92, 1)),
            cylinder(0.015, 0.1, WOOD, 4).at((0, 0.4, 0)),
            ellipsoid(0.07, 0.01, 0.035, (0.3, 0.65, 0.25), nu=6, nv=3).at((0.06, 0.46, 0), (0, 0, 0.4)),
        ).build()
    if k == "donut":
        return _single(
            "food",
            0.25,
            torus(0.25, 0.11, (0.85, 0.6, 0.35), 18, 8).at((0, 0.11, 0)),
            torus(0.25, 0.1, c or (1.0, 0.55, 0.75), 18, 8).at((0, 0.135, 0), scale=(1, 0.7, 1)),
        ).build()
    if k in ("bread", "loaf"):
        col = c or (0.92, 0.7, 0.4)
        return _single(
            "food",
            0.5,
            chamfer_box(0.4, 0.3, 0.7, 0.08, (0.97, 0.9, 0.75), base=True),
            ellipsoid(0.22, 0.14, 0.36, col, nu=12, nv=6, v0=0, v1=0.5).at((0, 0.28, 0)),
            box(0.42, 0.06, 0.72, col, base=True).at((0, 0.0, 0)),
            radius=0.4,
        ).build()
    if k == "croissant":
        return _single(
            "food",
            0.25,
            torus(0.3, 0.1, c or (0.92, 0.65, 0.3), 14, 7, arc=0.55).at((0, 0.1, 0), (0, PI * 0.72, 0)),
            radius=0.35,
        ).build()
    if k == "icecream":
        return _single(
            "food",
            0.9,
            cone(0.14, 0.45, (0.85, 0.6, 0.3), 10).at((0, 0.45, 0), (PI, 0, 0)),
            sphere(0.17, c or (1.0, 0.7, 0.8), nu=10, nv=7).at((0, 0.55, 0)),
            sphere(0.15, (0.6, 0.38, 0.25), nu=10, nv=7).at((0, 0.75, 0)),
            sphere(0.05, RED, nu=6, nv=4).at((0, 0.92, 0)),
        ).build()
    if k == "candy":
        col = c or pick
        return _single(
            "food",
            0.3,
            sphere(0.12, col, nu=10, nv=7, spec=1.5).at((0, 0.15, 0)),
            cone(0.1, 0.15, col, 6).at((0.1, 0.15, 0), (0, 0, PI / 2)),
            cone(0.1, 0.15, col, 6).at((-0.1, 0.15, 0), (0, 0, -PI / 2)),
            radius=0.3,
        ).build()
    if k == "egg":
        return _single(
            "food",
            0.4,
            ellipsoid(0.15, 0.2, 0.15, c or (0.98, 0.95, 0.88), nu=12, nv=8).at((0, 0.2, 0)),
            radius=0.15,
        ).build()
    if k == "burger":
        return _single(
            "food",
            0.45,
            ellipsoid(0.3, 0.06, 0.3, (0.9, 0.6, 0.3), nu=14, nv=5).at((0, 0.05, 0)),
            cylinder(0.3, 0.07, (0.45, 0.25, 0.12), 14).at((0, 0.08, 0)),
            box(0.5, 0.02, 0.5, (1, 0.8, 0.2)).at((0, 0.16, 0), (0, 0.4, 0)),
            cylinder(0.32, 0.03, (0.35, 0.75, 0.3), 14).at((0, 0.17, 0)),
            ellipsoid(0.3, 0.17, 0.3, (0.92, 0.62, 0.3), nu=14, nv=6, v0=0, v1=0.5).at((0, 0.2, 0)),
        ).build()
    if k == "banana":
        return _single(
            "food", 0.25, torus(0.3, 0.06, c or (1.0, 0.85, 0.2), 14, 6, arc=0.4).at((0, 0.08, 0)), radius=0.3
        ).build()
    # desconhecido: bloco
    return build_prop("block", c, rng)


# =================================================================== registro
@dataclass(frozen=True)
class Entry:
    cat: str  # person, animal, bird, fish, creature, insect, prop
    builder: Callable[[str, tuple | None, np.random.Generator], tuple[Model, float]]
    max_count: int = 40


def _h(kind, color, rng):
    return build_human(kind, color, rng)


def _q(kind, color, rng):
    m = quadruped(QUADS[kind], color)
    return m, 1.0


def _b(kind, color, rng):
    return bird(kind, color), 1.0


def _f(kind, color, rng):
    return fish(kind, color), 1.0


def _p(kind, color, rng):
    return build_prop(kind, color, rng), 1.0


def _c(kind, color, rng):
    if kind == "octopus":
        return octopus(color), 1.0
    if kind == "jellyfish":
        return jellyfish(color), 1.0
    if kind in ("snake", "fire_snake"):
        return snake(color, kind == "fire_snake"), 1.0
    return insect(kind, color), 1.0


REGISTRY: dict[str, Entry] = {}
for _k in HUMANS:
    REGISTRY[_k] = Entry("person", _h, 14)
for _k in QUADS:
    REGISTRY[_k] = Entry("animal", _q, 14)
for _k in BIRDS:
    REGISTRY[_k] = Entry("bird", _b, 20)
for _k in FISH:
    REGISTRY[_k] = Entry("fish", _f, 24)
for _k in ("octopus", "jellyfish", "snake", "fire_snake"):
    REGISTRY[_k] = Entry("creature", _c, 10)
for _k in ("butterfly", "ant", "bee", "ladybug", "spider"):
    REGISTRY[_k] = Entry("insect", _c, 30)
PROPS = (
    "block brick domino dice ball marble pyramid_block cylinder star heart coin gem crystal gear ring balloon gift "
    "tree pine palm dead_tree bush flower mushroom rock cactus log seaweed coral mountain volcano cloud rainbow grass snowman "
    "house building tower castle temple pyramid column hut tent barn lighthouse windmill fence tombstone lamp bench sign door elevator "
    "car taxi police_car bus truck rocket ufo airplane boat ship submarine satellite train "
    "planet earth mars jupiter saturn moon neptune venus sun black_hole asteroid comet galaxy "
    "table chair bed sofa tv screen computer laptop phone book candle campfire fire torch lantern clock chest treasure box crate barrel "
    "cauldron bottle potion flask beaker cup coffee mug bulb lightbulb idea tape sword shield hammer crown trophy flag magnifier arrow lightning "
    "atom dna molecule cell virus bacteria brain magnet pizza cake apple donut bread loaf croissant icecream candy egg burger banana"
).split()
for _k in PROPS:
    REGISTRY[_k] = Entry("prop", _p, 40)


def build(kind: str, color, rng: np.random.Generator) -> tuple[Model, float]:
    entry = REGISTRY.get(kind) or REGISTRY["block"]
    return entry.builder(kind if kind in REGISTRY else "block", color, rng)


def category(kind: str) -> str:
    e = REGISTRY.get(kind)
    return e.cat if e else "prop"
