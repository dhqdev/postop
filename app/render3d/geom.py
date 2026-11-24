"""Geometria do motor 3D: matrizes, malhas e primitivas (numpy puro).

Convenções: metros, eixo Y para cima, personagens olham para +Z. As faces são triângulos
anti-horários vistos de fora (a normal aponta para fora).
"""

from __future__ import annotations

import math

import numpy as np

F32 = np.float32
TAU = math.tau


# ------------------------------------------------------------------ matrizes
def rot_x(a: float) -> np.ndarray:
    c, s = math.cos(a), math.sin(a)
    return np.array([[1, 0, 0], [0, c, -s], [0, s, c]], F32)


def rot_y(a: float) -> np.ndarray:
    c, s = math.cos(a), math.sin(a)
    return np.array([[c, 0, s], [0, 1, 0], [-s, 0, c]], F32)


def rot_z(a: float) -> np.ndarray:
    c, s = math.cos(a), math.sin(a)
    return np.array([[c, -s, 0], [s, c, 0], [0, 0, 1]], F32)


def euler(rx: float, ry: float, rz: float) -> np.ndarray:
    """Rotação yaw (Y) · pitch (X) · roll (Z)."""
    return rot_y(ry) @ rot_x(rx) @ rot_z(rz)


def mat4(pos=(0.0, 0.0, 0.0), rot=(0.0, 0.0, 0.0), scale=1.0) -> np.ndarray:
    m = np.eye(4, dtype=F32)
    s = np.broadcast_to(np.asarray(scale, F32), (3,))
    m[:3, :3] = euler(*rot) * s
    m[:3, 3] = pos
    return m


def normalize(v: np.ndarray) -> np.ndarray:
    n = float(np.linalg.norm(v))
    return v / n if n > 1e-9 else v


def lerp(a, b, t):
    return a + (b - a) * t


def clamp01(x: float) -> float:
    return 0.0 if x < 0 else 1.0 if x > 1 else x


def smooth(t: float) -> float:
    t = clamp01(t)
    return t * t * (3 - 2 * t)


def ease_io(t: float) -> float:
    t = clamp01(t)
    return 4 * t * t * t if t < 0.5 else 1 - (-2 * t + 2) ** 3 / 2


def ease_out(t: float) -> float:
    t = clamp01(t)
    return 1 - (1 - t) ** 3


def ease_in(t: float) -> float:
    t = clamp01(t)
    return t * t * t


def elastic(t: float) -> float:
    """0 → 1 com passada e volta (efeito 'pop')."""
    t = clamp01(t)
    if t in (0.0, 1.0):
        return t
    return 2 ** (-10 * t) * math.sin((t * 10 - 0.75) * TAU / 3) + 1


def back_out(t: float) -> float:
    t = clamp01(t) - 1
    return 1 + 2.4 * t * t * t + 1.4 * t * t


def bounce_out(t: float) -> float:
    t = clamp01(t)
    n, d = 7.5625, 2.75
    if t < 1 / d:
        return n * t * t
    if t < 2 / d:
        t -= 1.5 / d
        return n * t * t + 0.75
    if t < 2.5 / d:
        t -= 2.25 / d
        return n * t * t + 0.9375
    t -= 2.625 / d
    return n * t * t + 0.984375


def hex_rgb(value, default=(0.8, 0.8, 0.8)) -> tuple[float, float, float]:
    if isinstance(value, (tuple, list)) and len(value) == 3:
        return tuple(float(x) for x in value)  # type: ignore[return-value]
    c = str(value or "").strip().lstrip("#")
    if len(c) == 3:
        c = "".join(ch * 2 for ch in c)
    try:
        return (int(c[0:2], 16) / 255, int(c[2:4], 16) / 255, int(c[4:6], 16) / 255)
    except (ValueError, IndexError):
        return default


def mix_rgb(a, b, t: float) -> tuple[float, float, float]:
    return tuple(float(x + (y - x) * t) for x, y in zip(a, b, strict=True))  # type: ignore[return-value]


