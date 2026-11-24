"""Cenários: chão (textura em coordenadas de mundo), céu por horário, luz, névoa, clima e decoração."""

from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass, field

import cv2
import numpy as np

from .geom import F32, Mesh, box, cone, cylinder, mat4, mix_rgb, sphere
from .renderer import Look, Particles, PointLight, World, value_noise

# ------------------------------------------------------------------ estilos visuais
LOOKS: dict[str, Look] = {
    "pixar3d": Look(sat=1.12, contrast=1.06, bloom=0.18, vignette=0.25, rim=0.22),
    "realista3d": Look(sat=1.0, contrast=1.12, bloom=0.16, vignette=0.32, rim=0.12, spec=1.2),
    "documental": Look(sat=0.95, contrast=1.06, tint=(1.03, 1.0, 0.95), vignette=0.3, rim=0.1),
    "sombrio": Look(
        sat=0.5,
        contrast=1.18,
        bright=-0.04,
        tint=(0.9, 0.97, 1.1),
        bloom=0.2,
        bloom_thr=190,
        vignette=0.62,
        grain=0.07,
        rim=0.25,
        shake=1.0,
    ),
    "fantasia": Look(
        sat=1.25, contrast=1.05, tint=(1.04, 0.98, 1.07), bloom=0.45, bloom_thr=185, vignette=0.35, rim=0.32
    ),
    "anime3d": Look(sat=1.3, contrast=1.1, cel=3, rim=0.35, bloom=0.15, vignette=0.2),
    "lowpoly": Look(sat=0.95, pastel=0.1, rim=0.1, spec=0.3, vignette=0.2),
    "clay": Look(sat=0.85, pastel=0.18, spec=0.35, grain=0.035, rim=0.08, vignette=0.28),
    "neon": Look(
        sat=1.35,
        contrast=1.15,
        bloom=0.75,
        bloom_thr=170,
        vignette=0.45,
        rim=0.9,
        rim_color=(1.0, 0.25, 0.85),
    ),
}

TIMES: dict[str, dict] = {
    "day": dict(
        zenith=(0.28, 0.52, 0.92),
        horizon=(0.76, 0.86, 0.97),
        sun_dir=(0.5, 0.8, 0.45),
        sun_color=(1.0, 0.95, 0.86),
        amb_sky=(0.45, 0.5, 0.62),
        amb_ground=(0.26, 0.23, 0.18),
        cloud_color=(1.0, 1.0, 1.0),
    ),
    "sunset": dict(
        zenith=(0.2, 0.22, 0.5),
        horizon=(1.0, 0.6, 0.34),
        sun_dir=(0.85, 0.2, -0.45),
        sun_color=(1.0, 0.62, 0.36),
        amb_sky=(0.45, 0.38, 0.46),
        amb_ground=(0.26, 0.18, 0.15),
        cloud_color=(1.0, 0.72, 0.62),
    ),
    "dawn": dict(
        zenith=(0.34, 0.45, 0.76),
        horizon=(1.0, 0.78, 0.62),
        sun_dir=(-0.85, 0.24, -0.45),
        sun_color=(1.0, 0.8, 0.62),
        amb_sky=(0.46, 0.46, 0.55),
        amb_ground=(0.25, 0.21, 0.19),
        cloud_color=(1.0, 0.86, 0.8),
    ),
    "night": dict(
        zenith=(0.015, 0.025, 0.07),
        horizon=(0.07, 0.09, 0.18),
        sun_dir=(-0.35, 0.62, -0.55),
        sun_color=(0.42, 0.5, 0.72),
        amb_sky=(0.17, 0.2, 0.31),
        amb_ground=(0.06, 0.06, 0.1),
        cloud_color=(0.16, 0.18, 0.26),
        stars=1.0,
        moon=True,
        sun_disc=False,
    ),
}


@dataclass
class Setting:
    ground: str | None = "grass"
    decor: tuple[tuple[str, int], ...] = ()
    backdrop: tuple[tuple[str, int], ...] = ()  # coisas grandes e distantes (montanhas, pirâmides)
    fog: float = 0.014
    clouds: float = 0.55
    time: str = "day"
    weather: str = "none"
    indoor: bool = False
    structure: str = ""
    override: dict = field(default_factory=dict)
    ring: tuple[float, float] = (6.5, 26.0)
    decor_color: tuple | None = None


