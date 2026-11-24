"""Rasterizador 3D em software (numpy + OpenCV) e gravação do clipe com ffmpeg.

Por quadro:
1. céu e chão por pixel (em meia resolução): degradê, sol/lua, estrelas, nuvens, textura do chão,
   água animada, sombras projetadas dos atores, poças de luz e névoa;
2. triângulos dos objetos ordenados por profundidade (algoritmo do pintor) com iluminação
   por face (sol, ambiente hemisférico, especular, contorno, luzes pontuais, emissão e névoa);
3. partículas (chuva, neve, vaga-lumes...) junto na ordenação;
4. pós: bloom, vinheta, granulação e flash.
"""

from __future__ import annotations

import math
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

import cv2
import numpy as np

from .geom import F32, Mesh, normalize

NEAR = 0.12


@dataclass
class Look:
    """Acabamento visual (vem do estilo escolhido no painel)."""

    sat: float = 1.1
    contrast: float = 1.05
    bright: float = 0.0
    tint: tuple[float, float, float] = (1.0, 1.0, 1.0)
    bloom: float = 0.2
    bloom_thr: int = 205
    vignette: float = 0.28
    grain: float = 0.0
    cel: int = 0  # 0 = sombreado contínuo; 2..4 = faixas (anime)
    rim: float = 0.18
    spec: float = 1.0
    pastel: float = 0.0
    shake: float = 0.0  # câmera na mão (terror)
    rim_color: tuple[float, float, float] | None = None


@dataclass
class PointLight:
    pos: np.ndarray
    color: tuple[float, float, float]
    power: float = 1.0
    radius: float = 4.0
    ground: bool = True  # False = só ilumina os objetos (luz de preenchimento da câmera)


@dataclass
class World:
    """Ambiente: céu, chão, luz e névoa."""

    zenith: tuple[float, float, float] = (0.32, 0.55, 0.92)
    horizon: tuple[float, float, float] = (0.78, 0.87, 0.98)
    nadir: tuple[float, float, float] | None = None  # cor abaixo do horizonte quando não há chão
    sun_dir: tuple[float, float, float] = (0.45, 0.75, 0.35)
    sun_color: tuple[float, float, float] = (1.0, 0.95, 0.85)
    sun_disc: bool = True
    amb_sky: tuple[float, float, float] = (0.42, 0.48, 0.6)
    amb_ground: tuple[float, float, float] = (0.22, 0.2, 0.16)
    fog_color: tuple[float, float, float] | None = None
    fog: float = 0.012
    ground: bool = True
    ground_tex: np.ndarray | None = None  # (N, N, 3) RGB 0..1 em coordenadas de mundo
    water_mask: np.ndarray | None = None  # (N, N) 0..1
    ground_extent: float = 80.0
    detail_tex: np.ndarray | None = None  # (n, n) ~1.0, repetida
    detail_scale: float = 3.0
    detail_amount: float = 0.35
    water_deep: tuple[float, float, float] = (0.05, 0.25, 0.4)
    water_shallow: tuple[float, float, float] = (0.12, 0.5, 0.62)
    shadow: float = 0.55
    stars: float = 0.0
    clouds: float = 0.0
    cloud_color: tuple[float, float, float] = (1.0, 1.0, 1.0)
    moon: bool = False
    moon_dir: tuple[float, float, float] = (-0.4, 0.45, -0.8)
    nebula: float = 0.0
    caustics: float = 0.0
    flashes: tuple[float, ...] = ()  # instantes de relâmpago
    seed: int = 0


@dataclass
class Particles:
    """Partículas desenhadas como pontos/traços com profundidade."""

    pos: np.ndarray  # (P, 3)
    radius: np.ndarray  # (P,) em metros
    color: np.ndarray  # (P, 3) RGB
    alpha: np.ndarray | None = None  # (P,) brilho 0..1 (emissivo)
    streak: np.ndarray | None = None  # (P, 3) vetor do traço (chuva)
    ring: bool = False  # desenha só o contorno (bolhas)
    emissive: bool = False


@dataclass
class Frame:
    """O que a cena entrega ao renderizador em um instante."""

    eye: np.ndarray
    target: np.ndarray
    roll: float = 0.0
    fov: float = 50.0
    dyn_v: np.ndarray | None = None  # vértices dinâmicos (mundo)
    emit_scale: np.ndarray | None = None  # (faces dinâmicas,) multiplicador de emissão
    lights: list[PointLight] = field(default_factory=list)
    particles: list[Particles] = field(default_factory=list)
    flash: float = 0.0