# ------------------------------------------------------------------ malha
class Mesh:
    """Triângulos com material por face: cor, emissão (0..1), brilho especular e dupla face."""

    __slots__ = ("v", "f", "c", "e", "s", "d")

    def __init__(self, v, f, color=(0.8, 0.8, 0.8), emit=0.0, spec=0.25, double=False):
        self.v = np.asarray(v, F32).reshape(-1, 3)
        self.f = np.asarray(f, np.int32).reshape(-1, 3)
        m = len(self.f)
        col = np.asarray(color, F32)
        self.c = np.tile(col, (m, 1)) if col.ndim == 1 else col.reshape(m, 3).copy()
        self.e = np.full(m, emit, F32)
        self.s = np.full(m, spec, F32)
        self.d = np.full(m, bool(double))

    def copy(self) -> Mesh:
        out = Mesh.__new__(Mesh)
        out.v, out.f, out.c, out.e, out.s, out.d = (
            self.v.copy(),
            self.f.copy(),
            self.c.copy(),
            self.e.copy(),
            self.s.copy(),
            self.d.copy(),
        )
        return out

    def paint(self, color=None, emit=None, spec=None, double=None) -> Mesh:
        out = self.copy()
        if color is not None:
            out.c[:] = np.asarray(color, F32)
        if emit is not None:
            out.e[:] = emit
        if spec is not None:
            out.s[:] = spec
        if double is not None:
            out.d[:] = bool(double)
        return out

    def at(self, pos=(0.0, 0.0, 0.0), rot=(0.0, 0.0, 0.0), scale=1.0) -> Mesh:
        return self.apply(mat4(pos, rot, scale))

    def apply(self, m: np.ndarray) -> Mesh:
        out = self.copy()
        out.v = (self.v @ m[:3, :3].T + m[:3, 3]).astype(F32)
        if np.linalg.det(m[:3, :3]) < 0:  # espelhamento: inverte a ordem para manter a normal
            out.f = out.f[:, ::-1].copy()
        return out

    def jitter(self, amount: float, seed: int = 0) -> Mesh:
        """Deforma os vértices (pedras, montanhas) mantendo as faces."""
        rng = np.random.default_rng(seed)
        out = self.copy()
        out.v = out.v + rng.uniform(-amount, amount, out.v.shape).astype(F32)
        return out

    def vary(self, amount: float, seed: int = 0) -> Mesh:
        """Pequena variação de cor por face (textura 'low poly')."""
        rng = np.random.default_rng(seed)
        out = self.copy()
        out.c = np.clip(out.c * rng.uniform(1 - amount, 1 + amount, (len(out.c), 1)), 0, 1).astype(F32)
        return out

    @staticmethod
    def merge(*meshes: Mesh) -> Mesh:
        meshes = tuple(m for m in meshes if m is not None and len(m.f))
        if not meshes:
            return Mesh(np.zeros((0, 3)), np.zeros((0, 3)))
        out = Mesh.__new__(Mesh)
        offs = np.cumsum([0] + [len(m.v) for m in meshes[:-1]])
        out.v = np.concatenate([m.v for m in meshes]).astype(F32)
        out.f = np.concatenate([m.f + o for m, o in zip(meshes, offs, strict=True)]).astype(np.int32)
        out.c = np.concatenate([m.c for m in meshes]).astype(F32)
        out.e = np.concatenate([m.e for m in meshes]).astype(F32)
        out.s = np.concatenate([m.s for m in meshes]).astype(F32)
        out.d = np.concatenate([m.d for m in meshes])
        return out

    def bounds(self) -> tuple[np.ndarray, np.ndarray]:
        if not len(self.v):
            z = np.zeros(3, F32)
            return z, z
        return self.v.min(axis=0), self.v.max(axis=0)


def _outward(v: np.ndarray, f: np.ndarray, center) -> np.ndarray:
    """Garante normais para fora em sólidos convexos (em relação ao centro)."""
    a, b, c = v[f[:, 0]], v[f[:, 1]], v[f[:, 2]]
    n = np.cross(b - a, c - a)
    out = (a + b + c) / 3 - np.asarray(center, F32)
    flip = (n * out).sum(axis=1) < 0
    f = f.copy()
    f[flip] = f[flip][:, ::-1]
    return f


