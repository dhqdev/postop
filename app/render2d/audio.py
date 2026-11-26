"""Som da cena 2D: ambiente do cenário + efeitos nos momentos certos (pop, whoosh, ding, palmas...).

Reaproveita os sintetizadores do motor 3D (`app/render3d/sound.py`): nada é baixado nem gerado por IA.
"""

from __future__ import annotations

import numpy as np

from ..render3d.sound import Track, _render_event, ambience, s_thunder, swell

AMBIENCE = {
    "room": "room", "bedroom": "room", "living_room": "room", "office": "office", "classroom": "room", "lab": "lab",
    "church": "room", "palace": "room", "street": "city", "city": "city", "night_city": "city",
    "ancient_city": "desert", "desert": "desert", "egypt": "egypt", "village": "village", "farm": "farm",
    "forest": "forest", "park": "park", "hills": "park", "beach": "beach", "underwater": "underwater",
    "space": "space", "sky": "sky", "graveyard": "graveyard", "cave": "cave", "mountains": "mountains",
    "snow": "snow", "fire": "volcano", "stage": "stage", "stable": "farm", "temple": "temple", "castle": "castle",
    "jungle": "jungle",
}  # fmt: skip


def scene_audio2d(scene, seed: int = 0) -> np.ndarray:
    """Trilha estéreo (ambiente baixo + efeitos) com a duração da cena."""
    rng = np.random.default_rng(seed + 777)
    T = scene.T
    tr = Track(T)
    setting = AMBIENCE.get(scene.spec.place, "")
    weather = {"rain": "rain", "snow": "snow", "lightning": "storm", "sparkles": "sparkles", "bubbles": "bubbles",
               "embers": "embers", "leaves": "leaves"}.get(scene.spec.fx, "none")  # fmt: skip
    if setting or weather != "none":
        bed = ambience(setting, scene.spec.time, weather, T, rng)
        tr.add_bed(bed * swell(len(bed), 0.2, 0.2), 0.55)
    cache: dict = {}
    for t, name, o in sorted(scene.events, key=lambda e: e[0]):
        if t >= T:
            continue
        if name == "thunder_soft":
            tr.add(s_thunder(rng, 2.5), t, 0.5 * float(o.get("g", 1.0)))
            continue
        key = (name, round(float(o.get("sec", 0)), 1), o.get("soft"))
        x = cache.get(key)
        if x is None:
            o2 = dict(o)
            if "sec" in o2:
                o2["sec"] = max(0.2, min(float(o2["sec"]), T - t))
            x = _render_event(name, o2, rng)
            if x is None:
                continue
            cache[key] = x
        tr.add(x, t, float(o.get("g", 1.0)) * 0.75, float(rng.uniform(-0.25, 0.25)))
    return tr.buf