# ------------------------------------------------------------------ texturas
def value_noise(size: int, cells: int, seed: int, octaves: int = 4) -> np.ndarray:
    """Ruído suave e repetível (tileável) em [0, 1]."""
    rng = np.random.default_rng(seed)
    out = np.zeros((size, size), F32)
    amp, total = 1.0, 0.0
    c = cells
    for _ in range(octaves):
        g = rng.random((c, c)).astype(F32)
        g = np.tile(g, (3, 3))
        up = cv2.resize(g, (size * 3, size * 3), interpolation=cv2.INTER_CUBIC)
        out += up[size : 2 * size, size : 2 * size] * amp
        total += amp
        amp *= 0.5
        c *= 2
    out /= total
    lo, hi = float(out.min()), float(out.max())
    return ((out - lo) / max(hi - lo, 1e-6)).astype(F32)


def star_panorama(seed: int, w: int = 2048, h: int = 1024, nebula: float = 0.0) -> np.ndarray:
    rng = np.random.default_rng(seed)
    img = np.zeros((h, w, 3), F32)
    if nebula > 0:
        n1 = cv2.resize(value_noise(256, 4, seed + 1, 5), (w, h))
        n2 = cv2.resize(value_noise(256, 3, seed + 2, 5), (w, h))
        img[..., 0] += (n1**4) * 0.22 * nebula
        img[..., 2] += (n2**3) * 0.3 * nebula
        img[..., 1] += (n1 * n2) ** 2 * 0.12 * nebula
    n = int(w * h / 900)
    xs, ys = rng.integers(0, w, n), rng.integers(0, h, n)
    b = rng.random(n) ** 3
    tint = rng.random((n, 3)) * 0.25 + 0.75
    for x, y, br, tt in zip(xs, ys, b, tint, strict=True):
        col = (tt * (0.35 + 0.65 * br)).tolist()
        r = 1 if br < 0.85 else 2
        cv2.circle(img, (int(x), int(y)), r, col, -1, cv2.LINE_AA)
    return img