# --------------------------------------------------------------- primitivas
def box(sx=1.0, sy=1.0, sz=1.0, color=(0.8, 0.8, 0.8), seg: int = 1, base=False, **mat) -> Mesh:
    """Caixa centrada (ou com a base em y=0). `seg` subdivide as faces (ajuda a ordenação)."""
    n = max(1, int(seg))
    verts, faces = [], []
    hx, hy, hz = sx / 2, sy / 2, sz / 2
    for axis in range(3):
        for sign in (-1, 1):
            u_ax, v_ax = [a for a in range(3) if a != axis]
            base_idx = len(verts)
            for i in range(n + 1):
                for j in range(n + 1):
                    p = [0.0, 0.0, 0.0]
                    p[axis] = sign * (hx, hy, hz)[axis]
                    p[u_ax] = (-1 + 2 * i / n) * (hx, hy, hz)[u_ax]
                    p[v_ax] = (-1 + 2 * j / n) * (hx, hy, hz)[v_ax]
                    verts.append(p)
            for i in range(n):
                for j in range(n):
                    a = base_idx + i * (n + 1) + j
                    faces += [(a, a + n + 1, a + 1), (a + 1, a + n + 1, a + n + 2)]
    v = np.asarray(verts, F32)
    f = _outward(v, np.asarray(faces, np.int32), (0, 0, 0))
    if base:
        v[:, 1] += hy
    return Mesh(v, f, color, **mat)


def chamfer_box(
    sx=1.0, sy=1.0, sz=1.0, bevel=0.08, color=(0.8, 0.8, 0.8), base=False, seg: int = 1, **mat
) -> Mesh:
    """Caixa com quinas chanfradas (blocos de brinquedo, prédios, móveis). `seg` é aceito e ignorado."""
    b = min(bevel, sx / 2.2, sy / 2.2, sz / 2.2)
    h = np.array([sx / 2, sy / 2, sz / 2], F32)
    verts: list[list[float]] = []
    index: dict[tuple[int, int, int, int], int] = {}
    for cx in (-1, 1):
        for cy in (-1, 1):
            for cz in (-1, 1):
                s = np.array([cx, cy, cz], F32)
                for ax in range(3):  # vértice da quina na face do eixo `ax`
                    p = s * (h - b)
                    p[ax] = s[ax] * h[ax]
                    index[(cx, cy, cz, ax)] = len(verts)
                    verts.append(p.tolist())
    faces: list[tuple[int, int, int]] = []
    # faces principais
    for ax in range(3):
        u, w = [a for a in range(3) if a != ax]
        for sign in (-1, 1):
            quad = []
            for su, sw in ((-1, -1), (1, -1), (1, 1), (-1, 1)):
                c = [0, 0, 0]
                c[ax], c[u], c[w] = sign, su, sw
                quad.append(index[(c[0], c[1], c[2], ax)])
            faces += [(quad[0], quad[1], quad[2]), (quad[0], quad[2], quad[3])]
    # chanfros das arestas
    for ax in range(3):  # aresta paralela ao eixo `ax`
        u, w = [a for a in range(3) if a != ax]
        for su in (-1, 1):
            for sw in (-1, 1):
                q = []
                for sa in (-1, 1):
                    c = [0, 0, 0]
                    c[ax], c[u], c[w] = sa, su, sw
                    q.append((index[(c[0], c[1], c[2], u)], index[(c[0], c[1], c[2], w)]))
                faces += [(q[0][0], q[0][1], q[1][1]), (q[0][0], q[1][1], q[1][0])]
    # cantos
    for cx in (-1, 1):
        for cy in (-1, 1):
            for cz in (-1, 1):
                faces.append(tuple(index[(cx, cy, cz, ax)] for ax in range(3)))  # type: ignore[arg-type]
    v = np.asarray(verts, F32)
    f = _outward(v, np.asarray(faces, np.int32), (0, 0, 0))
    if base:
        v[:, 1] += h[1]
    return Mesh(v, f, color, **mat)


