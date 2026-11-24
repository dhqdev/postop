"""Motor 3D: modelos, ações, normalização do roteiro, cenários e gravação de um clipe."""

import shutil

import numpy as np
import pytest

from app.render3d import catalog_text, normalize_scene, offline_script, render_scene
from app.render3d import models as M
from app.render3d.actions import ACTIONS
from app.render3d.renderer import Renderer
from app.render3d.scene import Actor, Scene, SceneSpec
from app.render3d.world import SETTINGS


def test_every_model_builds():
    rng = np.random.default_rng(0)
    for kind in M.REGISTRY:
        model, scale = M.build(kind, None, rng)
        mesh = model.mesh
        assert len(mesh.f) > 0 and scale > 0, kind
        assert np.isfinite(mesh.v).all(), kind
        assert mesh.f.min() >= 0 and mesh.f.max() < len(mesh.v), kind
        assert len(mesh.c) == len(mesh.f) == len(mesh.e) == len(mesh.s) == len(mesh.d), kind
        assert model.height > 0 and model.radius > 0, kind


def test_every_action_runs_on_every_kind_of_model():
    rng = np.random.default_rng(1)
    kinds = ["person", "ghost", "robot", "cat", "horse", "dragon", "bird", "penguin", "fish", "whale", "octopus",
             "jellyfish", "snake", "butterfly", "block", "car", "rocket", "chest", "elevator", "flag", "windmill",
             "clock", "atom", "planet"]  # fmt: skip
    for kind in kinds:
        model, scale = M.build(kind, None, rng)
        cat = model.kind if model.kind in ("ghost", "snake") else M.category(kind)
        for action in ACTIONS:
            a = Actor(model, kind, cat, scale, (0, 0, 0), 0.0, [(action, 0.0, 2.0), ("idle", 2.0, 3.0)], rng)
            a.gi, a.gn = 1, 3
            a.slot = np.array((1.0, 0.0, 0.0), np.float32)
            a.scatter = np.array((2.0, 0.0, 0.5), np.float32)
            for t in (0.0, 0.7, 1.9, 2.5):
                P = a.pose(t)
                v, _ = model.pose(a.matrix(P), P.rot, P.npos, P.nscale)
                assert np.isfinite(v).all(), (kind, action, t)


def test_normalize_scene_understands_portuguese_and_fixes_values():
    spec = normalize_scene(
        {
            "setting": "floresta",
            "time": "noite",
            "camera": "de cima",
            "actors": [
                {
                    "type": "gato laranja",
                    "actions": "andar e pular",
                    "count": "3",
                    "color": "vermelho",
                    "size": 99,
                },
                {"type": "coisa que não existe"},
                "foguete",
            ],
        }
    )
    assert (spec.setting, spec.time, spec.camera) == ("forest", "night", "top_down")
    cat, rocket = spec.actors
    assert cat.type == "cat" and cat.actions == ["walk", "jump"] and cat.count == 3
    assert cat.color is not None and cat.color[0] > 0.8 and cat.size <= 6
    assert rocket.type == "rocket" and rocket.actions == ["idle"]


def test_normalize_scene_infers_from_text_when_ai_sends_nothing():
    spec = normalize_scene(None, text="Um robô dançando na praia ao pôr do sol")
    assert spec.setting == "beach" and spec.time == "sunset"
    assert spec.actors[0].type == "robot" and spec.actors[0].actions == ["dance"]
    assert normalize_scene({}, theme_world="space", default_actor="astronaut").actors[0].type == "astronaut"


def test_offline_script_and_catalog():
    script = offline_script(
        "Um gato astronauta descobre um planeta feito de doces", 4, "space", hashtags=("#a",)
    )
    assert len(script["scenes"]) == 4 and script["hashtags"] == ["#a"]
    first = script["scenes"][0]
    assert first["text"] and first["scene3d"]["actors"][0]["type"] in ("cat", "astronaut")
    cams = {s["scene3d"]["camera"] for s in script["scenes"]}
    assert len(cams) > 1
    cat = catalog_text()
    for kind in M.REGISTRY:
        assert kind in cat, kind
    for setting in SETTINGS:
        assert setting in cat


def test_every_setting_renders_a_frame():
    for i, setting in enumerate(SETTINGS):
        spec = normalize_scene(
            {
                "setting": setting,
                "actors": [{"type": "person", "actions": ["walk"]}, {"type": "block", "count": 3}],
            }
        )
        scene = Scene(spec, 1.0, "pixar3d", seed=i, scene_index=i)
        img = Renderer(scene, 90, 160).frame(0.5)
        assert img.shape == (160, 90, 3) and img.dtype == np.uint8, setting
        assert img.std() > 2, setting  # não saiu uma tela lisa


@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg ausente")
def test_render_scene_writes_clip(tmp_path):
    from app import media

    spec = SceneSpec("studio", "day", "confetti", "orbit")
    spec.actors = normalize_scene({"actors": [{"type": "block", "count": 6, "actions": ["stack"]}]}).actors
    out = tmp_path / "clip.mp4"
    render_scene(spec, out, 1.0, "clay", seed=3, width=180, height=320, fps=12)
    assert media.video_size(out) == (180, 320)
    assert 0.8 <= media.duration_of(out) <= 1.3