# ----------------------------------------------------------------- renderer
class Renderer:
    def __init__(self, scene, width: int = 1080, height: int = 1920, bg_scale: float = 0.5):
        self.scene = scene
        self.W, self.H = width, height
        self.world: World = scene.world
        self.look: Look = scene.look
        self.bw, self.bh = max(16, int(width * bg_scale)), max(16, int(height * bg_scale))
        w = self.world
        self.sun = normalize(np.asarray(w.sun_dir, F32))
        self.fog_col = np.asarray(w.fog_color or w.horizon, F32)
        self.static: Mesh = scene.static
        self.dyn: Mesh = scene.dynamic
        allm = Mesh.merge(self.static, self.dyn) if len(self.dyn.f) else self.static
        self.n_static_v = len(self.static.v)
        self.n_static_f = len(self.static.f)
        self.F = allm.f if len(allm.f) else np.zeros((0, 3), np.int32)
        self.C = self._grade_colors(allm.c) if len(allm.f) else np.zeros((0, 3), F32)
        self.E = allm.e
        self.S = allm.s * self.look.spec
        self.D = allm.d
        px = (np.arange(self.bw, dtype=F32) + 0.5 - self.bw / 2)[None, :]
        py = (np.arange(self.bh, dtype=F32) + 0.5 - self.bh / 2)[:, None]
        self._px, self._py = np.broadcast_to(px, (self.bh, self.bw)), np.broadcast_to(py, (self.bh, self.bw))
        self.stars_tex = star_panorama(w.seed, nebula=w.nebula) if (w.stars > 0 or w.nebula > 0) else None
        self.cloud_tex = value_noise(256, 4, w.seed + 7, 5) if w.clouds > 0 else None
        self.caustic_tex = value_noise(256, 6, w.seed + 9, 2) if w.caustics > 0 else None
        self.ripple_tex = value_noise(256, 8, w.seed + 11, 3) if w.water_mask is not None else None
        # sombras: mapa de mundo centrado na ação
        self.sm_n = 768
        self.sm_center = np.asarray(getattr(scene, "focus", (0, 0, 0)), F32)[[0, 2]]
        self.sm_ext = float(getattr(scene, "shadow_extent", 36.0))
        self.static_shadow = self._shadow_map(self.static.v, self.static.f, self.static.e)
        self.vig = self._vignette()
        self.grain = None
        if self.look.grain > 0:
            rng = np.random.default_rng(3)
            self.grain = [
                cv2.resize(
                    rng.normal(128, 40, (self.H // 2, self.W // 2)).clip(0, 255).astype(np.uint8),
                    (self.W, self.H),
                )
                for _ in range(4)
            ]
        self.lut = self._lut()
        self._ground_avg = (
            w.ground_tex.reshape(-1, 3).mean(axis=0).astype(F32)
            if w.ground_tex is not None
            else np.zeros(3, F32)
        )
        self._frame_no = 0

    # ------------------------------------------------------------ cores
    def _grade_colors(self, c: np.ndarray) -> np.ndarray:
        lk = self.look
        c = np.asarray(c, F32)
        gray = c @ np.array([0.3, 0.59, 0.11], F32)
        c = gray[:, None] + (c - gray[:, None]) * lk.sat
        if lk.pastel:
            c = c * (1 - lk.pastel) + lk.pastel * 0.85
        c = c * np.asarray(lk.tint, F32)
        return np.clip(c, 0, 1.2).astype(F32)

    def _grade_bg(self, img: np.ndarray) -> np.ndarray:
        lk = self.look
        gray = img @ np.array([0.3, 0.59, 0.11], F32)
        img = gray[..., None] + (img - gray[..., None]) * lk.sat
        if lk.pastel:
            img = img * (1 - lk.pastel * 0.6) + lk.pastel * 0.6 * 0.85
        return img * np.asarray(lk.tint, F32)

    def _lut(self) -> np.ndarray:
        lk = self.look
        x = np.arange(256, dtype=F32) / 255
        y = (x - 0.5) * lk.contrast + 0.5 + lk.bright
        # curva suave (filmic leve) nos extremos
        y = np.clip(y, 0, 1)
        y = y * y * (3 - 2 * y) * 0.25 + y * 0.75
        return np.clip(y * 255 + 0.5, 0, 255).astype(np.uint8)

    def _vignette(self) -> np.ndarray | None:
        if self.look.vignette <= 0:
            return None
        h, w = self.H // 4, self.W // 4
        yy, xx = np.mgrid[0:h, 0:w].astype(F32)
        d = np.sqrt(((xx - w / 2) / (w / 2)) ** 2 * 0.8 + ((yy - h / 2) / (h / 2)) ** 2)
        v = 1 - self.look.vignette * np.clip(d - 0.45, 0, 1) ** 1.6
        v = cv2.resize((v * 255).astype(np.uint8), (self.W, self.H), interpolation=cv2.INTER_LINEAR)
        return cv2.merge([v, v, v])

    # ------------------------------------------------------------ sombras
    def _shadow_map(self, v: np.ndarray, f: np.ndarray, e: np.ndarray) -> np.ndarray:
        n = self.sm_n
        sm = np.zeros((n, n), np.uint8)
        if not self.world.ground or not len(f):
            return sm
        L = self.sun.copy()
        L[1] = max(L[1], 0.35)
        L = normalize(L)
        keep = e < 0.5
        f = f[keep]
        if not len(f):
            return sm
        p = v[f]  # (M, 3, 3)
        above = p[..., 1].max(axis=1) > 0.02
        p = p[above]
        if not len(p):
            return sm
        y = np.maximum(p[..., 1], 0)[..., None]
        g = p - L[None, None, :] * (y / L[1])
        sx = (g[..., 0] - self.sm_center[0]) / self.sm_ext * n + n / 2
        sz = (g[..., 2] - self.sm_center[1]) / self.sm_ext * n + n / 2
        pts = np.stack([sx, sz], axis=-1)
        ok = (pts.max(axis=1) > 0).all(axis=1) & (pts.min(axis=1) < n).all(axis=1)
        pts = (pts[ok] * 4).astype(np.int32)
        if len(pts):
            cv2.fillPoly(sm, list(pts), 255, cv2.LINE_8, 2)
        return sm

    def _shadow_sample(self, X: np.ndarray, Z: np.ndarray, dyn: np.ndarray) -> np.ndarray:
        sm = cv2.max(self.static_shadow, dyn)
        k = max(3, int(self.sm_n / self.sm_ext * 0.18) | 1)
        sm = cv2.GaussianBlur(sm, (k, k), 0).astype(F32) / 255
        n = self.sm_n
        mx = ((X - self.sm_center[0]) / self.sm_ext * n + n / 2).astype(F32)
        mz = ((Z - self.sm_center[1]) / self.sm_ext * n + n / 2).astype(F32)
        return cv2.remap(sm, mx, mz, cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT, borderValue=0)

    # ------------------------------------------------------------ fundo
    def _sky(self, dx, dy, dz, t: float) -> np.ndarray:
        """Cor do céu para as direções (dx, dy, dz) já normalizadas (arrays 2D)."""
        w = self.world
        zen, hor = np.asarray(w.zenith, F32), np.asarray(w.horizon, F32)
        k = np.sqrt(np.clip(dy, 0, 1))
        sky = hor + (zen - hor) * k[..., None]
        if not w.ground:
            nad = np.asarray(w.nadir or w.zenith, F32)
            kb = np.sqrt(np.clip(-dy, 0, 1))
            sky = np.where((dy < 0)[..., None], hor + (nad - hor) * kb[..., None], sky)
        if self.stars_tex is not None:
            sh, sw_ = self.stars_tex.shape[:2]
            lon = (np.arctan2(dx, -dz) * (1 / math.tau) + 0.5) * sw_
            lat = (0.5 - np.arcsin(np.clip(dy, -1, 1)) * (1 / math.pi)) * sh
            st = cv2.remap(
                self.stars_tex, lon.astype(F32), lat.astype(F32), cv2.INTER_LINEAR, borderMode=cv2.BORDER_WRAP
            )
            tw = 0.85 + 0.15 * math.sin(t * 3.1)
            if w.ground:
                sky += st * (np.clip(dy * 6, 0, 1) * (w.stars * tw))[..., None]
            else:
                sky += st * (w.stars * tw)
        if self.cloud_tex is not None:
            up = 1 / np.maximum(dy, 0.03)
            n = self.cloud_tex.shape[0]
            cu = (dx * up * 40 + t * 1.2) * (n / 90)
            cv_ = (dz * up * 40 + t * 0.4) * (n / 90)
            c = cv2.remap(
                self.cloud_tex, cu.astype(F32), cv_.astype(F32), cv2.INTER_LINEAR, borderMode=cv2.BORDER_WRAP
            )
            a = np.clip((c - 0.52) * (1 / 0.22), 0, 1) * np.clip((dy - 0.02) * 5, 0, 1) * w.clouds
            shade = 0.82 + 0.18 * np.clip((c - 0.5) * 3, 0, 1)
            ccol = np.asarray(w.cloud_color, F32)
            sky += (ccol * shade[..., None] - sky) * a[..., None]
        if w.sun_disc and self.sun[1] > -0.1:
            sd = np.clip(dx * self.sun[0] + dy * self.sun[1] + dz * self.sun[2], 0, 1)
            s2 = sd * sd
            s4 = s2 * s2
            s8 = s4 * s4
            s16 = s8 * s8
            s32 = s16 * s16
            glow = s32 * s16 * 0.5 + s4 * s2 * 0.12 + np.clip((sd - 0.9993) * (1 / 0.0003), 0, 1) * 1.4
            sky += np.asarray(w.sun_color, F32) * glow[..., None]
        if w.moon:
            m = normalize(np.asarray(w.moon_dir, F32))
            md = np.clip(dx * m[0] + dy * m[1] + dz * m[2], 0, 1)
            m2 = md * md
            m4 = m2 * m2
            m16 = m4 * m4 * m4 * m4
            glow = m16 * m16 * m16 * m16 * m16 * 0.25 + np.clip((md - 0.9988) * (1 / 0.0004), 0, 1) * 1.1
            sky += np.asarray((0.95, 0.95, 1.0), F32) * glow[..., None]
        return sky

    def _ground(self, eye, dx, dy, dz, t, lights, dyn_shadow) -> np.ndarray:
        w = self.world
        tt = np.minimum(eye[1] / np.maximum(-dy, 1e-4), 4000.0)
        X = eye[0] + tt * dx
        Z = eye[2] + tt * dz
        n = w.ground_tex.shape[0]
        e = w.ground_extent
        mx = ((X * (1 / e) + 0.5) * n).astype(F32)
        mz = ((Z * (1 / e) + 0.5) * n).astype(F32)
        tex = cv2.remap(w.ground_tex, mx, mz, cv2.INTER_LINEAR, borderMode=cv2.BORDER_WRAP)
        far = np.clip((tt - 12) * (1 / 45), 0, 1)
        if w.detail_tex is not None:
            dn = w.detail_tex.shape[0]
            k = dn / w.detail_scale
            det = cv2.remap(
                w.detail_tex,
                (X * k).astype(F32),
                (Z * k).astype(F32),
                cv2.INTER_LINEAR,
                borderMode=cv2.BORDER_WRAP,
            )
            tex *= (1 + (det - 0.5) * (2 * w.detail_amount) * (1 - far))[..., None]
        avg = self._ground_avg
        tex += (avg - tex) * (far * 0.7)[..., None]
        sun_y = max(float(self.sun[1]), 0.0)
        amb = np.asarray(w.amb_sky, F32) * 0.92 + np.asarray(w.amb_ground, F32) * 0.08
        direct = np.asarray(w.sun_color, F32) * sun_y
        shadow = None
        if w.shadow > 0:
            shadow = self._shadow_sample(X, Z, dyn_shadow) * w.shadow
            col = tex * (amb + direct * (1 - shadow)[..., None]) * (1 - shadow * 0.25)[..., None]
        else:
            col = tex * (amb + direct)
        if w.water_mask is not None:
            wm = cv2.remap(w.water_mask, mx, mz, cv2.INTER_LINEAR, borderMode=cv2.BORDER_WRAP)
            if wm.max() > 0.01:
                rn = self.ripple_tex.shape[0]
                r1 = cv2.remap(
                    self.ripple_tex,
                    ((X + t * 0.6) * (rn / 4)).astype(F32),
                    ((Z + t * 0.3) * (rn / 4)).astype(F32),
                    cv2.INTER_LINEAR,
                    borderMode=cv2.BORDER_WRAP,
                )
                r2 = cv2.remap(
                    self.ripple_tex,
                    ((X - t * 0.4) * (rn / 2.5)).astype(F32),
                    ((Z + t * 0.5) * (rn / 2.5)).astype(F32),
                    cv2.INTER_LINEAR,
                    borderMode=cv2.BORDER_WRAP,
                )
                wave = (r1 + r2) * 0.5
                fres = np.clip(1 + dy * 2.2, 0, 1) ** 3
                deep, shallow = np.asarray(w.water_deep, F32), np.asarray(w.water_shallow, F32)
                base = deep + (shallow - deep) * wave[..., None]
                refl = np.asarray(w.horizon, F32) * 0.6 + np.asarray(w.zenith, F32) * 0.4
                water = base * (amb + direct * 0.6) + (refl - base) * (fres * 0.85)[..., None]
                rs = np.clip(dx * self.sun[0] - dy * self.sun[1] + dz * self.sun[2], 0, 1)
                r4 = (rs * rs) ** 2
                r16 = (r4 * r4) ** 2
                glint = (r16**8) * 2.5 + (wave > 0.74) * (r4 * r4 * r4) * 0.6
                water += np.asarray(w.sun_color, F32) * (glint * sun_y)[..., None]
                if shadow is not None:
                    water *= (1 - shadow * 0.5)[..., None]
                col += (water - col) * wm[..., None]
        if self.caustic_tex is not None:
            cn = self.caustic_tex.shape[0]
            c1 = cv2.remap(
                self.caustic_tex,
                ((X + t * 0.35) * (cn / 3)).astype(F32),
                (Z * (cn / 3)).astype(F32),
                cv2.INTER_LINEAR,
                borderMode=cv2.BORDER_WRAP,
            )
            c2 = cv2.remap(
                self.caustic_tex,
                (X * (cn / 2.2)).astype(F32),
                ((Z - t * 0.3) * (cn / 2.2)).astype(F32),
                cv2.INTER_LINEAR,
                borderMode=cv2.BORDER_WRAP,
            )
            ca = np.clip(1 - np.abs(c1 - c2) * 7, 0, 1) ** 3 * w.caustics * (1 - far)
            col += ca[..., None] * np.asarray((0.6, 0.9, 1.0), F32)
        for lt in lights:
            if not lt.ground:
                continue
            lp = lt.pos
            ddx, ddz = X - lp[0], Z - lp[2]
            ly = max(float(lp[1]), 0.15)
            d2 = ddx * ddx + ddz * ddz + ly * ly
            k = lt.power * ly / np.sqrt(d2) / (1 + d2 * (1 / (lt.radius * lt.radius)))
            col += tex * (np.asarray(lt.color, F32) * 1.4) * k[..., None]
        fo = 1 - np.exp(-tt * w.fog)
        fo = np.maximum(fo, 1 - np.clip(-dy * 20, 0, 1))
        col += (self.fog_col - col) * fo[..., None]
        return col

    def _background(self, eye, r, u, f, fp_b, t, lights, dyn_shadow) -> np.ndarray:
        w = self.world
        PX, PY = self._px * (1 / fp_b), self._py * (1 / fp_b)
        dx = f[0] + r[0] * PX - u[0] * PY
        dy = f[1] + r[1] * PX - u[1] * PY
        dz = f[2] + r[2] * PX - u[2] * PY
        inv = 1 / np.sqrt(dx * dx + dy * dy + dz * dz)
        dx *= inv
        dy *= inv
        dz *= inv
        if not w.ground or eye[1] <= 0.01:
            return self._sky(dx, dy, dz, t)
        below = dy < -1e-4
        rows_any_ground = below.any(axis=1)
        rows_any_sky = (~below).any(axis=1)
        out = np.empty((self.bh, self.bw, 3), F32)
        if rows_any_sky.any():
            r1 = int(np.nonzero(rows_any_sky)[0].max()) + 1
            r0 = int(np.nonzero(rows_any_sky)[0].min())
            out[r0:r1] = self._sky(dx[r0:r1], dy[r0:r1], dz[r0:r1], t)
        if rows_any_ground.any():
            g0 = int(np.nonzero(rows_any_ground)[0].min())
            g1 = int(np.nonzero(rows_any_ground)[0].max()) + 1
            ground = self._ground(eye, dx[g0:g1], dy[g0:g1], dz[g0:g1], t, lights, dyn_shadow)
            mixed = rows_any_sky[g0:g1]
            if mixed.any():
                ground = np.where(below[g0:g1, :, None], ground, out[g0:g1])
            out[g0:g1] = ground
        return out

    # ------------------------------------------------------------ quadro
    def frame(self, t: float) -> np.ndarray:
        fr: Frame = self.scene.frame(t)
        lk, w = self.look, self.world
        W, H = self.W, self.H
        eye = np.asarray(fr.eye, F32)
        target = np.asarray(fr.target, F32)
        if lk.shake:
            s = lk.shake
            eye = (
                eye
                + np.array(
                    [
                        math.sin(t * 2.3) * 0.6 + math.sin(t * 5.7) * 0.3,
                        math.sin(t * 3.1) * 0.4,
                        math.cos(t * 2.9) * 0.4,
                    ],
                    F32,
                )
                * s
                * 0.12
            )
        f = normalize(target - eye)
        r = normalize(np.cross(f, np.array([0, 1, 0], F32)))
        if not np.isfinite(r).all() or np.linalg.norm(r) < 1e-6:
            r = np.array([1, 0, 0], F32)
        u = np.cross(r, f)
        if fr.roll:
            c, s_ = math.cos(fr.roll), math.sin(fr.roll)
            r, u = r * c + u * s_, u * c - r * s_
        tan = math.tan(math.radians(fr.fov) / 2)
        fp = (H / 2) / tan
        fp_b = (self.bh / 2) / tan

        # ---------------- geometria
        V = (
            self.static.v
            if fr.dyn_v is None
            else np.concatenate([self.static.v, fr.dyn_v])
            if self.n_static_v
            else fr.dyn_v
        )
        dyn_shadow = np.zeros((self.sm_n, self.sm_n), np.uint8)
        if fr.dyn_v is not None and len(self.dyn.f) and w.ground and w.shadow > 0:
            dyn_shadow = self._shadow_map(fr.dyn_v, self.dyn.f, self.dyn.e)
        bg = self._background(eye, r, u, f, fp_b, t, fr.lights, dyn_shadow)
        bg = self._grade_bg(bg)
        bg8 = np.clip(bg * 255, 0, 255).astype(np.uint8)
        img = cv2.resize(bg8, (W, H), interpolation=cv2.INTER_LINEAR)
        img = cv2.cvtColor(img, cv2.COLOR_RGB2BGR)

        draws = []  # (depth, kind, payload)
        under = None
        if w.ground and V is not None and len(V):
            below = V[:, 1] < -0.02
            if below.any():  # o chão esconde o que afunda: achata no chão e descarta o que ficou todo embaixo
                V = V.copy()
                np.maximum(V[:, 1], 0.0, out=V[:, 1])
                under = below[self.F].all(axis=1) if len(self.F) else None
        if len(self.F) and V is not None and len(V):
            tri = V[self.F]  # (M,3,3)
            e0 = tri[:, 1] - tri[:, 0]
            e1 = tri[:, 2] - tri[:, 0]
            n = np.cross(e0, e1)
            area = np.linalg.norm(n, axis=1)
            cen = tri.mean(axis=1)
            view = cen - eye
            valid = area > 1e-9
            if under is not None:
                valid &= ~under
            n = n / np.maximum(area, 1e-12)[:, None]
            facing = (n * view).sum(axis=1)
            vis = valid & ((facing < 0) | self.D)
            rel = tri - eye
            zc = rel @ f
            vis &= zc.min(axis=1) > NEAR
            idx = np.nonzero(vis)[0]
            if len(idx):
                rel = rel[idx]
                zc = zc[idx]
                xc = rel @ r
                yc = rel @ u
                sx = W / 2 + fp * xc / zc
                sy = H / 2 - fp * yc / zc
                on = (sx.max(1) > -2) & (sx.min(1) < W + 2) & (sy.max(1) > -2) & (sy.min(1) < H + 2)
                idx, sx, sy, zc = idx[on], sx[on], sy[on], zc[on]
            if len(idx):
                nn = n[idx]
                flip = facing[idx] > 0
                nn[flip] *= -1
                cols = self._shade(idx, nn, cen[idx], eye, fr)
                # expande 0,6 px para esconder as frestas do antialiasing
                cx, cy = sx.mean(1, keepdims=True), sy.mean(1, keepdims=True)
                dx, dy = sx - cx, sy - cy
                dl = np.sqrt(dx * dx + dy * dy) + 1e-6
                k = 1 + 0.6 / dl
                sx, sy = cx + dx * k, cy + dy * k
                pts = (np.stack([sx, sy], axis=-1).clip(-8000, 9000) * 16).astype(np.int32)
                depth = np.linalg.norm(cen[idx] - eye, axis=1)
                cols8 = (np.clip(cols, 0, 1) * 255)[:, ::-1].astype(np.int32).tolist()
                draws.append((depth, 0, (pts, cols8)))
        for p in fr.particles:
            item = self._particles(p, eye, r, u, f, fp, t)
            if item is not None:
                draws.append(item)

        if draws:
            depth = np.concatenate([d[0] for d in draws])
            owner = np.concatenate([np.full(len(d[0]), i) for i, d in enumerate(draws)])
            local = np.concatenate([np.arange(len(d[0])) for d in draws])
            order = np.argsort(-depth, kind="stable")
            fill = cv2.fillConvexPoly
            circle = cv2.circle
            line = cv2.line
            AA = cv2.LINE_AA
            for k in order:
                o, j = owner[k], local[k]
                kind, payload = draws[o][1], draws[o][2]
                if kind == 0:
                    fill(img, payload[0][j], payload[1][j], AA, 4)
                else:
                    c, rad, col, streak, ring = payload
                    if streak is not None:
                        line(img, c[j], streak[j], col[j], max(1, rad[j] // 16), AA, 4)
                    elif ring:
                        circle(img, c[j], max(16, rad[j]), col[j], 2, AA, 4)
                    else:
                        circle(img, c[j], max(12, rad[j]), col[j], -1, AA, 4)

        # ---------------- pós
        if lk.bloom > 0:
            sw, sh = W // 8, H // 8
            small = cv2.resize(img, (sw, sh), interpolation=cv2.INTER_AREA)
            small = cv2.subtract(small, (lk.bloom_thr,) * 3 + (0,))
            small = cv2.GaussianBlur(small, (0, 0), 4)
            small = cv2.GaussianBlur(small, (0, 0), 9) // 2 + small // 2
            glow = cv2.resize(small, (W, H), interpolation=cv2.INTER_LINEAR)
            img = cv2.addWeighted(img, 1.0, glow, lk.bloom * 3.0, 0)
        img = cv2.LUT(img, self.lut)
        if self.vig is not None:
            img = cv2.multiply(img, self.vig, scale=1 / 255)
        if self.grain is not None:
            g = self.grain[self._frame_no % len(self.grain)]
            img = cv2.addWeighted(img, 1.0, cv2.merge([g, g, g]), lk.grain, -128 * lk.grain)
        if fr.flash > 0:
            img = cv2.addWeighted(img, 1 - fr.flash * 0.3, np.full_like(img, 255), fr.flash * 0.6, 0)
        self._frame_no += 1
        return img

    def _shade(self, idx, n, cen, eye, fr: Frame) -> np.ndarray:
        w, lk = self.world, self.look
        base = self.C[idx]
        emit = self.E[idx].copy()
        if fr.emit_scale is not None:
            dyn = idx >= self.n_static_f
            if dyn.any():
                emit[dyn] = emit[dyn] * fr.emit_scale[idx[dyn] - self.n_static_f]
        spec = self.S[idx]
        L = self.sun
        ndl = np.clip(n @ L, 0, 1)
        if lk.cel:
            ndl = np.floor(ndl * lk.cel + 0.35) / lk.cel
        ny = n[:, 1]
        amb_s, amb_g = np.asarray(w.amb_sky, F32), np.asarray(w.amb_ground, F32)
        hemi = amb_g + (amb_s - amb_g) * (0.5 + 0.5 * ny)[:, None]
        scol = np.asarray(w.sun_color, F32)
        sun_ok = 1.0 if L[1] > -0.05 else 0.0
        lit = hemi + scol * (ndl * sun_ok)[:, None]
        vdir = eye - cen
        vdir = vdir / np.maximum(np.linalg.norm(vdir, axis=1, keepdims=True), 1e-6)
        h = vdir + L
        h = h / np.maximum(np.linalg.norm(h, axis=1, keepdims=True), 1e-6)
        sp = np.clip((n * h).sum(axis=1), 0, 1) ** 28 * spec * (ndl > 0)
        ndv = np.clip((n * vdir).sum(axis=1), 0, 1)
        rim = (1 - ndv) ** 3 * lk.rim
        rim_col = np.asarray(lk.rim_color, F32) if lk.rim_color else amb_s + scol * 0.3
        col = base * lit + scol * sp[:, None] * 0.9 + rim_col * rim[:, None]
        for lt in fr.lights:
            ld = lt.pos - cen
            dist2 = (ld * ld).sum(axis=1)
            dist = np.sqrt(dist2) + 1e-6
            k = np.clip((n * ld).sum(axis=1) / dist, 0, 1) * lt.power / (1 + dist2 / (lt.radius * lt.radius))
            col = col + base * np.asarray(lt.color, F32) * k[:, None] * 1.5
        if emit.any():
            col = col * (1 - emit[:, None]) + base * (emit[:, None] * 1.35)
        dist = np.linalg.norm(cen - eye, axis=1)
        fo = (1 - np.exp(-dist * w.fog)) * (1 - np.clip(emit, 0, 1) * 0.6)
        col = col + (self.fog_col * np.asarray(self.look.tint, F32) - col) * fo[:, None]
        return col

    def _particles(self, p: Particles, eye, r, u, f, fp, t):
        if not len(p.pos):
            return None
        rel = p.pos - eye
        zc = rel @ f
        ok = zc > NEAR * 2
        if not ok.any():
            return None
        W, H = self.W, self.H
        xc, yc = rel @ r, rel @ u
        sx = W / 2 + fp * xc / np.maximum(zc, 1e-3)
        sy = H / 2 - fp * yc / np.maximum(zc, 1e-3)
        rad = fp * p.radius / np.maximum(zc, 1e-3)
        ok &= (sx > -50) & (sx < W + 50) & (sy > -50) & (sy < H + 50) & (rad < 400)
        if not ok.any():
            return None
        if p.alpha is not None:  # sem transparência: partícula "apagando" fica menor, não mais escura
            ok &= p.alpha > 0.12
            rad = rad * (0.35 + 0.65 * np.clip(p.alpha, 0, 1))
            if not ok.any():
                return None
        idx = np.nonzero(ok)[0]
        dist = np.linalg.norm(rel[idx], axis=1)
        col = self._grade_colors(p.color[idx])
        if not p.emissive:
            amb = (
                np.asarray(self.world.amb_sky, F32)
                + np.asarray(self.world.sun_color, F32) * max(float(self.sun[1]), 0) * 0.8
            )
            col = col * np.clip(amb, 0, 1.4)
        fo = 1 - np.exp(-dist * self.world.fog)
        col = col + (self.fog_col - col) * (fo * (0.3 if p.emissive else 1.0))[:, None]
        c = (np.stack([sx[idx], sy[idx]], axis=1) * 16).astype(np.int32)
        rad16 = (rad[idx] * 16).astype(np.int32)
        streak = None
        if p.streak is not None:
            end = p.pos[idx] + p.streak[idx]
            rel2 = end - eye
            z2 = np.maximum(rel2 @ f, NEAR)
            ex = W / 2 + fp * (rel2 @ r) / z2
            ey = H / 2 - fp * (rel2 @ u) / z2
            streak = (np.stack([ex, ey], axis=1).clip(-8000, 9000) * 16).astype(np.int32)
        cols8 = (np.clip(col, 0, 1) * 255)[:, ::-1].astype(np.int32).tolist()
        return (dist, 1, (c, rad16, cols8, streak, p.ring))


# ------------------------------------------------------------------ gravação
def render_to_mp4(
    scene, out: Path, seconds: float, fps: int = 30, width: int = 1080, height: int = 1920
) -> Path:
    """Renderiza a cena quadro a quadro e grava um mp4 H.264 (sem áudio)."""
    rend = Renderer(scene, width, height)
    frames = max(int(round(seconds * fps)), 1)
    err = tempfile.TemporaryFile()
    cmd = [
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
        "-f", "rawvideo", "-pix_fmt", "bgr24", "-s", f"{width}x{height}", "-r", str(fps), "-i", "-",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "19", "-pix_fmt", "yuv420p", "-an", str(out),
    ]  # fmt: skip
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stderr=err)
    try:
        assert proc.stdin is not None
        for i in range(frames):
            img = rend.frame(i / fps)
            proc.stdin.write(np.ascontiguousarray(img).data)
        proc.stdin.close()
        code = proc.wait(timeout=600)
    except BaseException:
        proc.kill()
        raise
    if code != 0:
        err.seek(0)
        raise RuntimeError("ffmpeg falhou ao gravar a cena 3D: " + err.read().decode(errors="replace")[-800:])
    return out