def ellipsoid(
    rx=0.5, ry=None, rz=None, color=(0.8, 0.8, 0.8), nu=14, nv=9, v0=0.0, v1=1.0, cap=True, **mat
) -> Mesh:
    """Esfera/elipsoide UV. v0/v1 (0=topo, 1=base) recortam calotas (cabelo, cúpulas)."""
    ry = rx if ry is None else ry
    rz = rx if rz is None else rz
    phis = np.linspace(v0 * math.pi, v1 * math.pi, nv + 1)
    th = np.linspace(0, TAU, nu, endpoint=False)
    sp, cp = np.sin(phis)[:, None], np.cos(phis)[:, None]
    v = np.stack(
        [
            (rx * sp * np.cos(th)).ravel(),
            np.broadcast_to(ry * cp, (nv + 1, nu)).ravel(),
            (rz * sp * np.sin(th)).ravel(),
        ],
        axis=1,
    )
    faces = []
    for i in range(nv):
        for j in range(nu):
            a, b = i * nu + j, i * nu + (j + 1) % nu
            c, d = a + nu, b + nu
            faces += [(a, c, b), (b, c, d)]
    if cap and v1 < 0.999:  # fecha a base da calota
        ci = len(v)
        v = np.vstack([v, [[0, ry * math.cos(v1 * math.pi), 0]]])
        last = nv * nu
        faces += [(last + j, ci, last + (j + 1) % nu) for j in range(nu)]
    v = np.asarray(v, F32)
    f = np.asarray(faces, np.int32)
    a, b, c = v[f[:, 0]], v[f[:, 1]], v[f[:, 2]]
    area = np.linalg.norm(np.cross(b - a, c - a), axis=1)
    f = f[area > 1e-10]
    f = _outward(v, f, (0, ry * math.cos((v0 + v1) / 2 * math.pi) * 0.5 if v1 < 0.999 else 0, 0))
    return Mesh(v, f, color, **mat)


def sphere(r=0.5, color=(0.8, 0.8, 0.8), nu=14, nv=9, **mat) -> Mesh:
    return ellipsoid(r, r, r, color, nu, nv, **mat)


def lathe(profile, color=(0.8, 0.8, 0.8), seg=14, squash=1.0, **mat) -> Mesh:
    """Sólido de revolução: profile = [(raio, y), ...] de baixo para cima."""
    prof = [(max(float(r), 0.0), float(y)) for r, y in profile]
    th = np.linspace(0, TAU, seg, endpoint=False)
    rings = []
    for r, y in prof:
        rings.append(np.stack([r * np.cos(th), np.full(seg, y), r * np.sin(th) * squash], axis=1))
    v = np.concatenate(rings).astype(F32)
    faces = []
    for i in range(len(prof) - 1):
        for j in range(seg):
            a, b = i * seg + j, i * seg + (j + 1) % seg
            c, d = a + seg, b + seg
            faces += [(a, b, c), (b, d, c)]
    # tampas
    extra = []
    if prof[0][0] > 1e-6:
        ci = len(v) + len(extra)
        extra.append([0, prof[0][1], 0])
        faces += [(j, ci, (j + 1) % seg) for j in range(seg)][::-1]
    if prof[-1][0] > 1e-6:
        ci = len(v) + len(extra)
        extra.append([0, prof[-1][1], 0])
        o = (len(prof) - 1) * seg
        faces += [(o + (j + 1) % seg, ci, o + j) for j in range(seg)]
    if extra:
        v = np.vstack([v, np.asarray(extra, F32)])
    f = np.asarray(faces, np.int32)
    a, b, c = v[f[:, 0]], v[f[:, 1]], v[f[:, 2]]
    n = np.cross(b - a, c - a)
    area = np.linalg.norm(n, axis=1)
    keep = area > 1e-10
    f, n = f[keep], n[keep]
    # normal para fora: compara com a direção radial (ou vertical nas tampas)
    cen = (a + b + c)[keep] / 3
    radial = cen.copy()
    radial[:, 1] = 0
    rlen = np.linalg.norm(radial, axis=1)
    mid = (prof[0][1] + prof[-1][1]) / 2
    ref = np.where(rlen[:, None] > 1e-4, radial, np.stack([0 * rlen, cen[:, 1] - mid, 0 * rlen], axis=1))
    flip = (n * ref).sum(axis=1) < 0
    f[flip] = f[flip][:, ::-1]
    return Mesh(v, f, color, **mat)


