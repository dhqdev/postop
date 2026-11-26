"""Motor 2D: personagens, cenários, roteiro e uma cena curta renderizada de verdade."""

import shutil
import subprocess

import numpy as np
import pytest

from app.media import Word
from app.render2d import STYLE2D_NAMES, STYLES2D, render_scene2d
from app.render2d.anim import NATURAL
from app.render2d.characters import CHARACTER_TYPES, CRITTERS, PRESETS, build_rig, critter_height, make_look
from app.render2d.places import PLACES, draw_place
from app.render2d.props import PROP_NAMES, draw_prop
from app.render2d.scene import Element2D, Scene2D, SceneSpec2D
from app.render2d.story import catalog_text, normalize_story, offline_story

needs_ffmpeg = pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg ausente")


def _scene(actions, seconds=6.0, kind="king", **spec):
    el = Element2D(kind="char", type=kind, ref="a", look=make_look(kind, "1"), actions=actions, at="center")
    return Scene2D(
        SceneSpec2D(place="palace", time="day", elements=[el], camera="static", **spec),
        seconds,
        "papel",
        1,
        0,
        270,
        480,
    )


def test_every_character_type_draws():
    assert len(PRESETS) >= 55 and len(CRITTERS) >= 40
    for kind in CHARACTER_TYPES:
        rig = build_rig(make_look(kind, "s"), 240, paper=1.0, seed=3)
        head = rig.head("happy", 0.0)
        assert head.img.shape[2] == 4 and head.img[..., 3].max() > 200, kind


def _drawn_height(kind):
    el = Element2D(kind="char", type=kind, look=make_look(kind, "1"), actions=["idle"], at="center")
    scene = Scene2D(SceneSpec2D(place="plain", elements=[el], camera="static"), 3.0, "flat", 1, 0, 270, 480)
    empty = Scene2D(SceneSpec2D(place="plain", elements=[], camera="static"), 3.0, "flat", 1, 0, 270, 480)
    diff = np.abs(scene.frame(2.5).astype(int) - empty.frame(2.5)).sum(axis=2) > 40
    rows = np.where(diff.any(axis=1))[0]
    return rows.max() - rows.min(), scene._char_height(el)


@pytest.mark.parametrize("kind", ["man", "boy", "dog", "cat", "horse", "bird", "turtle"])
def test_characters_are_drawn_at_their_real_size(kind):
    """Animais do tamanho certo em relação às pessoas (um cachorro não fica do tamanho de um adulto)."""
    drawn, expected = _drawn_height(kind)
    assert 0.7 * expected <= drawn <= 1.35 * expected
    assert (critter_height(kind) < 70) == (kind in ("dog", "cat", "bird", "turtle")) or kind not in CRITTERS


def test_props_and_places_draw():
    for name in PROP_NAMES:
        spr = draw_prop(name, 160, paper=1.0, seed=2)
        assert spr.img[..., 3].max() > 0, name
    for name in PLACES:
        img = draw_place(name, "night" if name == "space" else "day", 108, 192, paper=1.0, seed=1)
        assert img.shape == (192, 108, 3) and img.std() > 1, name


def test_actions_happen_once_and_the_character_rests():
    """Nada de looping: o pulo acontece uma vez e depois o personagem fica parado."""
    scene = _scene(["jump"])
    actor = scene.actors[0]
    jumping = [i / 20 for i in range(121) if actor.pose(i / 20).jump > 1]
    assert jumping and jumping[-1] - jumping[0] <= NATURAL["jump"] + 0.05
    late = [actor.pose(t) for t in (3.0, 4.5, 6.0)]
    assert all(p.jump == 0 and p.x == 0 for p in late)


def test_walk_in_arrives_then_waves_then_stops():
    actor = _scene(["walk_in", "wave"]).actors[0]
    assert actor.pose(0.5).x != 0  # ainda chegando
    assert actor.pose(2.2).x == 0 and actor.pose(2.2).arm_r[0] > 1.5  # chegou e acena
    end = actor.pose(5.8)
    assert end.x == 0 and end.arm_r[0] < 0.5  # braço abaixado: o aceno terminou


