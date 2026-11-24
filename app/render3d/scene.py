"""Monta a cena 3D (atores, cenário, câmera, efeitos) a partir da especificação normalizada."""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np

from . import models as M
from .actions import MOVING, Pose, resolve
from .geom import F32, Mesh, ease_io, lerp, mat4, normalize, smooth
from .renderer import Frame, Particles, PointLight
from .world import LOOKS, decor_mesh, make_world, structure, weather

PI = math.pi
TAU = math.tau
DIAG = 0.55  # direção da fila em diagonal (radianos a partir de -Z)


@dataclass
class ActorSpec:
    type: str = "block"
    count: int = 1
    actions: list[str] = field(default_factory=lambda: ["idle"])
    formation: str = ""
    position: str = ""
    color: tuple | None = None
    size: float = 1.0
    facing: str = ""


@dataclass
class SceneSpec:
    setting: str = "studio"
    time: str = "day"
    weather: str = "none"
    camera: str = ""
    actors: list[ActorSpec] = field(default_factory=list)


# ------------------------------------------------------------------ ator
class Actor:
    def __init__(self, model: M.Model, kind: str, cat: str, scale: float, base, yaw: float, segs, rng):
        self.model = model
        self.kind = kind
        self.cat = cat
        self.scale = float(scale)
        self.base = np.asarray(base, F32)
        self.yaw0 = float(yaw)
        self.segs = segs
        self.fns = [resolve(name, cat) for name, _a, _b in segs]
        self.gi, self.gn = 0, 1
        self.slot = np.zeros(3, F32)
        self.scatter = np.zeros(3, F32)
        self.phase = float(rng.uniform(0, TAU))
        self.stride = self.scale
        self.face_cam = 0.0
        self.subject = True
        self.flicker_faces: np.ndarray | None = None
        mesh = model.mesh
        self.has_emit = bool((mesh.e > 0).any())
        names = model.names
        self.wheels = [n for n in names if n.startswith("wheel")]
        self.cloth = [n for n in names if n.startswith("cloth")]
        self.sway = [n for n in names if n.startswith("sw")]
        self.orbits = [n for n in names if n.startswith("orbit")]

    # -------------------------------------------------------------- pose
    def pose(self, t: float) -> Pose:
        P = Pose()
        P.yaw = self.yaw0
        prev = None
        for k, ((_name, t0, t1), fn) in enumerate(zip(self.segs, self.fns, strict=True)):
            dur = max(t1 - t0, 1e-3)
            if t >= t1 and k < len(self.segs) - 1:
                Q = P.fresh()
                fn(self, Q, 1.0, dur, dur, t1)
                P = Q.fresh()
                prev = Q
                continue
            lt = min(max(t - t0, 0.0), dur)
            cur = P.fresh()
            fn(self, cur, lt / dur, lt, dur, t)
            if prev is not None:
                cur.blend_from(prev, smooth(lt / min(0.35, dur * 0.5)))
            P = cur
            break
        self._auto(P, t)
        return P

    def _auto(self, P: Pose, t: float) -> None:
        m = self.model
        tags = m.tags
        if self.cat in ("person", "ghost") and m.has("eye_l"):
            q = (t + self.phase) % 3.7
            if q < 0.13:
                k = 0.12
                for e in ("eye_l", "eye_r"):
                    s = P.nscale.get(e, 1.0)
                    P.nscale[e] = np.array((1, k, 1), F32) * s
        mo = P.nscale.get("mouth")
        if mo is not None and np.isscalar(mo):
            P.nscale["mouth"] = np.array((1 + (mo - 1) * 0.35, mo, 1), F32)
        for name in m.flicker:
            P.nscale[name] = np.array(
                (1, 1 + 0.18 * math.sin(t * 17 + self.phase) + 0.08 * math.sin(t * 31), 1), F32
            )
        if "spinner" in tags:
            P.j("spin", 0, 0, t * (1.5 if m.kind == "building" else 25.0))
        if "spinner_body" in tags:
            P.j("body", 0, t * 0.35, 0)
        if "planet" in tags and "spinner_body" not in tags:
            P.j("body", 0, t * 0.2, 0)
        for i, w in enumerate(self.wheels):
            P.j(w, P.travel / 0.38 * (1 if i < 99 else 0))
        for i, c in enumerate(self.cloth):
            P.j(c, 0, 0.32 * math.sin(t * 5 - i * 0.9) * (0.6 + 0.4 * i))
        for i, s in enumerate(self.sway):
            P.j(s, 0.06 * math.sin(t * 1.1 + i), 0, 0.2 * math.sin(t * 1.3 + i * 0.6 + self.phase))
        for i, o in enumerate(self.orbits):
            P.j(o, 0, t * (2.5 + i * 0.8), 0)
        if "clock" in tags:
            P.j("hand_m", 0, 0, -t * 1.6)
            P.j("hand_h", 0, 0, -t * 0.14)
        if "glow" in tags:
            P.emit *= 0.75 + 0.35 * math.sin(t * 3 + self.phase)
        if "rocket" in tags and not P.fire:
            P.nscale["flame"] = 1e-4
            P.light = 0.0

    def matrix(self, P: Pose) -> np.ndarray:
        s = self.scale
        sq = P.squash
        sc = P.scale * np.array((s * (1 + sq * 0.6), s * (1 - sq), s * (1 + sq * 0.6)), F32)
        if P.hidden or float(sc.min()) < 0.01 * max(s, 0.1):
            sc = np.full(3, 1e-5, F32)
        pos = self.base + P.pos + np.array((0, P.lift, 0), F32)
        if P.pitch or P.roll:
            pv = P.pivot * s
            m = (
                mat4(pos, (0, P.yaw, 0))
                @ mat4(pv)
                @ mat4((0, 0, 0), (P.pitch, 0, P.roll))
                @ mat4(-pv)
                @ mat4(scale=sc)
            )
        else:
            m = mat4(pos, (0, P.yaw, 0), sc)
        return m

    def root_pos(self, t: float) -> np.ndarray:
        P = self.pose(t)
        return self.base + P.pos + np.array((0, P.lift, 0), F32)