def cylinder(r=0.5, h=1.0, color=(0.8, 0.8, 0.8), seg=12, r_top=None, center=False, **mat) -> Mesh:
    rt = r if r_top is None else r_top
    y0 = -h / 2 if center else 0.0
    return lathe([(r, y0), (rt, y0 + h)], color, seg, **mat)


def cone(r=0.5, h=1.0, color=(0.8, 0.8, 0.8), seg=12, **mat) -> Mesh:
    return lathe([(r, 0.0), (0.0, h)], color, seg, **mat)


def capsule(r=0.1, length=0.5, color=(0.8, 0.8, 0.8), seg=10, down=True, r2=None, **mat) -> Mesh:
    """Membro: cápsula de comprimento `length` saindo do pivô para baixo (-Y)."""
    r2 = r if r2 is None else r2
    prof = []
    for k in range(4):  # meia esfera de cima
        a = math.pi / 2 * (1 - k / 3)
        prof.append((r * math.cos(a), r * math.sin(a)))
    for k in range(4):  # meia esfera de baixo
        a = math.pi / 2 * (k / 3)
        prof.append((r2 * math.cos(a), -length - r2 * math.sin(a)))
    prof = sorted(prof, key=lambda p: p[1])
    m = lathe(prof, color, seg, **mat)
    if not down:
        m = m.at(rot=(math.pi, 0, 0))
    return m


def torus(big=0.5, small=0.15, color=(0.8, 0.8, 0.8), nu=18, nv=8, arc=1.0, **mat) -> Mesh:
    """Toro deitado no plano XZ. `arc` < 1 faz um arco (arco-íris, ferradura)."""
    us = np.linspace(0, TAU * arc, nu + (1 if arc < 1 else 0), endpoint=arc < 1)
    vs = np.linspace(0, TAU, nv, endpoint=False)
    nu_eff = len(us)
    v = []
    for u in us:
        for w in vs:
            rr = big + small * math.cos(w)
            v.append((rr * math.cos(u), small * math.sin(w), rr * math.sin(u)))
    faces = []
    for i in range(nu_eff if arc >= 1 else nu_eff - 1):
        for j in range(nv):
            i2 = (i + 1) % nu_eff
            a, b = i * nv + j, i * nv + (j + 1) % nv
            c, d = i2 * nv + j, i2 * nv + (j + 1) % nv
            faces += [(a, b, c), (b, d, c)]
    v = np.asarray(v, F32)
    f = np.asarray(faces, np.int32)
    a, b, c = v[f[:, 0]], v[f[:, 1]], v[f[:, 2]]
    n = np.cross(b - a, c - a)
    cen = (a + b + c) / 3
    ring = cen.copy()
    ring[:, 1] = 0
    ring = ring / np.maximum(np.linalg.norm(ring, axis=1, keepdims=True), 1e-6) * big
    flip = (n * (cen - ring)).sum(axis=1) < 0
    f[flip] = f[flip][:, ::-1]
    return Mesh(v, f, color, **mat)