def test_frames_have_the_right_size_and_captions():
    words = [
        Word(0.2 + i * 0.3, 0.45 + i * 0.3, w)
        for i, w in enumerate(" Os três jovens na fornalha".split(" ")[1:])
    ]
    scene = Scene2D(
        SceneSpec2D(place="fire", banner="A FORNALHA", fx="embers",
                    elements=[Element2D(kind="char", type="biblical_man", look=make_look("biblical_man", "x"), count=3, actions=["pray"])]),
        2.0, "papel", 4, 0, 216, 384, words=words,
    )  # fmt: skip
    first, last = scene.frame(0.0), scene.frame(1.9)
    assert first.shape == (384, 216, 3) and first.dtype == np.uint8
    assert np.abs(first.astype(int) - last).mean() > 1


def test_story_normalization_fixes_names_and_keeps_cast():
    raw = {
        "title": "Daniel 3",
        "cast": [{"id": "rei", "type": "rei"}, {"id": "jovem", "type": "homem bíblico", "color": "azul"}],
        "scenes": [
            {"narration": "Tudo começou assim.", "place": "lugar inventado", "show": [{"id": "rei", "do": ["acenar"]}]},
            {"narration": "O rei fez uma estátua.", "place": "palácio",
             "show": [{"id": "rei", "do": ["apontar"]}, {"prop": "estátua", "do": ["brilhar"]}, {"prop": "coisa xyz"}]},
            {"narration": "Os jovens não se curvaram.", "place": "outro lugar inventado", "show": [{"id": "jovem", "do": ["rezar"]}]},
        ],
    }  # fmt: skip
    story = normalize_story(raw, 3, "desert", "prophet")
    first, second, third = story.scenes
    # lugar desconhecido: cenário do tema na 1ª cena, depois continua no lugar anterior
    assert (first.place, second.place, third.place) == ("desert", "palace", "palace")
    kinds = [(e.kind, e.type) for e in second.elements]
    assert kinds == [("char", "king"), ("prop", "statue")]  # objeto fora do catálogo sai
    assert first.elements[0].actions == ["wave"] and second.elements[0].actions == ["point"]
    assert second.elements[1].actions == ["glow"] and third.elements[0].actions == ["pray"]
    # o mesmo personagem tem a mesma aparência em todas as cenas
    assert first.elements[0].look == second.elements[0].look == story.cast["rei"].look
    assert third.elements[0].look == story.cast["jovem"].look


def test_offline_story_and_catalog_are_compact():
    data = offline_story("Um cachorro astronauta viaja até a Lua. Lá ele encontra um robô. Os dois voltam juntos.",
                         4, "space", "astronaut", ("#espaco",))  # fmt: skip
    assert len(data["scenes"]) == 4 and data["scenes"][0]["narration"].startswith("Um cachorro")
    story = normalize_story(data, 4, "space", "astronaut")
    assert len(story.scenes) == 4 and all(s.elements for s in story.scenes)
    assert len(catalog_text()) < 4500  # vai no prompt: poucos tokens
    assert set(STYLES2D) == set(STYLE2D_NAMES) == {"papel", "flat"}


@needs_ffmpeg
def test_render_scene2d_writes_a_short_clip(tmp_path):
    spec = SceneSpec2D(place="street", time="sunset", banner="TESTE", tag="FATO",
                       elements=[Element2D(kind="char", type="woman", look=make_look("woman", "w"), actions=["walk_in", "wave"])])  # fmt: skip
    out = tmp_path / "s.mp4"
    wav = tmp_path / "s.wav"
    render_scene2d(spec, out, 1.0, width=216, height=384, fps=10, audio_out=str(wav))
    probe = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0", "-count_frames", "-show_entries",
         "stream=width,height,nb_read_frames", "-of", "csv=p=0", str(out)],
        capture_output=True, text=True, check=True,
    )  # fmt: skip
    assert probe.stdout.strip() == "216,384,10"
    assert wav.exists() and wav.stat().st_size > 1000