# ------------------------------------------------------------------ layout
def formation_slots(form: str, n: int, r: float, h: float, rng) -> list[np.ndarray]:
    gap = max(0.12, r * 0.35)
    w = 2 * r + gap
    out = []
    if n == 1:
        return [np.zeros(3, F32)]
    if form == "stack":
        return [np.array((rng.uniform(-0.04, 0.04) * w, i * h * 0.995, 0), F32) for i in range(n)]
    if form == "pyramid":
        m = 1
        while m * (m + 1) // 2 < n:
            m += 1
        k = 0
        for row in range(m):
            cnt = m - row
            for j in range(cnt):
                if k >= n:
                    break
                out.append(np.array(((j - (cnt - 1) / 2) * (2 * r * 1.02), row * h * 0.995, 0), F32))
                k += 1
        return out
    if form == "wall":
        cols = max(2, math.ceil(math.sqrt(n * 1.6)))
        for i in range(n):
            row, col = divmod(i, cols)
            off = (r if row % 2 else 0) * 0.5
            out.append(np.array(((col - (cols - 1) / 2) * 2 * r * 1.02 + off, row * h * 0.995, 0), F32))
        return out
    if form in ("line", "column"):
        return [np.array((0, 0, -i * w), F32) for i in range(n)]
    if form == "diagonal":  # fila entrando na cena em diagonal (dominós)
        step = max(h * 0.55, r * 0.6)
        return [np.array((math.sin(DIAG) * i * step, 0, -math.cos(DIAG) * i * step), F32) for i in range(n)]
    if form in ("circle", "around", "ring"):
        R = max(1.2, n * w / TAU)
        return [np.array((math.cos(i / n * TAU) * R, 0, math.sin(i / n * TAU) * R), F32) for i in range(n)]
    if form == "arc":
        R = max(1.5, n * w / PI)
        return [
            np.array(
                (
                    math.sin((i / max(n - 1, 1) - 0.5) * 2.2) * R,
                    0,
                    -math.cos((i / max(n - 1, 1) - 0.5) * 2.2) * R + R * 0.6,
                ),
                F32,
            )
            for i in range(n)
        ]
    if form == "v":
        return [
            np.array(((i + 1) // 2 * w * (1 if i % 2 else -1), 0, -((i + 1) // 2) * w * 0.8), F32)
            for i in range(n)
        ]
    if form == "grid" or form == "crowd":
        cols = max(1, math.ceil(math.sqrt(n * (1.0 if form == "grid" else 0.8))))
        for i in range(n):
            row, col = divmod(i, cols)
            j = rng.uniform(-0.25, 0.25, 2) * w if form == "crowd" else np.zeros(2)
            out.append(np.array(((col - (cols - 1) / 2) * w + j[0], 0, -row * w * 1.1 + j[1]), F32))
        return out
    if form in ("scatter", "random"):
        R = max(1.0, math.sqrt(n) * w * 0.9)
        for _ in range(n):
            for _try in range(30):
                p = np.array((rng.uniform(-R, R), 0, rng.uniform(-R, R * 0.5)), F32)
                if all(np.linalg.norm(p - q) > w * 0.9 for q in out):
                    break
            out.append(p)
        return out
    # row (padrão)
    return [np.array(((i - (n - 1) / 2) * w, 0, 0), F32) for i in range(n)]


def default_formation(kind: str, cat: str, n: int, actions: list[str]) -> str:
    if n <= 1:
        return ""
    a = set(actions)
    if "stack" in a:
        return "stack"
    if "domino" in a:
        return "diagonal"
    if "build" in a or ("explode" in a and kind in ("block", "brick", "dice")):
        return "pyramid" if n <= 15 else "wall"
    if "rain" in a or "scatter" in a:
        return "scatter"
    if "carousel" in a:
        return "circle"
    if cat == "bird":
        return "v" if "fly" in a else "scatter"
    if cat in ("fish", "insect", "creature"):
        return "scatter"
    if cat in ("person", "animal", "ghost"):
        return "row" if n <= 3 else "crowd"
    if kind in (
        "tree",
        "pine",
        "palm",
        "rock",
        "flower",
        "mushroom",
        "bush",
        "cloud",
        "coin",
        "star",
        "asteroid",
    ):
        return "scatter"
    return "row" if n <= 5 else "grid"


# ------------------------------------------------------------------ cena
class Scene:
    """Cena pronta para o renderizador: mundo, malhas estáticas, atores e câmera."""

    def __init__(
        self, spec: SceneSpec, seconds: float, look: str = "pixar3d", seed: int = 0, scene_index: int = 0
    ):
        self.spec = spec
        self.T = max(float(seconds), 0.5)
        self.rng = np.random.default_rng(seed)
        self.look = LOOKS.get(look, LOOKS["pixar3d"])
        self.world, self.setting, self.time = make_world(spec.setting, spec.time, look, seed)
        self.night = self.time == "night" or self.setting.indoor or spec.setting in ("cave", "stage")
        self.scene_index = scene_index
        self.actors: list[Actor] = []
        self._build_actors(spec)
        self._center_paths()
        self._frame_camera(spec.camera)
        self.focus = self.cam_focus.copy()
        self.shadow_extent = float(np.clip(self.cam_dist * 3.2, 24, 70))
        self._build_static(spec)
        self.dynamic = (
            Mesh.merge(*[a.model.mesh for a in self.actors])
            if self.actors
            else Mesh(np.zeros((0, 3)), np.zeros((0, 3)))
        )
        self._dyn_slices()
        wk = spec.weather if spec.weather not in ("", "none") else self.setting.weather
        if look == "fantasia" and wk in ("", "none") and not self.setting.indoor:
            wk = "sparkles"
        self.flash_times: list[float] = []
        if wk == "storm":
            wk = "rain"
            self.flash_times = [self.T * 0.3, self.T * 0.75]
            self.world.zenith = tuple(c * 0.5 for c in self.world.zenith)
        if wk == "fog":
            self.world.fog = max(self.world.fog, 0.045)
            wk = "dust" if not self.night else "none"
        self.weather = weather(wk, seed, self.cam_focus, self.cam_dist) if wk else None
        self._effects_setup()
        dark = self.time == "night" or spec.setting in ("cave", "stage", "graveyard")
        self.fill = 0.85 if dark else 0.5 if self.time in ("sunset", "dawn") else 0.0
        warm = self.time in ("sunset", "dawn")
        self.fill_color = (
            (1.0, 0.45, 0.85) if look == "neon" else (1.0, 0.8, 0.65) if warm else (0.62, 0.7, 0.95)
        )

    # -------------------------------------------------------------- atores
    def _build_actors(self, spec: SceneSpec) -> None:
        groups = []
        for gi, a in enumerate(spec.actors[:6]):
            kind = a.type if a.type in M.REGISTRY else "block"
            entry = M.REGISTRY[kind]
            n = int(np.clip(a.count, 1, entry.max_count))
            proto, base_scale = M.build(kind, a.color, self.rng)
            cat = proto.kind if proto.kind in ("ghost", "snake", "statue") else entry.cat
            if cat == "statue":
                cat = "prop"
            size = float(np.clip(a.size or 1.0, 0.15, 8.0))
            scale = base_scale * size
            form = a.formation or default_formation(kind, cat, n, a.actions)
            slots = formation_slots(form, n, proto.radius * scale, proto.height * scale, self.rng)
            ext = (
                np.array([np.abs(s[[0, 2]]).max() for s in slots]).max() + proto.radius * scale
                if n > 1
                else proto.radius * scale
            )
            groups.append(
                dict(
                    spec=a,
                    kind=kind,
                    cat=cat,
                    n=n,
                    proto=proto,
                    scale=scale,
                    slots=slots,
                    form=form,
                    ext=float(ext),
                    gi=gi,
                )
            )
        if not groups:
            return
        # posições dos grupos (em vídeo vertical, os coadjuvantes ficam um pouco atrás, não só ao lado)
        main = groups[0]
        R0 = main["ext"]
        H0 = main["proto"].height * main["scale"]
        celestial = {"sun", "moon", "planet", "earth", "saturn", "jupiter", "mars", "neptune", "venus", "galaxy",
                     "black_hole", "comet", "cloud", "rainbow", "ufo", "airplane", "satellite"}  # fmt: skip
        big = {"house", "building", "castle", "temple", "tower", "barn", "lighthouse", "windmill", "mountain",
               "volcano", "pyramid"}  # fmt: skip
        used = {g["spec"].position for g in groups if g["spec"].position}
        auto = [p for p in ("back_right", "back_left", "right", "left", "front", "back") if p not in used]
        auto = auto or ["back_right"]
        if main["spec"].position not in ("", "center") and "center" not in used:
            auto.insert(0, "center")  # protagonista de lado: o próximo grupo ocupa o centro
        k_auto = 0
        for g in groups:
            pos = g["spec"].position
            kind = g["kind"]
            if not pos:
                if g is main:
                    pos = "center"
                elif kind in celestial and self.spec.setting != "space":
                    pos = "sky"
                elif g["cat"] == "prop" and g["proto"].hover > 0.2 and g["n"] == 1:
                    pos = "above"  # símbolo flutuando sobre o protagonista (ideia, coração, estrela...)
                elif g["proto"].height * g["scale"] > 3.2 or kind in big:
                    pos = "back"
                else:
                    pos = auto[k_auto % len(auto)]
                    k_auto += 1
            g["pos"] = pos
            e = g["ext"]
            gapx = R0 + e + 0.35
            flier = g["cat"] in ("bird", "insect") or "flies" in g["proto"].tags
            anchor = {
                "center": (0, 0, 0),
                "left": (-gapx, 0, 0),
                "right": (gapx, 0, 0),
                "front": (0, 0, R0 * 0.5 + e + 0.6),
                "back": (0, 0, -(R0 + e + 1.2)),
                "back_left": (-gapx * 0.75, 0, -(R0 + e) * 0.9),
                "back_right": (gapx * 0.75, 0, -(R0 + e) * 0.9),
                "far": (0, 0, -(R0 + e + 12)),
                "sky": (0, 1.0, -(4 + e)) if flier else (0, max(4.0, e), -(10 + e * 1.5)),
                "above": (0, H0 + 0.35, 0),
                "around": (0, 0, 0),
            }.get(pos, (0, 0, 0))
            g["anchor"] = np.asarray(anchor, F32)
            if pos == "around" and g["n"] > 1:
                ring = max(R0 + 1.0, g["proto"].radius * g["scale"] * 2)
                g["slots"] = formation_slots("circle", g["n"], ring, 1, self.rng)
        # instâncias
        T = self.T
        for g in groups:
            a: ActorSpec = g["spec"]
            acts = [x for x in a.actions if x] or ["idle"]
            k = len(acts)
            segs = [(acts[i], T * i / k, T * (i + 1) / k) for i in range(k)]
            for i in range(g["n"]):
                if i == 0:
                    model = g["proto"]
                else:
                    color = a.color
                    if color is None and g["kind"] in (
                        "block",
                        "brick",
                        "ball",
                        "balloon",
                        "gift",
                        "candy",
                        "marble",
                        "flower",
                        "cylinder",
                        "pyramid_block",
                        "car",
                    ):
                        color = M.VIVID[(i + g["gi"]) % len(M.VIVID)]
                    model, _ = (
                        M.build(g["kind"], color, self.rng)
                        if (color is not None or g["cat"] == "person")
                        else (g["proto"], 1.0)
                    )
                if self.night and "windows" in model.tags:
                    model = _night_windows(model, self.rng)
                base = g["anchor"] + g["slots"][i]
                if (
                    g["cat"] == "prop"
                    and model.hover > 0
                    and self.spec.setting != "space"
                    and g["pos"] != "above"
                ):
                    base = base + np.array((0, model.hover, 0), F32)
                yaw = self._facing(a.facing, g, i, base, acts)
                act = Actor(model, g["kind"], g["cat"], g["scale"], base, yaw, segs, self.rng)
                act.gi, act.gn, act.slot = i, g["n"], g["slots"][i]
                d = act.slot.copy()
                d[1] = 0
                if np.linalg.norm(d) < 1e-3:
                    d = np.array((self.rng.uniform(-1, 1), 0, self.rng.uniform(-1, 0.3)), F32)
                act.scatter = normalize(d) * float(self.rng.uniform(2.5, 4.5)) * max(1.0, g["scale"])
                act.subject = g["pos"] not in ("sky", "far")
                act.group = g
                self.actors.append(act)

    def _facing(self, facing: str, g: dict, i: int, base, acts) -> float:
        moving = any(
            x in ("walk", "run", "drive", "fly", "swim", "push", "roll", "tumble", "slide") for x in acts
        )
        if "domino" in acts:  # cada peça tomba sobre a próxima da fila
            return {"diagonal": -DIAG, "row": -PI / 2}.get(g["form"], 0.0)
        if facing in ("camera", "front"):
            return 0.0
        if facing == "left":
            return -PI / 2
        if facing == "right":
            return PI / 2
        if facing in ("away", "back"):
            return PI
        if facing == "center" or (g["form"] in ("circle",) and not moving):
            return math.atan2(-base[0], -base[2]) if np.linalg.norm(base[[0, 2]]) > 0.1 else 0.0
        if moving:
            across = 1.15 if g["cat"] == "person" else PI / 2
            if g["cat"] in ("fish", "bird", "insect") or g["kind"] in (
                "car",
                "taxi",
                "bus",
                "truck",
                "train",
                "boat",
                "ship",
                "police_car",
                "submarine",
                "airplane",
            ):
                across = PI / 2
            return across if g["anchor"][0] <= 0.01 else -across
        if g["cat"] in ("person", "animal", "ghost") and g["n"] > 1 and g["form"] in ("row", "crowd", "arc"):
            return float(self.rng.uniform(-0.25, 0.25))
        if g["cat"] == "animal":
            return 0.6 if g["anchor"][0] <= 0 else -0.6
        return 0.0

    def _center_paths(self) -> None:
        for a in self.actors:
            names = {s[0] for s in a.segs}
            if not names & MOVING or names & {"circle", "orbit", "carousel"}:
                continue
            end = a.pose(self.T).pos
            if np.linalg.norm(end) > 0.3:
                a.base = a.base - end * 0.5

    # -------------------------------------------------------------- câmera
    def _frame_camera(self, preset: str) -> None:
        subj = [a for a in self.actors if a.subject] or self.actors
        tv = math.tan(math.radians(25))
        th = tv * 9 / 16

        def bbox(group):
            lo = np.array([1e9, 1e9, 1e9], F32)
            hi = -lo
            for a in group:
                r = a.model.radius * a.scale
                h = a.model.height * a.scale
                for t in np.linspace(0.2 * self.T, 0.8 * self.T, 4):
                    P = a.pose(float(t))
                    if P.hidden:
                        continue
                    p = a.base + P.pos + np.array((0, min(P.lift, 3.0), 0), F32)
                    lo = np.minimum(lo, p + np.array((-r, 0, -r), F32))
                    hi = np.maximum(hi, p + np.array((r, h * float(min(P.scale.max(), 1.6)), r), F32))
            if lo[0] > hi[0]:
                lo, hi = np.array((-1, 0, -1), F32), np.array((1, 1.6, 1), F32)
            if self.world.ground:
                lo[1] = max(lo[1], -0.5)
            size = hi - lo
            h = max(float(size[1]), 0.5)
            w = max(float(size[0]), float(size[2]) * 0.55, 0.6)
            D = max((h * 0.5 / 0.62) / tv, (w * 0.5 / 0.94) / th, 2.6)
            return (lo + hi) / 2, h, D

        center, h, D_all = bbox(subj)
        if subj:
            g0 = getattr(subj[0], "group", None)
            main = [a for a in subj if getattr(a, "group", None) is g0]
            c_main, h_main, D_main = bbox(main)
            if D_all > D_main * 1.25:
                k = 0.6
                center = c_main + (center - c_main) * k
                h = max(h_main, h * 0.75)
                D_all = max(D_main, D_all * 0.8)
        D = float(np.clip(D_all, 2.4, 70))
        self.cam_dist = D
        self.cam_focus = np.asarray(center, F32)
        self.cam_h = h
        # personagem principal (para "follow" e "closeup")
        self.main = subj[0] if subj else None
        main_moves = self.main is not None and bool(
            {s[0] for s in self.main.segs} & {"walk", "run", "drive", "fly", "swim", "push"}
        )
        if not preset:
            cycle = [
                "dolly_in",
                "orbit",
                "pan_right",
                "crane_up",
                "orbit",
                "dolly_out",
                "spiral",
                "low_angle",
            ]
            preset = cycle[self.scene_index % len(cycle)]
            if main_moves and self.main is not None and self.main.gn == 1:
                preset = "follow"
        self.preset = preset
        if preset == "follow" and self.main is not None:
            mh = self.main.model.height * self.main.scale
            self.cam_dist = float(np.clip(max((mh * 0.5 / 0.55) / tv, 3.0) * 1.1, 2.6, 30))
        for a in self.actors:
            a.face_cam = 0.0

    def camera(self, t: float) -> tuple[np.ndarray, np.ndarray, float, float]:
        T = self.T
        u = ease_io(t / T)
        F = self.cam_focus.copy()
        D = self.cam_dist
        h = self.cam_h
        el, az, fov, roll = 0.13, 0.0, 50.0, 0.0
        tgt_off = np.array((0, -h * 0.08, 0), F32)
        p = self.preset
        dist = D
        if p == "orbit":
            az = lerp(-0.4, 0.4, u) * (1 if self.scene_index % 2 == 0 else -1)
        elif p == "dolly_in":
            dist = lerp(1.35, 0.88, u) * D
            az = 0.08 * math.sin(t * 0.3)
        elif p == "dolly_out":
            dist = lerp(0.85, 1.3, u) * D
            el = lerp(0.12, 0.3, u)
        elif p in ("pan_left", "pan_right"):
            s = 1 if p == "pan_right" else -1
            off = lerp(-1, 1, u) * s * D * 0.18
            F = F + np.array((off, 0, 0), F32)
            az = -0.1 * s
        elif p == "crane_up":
            el = lerp(0.03, 0.55, u)
            dist = D * lerp(0.95, 1.1, u)
        elif p == "crane_down":
            el = lerp(0.6, 0.12, u)
        elif p == "low_angle":
            el = 0.0
            dist = D * lerp(1.05, 0.85, u)
            tgt_off = np.array((0, h * 0.2, 0), F32)
            fov = 54
        elif p == "top_down":
            el = 1.25
            az = lerp(0, 0.7, u)
            dist = D * 1.15
            fov = 55
        elif p == "spiral":
            az = lerp(-0.7, 0.7, u)
            dist = D * lerp(1.35, 0.92, u)
            el = lerp(0.5, 0.15, u)
        elif p == "reveal":
            dist = D * lerp(0.55, 1.3, u)
            el = lerp(0.03, 0.35, u)
        elif p == "flyover":
            el = 0.45
            dist = D * 1.4
            F = F + np.array((0, 0, lerp(D * 0.25, -D * 0.25, u)), F32)
        elif p == "closeup":
            if self.main is not None:
                mh = self.main.model.height * self.main.scale
                F = self.main.root_pos(t) + np.array((0, mh * 0.75, 0), F32)
                dist = max(1.2, mh * 1.3) * lerp(1.1, 0.9, u)
                tgt_off = np.zeros(3, F32)
                el = 0.08
                fov = 42
        elif p == "follow" and self.main is not None:
            mh = self.main.model.height * self.main.scale
            F = self.main.root_pos(t) * np.array((1, 0, 1), F32) + np.array(
                (0, self.main.root_pos(t)[1] * 0.5 + mh * 0.5, 0), F32
            )
            az = 0.35
        elif p == "shake":
            az = 0.05 * math.sin(t * 0.6)
            roll = 0.03 * math.sin(t * 3.3)
            F = F + np.array((math.sin(t * 7.1) * 0.03, math.sin(t * 9.3) * 0.03, 0), F32) * D * 0.2
        else:  # static
            az = 0.06 * math.sin(t * 0.4)
            dist = D * lerp(1.02, 0.97, u)
        if self.spec.setting == "space":
            el = el * 0.6
        eye = (
            F + np.array((math.sin(az) * math.cos(el), math.sin(el), math.cos(az) * math.cos(el)), F32) * dist
        )
        if self.world.ground:
            eye[1] = max(eye[1], 0.3)
        target = F + tgt_off
        if p == "low_angle":
            eye[1] = max(0.3, min(eye[1], 0.5))
        return eye.astype(F32), target.astype(F32), roll, fov

    # -------------------------------------------------------------- cenário
    def _build_static(self, spec: SceneSpec) -> None:
        st = self.setting
        meshes: list[Mesh] = []
        self.static_lights: list[PointLight] = []
        if st.structure:
            sm, sl = structure(st.structure, spec.setting, int(self.rng.integers(0, 1 << 30)), self.time)
            meshes += sm
            self.static_lights += sl
        # corredor da câmera
        eyes, targets = [], []
        for t in np.linspace(0, self.T, 7):
            e, tg, _r, _f = self.camera(float(t))
            eyes.append(e)
            targets.append(tg)
        subj_pts = [a.base for a in self.actors] or [np.zeros(3, F32)]
        subj_r = [a.model.radius * a.scale for a in self.actors] or [0.5]
        placed: list[tuple[np.ndarray, float]] = []
        look_dir = normalize(np.mean(targets, axis=0) - np.mean(eyes, axis=0))
        back_ang = math.atan2(look_dir[2], look_dir[0])
        R_sub = max(
            float(
                np.max(
                    [
                        np.linalg.norm(p[[0, 2]] - self.cam_focus[[0, 2]]) + r
                        for p, r in zip(subj_pts, subj_r, strict=True)
                    ]
                )
            ),
            1.0,
        )

        def clear(p, r):
            for e, tg in zip(eyes, targets, strict=True):
                if _seg_dist(p, e, tg) < r + 0.6:
                    return False
                if np.linalg.norm((p - e)[[0, 2]]) < r + 1.5:
                    return False
            for q, rq in zip(subj_pts, subj_r, strict=True):
                if np.linalg.norm((p - q)[[0, 2]]) < r + rq + 0.8:
                    return False
            return all(np.linalg.norm((p - q)[[0, 2]]) > r + rq * 0.8 for q, rq in placed)

        def place(kind, count, rmin, rmax, spread, scale=(0.8, 1.25), color=None):
            rmax = max(rmax, rmin + 6.0)  # atores enormes empurram a decoração para longe
            for _ in range(count):
                mesh, rad, lights, hover = decor_mesh(kind, self.rng, color)
                if self.night and kind in ("house", "building"):
                    mesh = M.night_windows(mesh, self.rng)
                for _try in range(14):
                    s = float(self.rng.uniform(*scale))
                    ang = back_ang + float(self.rng.normal(0, spread))
                    r = float(self.rng.uniform(rmin, rmax))
                    y = hover * float(self.rng.uniform(0.6, 1.6)) if hover > 0.5 else 0.0
                    p = self.cam_focus * np.array((1, 0, 1), F32) + np.array(
                        (math.cos(ang) * r, y, math.sin(ang) * r), F32
                    )
                    if clear(p, rad * s):
                        yaw = float(self.rng.uniform(0, TAU))
                        mm = mesh.apply(mat4(p, (0, yaw, 0), s))
                        meshes.append(mm)
                        placed.append((p, rad * s))
                        for lp, lc, pw, lr in lights:
                            wp = mat4(p, (0, yaw, 0), s)[:3, :3] @ lp + p
                            self.static_lights.append(PointLight(wp.astype(F32), lc, pw, lr * s))
                        break

        r0 = max(st.ring[0], R_sub + 2.5)
        if st.decor and self.world.ground or spec.setting in ("space",):
            for kind, count in st.decor:
                spread = 0.9 if kind not in ("rock", "flower", "mushroom", "grass", "bush") else 1.3
                place(
                    kind,
                    count,
                    r0,
                    max(r0 + 6, st.ring[1]),
                    spread,
                    color=st.decor_color if kind in ("pine",) else None,
                )
        for kind, count in st.backdrop:
            if kind == "mountain":
                place(kind, count, 38, 55, 0.7, (0.8, 1.4))
            elif kind in ("planet", "earth"):
                for _ in range(count):
                    mesh, rad, _l, _h = decor_mesh(kind, self.rng)
                    ang = back_ang + float(self.rng.uniform(-0.5, 0.5))
                    r = float(self.rng.uniform(28, 45))
                    y = (
                        float(self.rng.uniform(4, 14))
                        if spec.setting != "space"
                        else float(self.rng.uniform(-6, 10))
                    )
                    p = np.array((math.cos(ang) * r, y, math.sin(ang) * r), F32) + self.cam_focus * np.array(
                        (1, 0, 1), F32
                    )
                    meshes.append(
                        mesh.apply(
                            mat4(
                                p,
                                (0.3, float(self.rng.uniform(0, TAU)), 0),
                                float(self.rng.uniform(1.2, 2.5)),
                            )
                        )
                    )
            else:
                place(kind, count, max(16, r0 + 8), 30, 0.5, (0.9, 1.1))
        if spec.setting == "space" and not any(a.kind == "sun" for a in self.actors):
            sd = normalize(np.asarray(self.world.sun_dir, F32))
            sun = M.build("sun", None, self.rng)[0]
            meshes.append(
                sun.mesh.apply(mat4(self.cam_focus + sd * 90 - np.array((0, 3, 0), F32), (0, 0, 0), 2.5))
            )
        self.static = Mesh.merge(*meshes) if meshes else Mesh(np.zeros((0, 3)), np.zeros((0, 3)))
        if not self.night:
            self.static_lights = [lt for lt in self.static_lights if lt.power > 1.6]

    def _dyn_slices(self) -> None:
        self.vslices, self.fslices = [], []
        v = f = 0
        for a in self.actors:
            nv, nf = len(a.model.mesh.v), len(a.model.mesh.f)
            self.vslices.append((v, v + nv))
            self.fslices.append((f, f + nf))
            v += nv
            f += nf
        self.n_dyn_v, self.n_dyn_f = v, f

    # -------------------------------------------------------------- efeitos
    def _effects_setup(self) -> None:
        self.booms: list[tuple[float, Actor]] = []
        self.launches: list[tuple[float, float, Actor]] = []
        for a in self.actors:
            for name, t0, t1 in a.segs:
                if name == "explode":
                    self.booms.append((t0 + (t1 - t0) * (0.35 if a.gn > 1 else 0.4), a))
                if name in ("launch",) or (name == "rise" and "rocket" in a.model.tags):
                    self.launches.append((t0, t1, a))
        seen = set()
        uniq = []
        for tb, a in self.booms:
            key = (round(tb, 2), id(getattr(a, "group", a)))
            if a.gn > 1 and key in seen:
                continue
            seen.add(key)
            uniq.append((tb, a))
        self.booms = uniq
        rng = np.random.default_rng(7)
        self._spark_dir = rng.normal(size=(60, 3)).astype(F32)
        self._spark_dir[:, 1] = np.abs(self._spark_dir[:, 1]) + 0.3
        self._spark_speed = rng.uniform(2.5, 6, 60).astype(F32)
        self._ember_base = rng.uniform(-1, 1, (24, 3)).astype(F32)
        self._ember_ph = rng.uniform(0, 1, 24).astype(F32)

    def _effects(self, t: float, mats_by_actor: list) -> list[Particles]:
        out: list[Particles] = []
        for tb, a in self.booms:
            s = t - tb
            if 0 <= s < 1.4:
                c = a.base + np.array((0, a.model.height * a.scale * 0.5, 0), F32)
                if a.gn > 1:
                    c = a.group["anchor"] + np.array((0, a.model.height * a.scale, 0), F32)
                p = c + self._spark_dir * self._spark_speed[:, None] * s - np.array((0, 4.9 * s * s, 0), F32)
                k = max(0.0, 1 - s / 1.4)
                col = np.tile(np.asarray((1.0, 0.75, 0.3), F32), (len(p), 1))
                out.append(
                    Particles(
                        p.astype(F32),
                        np.full(len(p), 0.05 * k + 0.01, F32),
                        col,
                        np.full(len(p), k, F32),
                        None,
                        False,
                        True,
                    )
                )
        for t0, t1, a in self.launches:
            if self.world.ground and t0 <= t <= t1 + 1.5:
                P = a.pose(min(t, t1))
                base = a.base + P.pos + np.array((0, P.lift, 0), F32)
                n = 30
                ages = (np.arange(n, dtype=F32) / n + t * 0.8) % 1.0
                pos = base[None] + np.c_[
                    np.sin(np.arange(n) * 2.1) * ages * 1.2,
                    -ages * 3.0,
                    np.cos(np.arange(n) * 1.7) * ages * 1.2,
                ].astype(F32)
                pos[:, 1] = np.maximum(pos[:, 1], 0.2)
                col = np.tile(np.asarray((0.92, 0.92, 0.92), F32), (n, 1))
                out.append(
                    Particles(
                        pos.astype(F32), (0.3 + ages * 0.8).astype(F32) * (1 - ages * 0.6) * a.scale, col
                    )
                )
        for i, a in enumerate(self.actors):
            if "fire" in a.model.tags or "bubbles" in a.model.tags:
                mats = mats_by_actor[i]
                if mats is None:
                    continue
                node = "flame" if a.model.has("flame") else a.model.names[0]
                m = mats[a.model.names.index(node)]
                c = m[:3, 3]
                k = a.scale * (3.0 if a.kind == "volcano" else 1.0)
                ages = (self._ember_ph + t * 0.6) % 1.0
                pos = (
                    c[None]
                    + self._ember_base * np.array((0.25, 0, 0.25), F32) * k
                    + np.c_[np.zeros(24), ages * 1.6 * k, np.zeros(24)].astype(F32)
                )
                if "bubbles" in a.model.tags:
                    col = np.tile(np.asarray((0.5, 1.0, 0.4), F32), (24, 1))
                    out.append(
                        Particles(
                            pos.astype(F32),
                            np.full(24, 0.04 * k, F32),
                            col,
                            (1 - ages).astype(F32),
                            None,
                            True,
                            True,
                        )
                    )
                else:
                    col = np.tile(np.asarray((1.0, 0.55, 0.15), F32), (24, 1))
                    out.append(
                        Particles(
                            pos.astype(F32),
                            np.full(24, 0.02 * k, F32),
                            col,
                            (1 - ages).astype(F32),
                            None,
                            False,
                            True,
                        )
                    )
        return out

    # -------------------------------------------------------------- quadro
    def frame(self, t: float) -> Frame:
        eye, target, roll, fov = self.camera(t)
        verts = np.empty((self.n_dyn_v, 3), F32)
        emit = np.ones(self.n_dyn_f, F32)
        lights: list[PointLight] = list(self.static_lights)
        mats_by_actor: list = []
        for i, a in enumerate(self.actors):
            P = a.pose(t)
            root = a.matrix(P)
            v, mats = a.model.pose(root, P.rot, P.npos, P.nscale)
            s, e = self.vslices[i]
            verts[s:e] = v
            fs, fe = self.fslices[i]
            if P.emit != 1.0:
                emit[fs:fe] = P.emit
            mats_by_actor.append(mats)
            if P.hidden:
                continue
            for node, pos, col, power, radius, flick in a.model.lights:
                mt = mats[a.model.names.index(node)]
                wp = mt[:3, :3] @ np.asarray(pos, F32) + mt[:3, 3]
                pw = power * P.light if power > 0 else max(0.0, P.light - 1) * 0.6
                if flick:
                    pw *= 0.82 + 0.12 * math.sin(t * 13 + a.phase) + 0.06 * math.sin(t * 29)
                if pw > 0.01:
                    lights.append(PointLight(wp.astype(F32), col, pw, radius * a.scale))
        if len(lights) > 5:
            lights.sort(key=lambda lt: float(np.linalg.norm(lt.pos - self.cam_focus)))
            lights = lights[:5]
        if self.fill > 0:
            up = np.array((0, 1.2 + self.cam_h * 0.4, 0), F32)
            lights.append(
                PointLight(
                    (eye + (target - eye) * 0.15 + up).astype(F32),
                    self.fill_color,
                    self.fill,
                    self.cam_dist * 1.6,
                    False,
                )
            )
        parts: list[Particles] = []
        if self.weather is not None:
            parts += self.weather(t)
        parts += self._effects(t, mats_by_actor)
        flash = 0.0
        for ft in self.flash_times:
            d = t - ft
            if 0 <= d < 0.35:
                flash = max(flash, (1 - d / 0.35) * (0.6 + 0.4 * math.sin(d * 60)))
        return Frame(
            eye,
            target,
            roll,
            fov,
            verts if self.n_dyn_v else None,
            emit if self.n_dyn_f else None,
            lights,
            parts,
            flash,
        )


def _seg_dist(p, a, b) -> float:
    ab = b - a
    t = float(np.clip(np.dot(p - a, ab) / max(np.dot(ab, ab), 1e-6), 0, 1))
    q = a + ab * t
    return float(np.linalg.norm((p - q)[[0, 2]]))


def _night_windows(model: M.Model, rng) -> M.Model:
    out = M.Model(model.kind, model.height, model.radius)
    out.__dict__.update({k: v for k, v in model.__dict__.items() if k != "mesh"})
    out.mesh = M.night_windows(model.mesh, rng)
    return out