SETTINGS: dict[str, Setting] = {
    "forest": Setting(
        "forest",
        (("tree", 9), ("pine", 12), ("bush", 9), ("rock", 5), ("mushroom", 5), ("flower", 9)),
        fog=0.02,
    ),
    "jungle": Setting(
        "jungle",
        (("palm", 8), ("tree", 10), ("bush", 14), ("flower", 8), ("rock", 4)),
        fog=0.032,
        clouds=0.3,
        override=dict(fog_tint=(0.72, 0.85, 0.72)),
    ),
    "park": Setting(
        "grass", (("tree", 8), ("bush", 6), ("bench", 3), ("lamp", 4), ("flower", 12)), fog=0.012
    ),
    "city": Setting("city", (("lamp", 5),), structure="city", fog=0.012, ring=(7.0, 30.0)),
    "village": Setting(
        "grass", (("house", 7), ("tree", 8), ("fence", 4), ("bush", 5), ("flower", 6)), fog=0.012
    ),
    "farm": Setting(
        "farm", (("tree", 5), ("fence", 6), ("bush", 4)), backdrop=(("barn", 1), ("windmill", 1)), fog=0.01
    ),
    "desert": Setting(
        "desert",
        (("cactus", 8), ("rock", 6)),
        backdrop=(("pyramid", 2),),
        fog=0.006,
        clouds=0.15,
        override=dict(horizon=(0.95, 0.85, 0.7)),
    ),
    "egypt": Setting(
        "desert",
        (("rock", 4), ("column", 4), ("palm", 3)),
        backdrop=(("pyramid", 3),),
        fog=0.006,
        clouds=0.1,
        override=dict(horizon=(0.97, 0.86, 0.68)),
    ),
    "beach": Setting("beach", (("palm", 6), ("rock", 3)), fog=0.008, clouds=0.4),
    "ocean": Setting("ocean", (), backdrop=(("rock", 2),), fog=0.008, clouds=0.5),
    "river": Setting("river", (("tree", 8), ("bush", 8), ("rock", 5), ("flower", 6)), fog=0.015),
    "underwater": Setting(
        "underwater",
        (("seaweed", 14), ("coral", 10), ("rock", 6)),
        clouds=0.0,
        weather="bubbles",
        override=dict(
            zenith=(0.05, 0.33, 0.52),
            horizon=(0.08, 0.42, 0.58),
            sun_color=(0.55, 0.85, 0.95),
            amb_sky=(0.32, 0.52, 0.62),
            amb_ground=(0.12, 0.25, 0.3),
            sun_disc=False,
            caustics=0.55,
            fog=0.085,
        ),
    ),
    "mountains": Setting(
        "grass", (("pine", 14), ("rock", 7), ("flower", 6)), backdrop=(("mountain", 6),), fog=0.008
    ),
    "snow": Setting(
        "snow",
        (("pine", 14), ("rock", 4), ("snowman", 1)),
        backdrop=(("mountain", 4),),
        fog=0.016,
        weather="snow",
        decor_color=(0.85, 0.92, 0.95),
        override=dict(horizon=(0.85, 0.9, 0.97)),
    ),
    "cave": Setting(
        "cave",
        (("rock", 10), ("crystal", 7)),
        clouds=0.0,
        structure="cave",
        override=dict(
            zenith=(0.03, 0.03, 0.04),
            horizon=(0.05, 0.05, 0.06),
            sun_color=(0.25, 0.23, 0.22),
            amb_sky=(0.14, 0.13, 0.16),
            amb_ground=(0.05, 0.05, 0.06),
            sun_disc=False,
            stars=0.0,
            moon=False,
            fog=0.07,
        ),
    ),
    "graveyard": Setting(
        "graveyard",
        (("tombstone", 14), ("dead_tree", 5), ("fence", 3)),
        time="night",
        fog=0.05,
        weather="fog",
    ),
    "room": Setting("wood", (), indoor=True, structure="room"),
    "office": Setting("tiles", (), indoor=True, structure="office"),
    "lab": Setting("tiles", (), indoor=True, structure="lab"),
    "stage": Setting("stage", (), indoor=True, structure="stage"),
    "studio": Setting("studio", (), clouds=0.0, structure="studio", fog=0.004),
    "space": Setting(
        None,
        (("asteroid", 8),),
        backdrop=(("planet", 3),),
        clouds=0.0,
        override=dict(
            zenith=(0.0, 0.0, 0.02),
            horizon=(0.02, 0.02, 0.06),
            nadir=(0.0, 0.0, 0.02),
            stars=1.3,
            nebula=0.8,
            sun_dir=(0.6, 0.35, 0.5),
            sun_color=(1.0, 0.97, 0.92),
            amb_sky=(0.1, 0.1, 0.15),
            amb_ground=(0.04, 0.04, 0.07),
            sun_disc=True,
            fog=0.0,
        ),
    ),
    "moon": Setting(
        "moon",
        (("rock", 10),),
        backdrop=(("earth", 1),),
        clouds=0.0,
        override=dict(
            zenith=(0.0, 0.0, 0.02),
            horizon=(0.03, 0.03, 0.05),
            stars=1.2,
            sun_dir=(0.6, 0.45, 0.4),
            sun_color=(1.0, 0.98, 0.95),
            amb_sky=(0.12, 0.12, 0.16),
            amb_ground=(0.06, 0.06, 0.07),
            fog=0.003,
        ),
    ),
    "mars": Setting(
        "mars",
        (("rock", 12),),
        backdrop=(("mountain", 3),),
        clouds=0.0,
        fog=0.02,
        decor_color=(0.6, 0.32, 0.2),
        override=dict(zenith=(0.55, 0.4, 0.33), horizon=(0.88, 0.62, 0.45), sun_color=(1.0, 0.85, 0.7)),
    ),
    "sky": Setting("clouds", (("cloud", 12),), clouds=0.6, fog=0.03),
    "temple": Setting("marble", (("column", 8),), backdrop=(("temple", 1),), fog=0.01),
    "castle": Setting("grass", (("tree", 7), ("bush", 6), ("tower", 2)), backdrop=(("castle", 1),), fog=0.01),
    "volcano": Setting(
        "volcanic",
        (("rock", 9), ("dead_tree", 3)),
        backdrop=(("volcano", 1),),
        fog=0.025,
        clouds=0.2,
        weather="embers",
        override=dict(horizon=(0.75, 0.45, 0.35), zenith=(0.3, 0.2, 0.22)),
    ),
    "road": Setting("road", (("lamp", 6), ("tree", 6), ("rock", 4)), structure="road", fog=0.01),
}