def _triangulate(poly: np.ndarray) -> list[tuple[int, int, int]]:
    """Ear clipping para polígono simples anti-horário."""
    idx = list(range(len(poly)))
    out = []

    def area2(a, b, c):
        return (b[0] - a[0]) * (c[1] - a[1]) - (c[0] - a[0]) * (b[1] - a[1])

    def inside(p, a, b, c):
        return area2(a, b, p) >= 0 and area2(b, c, p) >= 0 and area2(c, a, p) >= 0

    guard = 0
    while len(idx) > 3 and guard < 10000:
        guard += 1
        n = len(idx)
        for k in range(n):
            i0, i1, i2 = idx[(k - 1) % n], idx[k], idx[(k + 1) % n]
            a, b, c = poly[i0], poly[i1], poly[i2]
            if area2(a, b, c) <= 1e-12:
                continue
            if any(inside(poly[j], a, b, c) for j in idx if j not in (i0, i1, i2)):
                continue
            out.append((i0, i1, i2))
            idx.pop(k)
            break
        else:
            break
    if len(idx) == 3:
        out.append((idx[0], idx[1], idx[2]))
    return out


def extrude(points, depth=0.2, color=(0.8, 0.8, 0.8), **mat) -> Mesh:
    """Extruda um contorno 2D (x, y) ao longo de Z (estrela, coração, raio, engrenagem)."""
    p = np.asarray(points, F32)
    if (np.roll(p[:, 0], -1) - p[:, 0]) @ (np.roll(p[:, 1], -1) + p[:, 1]) > 0:
        p = p[::-1]  # garante anti-horário
    n = len(p)
    tris = _triangulate(p)
    hz = depth / 2
    v = np.concatenate([np.c_[p, np.full(n, hz)], np.c_[p, np.full(n, -hz)]]).astype(F32)
    faces = [(a, b, c) for a, b, c in tris] + [(c + n, b + n, a + n) for a, b, c in tris]
    for i in range(n):
        j = (i + 1) % n
        faces += [(i, i + n, j), (j, i + n, j + n)]
    return Mesh(v, faces, color, **mat)


def plane(w=1.0, d=1.0, color=(0.8, 0.8, 0.8), nx=1, nz=1, double=True, **mat) -> Mesh:
    """Plano XZ (normal +Y), útil para tecidos, bandeiras e folhas."""
    xs = np.linspace(-w / 2, w / 2, nx + 1)
    zs = np.linspace(-d / 2, d / 2, nz + 1)
    v = np.array([(x, 0.0, z) for z in zs for x in xs], F32)
    faces = []
    for j in range(nz):
        for i in range(nx):
            a = j * (nx + 1) + i
            faces += [(a, a + nx + 1, a + 1), (a + 1, a + nx + 1, a + nx + 2)]
    return Mesh(v, faces, color, double=double, **mat)


def star_points(n=5, r_out=0.5, r_in=0.22) -> list[tuple[float, float]]:
    pts = []
    for i in range(n * 2):
        a = math.pi / 2 + i * math.pi / n
        r = r_out if i % 2 == 0 else r_in
        pts.append((r * math.cos(a), r * math.sin(a)))
    return pts


def heart_points(size=0.5, n=28) -> list[tuple[float, float]]:
    pts = []
    for i in range(n):
        t = TAU * i / n
        x = 16 * math.sin(t) ** 3
        y = 13 * math.cos(t) - 5 * math.cos(2 * t) - 2 * math.cos(3 * t) - math.cos(4 * t)
        pts.append((x / 32 * size * 2, y / 32 * size * 2))
    # remove pontos quase repetidos do bico
    out = [pts[0]]
    for p in pts[1:]:
        if math.dist(p, out[-1]) > 1e-3:
            out.append(p)
    return out


def gear_points(teeth=10, r_out=0.5, r_in=0.4) -> list[tuple[float, float]]:
    pts = []
    for i in range(teeth):
        a0 = TAU * i / teeth
        step = TAU / teeth
        for k, r in ((0.0, r_in), (0.2, r_out), (0.5, r_out), (0.7, r_in)):
            a = a0 + step * k
            pts.append((r * math.cos(a), r * math.sin(a)))
    return pts


def bolt_points(s=0.5) -> list[tuple[float, float]]:
    return [
        (0.1 * s, s),
        (-0.45 * s, -0.05 * s),
        (-0.05 * s, -0.05 * s),
        (-0.2 * s, -s),
        (0.45 * s, 0.1 * s),
        (0.05 * s, 0.1 * s),
    ]