INDOOR_WALL = {
    "room": (0.93, 0.86, 0.74),
    "office": (0.88, 0.9, 0.92),
    "lab": (0.9, 0.95, 0.97),
    "stage": (0.12, 0.08, 0.1),
}


# ------------------------------------------------------------------ textura do chão
N_TEX = 1024
EXTENT = 80.0


def _grid() -> tuple[np.ndarray, np.ndarray]:
    c = ((np.arange(N_TEX, dtype=F32) + 0.5) / N_TEX - 0.5) * EXTENT
    X, Z = np.meshgrid(c, c)
    return X, Z


def _mix(a, b, t):
    a, b = np.asarray(a, F32), np.asarray(b, F32)
    return a + (b - a) * t[..., None]


def ground_texture(kind: str, seed: int) -> tuple[np.ndarray, np.ndarray | None, np.ndarray | None, float]:
    """Retorna (textura RGB, máscara de água, detalhe, escala do detalhe)."""
    X, Z = _grid()
    n1 = value_noise(N_TEX, 8, seed, 4)
    n2 = value_noise(N_TEX, 40, seed + 1, 3)
    detail = value_noise(256, 16, seed + 2, 3)
    water = None
    dscale = 3.0

    def base(c1, c2, var=0.06):
        return _mix(c1, c2, n1) * (1 + (n2[..., None] - 0.5) * var * 2)

    if kind in ("grass", "forest", "jungle", "graveyard", "river", "farm", "road"):
        pal = {
            "grass": ((0.27, 0.39, 0.18), (0.38, 0.47, 0.22)),
            "forest": ((0.22, 0.32, 0.15), (0.33, 0.41, 0.19)),
            "jungle": ((0.15, 0.27, 0.12), (0.23, 0.35, 0.15)),
            "graveyard": ((0.19, 0.23, 0.15), (0.26, 0.29, 0.19)),
        }
        c1, c2 = pal.get(kind, pal["grass"])
        tex = base(c1, c2)
        dirt = np.clip((value_noise(N_TEX, 14, seed + 3, 3) - 0.7) / 0.08, 0, 1)
        tex = tex + (np.asarray((0.45, 0.37, 0.26), F32) - tex) * (dirt * 0.8)[..., None]
        if kind == "graveyard":
            path = np.clip(1.2 - np.abs(X + 0.6 * np.sin(Z * 0.15)) / 1.1, 0, 1)
            tex = tex + (np.asarray((0.33, 0.29, 0.24), F32) - tex) * path[..., None]
        if kind == "farm":
            field_ = ((X > 4) & (Z < -3)).astype(F32)
            rows = (np.sin(X * 4.2) > 0.2).astype(F32)
            crop = _mix((0.45, 0.33, 0.2), (0.35, 0.55, 0.2), rows)
            tex = tex + (crop - tex) * field_[..., None]
        if kind == "river":
            edge = -5.5 + 1.0 * np.sin(X * 0.18) + 0.5 * np.sin(X * 0.47 + 1)
            d = np.abs(Z - edge)
            water = np.clip((2.2 - d) / 0.25, 0, 1).astype(F32)
            bank = np.clip((3.0 - d) / 0.6, 0, 1) * (1 - water)
            tex = tex + (np.asarray((0.55, 0.47, 0.33), F32) - tex) * (bank * 0.8)[..., None]
        if kind == "road":
            road = (np.abs(Z) < 2.2).astype(F32)
            asphalt = np.full_like(tex, 0.24) * (1 + (n2[..., None] - 0.5) * 0.15)
            tex = tex + (asphalt - tex) * road[..., None]
            dash = ((np.abs(Z) < 0.07) & (np.mod(X, 3.0) < 1.6)).astype(F32)
            edge_line = (np.abs(np.abs(Z) - 2.0) < 0.06).astype(F32)
            tex = tex + (np.asarray((0.95, 0.8, 0.25), F32) - tex) * dash[..., None]
            tex = tex + (np.asarray((0.9, 0.9, 0.88), F32) - tex) * edge_line[..., None]
    elif kind in ("sand", "beach", "underwater"):
        tex = base((0.84, 0.75, 0.54), (0.93, 0.85, 0.66))
        rip = np.sin(X * 2.6 + n1 * 9) * 0.035
        tex = tex * (1 + rip[..., None])
        if kind == "underwater":
            tex = tex * np.asarray((0.85, 0.95, 0.95), F32)
        if kind == "beach":
            shore = -7.0 + 0.8 * np.sin(X * 0.25) + 0.4 * np.sin(X * 0.7)
            water = np.clip((shore - Z) / 0.6, 0, 1).astype(F32)
            wet = np.clip(1 - np.abs(Z - shore - 0.6) / 1.2, 0, 1)
            tex = tex * (1 - 0.18 * wet[..., None])
            foam = np.clip(1 - np.abs(Z - shore + 0.1) / 0.18, 0, 1)
            tex = tex + (1 - tex) * (foam * 0.85)[..., None]
    elif kind == "desert":
        tex = base((0.82, 0.62, 0.38), (0.91, 0.73, 0.48))
        dunes = np.sin((X + Z * 0.4) / 5.5 + n1 * 4) * 0.08
        tex = tex * (1 + dunes[..., None])
    elif kind == "snow":
        tex = base((0.84, 0.88, 0.95), (0.97, 0.98, 1.0), 0.03)
    elif kind in ("moon", "mars"):
        c1, c2 = (
            ((0.4, 0.4, 0.42), (0.6, 0.6, 0.61)) if kind == "moon" else ((0.6, 0.3, 0.17), (0.78, 0.45, 0.26))
        )
        tex = base(c1, c2, 0.1)
        rng = np.random.default_rng(seed)
        dark = np.zeros((N_TEX, N_TEX), F32)
        rim = np.zeros((N_TEX, N_TEX), F32)
        for _ in range(55 if kind == "moon" else 18):
            cx, cy = rng.integers(0, N_TEX, 2)
            r = int(rng.uniform(4, 40))
            cv2.circle(dark, (int(cx), int(cy)), r, 1.0, -1, cv2.LINE_AA)
            cv2.circle(rim, (int(cx), int(cy)), r + 2, 1.0, max(2, r // 6), cv2.LINE_AA)
        dark = cv2.GaussianBlur(dark, (0, 0), 3)
        rim = cv2.GaussianBlur(rim, (0, 0), 2)
        tex = tex * (1 - 0.25 * dark[..., None]) * (1 + 0.18 * rim[..., None])
    elif kind == "city":
        tile = ((np.mod(X, 1.5) < 0.05) | (np.mod(Z, 1.5) < 0.05)).astype(F32)
        tex = base((0.6, 0.6, 0.58), (0.68, 0.67, 0.64), 0.04) * (1 - 0.18 * tile[..., None])
        road = ((Z < -5.5) & (Z > -12.5)) | ((X < -9.5) & (X > -15.5))
        asphalt = np.full_like(tex, 0.23) * (1 + (n2[..., None] - 0.5) * 0.15)
        tex = np.where(road[..., None], asphalt, tex)
        dash = (np.abs(Z + 9.0) < 0.07) & (np.mod(X, 3.0) < 1.6) & (X > -9.5)
        tex[dash] = (0.95, 0.82, 0.25)
        cross = (Z < -5.8) & (Z > -12.2) & (np.abs(X - 2.0) < 2.0) & (np.mod(Z, 0.9) < 0.45)
        tex[cross] = (0.88, 0.88, 0.86)
    elif kind in ("tiles", "marble"):
        size = 1.0 if kind == "tiles" else 2.0
        c1, c2 = (
            ((0.85, 0.86, 0.88), (0.9, 0.9, 0.92))
            if kind == "tiles"
            else ((0.86, 0.84, 0.8), (0.93, 0.91, 0.87))
        )
        tex = base(c1, c2, 0.03)
        grout = ((np.mod(X, size) < 0.03) | (np.mod(Z, size) < 0.03)).astype(F32)
        tex = tex * (1 - 0.2 * grout[..., None])
        if kind == "marble":
            vein = np.clip(1 - np.abs(np.sin(X * 0.8 + n1 * 14 + Z * 0.3)) * 18, 0, 1)
            tex = tex * (1 - 0.12 * vein[..., None])
        dscale = 6.0
    elif kind in ("wood", "stage"):
        width = 0.22
        idx = np.floor(Z / width)
        h = np.mod(np.sin(idx * 12.9898) * 43758.5453, 1.0).astype(F32)
        c1, c2 = (
            ((0.52, 0.35, 0.2), (0.7, 0.5, 0.31))
            if kind == "wood"
            else ((0.24, 0.16, 0.11), (0.34, 0.23, 0.15))
        )
        tex = _mix(c1, c2, h * 0.7 + n2 * 0.3)
        seam = (np.mod(Z, width) < 0.012) | (np.mod(X + h * 2.4, 2.4) < 0.015)
        tex = tex * (1 - 0.3 * seam[..., None].astype(F32))
        grain = np.sin(X * 25 + n1 * 30) * 0.03
        tex = tex * (1 + grain[..., None])
        dscale = 5.0
    elif kind == "studio":
        tex = np.ones((N_TEX, N_TEX, 3), F32) * np.asarray((0.86, 0.87, 0.9), F32)
        detail = None
    elif kind == "cave":
        tex = base((0.19, 0.17, 0.16), (0.3, 0.27, 0.25), 0.15)
    elif kind == "volcanic":
        tex = base((0.14, 0.12, 0.11), (0.24, 0.2, 0.18), 0.12)
        crack = np.clip(1 - np.abs(n1 - 0.5) * 90, 0, 1) + np.clip(1 - np.abs(n2 - 0.5) * 60, 0, 1) * 0.6
        tex = tex + (np.asarray((1.0, 0.36, 0.08), F32) - tex) * np.clip(crack, 0, 1)[..., None]
    elif kind == "clouds":
        tex = base((0.78, 0.83, 0.95), (0.98, 0.98, 1.0), 0.04)
        dscale = 8.0
    elif kind == "ocean":
        tex = np.ones((N_TEX, N_TEX, 3), F32) * np.asarray((0.1, 0.3, 0.45), F32)
        water = np.ones((N_TEX, N_TEX), F32)
    else:
        tex = base((0.5, 0.5, 0.5), (0.6, 0.6, 0.6))
    return np.clip(tex, 0, 1).astype(F32), water, detail, dscale


# ------------------------------------------------------------------ montagem do mundo
def make_world(setting_key: str, time_key: str, look_key: str, seed: int) -> tuple[World, Setting, str]:
    st = SETTINGS.get(setting_key) or SETTINGS["studio"]
    time_key = time_key if time_key in TIMES else st.time
    if look_key == "sombrio" and not st.indoor and setting_key not in ("space", "underwater", "cave"):
        time_key = "night"
    if look_key == "neon" and not st.indoor and setting_key not in ("space", "underwater"):
        time_key = "night"
    if setting_key in ("space", "moon", "underwater", "cave"):
        time_key = "day"
    t = dict(TIMES[time_key])
    w = World(seed=seed)
    for k in ("zenith", "horizon", "sun_dir", "sun_color", "amb_sky", "amb_ground", "cloud_color"):
        setattr(w, k, tuple(t[k]))
    w.stars = t.get("stars", 0.0)
    w.moon = t.get("moon", False)
    w.sun_disc = t.get("sun_disc", True)
    w.clouds = st.clouds if time_key != "night" else st.clouds * 0.6
    w.fog = st.fog
    ov = dict(st.override)
    fog_tint = ov.pop("fog_tint", None)
    for k, v in ov.items():
        setattr(w, k, v)
    if st.indoor:
        wall = INDOOR_WALL.get(setting_key, (0.9, 0.88, 0.85))
        w.zenith = w.horizon = mix_rgb(wall, (0, 0, 0), 0.15)
        w.fog = 0.012
        w.clouds = 0.0
        w.stars = 0.0
        w.moon = False
        w.sun_disc = False
        w.sun_dir = (0.45, 0.85, 0.5)
        if setting_key == "stage":
            w.sun_color, w.amb_sky, w.amb_ground = (0.35, 0.32, 0.4), (0.12, 0.1, 0.16), (0.05, 0.04, 0.06)
            w.fog = 0.03
        else:
            w.sun_color = (0.75, 0.72, 0.66) if time_key != "night" else (0.35, 0.33, 0.32)
            w.amb_sky, w.amb_ground = (0.52, 0.5, 0.48), (0.3, 0.27, 0.24)
        w.shadow = 0.42
    if setting_key == "studio":
        bg = (0.78, 0.8, 0.85)
        if look_key in ("clay", "lowpoly", "pixar3d", "anime3d", "fantasia"):
            bg = {
                "clay": (0.93, 0.8, 0.72),
                "lowpoly": (0.74, 0.82, 0.93),
                "pixar3d": (0.72, 0.82, 0.95),
                "anime3d": (0.95, 0.8, 0.88),
                "fantasia": (0.55, 0.45, 0.75),
            }[look_key]
        if look_key in ("sombrio", "neon"):
            bg = (0.07, 0.07, 0.1)
        w.zenith = tuple(c * 0.82 for c in bg)
        w.horizon = bg
        w.sun_disc = False
        w.stars = 0.0
        w.moon = False
        w.amb_sky, w.amb_ground = (0.42, 0.43, 0.47), (0.22, 0.22, 0.25)
        w.sun_color = (0.8, 0.78, 0.74)
        w.sun_dir = (0.45, 0.8, 0.55)
        w.shadow = 0.5
    if st.ground:
        tex, water, detail, dscale = ground_texture(st.ground, seed)
        if setting_key == "studio":
            tex = tex * 0 + np.asarray(mix_rgb(w.horizon, (1, 1, 1), 0.0), F32)
        w.ground_tex = tex
        w.water_mask = water
        w.detail_tex = detail
        w.detail_scale = dscale
        w.ground_extent = EXTENT
        if st.ground in ("snow", "clouds"):
            w.detail_amount = 0.12
    else:
        w.ground = False
    if look_key == "sombrio":
        w.fog = max(w.fog, 0.035) * 1.6
        w.amb_sky = tuple(c * 0.88 for c in w.amb_sky)
    if look_key == "neon":
        w.amb_sky = (0.12, 0.08, 0.2)
    fog = w.horizon if fog_tint is None else mix_rgb(w.horizon, fog_tint, 0.5)
    w.fog_color = tuple(fog)
    return w, st, time_key


# ------------------------------------------------------------------ estruturas fixas
def structure(kind: str, setting_key: str, seed: int, time_key: str) -> tuple[list[Mesh], list[PointLight]]:
    """Paredes, cortinas, ruas... já em coordenadas de mundo."""
    rng = np.random.default_rng(seed)
    meshes: list[Mesh] = []
    lights: list[PointLight] = []
    night = time_key == "night"
    if kind in ("room", "office", "lab"):
        wall = INDOOR_WALL[kind]
        back_z, side_x, h = -5.0, 6.5, 6.0
        meshes.append(box(2 * side_x + 1, h, 0.3, wall, seg=6, base=True).at((0, 0, back_z - 0.15)))
        for sx in (-1, 1):
            meshes.append(
                box(0.3, h, 14, mix_rgb(wall, (0, 0, 0), 0.06), seg=6, base=True).at(
                    (sx * (side_x + 0.15), 0, 2.0)
                )
            )
        meshes.append(
            box(2 * side_x, 0.25, 0.08, mix_rgb(wall, (0.3, 0.2, 0.1), 0.5), base=True).at(
                (0, 0, back_z + 0.02)
            )
        )
        glass = (0.55, 0.78, 0.95) if not night else (0.06, 0.08, 0.18)
        for x in (-3.2, 3.2):
            meshes.append(box(2.2, 2.0, 0.1, (0.95, 0.95, 0.95), base=True).at((x, 1.6, back_z + 0.05)))
            meshes.append(
                box(1.9, 1.7, 0.05, glass, base=True, emit=0.8 if not night else 0.3).at(
                    (x, 1.75, back_z + 0.1)
                )
            )
        meshes.append(box(1.2, 0.9, 0.06, (0.85, 0.5, 0.3), base=True).at((0, 2.1, back_z + 0.08)))
        meshes.append(box(1.05, 0.75, 0.07, (0.35, 0.55, 0.7), base=True).at((0, 2.18, back_z + 0.1)))
        if kind == "room":
            props = [
                ("sofa", (-3.8, 0, -3.8), 0.0),
                ("table", (3.6, 0, -3.6), 0.0),
                ("chair", (2.6, 0, -2.8), 0.6),
                ("tv", (0, 0, -4.5), 0.0),
                ("lamp_floor", (-5.5, 0, -4.2), 0.0),
            ]
        elif kind == "office":
            props = [
                ("table", (-3.5, 0, -3.5), 0.0),
                ("table", (3.5, 0, -3.5), 0.0),
                ("computer", (-3.5, 0.8, -3.6), 0.0),
                ("computer", (3.5, 0.8, -3.6), 0.0),
                ("chair", (-3.5, 0, -2.6), PI_),
                ("chair", (3.5, 0, -2.6), PI_),
            ]
        else:
            props = [
                ("table", (-3.8, 0, -3.6), 0.0),
                ("table", (3.8, 0, -3.6), 0.0),
                ("beaker", (-4.1, 0.8, -3.6), 0.0),
                ("beaker", (-3.5, 0.8, -3.7), 0.0),
                ("bottle", (3.6, 0.8, -3.6), 0.0),
                ("computer", (4.1, 0.8, -3.5), 0.0),
            ]
        from .models import build as build_model

        for name, pos, yaw in props:
            if name == "lamp_floor":
                meshes += [
                    cylinder(0.03, 1.6, (0.2, 0.2, 0.22), 6).at(pos),
                    cone(0.3, 0.35, (1.0, 0.92, 0.75), 10, emit=0.9).at((pos[0], 1.55, pos[2])),
                ]
                lights.append(PointLight(np.array((pos[0], 1.6, pos[2]), F32), (1.0, 0.82, 0.55), 1.4, 4.5))
                continue
            m, _ = build_model(name, None, rng)
            v, _ = m.pose(_m4(pos, yaw), {}, {}, {})
            mm = m.mesh.copy()
            mm.v = v
            meshes.append(mm)
        lights.append(PointLight(np.array((0, 4.8, 0.5), F32), (1.0, 0.92, 0.8), 1.1, 7.0))
    elif kind == "stage":
        back_z = -4.5
        for i in range(26):
            x = -9 + i * 0.72
            meshes.append(
                cylinder(0.38, 7.0, (0.55, 0.06, 0.1), 8)
                .vary(0.08, i)
                .at((x, 0, back_z + 0.25 * math.sin(i * 1.7)))
            )
        meshes.append(box(20, 0.6, 9, (0.22, 0.14, 0.1), base=True, seg=4).at((0, -0.55, -0.5)))
        for x in (-3.5, 0.0, 3.5):
            meshes.append(cylinder(0.25, 0.35, (0.15, 0.15, 0.17), 10).at((x, 6.2, 2.0)))
            meshes.append(cylinder(0.2, 0.02, (1.0, 0.95, 0.8), 10, emit=1.0).at((x, 6.18, 2.0)))
            lights.append(
                PointLight(
                    np.array((x, 5.5, 1.5), F32), (1.0, 0.85, 0.65) if x else (0.7, 0.75, 1.0), 2.6, 5.5
                )
            )
    elif kind == "city":
        palette = [
            (0.62, 0.66, 0.72),
            (0.74, 0.68, 0.6),
            (0.5, 0.55, 0.62),
            (0.82, 0.78, 0.72),
            (0.7, 0.55, 0.5),
        ]
        from .models import build_structure, night_windows

        spots = [(x, -16.0) for x in np.arange(-22, 23, 4.6)] + [(x, -21.0) for x in np.arange(-20, 21, 5.2)]
        spots += [(sx * 13.0, z) for sx in (-1, 1) for z in (-3.0, 2.5, 8.0)] + [(18.5, -9.0), (-20.0, -9.0)]
        for x, z in spots:
            m = build_structure("building", palette[int(rng.integers(0, len(palette)))], rng)
            v, _ = m.pose(_m4((x, 0, z), 0.0), {}, {}, {})
            mm = night_windows(m.mesh, rng) if night else m.mesh.copy()
            mm.v = v
            meshes.append(mm)
        for x in (-6, 6):
            meshes += [
                cylinder(0.05, 3.0, (0.2, 0.2, 0.22), 6).at((x, 0, -5.2)),
                box(0.25, 0.7, 0.25, (0.15, 0.15, 0.17), base=True).at((x, 3.0, -5.2)),
                sphere(0.06, (0.2, 1.0, 0.3), nu=6, nv=4, emit=1.0).at((x, 3.2, -5.05)),
                sphere(0.06, (1.0, 0.2, 0.15), nu=6, nv=4, emit=1.0).at((x, 3.5, -5.05)),
            ]
    elif kind == "cave":
        for i in range(18):
            a = -PI_ / 2 + (i / 17 - 0.5) * 3.4
            r = rng.uniform(7, 14)
            h = rng.uniform(2.5, 7)
            meshes.append(
                cone(rng.uniform(0.6, 1.4), h, (0.25, 0.22, 0.21), 7)
                .jitter(0.08, i)
                .vary(0.1, i)
                .at((math.cos(a) * r, 0, math.sin(a) * r))
            )
            meshes.append(
                cone(rng.uniform(0.5, 1.0), h * 0.7, (0.22, 0.2, 0.19), 7)
                .jitter(0.06, i + 50)
                .at((math.cos(a) * r * 1.1, 9.0, math.sin(a) * r * 1.1), (PI_, 0, 0))
            )
        meshes.append(box(60, 0.5, 60, (0.12, 0.11, 0.11), base=True, seg=8).at((0, 9.0, 0)))
    elif kind == "road":
        for i in range(-6, 7):
            x = i * 6.0
            meshes.append(box(0.12, 0.9, 0.12, (0.9, 0.9, 0.9), base=True).at((x, 0, -2.6)))
            meshes.append(box(0.12, 0.12, 0.05, (1.0, 0.3, 0.1), base=True, emit=0.8).at((x, 0.75, -2.53)))
    return meshes, lights


PI_ = math.pi


def _m4(pos, yaw):
    from .geom import mat4

    return mat4(pos, (0, yaw, 0), 1.0)


# ------------------------------------------------------------------ clima
def weather(
    kind: str, seed: int, center: np.ndarray, span: float
) -> Callable[[float], list[Particles]] | None:
    """Partículas determinísticas em função do tempo (não precisa simular estado)."""
    rng = np.random.default_rng(seed + 99)
    c = np.asarray(center, F32)
    W = max(8.0, span * 1.4)
    if kind == "rain":
        n = 650
        base = np.c_[rng.uniform(-W, W, n), rng.uniform(0, 9, n), rng.uniform(-W * 1.3, W * 0.6, n)].astype(
            F32
        )
        speed = rng.uniform(8, 11, n).astype(F32)
        col = np.tile(np.asarray((0.72, 0.78, 0.9), F32), (n, 1))
        streak = np.tile(np.asarray((0.04, 0.5, 0.0), F32), (n, 1))

        def rain(t):
            p = base.copy()
            p[:, 1] = np.mod(base[:, 1] - speed * t, 9.0)
            p[:, 0] += c[0]
            p[:, 2] += c[2]
            return [Particles(p, np.full(n, 0.012, F32), col, np.full(n, 0.75, F32), streak)]

        return rain
    if kind == "snow":
        n = 450
        base = np.c_[rng.uniform(-W, W, n), rng.uniform(0, 8, n), rng.uniform(-W * 1.3, W * 0.6, n)].astype(
            F32
        )
        ph = rng.uniform(0, 6.28, n).astype(F32)
        rad = rng.uniform(0.02, 0.05, n).astype(F32)
        col = np.tile(np.asarray((1.0, 1.0, 1.0), F32), (n, 1))

        def snow(t):
            p = base.copy()
            p[:, 1] = np.mod(base[:, 1] - 0.8 * t, 8.0)
            p[:, 0] += c[0] + 0.35 * np.sin(t * 0.8 + ph)
            p[:, 2] += c[2]
            return [Particles(p, rad, col, None, None, False, True)]

        return snow
    if kind in ("fireflies", "sparkles", "magic"):
        n = 70 if kind == "fireflies" else 110
        base = np.c_[
            rng.uniform(-W * 0.6, W * 0.6, n), rng.uniform(0.3, 3.5, n), rng.uniform(-W * 0.8, W * 0.3, n)
        ].astype(F32)
        ph = rng.uniform(0, 6.28, n).astype(F32)
        if kind == "fireflies":
            col = np.tile(np.asarray((0.85, 1.0, 0.4), F32), (n, 1))
        else:
            pal = np.asarray([(1.0, 0.9, 0.5), (1.0, 1.0, 1.0), (0.7, 0.8, 1.0), (1.0, 0.6, 0.9)], F32)
            col = pal[rng.integers(0, len(pal), n)]

        def glow(t):
            p = base.copy()
            p[:, 0] += c[0] + 0.4 * np.sin(t * 0.5 + ph)
            p[:, 1] += 0.25 * np.sin(t * 0.7 + ph * 2)
            p[:, 2] += c[2] + 0.4 * np.cos(t * 0.45 + ph)
            a = (0.5 + 0.5 * np.sin(t * (2.0 if kind == "fireflies" else 4.0) + ph)) ** 2
            r = np.full(n, 0.035 if kind == "fireflies" else 0.03, F32) * (0.6 + 0.6 * a)
            return [Particles(p, r.astype(F32), col, (0.3 + 0.9 * a).astype(F32), None, False, True)]

        return glow
    if kind == "bubbles":
        n = 90
        base = np.c_[
            rng.uniform(-W * 0.6, W * 0.6, n), rng.uniform(0, 6, n), rng.uniform(-W * 0.8, W * 0.3, n)
        ].astype(F32)
        ph = rng.uniform(0, 6.28, n).astype(F32)
        rad = rng.uniform(0.03, 0.09, n).astype(F32)
        col = np.tile(np.asarray((0.8, 0.95, 1.0), F32), (n, 1))

        def bubbles(t):
            p = base.copy()
            p[:, 1] = np.mod(base[:, 1] + 0.7 * t, 6.0)
            p[:, 0] += c[0] + 0.12 * np.sin(t * 3 + ph)
            p[:, 2] += c[2]
            return [Particles(p, rad, col, np.full(n, 0.9, F32), None, True, True)]

        return bubbles
    if kind == "embers":
        n = 140
        base = np.c_[
            rng.uniform(-W * 0.7, W * 0.7, n), rng.uniform(0, 7, n), rng.uniform(-W, W * 0.3, n)
        ].astype(F32)
        ph = rng.uniform(0, 6.28, n).astype(F32)
        col = np.tile(np.asarray((1.0, 0.5, 0.12), F32), (n, 1))

        def embers(t):
            p = base.copy()
            p[:, 1] = np.mod(base[:, 1] + 1.1 * t, 7.0)
            p[:, 0] += c[0] + 0.5 * np.sin(t * 0.9 + ph)
            p[:, 2] += c[2]
            a = np.clip(1 - p[:, 1] / 7.0, 0, 1) * (0.6 + 0.4 * np.sin(t * 9 + ph))
            return [Particles(p, np.full(n, 0.03, F32), col, a.astype(F32), None, False, True)]

        return embers
    if kind in ("confetti", "leaves", "petals"):
        n = 260 if kind == "confetti" else 70
        base = np.c_[
            rng.uniform(-W * 0.8, W * 0.8, n), rng.uniform(0, 8, n), rng.uniform(-W, W * 0.4, n)
        ].astype(F32)
        ph = rng.uniform(0, 6.28, n).astype(F32)
        if kind == "confetti":
            pal = np.asarray(
                [(0.95, 0.3, 0.3), (1.0, 0.8, 0.2), (0.3, 0.8, 0.4), (0.3, 0.6, 1.0), (0.9, 0.4, 0.9)], F32
            )
        elif kind == "leaves":
            pal = np.asarray([(0.85, 0.45, 0.12), (0.9, 0.7, 0.2), (0.6, 0.3, 0.1), (0.45, 0.6, 0.2)], F32)
        else:
            pal = np.asarray([(1.0, 0.75, 0.85), (1.0, 0.9, 0.95)], F32)
        col = pal[rng.integers(0, len(pal), n)]
        speed = 1.4 if kind == "confetti" else 0.7

        def falling(t):
            p = base.copy()
            p[:, 1] = np.mod(base[:, 1] - speed * t, 8.0)
            p[:, 0] += c[0] + 0.6 * np.sin(t * 1.3 + ph)
            p[:, 2] += c[2] + 0.3 * np.cos(t * 1.1 + ph)
            flick = 0.55 + 0.45 * np.abs(np.sin(t * 6 + ph))
            r = np.full(n, 0.04 if kind == "confetti" else 0.06, F32)
            return [Particles(p, r, col, flick.astype(F32))]

        return falling
    if kind == "dust":
        n = 120
        base = np.c_[
            rng.uniform(-W * 0.5, W * 0.5, n), rng.uniform(0.2, 4, n), rng.uniform(-W * 0.6, W * 0.3, n)
        ].astype(F32)
        ph = rng.uniform(0, 6.28, n).astype(F32)
        col = np.tile(np.asarray((1.0, 0.95, 0.85), F32), (n, 1))

        def dust(t):
            p = base.copy()
            p[:, 0] += c[0] + 0.3 * np.sin(t * 0.3 + ph)
            p[:, 1] += 0.2 * np.sin(t * 0.4 + ph)
            p[:, 2] += c[2]
            return [Particles(p, np.full(n, 0.012, F32), col, np.full(n, 0.45, F32), None, False, True)]

        return dust
    return None


def decor_mesh(kind: str, rng: np.random.Generator, color=None) -> tuple[Mesh, float, list, float]:
    """Malha (local) de um item de cenário, seu raio, luzes (posições locais) e altura em que flutua."""
    from .models import build as build_model

    m, sc = build_model(kind, color, rng)
    v, mats = m.pose(mat4(scale=sc), {}, {}, {})
    mesh = m.mesh.copy()
    mesh.v = v
    lights = []
    for node, pos, col, power, radius, _flick in m.lights:
        mt = mats[m.names.index(node)]
        lights.append((mt[:3, :3] @ np.asarray(pos, F32) + mt[:3, 3], col, power, radius))
    return mesh, m.radius * sc, lights, m.hover
