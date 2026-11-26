"""Personagens 2D desenhados por código (estilo recorte de papel / desenho animado).

Cada personagem é um "boneco articulado": pernas, quadril, tronco, braços em duas partes e cabeça
(com expressões e olhar para o lado). A aparência vem de um `Look` (tipo, pele, cabelo, roupa,
chapéu, barba, acessórios), montado a partir dos modelos prontos em `PRESETS` e das cores que a
IA escolheu. Medidas em unidades: um adulto tem 100 unidades de altura, pés em y = 0.
"""

from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass, field, replace

import numpy as np

from .draw import Pen, Sprite, bez, pen_sprite, rgb, shade

# ------------------------------------------------------------------ paletas
SKINS = {
    "light": (255, 220, 190),
    "fair": (246, 205, 170),
    "medium": (226, 172, 128),
    "tan": (196, 138, 96),
    "brown": (150, 98, 64),
    "dark": (104, 66, 44),
}
SKIN_LIST = list(SKINS.values())
HAIRS = {
    "black": (36, 30, 34),
    "dark": (66, 44, 34),
    "brown": (112, 70, 42),
    "auburn": (150, 66, 38),
    "blond": (232, 190, 96),
    "red": (196, 82, 46),
    "gray": (170, 170, 176),
    "white": (236, 236, 240),
}
HAIR_LIST = [HAIRS[k] for k in ("black", "dark", "brown", "auburn", "blond", "dark", "black")]
PALETTE = [
    (231, 76, 60), (52, 120, 219), (46, 174, 96), (243, 156, 18), (155, 89, 182), (26, 188, 156),
    (230, 103, 160), (241, 196, 15), (52, 73, 94), (211, 84, 0), (89, 160, 230), (120, 170, 60),
]  # fmt: skip
GOLD = (246, 196, 64)
SHOE = (70, 52, 44)
MOUTH = (128, 44, 52)
TONGUE = (232, 110, 120)
EYE = (40, 32, 40)
BLUSH = (255, 120, 130)
WHITE = (250, 250, 250)


@dataclass
class Look:
    kind: str = "person"
    skin: tuple = SKINS["fair"]
    hair: tuple = HAIRS["dark"]
    hair_style: str = "short"  # short, side, long, curly, afro, bun, ponytail, spiky, bald, veil, wavy
    beard: str = ""  # full, short, mustache, goatee
    top: tuple = (52, 120, 219)  # cor principal da roupa
    bottom: tuple = (52, 73, 94)  # calça
    accent: tuple = (231, 76, 60)  # faixa, gravata, detalhes
    outfit: str = (
        "shirt"  # shirt, tshirt, robe, royal, tunic, dress, suit, coat, armor, uniform, space, hoodie,
    )
    # overalls, toga, apron, vest, sweater, ghost, robot
    head: str = (
        ""  # crown, tiara, helmet, roman, cap, police, hat, cowboy, straw, turban, headband, halo, chef,
    )
    # wizard, witch, grad, astronaut, hood, pharaoh, party, hardhat, beanie, headcloth
    head_color: tuple = (231, 76, 60)
    extras: tuple = ()  # sunglasses, glasses, eyepatch, mask, freckles, cape, wings, badge, tie, stethoscope
    hold: str = (
        ""  # staff, scepter, book, phone, sword, mic, candle, torch, flag, sign, briefcase, flower, scroll,
    )
    # cup, magnifier, lantern, bible, star, balloon, money
    age: str = "adult"  # adult, child, baby, old
    body: str = "human"  # human, ghost, robot, alien, mermaid
    shoes: tuple = SHOE
    cape: tuple = (200, 40, 50)

    def key(self) -> str:
        return hashlib.md5(repr(self).encode()).hexdigest()[:12]


# Modelos prontos (o que a IA escolhe em "type"). Valores ausentes vêm do sorteio por id.
PRESETS: dict[str, dict] = {
    "person": {},
    "man": {"hair_style": "short"},
    "woman": {"hair_style": "long", "outfit": "dress"},
    "boy": {"age": "child", "hair_style": "short", "outfit": "tshirt"},
    "girl": {"age": "child", "hair_style": "ponytail", "outfit": "dress"},
    "baby": {"age": "baby", "hair_style": "bald", "outfit": "tshirt", "top": (250, 236, 200)},
    "old_man": {
        "age": "old",
        "hair_style": "bald",
        "hair": HAIRS["gray"],
        "beard": "mustache",
        "outfit": "sweater",
        "extras": ("glasses",),
    },
    "old_woman": {
        "age": "old",
        "hair_style": "bun",
        "hair": HAIRS["gray"],
        "outfit": "dress",
        "extras": ("glasses",),
    },
    "king": {
        "outfit": "royal",
        "head": "crown",
        "beard": "full",
        "top": (128, 60, 170),
        "accent": (214, 48, 49),
        "hold": "",
        "hair": HAIRS["black"],
    },
    "queen": {"outfit": "royal", "head": "crown", "hair_style": "long", "top": (190, 50, 90), "accent": GOLD},
    "prince": {"outfit": "royal", "head": "tiara", "top": (52, 120, 219), "accent": GOLD},
    "princess": {
        "outfit": "dress",
        "head": "tiara",
        "hair_style": "long",
        "top": (240, 130, 190),
        "hair": HAIRS["blond"],
    },
    "prophet": {
        "outfit": "robe",
        "beard": "full",
        "hair_style": "long",
        "top": (214, 190, 150),
        "accent": (60, 110, 190),
        "hold": "staff",
    },
    "shepherd": {
        "outfit": "robe",
        "head": "headcloth",
        "beard": "short",
        "top": (196, 164, 120),
        "accent": (150, 90, 60),
        "head_color": (232, 220, 190),
        "hold": "staff",
    },
    "disciple": {"outfit": "robe", "beard": "short", "top": (100, 150, 200), "accent": (220, 200, 150)},
    "jesus": {
        "outfit": "robe",
        "beard": "short",
        "hair_style": "long",
        "hair": HAIRS["brown"],
        "top": (246, 244, 236),
        "accent": (200, 50, 50),
        "skin": SKINS["medium"],
    },
    "mary": {
        "outfit": "robe",
        "hair_style": "veil",
        "top": (230, 230, 236),
        "accent": (70, 120, 200),
        "head_color": (70, 120, 200),
    },
    "biblical_man": {"outfit": "robe", "beard": "short", "top": (90, 140, 200), "accent": (230, 210, 160)},
    "biblical_woman": {
        "outfit": "robe",
        "hair_style": "veil",
        "top": (210, 110, 110),
        "head_color": (240, 220, 190),
    },
    "angel": {
        "outfit": "robe",
        "head": "halo",
        "extras": ("wings",),
        "hair_style": "curly",
        "hair": HAIRS["blond"],
        "top": (250, 250, 250),
        "accent": (246, 196, 64),
    },
    "priest": {"outfit": "robe", "top": (40, 40, 48), "accent": (250, 250, 250)},
    "pharaoh": {
        "outfit": "tunic",
        "head": "pharaoh",
        "top": (250, 244, 225),
        "accent": GOLD,
        "skin": SKINS["tan"],
    },
    "soldier": {
        "outfit": "armor",
        "head": "roman",
        "top": (190, 50, 50),
        "accent": (160, 160, 170),
        "hold": "sword",
    },
    "guard": {"outfit": "armor", "head": "helmet", "top": (150, 150, 160), "accent": (190, 50, 50)},
    "knight": {
        "outfit": "armor",
        "head": "helmet",
        "top": (165, 170, 182),
        "accent": (52, 90, 190),
        "hold": "sword",
        "extras": ("cape",),
        "cape": (52, 90, 190),
    },
    "roman": {"outfit": "toga", "top": (250, 248, 240), "accent": (170, 40, 50), "head": ""},
    "viking": {
        "outfit": "tunic",
        "head": "helmet",
        "beard": "full",
        "hair": HAIRS["red"],
        "top": (120, 90, 60),
    },
    "scientist": {"outfit": "coat", "extras": ("glasses",), "hair_style": "spiky", "hold": ""},
    "doctor": {
        "outfit": "coat",
        "extras": ("stethoscope",),
        "top": (250, 250, 250),
        "accent": (90, 170, 220),
    },
    "nurse": {"outfit": "uniform", "top": (120, 200, 220), "hair_style": "bun"},
    "teacher": {"outfit": "sweater", "extras": ("glasses",), "hold": "book"},
    "student": {"age": "child", "outfit": "tshirt", "hold": "book"},
    "police": {"outfit": "uniform", "head": "police", "top": (40, 70, 140), "extras": ("badge",)},
    "detective": {
        "outfit": "coat",
        "head": "hat",
        "top": (170, 140, 100),
        "hold": "magnifier",
        "head_color": (110, 90, 70),
    },
    "agent": {
        "outfit": "suit",
        "extras": ("sunglasses",),
        "top": (36, 36, 44),
        "accent": (36, 36, 44),
        "hair_style": "short",
        "hair": HAIRS["black"],
    },
    "businessman": {"outfit": "suit", "top": (52, 73, 120), "accent": (200, 50, 60), "hold": "briefcase"},
    "reporter": {"outfit": "suit", "top": (180, 60, 60), "accent": (240, 240, 240), "hold": "mic"},
    "chef": {"outfit": "apron", "head": "chef", "top": (250, 250, 250)},
    "farmer": {"outfit": "overalls", "head": "straw", "top": (210, 70, 60)},
    "worker": {"outfit": "vest", "head": "hardhat", "top": (243, 130, 30)},
    "astronaut": {"outfit": "space", "head": "astronaut", "top": (245, 245, 248), "accent": (52, 120, 219)},
    "pilot": {
        "outfit": "suit",
        "head": "cap",
        "top": (40, 60, 110),
        "head_color": (40, 60, 110),
        "extras": ("sunglasses",),
    },
    "firefighter": {
        "outfit": "uniform",
        "head": "hardhat",
        "top": (220, 60, 40),
        "head_color": (220, 60, 40),
    },
    "athlete": {"outfit": "tshirt", "head": "headband", "top": (230, 60, 60), "bottom": (40, 40, 60)},
    "superhero": {
        "outfit": "suit",
        "extras": ("mask", "cape"),
        "top": (52, 90, 220),
        "accent": (230, 50, 50),
        "cape": (230, 50, 50),
    },
    "ninja": {"outfit": "suit", "head": "hood", "top": (40, 40, 48), "head_color": (40, 40, 48)},
    "pirate": {
        "outfit": "shirt",
        "head": "headband",
        "extras": ("eyepatch",),
        "beard": "full",
        "top": (250, 245, 230),
        "head_color": (200, 40, 40),
        "hold": "sword",
    },
    "cowboy": {"outfit": "vest", "head": "cowboy", "top": (180, 120, 70)},
    "explorer": {
        "outfit": "shirt",
        "head": "hat",
        "top": (190, 170, 120),
        "head_color": (170, 140, 90),
        "hold": "magnifier",
    },
    "wizard": {
        "outfit": "robe",
        "head": "wizard",
        "beard": "full",
        "hair": HAIRS["white"],
        "top": (70, 60, 160),
        "head_color": (70, 60, 160),
        "hold": "staff",
    },
    "witch": {
        "outfit": "dress",
        "head": "witch",
        "hair_style": "long",
        "top": (60, 40, 80),
        "head_color": (40, 30, 50),
    },
    "vampire": {
        "outfit": "suit",
        "extras": ("cape",),
        "skin": (238, 232, 236),
        "hair": HAIRS["black"],
        "cape": (40, 20, 30),
        "top": (30, 30, 36),
    },
    "zombie": {"outfit": "tshirt", "skin": (150, 190, 130), "hair_style": "spiky", "top": (120, 110, 130)},
    "ghost": {"body": "ghost", "outfit": "ghost", "top": (246, 246, 252)},
    "robot": {"body": "robot", "outfit": "robot", "top": (170, 180, 196), "accent": (52, 200, 230)},
    "alien": {
        "body": "alien",
        "skin": (140, 210, 120),
        "hair_style": "bald",
        "outfit": "space",
        "top": (200, 210, 230),
    },
    "caveman": {"outfit": "tunic", "hair_style": "curly", "beard": "full", "top": (190, 130, 70), "hold": ""},
    "musician": {"outfit": "tshirt", "top": (40, 40, 48), "hair_style": "long", "hold": "mic"},
    "influencer": {"outfit": "hoodie", "hold": "phone", "hair_style": "side"},
    "mermaid": {
        "body": "mermaid",
        "outfit": "dress",
        "hair_style": "long",
        "hair": HAIRS["red"],
        "top": (60, 190, 170),
    },
    "saci": {
        "age": "child",
        "skin": SKINS["dark"],
        "head": "party",
        "head_color": (210, 40, 40),
        "outfit": "tunic",
        "top": (210, 40, 40),
        "hair_style": "bald",
    },
    "curupira": {
        "age": "child",
        "hair_style": "spiky",
        "hair": (240, 100, 40),
        "outfit": "tunic",
        "top": (90, 150, 70),
    },
}

ANIMALS: dict[str, dict] = {
    # tipo: corpo, barriga, orelha, focinho, cauda, padrão, altura (unidades), extras
    "cat": dict(
        c=(243, 156, 70), b=(255, 225, 190), ear="pointy", snout="small", tail="thin", whisk=True, h=46
    ),
    "dog": dict(c=(196, 140, 90), b=(250, 230, 200), ear="floppy", snout="muzzle", tail="thin", h=52),
    "fox": dict(c=(230, 110, 40), b=(255, 245, 235), ear="pointy", snout="small", tail="bushy", h=48),
    "lion": dict(
        c=(232, 170, 70),
        b=(250, 220, 160),
        ear="round",
        snout="muzzle",
        tail="tuft",
        mane=(180, 100, 40),
        h=64,
    ),
    "tiger": dict(
        c=(240, 140, 40),
        b=(255, 240, 225),
        ear="round",
        snout="muzzle",
        tail="thin",
        stripes=True,
        whisk=True,
        h=62,
    ),
    "bear": dict(c=(140, 96, 64), b=(200, 160, 120), ear="round", snout="muzzle", tail="puff", h=70),
    "panda": dict(
        c=(250, 250, 250), b=(250, 250, 250), ear="round", snout="muzzle", tail="puff", panda=True, h=66
    ),
    "rabbit": dict(
        c=(236, 236, 240), b=(255, 255, 255), ear="long", snout="small", tail="puff", whisk=True, h=46
    ),
    "mouse": dict(
        c=(170, 170, 180), b=(230, 220, 225), ear="big_round", snout="small", tail="thin", whisk=True, h=34
    ),
    "sheep": dict(
        c=(250, 250, 248), b=(250, 250, 248), ear="side", snout="dark_face", tail="puff", fluffy=True, h=52
    ),
    "cow": dict(
        c=(250, 250, 250),
        b=(250, 250, 250),
        ear="side",
        snout="pink_muzzle",
        tail="tuft",
        spots=True,
        horns=True,
        h=72,
    ),
    "pig": dict(c=(250, 175, 190), b=(255, 200, 210), ear="pointy", snout="pig", tail="curly", h=48),
    "horse": dict(
        c=(150, 96, 60), b=(190, 140, 100), ear="pointy", snout="long", tail="tuft", mane=(70, 44, 30), h=86
    ),
    "unicorn": dict(
        c=(250, 250, 255),
        b=(255, 255, 255),
        ear="pointy",
        snout="long",
        tail="tuft",
        mane=(240, 140, 200),
        horn=True,
        h=86,
    ),
    "donkey": dict(c=(150, 140, 140), b=(210, 200, 200), ear="long", snout="long", tail="tuft", h=70),
    "camel": dict(
        c=(214, 170, 110), b=(230, 200, 150), ear="round", snout="long", tail="tuft", hump=True, h=90
    ),
    "elephant": dict(c=(160, 170, 186), b=(180, 190, 204), ear="elephant", snout="trunk", tail="thin", h=96),
    "monkey": dict(c=(150, 100, 64), b=(240, 200, 160), ear="side_round", snout="monkey", tail="curl", h=50),
    "capybara": dict(c=(170, 120, 80), b=(190, 140, 100), ear="tiny", snout="muzzle", tail="none", h=48),
    "frog": dict(c=(110, 190, 80), b=(200, 240, 150), ear="frog", snout="frog", tail="none", h=34),
    "dinosaur": dict(
        c=(110, 180, 90), b=(200, 230, 150), ear="none", snout="muzzle", tail="long", spikes=True, h=80
    ),
    "dragon": dict(
        c=(200, 60, 60),
        b=(250, 200, 120),
        ear="horns",
        snout="muzzle",
        tail="long",
        spikes=True,
        wings=True,
        h=84,
    ),
    "wolf": dict(c=(130, 136, 150), b=(220, 222, 230), ear="pointy", snout="muzzle", tail="bushy", h=58),
    "deer": dict(
        c=(180, 120, 70), b=(240, 210, 170), ear="side", snout="long", tail="puff", antlers=True, h=78
    ),
    "goat": dict(
        c=(236, 232, 226),
        b=(250, 250, 250),
        ear="side",
        snout="long",
        tail="puff",
        horns=True,
        beard=True,
        h=58,
    ),
    "squirrel": dict(c=(200, 110, 50), b=(250, 220, 180), ear="pointy", snout="small", tail="bushy", h=36),
    "koala": dict(c=(160, 160, 170), b=(220, 220, 225), ear="big_round", snout="koala", tail="none", h=48),
}
BIRDS: dict[str, dict] = {
    "bird": dict(c=(80, 160, 230), b=(250, 230, 160), beak=(250, 170, 40), h=30),
    "dove": dict(c=(250, 250, 252), b=(240, 240, 245), beak=(250, 170, 60), h=30),
    "chicken": dict(c=(250, 250, 248), b=(250, 250, 248), beak=(250, 170, 40), comb=True, h=40),
    "chick": dict(c=(255, 220, 70), b=(255, 235, 140), beak=(250, 150, 40), h=24),
    "duck": dict(c=(250, 250, 250), b=(250, 250, 250), beak=(250, 160, 40), flat=True, h=36),
    "owl": dict(c=(150, 110, 70), b=(230, 200, 150), beak=(240, 180, 60), owl=True, h=40),
    "parrot": dict(c=(220, 50, 50), b=(250, 210, 60), beak=(60, 60, 60), h=40),
    "penguin": dict(c=(40, 40, 52), b=(250, 250, 250), beak=(250, 160, 40), penguin=True, h=44),
    "eagle": dict(c=(110, 70, 40), b=(250, 250, 250), beak=(250, 200, 50), eagle=True, h=44),
    "flamingo": dict(c=(250, 140, 170), b=(250, 170, 190), beak=(40, 40, 40), h=60),
    "toucan": dict(c=(40, 40, 48), b=(250, 240, 220), beak=(250, 140, 40), big_beak=True, h=40),
    "crow": dict(c=(40, 40, 52), b=(60, 60, 72), beak=(60, 60, 60), h=32),
    "bat": dict(c=(70, 60, 80), b=(110, 100, 120), beak=(0, 0, 0), bat=True, h=30),
}
OTHER_CRITTERS = {
    "fish": dict(c=(255, 150, 50), b=(255, 210, 120), h=26),
    "goldfish": dict(c=(255, 160, 40), b=(255, 220, 120), h=24),
    "shark": dict(c=(120, 140, 170), b=(240, 240, 245), h=40, shark=True),
    "whale": dict(c=(70, 110, 180), b=(200, 220, 240), h=56, whale=True),
    "dolphin": dict(c=(120, 160, 210), b=(230, 240, 250), h=40, dolphin=True),
    "turtle": dict(c=(110, 170, 90), b=(160, 120, 70), h=36),
    "snake": dict(c=(110, 180, 70), b=(230, 220, 120), h=30),
    "butterfly": dict(c=(240, 120, 180), b=(80, 60, 80), h=26),
    "bee": dict(c=(250, 200, 40), b=(40, 40, 40), h=22),
    "ladybug": dict(c=(220, 40, 40), b=(30, 30, 30), h=18),
    "octopus": dict(c=(230, 100, 140), b=(250, 170, 190), h=40),
    "crab": dict(c=(230, 80, 60), b=(250, 140, 110), h=26),
    "spider": dict(c=(50, 46, 56), b=(90, 80, 100), h=24),
}
CRITTERS = set(ANIMALS) | set(BIRDS) | set(OTHER_CRITTERS)
CHARACTER_TYPES = tuple(PRESETS)


def is_character(kind: str) -> bool:
    return kind in PRESETS or kind in CRITTERS


def make_look(kind: str, seed: str = "", color=None, skin=None, hair=None, extra: dict | None = None) -> Look:
    """Monta a aparência: modelo pronto + sorteio estável (pelo id) + cores pedidas."""
    preset = dict(PRESETS.get(kind, {}))
    h = int(hashlib.md5(f"{kind}:{seed}".encode()).hexdigest(), 16)
    lk = Look(kind=kind)
    lk.skin = SKIN_LIST[h % len(SKIN_LIST)]
    lk.hair = HAIR_LIST[(h >> 4) % len(HAIR_LIST)]
    lk.top = PALETTE[(h >> 8) % len(PALETTE)]
    lk.bottom = [(52, 73, 94), (44, 62, 110), (90, 70, 56), (60, 60, 70)][(h >> 12) % 4]
    lk.accent = PALETTE[(h >> 16) % len(PALETTE)]
    if kind in ("person", "man", "boy"):
        lk.hair_style = ["short", "side", "curly", "short", "spiky", "afro"][(h >> 20) % 6]
    elif kind in ("woman", "girl"):
        lk.hair_style = ["long", "ponytail", "bun", "wavy", "long", "curly"][(h >> 20) % 6]
    if kind in ("man", "person") and (h >> 24) % 5 == 0:
        lk.beard = "short"
    for k, v in preset.items():
        setattr(lk, k, v)
    if skin is not None:
        lk.skin = SKINS.get(str(skin), None) or rgb(skin, lk.skin)
    if hair is not None:
        lk.hair = HAIRS.get(str(hair), None) or rgb(hair, lk.hair)
    if color is not None:
        c = rgb(color, lk.top)
        if lk.outfit in ("armor",):
            lk.accent = c
        else:
            lk.top = c
    for k, v in (extra or {}).items():
        if hasattr(lk, k):
            setattr(lk, k, v)
    return lk


# ------------------------------------------------------------------ geometria do boneco
@dataclass
class Body:
    """Medidas (unidades) do boneco conforme a idade."""

    head_r: float = 21.0
    neck_y: float = -58.0  # pivô da cabeça
    waist_y: float = -33.0  # pivô do tronco
    hip_y: float = -30.0  # pivô das pernas
    shoulder: tuple = (13.5, -55.0)
    sh_w: float = 15.0
    waist_w: float = 12.5
    leg_len: float = 27.0
    upper: float = 12.0
    fore: float = 10.5
    hand_r: float = 4.2
    height: float = 100.0


def body_for(age: str) -> Body:
    if age == "child":
        return Body(head_r=20.0, neck_y=-45, waist_y=-25, hip_y=-22, shoulder=(11.5, -42), sh_w=12.5, waist_w=11,
                    leg_len=19, upper=9.5, fore=8.5, hand_r=3.8, height=84)  # fmt: skip
    if age == "baby":
        return Body(head_r=19.0, neck_y=-30, waist_y=-16, hip_y=-13, shoulder=(10, -28), sh_w=11, waist_w=11.5,
                    leg_len=11, upper=7, fore=6, hand_r=3.6, height=68)  # fmt: skip
    return Body()


# ------------------------------------------------------------------ desenho: cabeça
EXPRESSIONS = ("neutral", "blink", "talk", "happy", "surprised", "sad", "angry", "scared", "sleep", "love")


def _eyes(p: Pen, lk: Look, expr: str, t: float, cy: float) -> None:
    ex = 7.4
    dx = t * 3.2
    for s in (-1, 1):
        x = s * ex + dx
        y = cy + 1.0
        if lk.body == "robot":
            p.rect(x - 3.4, y - 2.6, x + 3.4, y + 2.6, lk.accent, r=1.2)
            continue
        if expr in ("blink", "sleep"):
            p.arc(x, y - 0.6, 3.0, 1.8, 20, 160, 1.15, EYE)
        elif expr in ("happy", "love"):
            p.arc(x, y + 1.4, 3.0, 2.6, 200, 340, 1.25, EYE)
        elif expr in ("surprised", "scared"):
            p.ellipse(x, y, 4.0, 4.6, WHITE, outline=EYE, width=0.6)
            pr = 1.6 if expr == "scared" else 2.3
            p.circle(x + t * 0.8, y + 0.3, pr, EYE)
            p.circle(x + t * 0.8 + 0.7, y - 0.6, 0.6, WHITE)
        else:
            big = 3.6 if lk.body == "alien" else 2.8
            p.ellipse(x, y, big, big * 1.25, EYE)
            p.circle(x + 0.9, y - 1.3, big * 0.36, WHITE)
            p.circle(x - 0.8, y + 1.2, big * 0.15, (255, 255, 255, 170))
        if expr == "sad":
            p.line([(x - 3.2 * s * -1, y - 6.4), (x + 3.0 * s * -1, y - 5.0)], 1.1, EYE)
        elif expr == "angry":
            p.line([(x - 3.4 * s, y - 6.6), (x + 2.6 * s, y - 4.4)], 1.4, EYE)
    if lk.age == "old" or lk.beard == "full":
        if expr not in ("sad", "angry"):
            for s in (-1, 1):
                x = s * ex + dx
                p.arc(x, cy - 4.0, 3.4, 1.6, 200, 340, 1.4, shade(lk.hair, 0.8))


def _mouth(p: Pen, lk: Look, expr: str, t: float, cy: float, on_beard: bool) -> None:
    x = t * 3.4
    y = cy + 8.2
    line_col = (250, 236, 230) if on_beard else MOUTH
    if lk.body == "robot":
        p.rect(x - 5, y - 1, x + 5, y + 1.6, shade(lk.accent, 0.8), r=0.8)
        return
    if expr in ("talk",):
        p.chord(x, y - 0.6, 3.8, 3.4, 0, 180, MOUTH)
        p.ellipse(x, y + 1.6, 2.2, 1.0, TONGUE)
    elif expr in ("happy", "love"):
        p.chord(x, y - 1.0, 4.6, 4.2, 0, 180, MOUTH)
        p.rect(x - 3.6, y - 1.1, x + 3.6, y + 0.1, WHITE)
        p.ellipse(x, y + 2.2, 2.4, 1.1, TONGUE)
    elif expr in ("surprised", "sleep"):
        r = 1.5 if expr == "sleep" else 2.4
        p.ellipse(x, y + 0.6, r, r * 1.25, MOUTH)
    elif expr == "scared":
        pts = [(x - 4 + i * 1.0, y + (0.8 if i % 2 else -0.6)) for i in range(9)]
        p.line(pts, 1.1, line_col)
    elif expr == "sad":
        p.arc(x, y + 2.2, 3.4, 2.2, 200, 340, 1.2, line_col)
    elif expr == "angry":
        p.line([(x - 3.2, y + 0.6), (x + 3.2, y + 0.6)], 1.3, line_col)
    else:
        p.arc(x, y - 1.6, 3.6, 2.8, 25, 155, 1.2, line_col)


def _hair_front(p: Pen, lk: Look, cy: float, r: float, t: float) -> None:
    hs = lk.hair_style
    hc = lk.hair
    if (
        hs == "bald"
        or lk.head in ("astronaut", "hood", "pharaoh", "headcloth")
        or lk.body in ("robot", "ghost")
    ):
        if hs == "bald" and lk.body == "human" and lk.head in ("",):
            p.soft(lambda q: q.ellipse(-7, cy - r * 0.62, 5, 2.4, (255, 255, 255, 70)))
        return
    if hs == "veil":
        vc = lk.head_color
        p.poly(
            bez((-r - 3, cy + 10), (-r - 4, cy - r - 8), (r + 4, cy - r - 8), (r + 3, cy + 10), 20)
            + bez((r - 2, cy + 6), (r - 3, cy - r + 2), (-r + 3, cy - r + 2), (-r + 2, cy + 6), 20),
            vc,
        )
        p.poly(bez((-r + 3, cy - r * 0.55), (0, cy - r * 0.95), (r - 3, cy - r * 0.55), n=12)
               + [(r - 6, cy - r * 0.42), (-r + 6, cy - r * 0.42)], hc)  # fmt: skip
        return
    if hs in ("curly", "afro"):
        k = 1.25 if hs == "afro" else 1.0
        rr = 7.2 * k
        for i in range(9):
            a = math.radians(180 + i * 22.5)
            p.circle(math.cos(a) * (r - 2) * 1.02, cy - 2 + math.sin(a) * (r - 1) * (1.05 if hs == "afro" else 0.98),
                     rr, hc)  # fmt: skip
        for i in range(5):
            p.circle(-r * 0.55 + i * r * 0.275, cy - r * 0.62, 5.8 * k, hc)
        return
    # base: calota de cabelo sobre a testa
    top = bez((-r - 1.6, cy + 2), (-r - 2, cy - r * 1.42), (r + 2, cy - r * 1.42), (r + 1.6, cy + 2), 24)
    if hs == "side":
        fringe = bez(
            (r + 1, cy - 2), (r * 0.4, cy - r * 0.2), (-r * 0.3, cy - r * 0.95), (-r - 1, cy - 1), 18
        )
    elif hs == "spiky":
        fringe = [(r + 1, cy - 1)]
        for i in range(7):
            xx = r - (i + 0.5) * (2 * r / 7)
            fringe += [(xx + 1.5, cy - r * 0.5), (xx, cy - r * (0.82 if i % 2 else 0.62))]
        fringe += [(-r - 1, cy - 1)]
        top = [(-r - 1.5, cy + 1)] + [
            (math.cos(math.radians(180 + i * 15)) * (r + (5 if i % 2 else 1)),
             cy - 3 + math.sin(math.radians(180 + i * 15)) * (r + (6 if i % 2 else 2)))
            for i in range(13)
        ] + [(r + 1.5, cy + 1)]  # fmt: skip
    else:
        fringe = [(r + 1, cy - 1)]
        n = 4
        for i in range(n):
            x0 = r - i * (2 * r / n)
            x1 = r - (i + 1) * (2 * r / n)
            fringe += bez((x0, cy - r * 0.52), ((x0 + x1) / 2, cy - r * 0.2), (x1, cy - r * 0.55), n=6)[1:]
        fringe += [(-r - 1, cy - 1)]
    p.poly(top + fringe, hc)
    if hs in ("long", "wavy", "ponytail", "bun") or lk.kind in ("woman", "girl", "queen", "princess"):
        for s in (-1, 1):
            p.poly(bez((s * (r + 1.5), cy - 4), (s * (r + 3.5), cy + 8), (s * (r - 1.5), cy + 15), n=10)
                   + [(s * (r - 4), cy + 6), (s * (r - 3), cy - 6)], hc)  # fmt: skip
    if hs == "bun":
        p.circle(0, cy - r - 4.5, 6.8, hc)
    p.soft(lambda q: q.arc(-6, cy - r * 0.7, 6, 2.6, 200, 300, 1.4, (255, 255, 255, 60)))


def arc_top(cy: float, r: float) -> list[tuple[float, float]]:
    """Arco por cima da cabeça (da direita para a esquerda), para fechar formas sem bico."""
    return [
        (math.cos(math.radians(a)) * r, cy - 2 + math.sin(math.radians(a)) * r) for a in range(-5, -176, -10)
    ]


def _hair_back(p: Pen, lk: Look, cy: float, r: float) -> bool:
    hs = lk.hair_style
    if lk.body in ("robot", "ghost") or lk.head in ("astronaut",):
        return False
    if hs in ("long", "wavy"):
        hc = shade(lk.hair, 0.88)
        pts = bez((-r - 2, cy - 6), (-r - 8, cy + 26), (-r + 2, cy + 36), n=14) + bez(
            (r - 2, cy + 36), (r + 8, cy + 26), (r + 2, cy - 6), n=14
        )
        p.poly(pts + arc_top(cy, r + 2.5), hc)
        if hs == "wavy":
            for s in (-1, 1):
                for i in range(3):
                    p.circle(s * (r + 1.5 - i * 1.2), cy + 12 + i * 9, 4.2, hc)
        return True
    if hs == "ponytail":
        p.poly(bez((r * 0.4, cy - r * 0.9), (r + 14, cy - 6), (r + 8, cy + 22), n=14)
               + bez((r + 3, cy + 20), (r + 6, cy), (r * 0.2, cy - r * 0.6), n=10), shade(lk.hair, 0.9))  # fmt: skip
        p.circle(r * 0.55, cy - r * 0.78, 3.2, lk.accent)
        return True
    if hs == "veil":
        vc = shade(lk.head_color, 0.9)
        p.poly(bez((-r - 3, cy - 4), (-r - 10, cy + 30), (-r - 4, cy + 46), n=14) + bez(
            (r + 4, cy + 46), (r + 10, cy + 30), (r + 3, cy - 4), n=14) + arc_top(cy, r + 3.5), vc)  # fmt: skip
        return True
    if lk.head == "headcloth":
        vc = shade(lk.head_color, 0.9)
        p.poly(bez((-r - 3, cy - 4), (-r - 7, cy + 18), (-r - 2, cy + 30), n=10) + bez(
            (r + 2, cy + 30), (r + 7, cy + 18), (r + 3, cy - 4), n=10) + arc_top(cy, r + 3.5), vc)  # fmt: skip
        return True
    if lk.head == "pharaoh":
        p.poly([(-r - 4, cy - 6), (-r - 7, cy + 26), (r + 7, cy + 26), (r + 4, cy - 6)], GOLD)
        for i in range(5):
            y = cy + i * 6
            p.line([(-r - 6, y), (r + 6, y)], 1.6, (40, 70, 160))
        return True
    return False


def _beard(p: Pen, lk: Look, cy: float, r: float, t: float) -> bool:
    b = lk.beard
    if not b or lk.body != "human":
        return False
    bc = lk.hair
    x = t * 2.2
    if b == "full":
        pts = bez((-r + 0.8, cy + 3), (-r - 1, cy + 22), (x - 6, cy + r + 13), (x, cy + r + 14), 16) + bez(
            (x, cy + r + 14), (x + 6, cy + r + 13), (r + 1, cy + 22), (r - 0.8, cy + 3), 16
        )
        pts += bez((r - 3.5, cy + 7), (x + 5, cy + 6), (x - 5, cy + 6), (-r + 3.5, cy + 7), 10)
        p.poly(pts, bc)
    elif b == "short":
        pts = bez((-r + 1, cy + 4), (-r + 1, cy + 16), (x - 5, cy + r + 2), (x, cy + r + 2.5), 12) + bez(
            (x, cy + r + 2.5), (x + 5, cy + r + 2), (r - 1, cy + 16), (r - 1, cy + 4), 12
        )
        pts += bez((r - 3.5, cy + 6), (x + 5, cy + 13), (x - 5, cy + 13), (-r + 3.5, cy + 6), 10)
        p.poly(pts, bc)
    elif b == "goatee":
        p.ellipse(x, cy + r - 2, 4.6, 4.2, bc)
    if b in ("full", "short", "mustache"):
        for s in (-1, 1):
            p.poly(bez((x, cy + 5.2), (x + s * 4, cy + 3.4), (x + s * 7.5, cy + 7.6), n=8)
                   + bez((x + s * 7.5, cy + 7.6), (x + s * 3, cy + 8.0), (x, cy + 6.8), n=8), shade(bc, 0.92))  # fmt: skip
    return b == "full"


def _headwear(p: Pen, lk: Look, cy: float, r: float) -> None:
    h = lk.head
    c = lk.head_color
    top = cy - r
    if not h:
        return
    if h in ("crown", "tiara"):
        k = 0.65 if h == "tiara" else 1.0
        w = r * 0.95 * (0.85 if h == "tiara" else 1.0)
        base = top + 6.5
        pts = [(-w, base)]
        n = 5
        for i in range(n):
            x0 = -w + i * 2 * w / n
            pts += [(x0 + w / n * 0.5, base - 12 * k), (x0 + w / n, base - 4.5 * k)]
        pts[-1] = (w, base - 4.5 * k)
        pts += [(w, base)]
        p.poly(pts, GOLD)
        p.rect(-w, base - 4.5 * k, w, base + 1.2, shade(GOLD, 0.9), r=1)
        for i in range(n):
            p.circle(-w + (i + 0.5) * 2 * w / n, base - 12 * k, 1.6 * k, shade(GOLD, 1.2))
        p.circle(0, base - 1.6, 2.0, (214, 48, 49))
        p.circle(-w * 0.55, base - 1.6, 1.4, (52, 120, 219))
        p.circle(w * 0.55, base - 1.6, 1.4, (46, 174, 96))
    elif h == "halo":
        lift = 12 if lk.hair_style in ("curly", "afro") else 6
        p.ellipse(0, top - lift, 12, 3.4, None, outline=GOLD, width=2.4)
    elif h in ("helmet", "roman"):
        col = (178, 182, 194) if h == "helmet" else (205, 170, 70)
        p.chord(0, cy - 2, r + 2.5, r + 3, 180, 360, col)
        p.rect(-r - 2.5, cy - 4, r + 2.5, cy - 1, shade(col, 0.85), r=1)
        if h == "roman":
            p.poly(
                bez((-3, top - 2), (-2, top - 14), (14, top - 16), (16, top - 4), 14) + [(3, top - 1)],
                (200, 40, 50),
            )
            for s in (-1, 1):
                p.rect(s * (r + 1.5) - 3, cy - 3, s * (r + 1.5) + 3, cy + 10, col, r=2)
        else:
            p.rect(-1.6, cy - 4, 1.6, cy + 6, shade(col, 0.8), r=0.8)
            if lk.kind == "viking":
                for s in (-1, 1):
                    p.poly(bez((s * r * 0.8, cy - r * 0.6), (s * (r + 9), cy - r * 0.9), (s * (r + 6), cy - r - 10),
                               n=10) + [(s * r * 0.55, cy - r * 0.8)], (250, 245, 230))  # fmt: skip
    elif h in ("cap", "police", "beanie", "hardhat"):
        col = c
        p.chord(0, cy - 3, r + 1.6, r + 1.5, 180, 360, col)
        if h == "police":
            p.rect(-r - 1.6, cy - 6.5, r + 1.6, cy - 2, shade(col, 0.7), r=1)
            p.star(0, cy - 12, 3.4, 1.5, GOLD)
            p.ellipse(4, cy - 2, r * 0.75, 2.4, shade(col, 0.55))
        elif h == "hardhat":
            p.rect(-r - 4, cy - 4.5, r + 4, cy - 1.5, shade(col, 0.9), r=1.5)
            p.rect(-1.5, top - 1, 1.5, cy - 4, shade(col, 1.1), r=1)
        elif h == "beanie":
            p.rect(-r - 1.6, cy - 6, r + 1.6, cy - 1, shade(col, 0.85), r=2)
            p.circle(0, top - 3, 3.4, shade(col, 1.15))
        else:
            p.ellipse(r * 0.55, cy - 2.4, r * 0.9, 2.6, shade(col, 0.8))
    elif h in ("hat", "cowboy", "straw", "witch", "wizard", "party", "chef", "grad"):
        if h == "chef":
            p.rect(-r * 0.75, top - 6, r * 0.75, top + 6, WHITE, r=2)
            for i in range(3):
                p.circle(-r * 0.5 + i * r * 0.5, top - 9, 7, WHITE)
            p.line([(-r * 0.7, top + 2.5), (r * 0.7, top + 2.5)], 0.8, (220, 220, 225))
        elif h == "grad":
            p.poly([(0, top - 9), (r + 6, top - 4), (0, top + 1), (-r - 6, top - 4)], (40, 40, 48))
            p.rect(-r * 0.6, top - 3, r * 0.6, top + 5, (40, 40, 48), r=2)
            p.line([(r + 4, top - 4), (r + 5, top + 8)], 1.2, GOLD)
        elif h in ("witch", "wizard", "party"):
            hh = 30 if h != "party" else 22
            col = c if h != "party" else c
            if h != "party":
                p.ellipse(0, top + 4, r + 9, 4.2, col)
            p.poly([(-r * 0.75, top + 4), (5, top - hh), (r * 0.75, top + 4)], col)
            if h == "wizard":
                p.star(2, top - hh * 0.45, 3.6, 1.6, GOLD)
                p.star(-6, top - 2, 2.2, 1.0, GOLD)
            elif h == "witch":
                p.rect(-r * 0.7, top - 1, r * 0.7, top + 3, (150, 80, 200))
            else:
                for i in range(3):
                    p.circle(-4 + i * 4, top - 6 - i * 6, 1.8, (250, 250, 250))
                p.circle(5, top - hh - 1, 3, (250, 220, 60))
        else:
            col = {"straw": (236, 200, 120), "cowboy": (150, 96, 56)}.get(h, c)
            brim = r + (12 if h in ("straw", "cowboy") else 7)
            if h == "cowboy":
                p.poly(bez((-brim, top + 2), (-brim + 2, top + 8), (brim - 2, top + 8), (brim, top + 2), 14)
                       + [(brim - 4, top + 5), (-brim + 4, top + 5)], col)  # fmt: skip
            else:
                p.ellipse(0, top + 4.5, brim, 4.4, col)
            p.rect(-r * 0.72, top - 10, r * 0.72, top + 5, col, r=4)
            p.rect(
                -r * 0.72, top + 0.5, r * 0.72, top + 4, shade(col, 0.7) if h != "straw" else (200, 60, 60)
            )
    elif h == "turban":
        col = c
        p.ellipse(0, top + 2, r + 3, 10, col)
        p.line(bez((-r, top + 6), (0, top - 6), (r, top + 2)), 2.0, shade(col, 0.85))
        p.circle(0, top - 1, 2.6, (214, 48, 49))
    elif h == "headband":
        p.rect(-r - 0.5, cy - r * 0.62, r + 0.5, cy - r * 0.38, c, r=1.4)
        p.poly(
            [(r - 1, cy - r * 0.55), (r + 8, cy - r * 0.35), (r + 7, cy - r * 0.1), (r - 1, cy - r * 0.4)], c
        )
    elif h == "hood":
        p.poly(bez((-r - 4, cy + 14), (-r - 5, cy - r - 8), (r + 5, cy - r - 8), (r + 4, cy + 14), 20)
               + bez((r - 3, cy + 10), (r - 4, cy - r + 4), (-r + 4, cy - r + 4), (-r + 3, cy + 10), 20), c)  # fmt: skip
    elif h == "headcloth":
        col = c
        p.poly(bez((-r - 3, cy + 4), (-r - 3, cy - r - 7), (r + 3, cy - r - 7), (r + 3, cy + 4), 18)
               + bez((r - 2, cy - 2), (r - 3, cy - r + 3), (-r + 3, cy - r + 3), (-r + 2, cy - 2), 18), col)  # fmt: skip
        p.rect(-r - 2, cy - r * 0.62, r + 2, cy - r * 0.42, shade(lk.accent, 0.9), r=1)
    elif h == "pharaoh":
        p.poly(bez((-r - 3, cy + 2), (-r - 3, cy - r - 6), (r + 3, cy - r - 6), (r + 3, cy + 2), 18)
               + bez((r - 2, cy - 3), (r - 3, cy - r + 3), (-r + 3, cy - r + 3), (-r + 2, cy - 3), 18), GOLD)  # fmt: skip
        for i in range(4):
            y = cy - r + 2 + i * 5
            p.line([(-r - 2, y), (-r + 4, y + 1)], 1.6, (40, 70, 160))
            p.line([(r + 2, y), (r - 4, y + 1)], 1.6, (40, 70, 160))
        p.circle(0, top + 1.5, 2.4, (40, 70, 160))


def _face_extras(p: Pen, lk: Look, cy: float, r: float, t: float, expr: str) -> None:
    ex = set(lk.extras)
    dx = t * 3.2
    if "sunglasses" in ex:
        for s in (-1, 1):
            p.rect(s * 7.4 + dx - 4.6, cy - 2.2, s * 7.4 + dx + 4.6, cy + 3.8, (24, 24, 30), r=2.4)
        p.line([(-3 + dx, cy - 0.8), (3 + dx, cy - 0.8)], 1.1, (24, 24, 30))
        p.soft(lambda q: q.line([(-10 + dx, cy - 0.6), (-7 + dx, cy - 1.6)], 0.9, (255, 255, 255, 120)))
    elif "glasses" in ex:
        for s in (-1, 1):
            p.circle(s * 7.4 + dx, cy + 1, 4.6, None, outline=(60, 50, 60), width=1.0)
        p.line([(-2.8 + dx, cy + 0.5), (2.8 + dx, cy + 0.5)], 0.9, (60, 50, 60))
    if "eyepatch" in ex:
        p.ellipse(-7.4 + dx, cy + 1, 4.0, 3.8, (20, 20, 24))
        p.line([(-r, cy - 7), (r * 0.8, cy - 4)], 1.0, (20, 20, 24))
    if "mask" in ex:
        p.poly([(-r + 3, cy - 2), (-2 + dx, cy - 3.5), (2 + dx, cy - 3.5), (r - 3, cy - 2), (r - 4, cy + 4),
                (2 + dx, cy + 3), (-2 + dx, cy + 3), (-r + 4, cy + 4)], lk.accent)  # fmt: skip
        for s in (-1, 1):
            p.ellipse(s * 7.4 + dx, cy + 0.6, 2.4, 2.0, WHITE)
    if "freckles" in ex:
        for s in (-1, 1):
            for i in range(3):
                p.circle(s * (11 + i * 1.6) + dx, cy + 5 + (i % 2) * 1.2, 0.5, shade(lk.skin, 0.7))
    if expr == "sad":
        p.soft(lambda q: q.poly(bez((8 + dx, cy + 5), (6.4 + dx, cy + 9), (8 + dx, cy + 10.5), (9.6 + dx, cy + 9), 8),
                                (90, 170, 240, 220)))  # fmt: skip
    if expr == "scared":
        p.soft(lambda q: q.poly(bez((r - 2, cy - 10), (r - 4, cy - 5), (r - 2, cy - 3.6), (r, cy - 5), 8),
                                (140, 200, 250, 220)))  # fmt: skip


def draw_head(lk: Look, bd: Body, expr: str, t: float, k: float, paper: float, seed: int) -> Sprite:
    """Cabeça completa (rosto, cabelo da frente, barba, chapéu). Pivô no pescoço."""
    r = bd.head_r
    cy = -r + 1.5  # centro da cabeça relativo ao pivô do pescoço
    box = (-r - 16, cy - r - 36, r + 16, cy + r + 20)
    p = Pen(box, k)
    skin = lk.skin
    if lk.body == "ghost":
        _ghost_head(p, lk, cy, r, expr, t)
    elif lk.body == "robot":
        p.rect(-2.4, cy + r - 4, 2.4, cy + r + 4, shade(lk.top, 0.8))
        p.rect(-r + 1, cy - r + 3, r - 1, cy + r - 2, lk.top, r=6)
        p.rect(-r + 4, cy - r + 7, r - 4, cy + r - 6, (40, 50, 64), r=4)
        p.line([(0, cy - r + 3), (0, cy - r - 7)], 1.4, shade(lk.top, 0.8))
        p.circle(0, cy - r - 8, 2.6, lk.accent)
        for s in (-1, 1):
            p.rect(s * (r + 0.5) - 2, cy - 4, s * (r + 0.5) + 2, cy + 4, shade(lk.top, 0.8), r=1)
        _eyes(p, lk, expr, t, cy)
        _mouth(p, lk, expr, t, cy, False)
    else:
        if lk.body == "alien":
            for s in (-1, 1):
                p.line([(s * 6, cy - r + 2), (s * 11, cy - r - 9)], 1.3, shade(skin, 0.8))
                p.circle(s * 11, cy - r - 9, 2.4, (250, 220, 70))
        else:
            for s in (-1, 1):  # orelhas
                p.circle(s * (r - 0.6) + t * 1.4, cy + 1.5, 4.4, skin)
                p.circle(s * (r - 0.6) + t * 1.4, cy + 1.5, 2.2, shade(skin, 0.86))
        p.ellipse(0, cy, r + 0.6, r, skin)
        p.soft(lambda q: q.ellipse(0, cy + r * 0.55, r * 0.8, r * 0.38, (*shade(skin, 0.86), 90)))
        on_beard = _beard(p, lk, cy, r, t)
        p.soft(lambda q: [q.ellipse(s * 12.5 + t * 2.5, cy + 6, 3.4, 2.1, (*BLUSH, 95 if expr != "love" else 170))
                          for s in (-1, 1)])  # fmt: skip
        if lk.body != "alien":
            p.ellipse(t * 4.2, cy + 4.2, 1.6, 1.2, shade(skin, 0.84))
        _eyes(p, lk, expr, t, cy)
        _mouth(p, lk, expr, t, cy, on_beard)
        _hair_front(p, lk, cy, r, t)
        _face_extras(p, lk, cy, r, t, expr)
        _headwear(p, lk, cy, r)
        if lk.head == "astronaut":
            p.soft(lambda q: q.circle(0, cy, r + 6, (200, 230, 255, 70)))
            p.circle(0, cy, r + 6, None, outline=(235, 238, 245), width=2.4)
            p.soft(lambda q: q.arc(-6, cy - 8, 9, 7, 200, 260, 2.0, (255, 255, 255, 160)))
    return pen_sprite(p, (0, 0), shadow=0.22 * (paper > 0), paper=paper, seed=seed, shadow_scale=k / 4.4)


def _ghost_head(p: Pen, lk: Look, cy: float, r: float, expr: str, t: float) -> None:
    col = lk.top
    p.ellipse(0, cy + 2, r + 3, r + 2, col)
    dx = t * 3
    for s in (-1, 1):
        if expr in ("blink", "sleep"):
            p.arc(s * 7 + dx, cy, 3.2, 2, 20, 160, 1.3, EYE)
        else:
            p.ellipse(s * 7 + dx, cy, 3.4, 4.6, EYE)
    if expr in ("talk", "surprised", "scared", "happy"):
        p.ellipse(dx, cy + 9, 3.6, 4.6, EYE)
    else:
        p.arc(dx, cy + 6, 3.6, 2.6, 25, 155, 1.2, EYE)
    p.soft(lambda q: [q.ellipse(s * 12 + dx, cy + 6, 3.2, 2, (*BLUSH, 80)) for s in (-1, 1)])


def draw_hair_back(lk: Look, bd: Body, k: float, paper: float, seed: int) -> Sprite | None:
    r = bd.head_r
    cy = -r + 1.5
    p = Pen((-r - 16, cy - r - 12, r + 16, cy + r + 30), k)
    if not _hair_back(p, lk, cy, r):
        return None
    return pen_sprite(p, (0, 0), shadow=0.18 * (paper > 0), paper=paper, seed=seed, shadow_scale=k / 4.4)


# ------------------------------------------------------------------ desenho: corpo
def _torso_shape(sh: float, wa: float, top: float, bot: float) -> list[tuple[float, float]]:
    return (
        [(-wa, bot)]
        + bez((-sh, top + 9), (-sh, top + 1.5), (-sh + 6, top), n=8)
        + bez((sh - 6, top), (sh, top + 1.5), (sh, top + 9), n=8)
        + [(wa, bot)]
    )


def draw_torso(lk: Look, bd: Body, k: float, paper: float, seed: int) -> Sprite:
    """Tronco (do quadril aos ombros). Pivô na cintura."""
    sh, wa = bd.sh_w, bd.waist_w
    top = bd.shoulder[1] - bd.waist_y - 4  # topo dos ombros relativo ao pivô
    bot = 4.0
    p = Pen((-sh - 6, top - 8, sh + 6, bot + 6), k)
    c = lk.top
    o = lk.outfit
    skin = lk.skin
    if lk.body == "ghost":
        return pen_sprite(p, (0, 0))
    p.rect(-3.6, top - 4, 3.6, top + 3, skin if lk.body != "robot" else shade(c, 0.7), r=1.5)  # pescoço
    shape = _torso_shape(sh, wa, top, bot)
    if o == "robot":
        p.rect(-sh, top, sh, bot, c, r=4)
        p.rect(-sh * 0.55, top + 5, sh * 0.55, top + 14, (40, 50, 64), r=2)
        for i, col in enumerate(((231, 76, 60), (241, 196, 15), (46, 174, 96))):
            p.circle(-5 + i * 5, top + 9.5, 1.6, col)
        return pen_sprite(p, (0, 0), shadow=0.22 * (paper > 0), paper=paper, seed=seed, shadow_scale=k / 4.4)
    if "cape" in lk.extras:
        p.poly(
            [(-sh + 1, top + 1), (sh - 1, top + 1), (sh + 2, top + 8), (-sh - 2, top + 8)],
            shade(lk.cape, 0.85),
        )
    if o in ("suit",):
        p.poly(shape, c)
        p.poly([(-5.5, top), (0, top + 16), (5.5, top)], (250, 250, 250))
        p.poly([(-1.6, top + 2), (1.6, top + 2), (2.2, top + 13), (0, top + 16), (-2.2, top + 13)], lk.accent)
        for s in (-1, 1):
            p.poly([(s * 5.5, top), (s * 9, top + 2), (s * 2.5, top + 15)], shade(c, 0.82))
        p.circle(0, top + 20, 0.9, shade(c, 0.6))
    elif o == "coat":
        p.poly(shape, (250, 250, 250))
        p.poly(
            [(-4.5, top), (0, top + 9), (4.5, top), (4.5, bot), (-4.5, bot)],
            lk.top if lk.top != WHITE else (90, 150, 210),
        )
        for s in (-1, 1):
            p.poly([(s * 4.5, top), (s * 8.5, top + 3), (s * 4.5, top + 12)], (230, 230, 236))
        p.rect(-sh + 3, top + 13, -sh + 8.5, top + 18, (230, 230, 236), r=1)
    elif o in ("royal",):
        p.poly(shape, c)
        p.poly([(-sh, top + 4), (-sh + 3, top - 0.5), (sh - 3, top - 0.5), (sh, top + 4), (sh - 4, top + 9),
                (-sh + 4, top + 9)], lk.accent)  # fmt: skip
        p.rect(-wa, bot - 6, wa, bot - 2.5, GOLD, r=1)
        p.line([(0, top + 9), (0, bot - 6)], 1.8, shade(GOLD, 0.95))
    elif o in ("robe",):
        p.poly(shape, c)
        p.poly([(-sh + 2, top + 1), (-sh + 7, top), (wa + 1, bot - 3), (wa - 3, bot)], lk.accent)  # faixa
        p.poly([(-4, top), (0, top + 5), (4, top)], shade(c, 0.8))
        p.rect(-wa, bot - 4.5, wa, bot - 1.5, shade(c, 0.72), r=1)
    elif o == "toga":
        p.poly(shape, c)
        p.poly([(-sh, top + 2), (-sh + 6, top), (wa, bot - 1), (wa - 7, bot)], lk.accent)
    elif o == "armor":
        p.poly(shape, lk.accent if lk.kind != "soldier" else (205, 170, 70))
        mc = lk.accent if lk.kind != "soldier" else (205, 170, 70)
        for i in range(3):
            y = top + 7 + i * 5.5
            p.line([(-wa + 1.5, y), (wa - 1.5, y)], 0.9, shade(mc, 0.75))
        for s in (-1, 1):
            p.ellipse(s * (sh - 2), top + 3, 5.4, 4.2, shade(mc, 1.08))
        p.rect(-wa, bot - 4, wa, bot - 0.5, (120, 80, 50), r=1)
        p.rect(-2, bot - 4.2, 2, bot - 0.3, GOLD, r=0.6)
        if lk.kind == "knight":
            p.poly([(-3, top + 7), (3, top + 7), (3, top + 15), (0, top + 17), (-3, top + 15)], c)
    elif o == "space":
        p.poly(shape, c)
        p.rect(-6, top + 6, 6, top + 15, shade(c, 0.85), r=2)
        for i, col in enumerate(((231, 76, 60), lk.accent, (46, 174, 96))):
            p.circle(-3.2 + i * 3.2, top + 10.5, 1.2, col)
        p.rect(-wa, bot - 4, wa, bot - 1, shade(c, 0.8), r=1)
    elif o == "hoodie":
        p.poly(shape, c)
        p.chord(0, top + 1, 8, 5, 0, 180, shade(c, 0.85))
        p.rect(-7, bot - 9, 7, bot - 2.5, shade(c, 0.9), r=2)
        for s in (-1, 1):
            p.line([(s * 2.4, top + 3), (s * 2.6, top + 10)], 0.8, (250, 250, 250))
    elif o == "overalls":
        p.poly(shape, c)
        p.rect(-wa + 2, top + 9, wa - 2, bot, (60, 100, 170), r=1.5)
        for s in (-1, 1):
            p.line([(s * (wa - 3), top + 10), (s * (sh - 4), top + 0.5)], 2.2, (60, 100, 170))
            p.circle(s * (wa - 3.5), top + 10.5, 1.1, GOLD)
    elif o == "apron":
        p.poly(shape, c)
        p.rect(-wa + 2.5, top + 6, wa - 2.5, bot, (250, 250, 250), r=2)
        p.line([(-wa + 2.5, top + 6), (-sh + 5, top + 0.5)], 1.0, (230, 230, 236))
        p.line([(wa - 2.5, top + 6), (sh - 5, top + 0.5)], 1.0, (230, 230, 236))
    elif o == "vest":
        p.poly(shape, (250, 250, 248) if lk.kind == "worker" else shade(c, 1.15))
        for s in (-1, 1):
            p.poly([(s * 3, top), (s * sh, top + 3), (s * wa, bot), (s * 3, bot)], c)
        if lk.kind == "worker":
            p.rect(-wa, top + 13, wa, top + 15.5, (240, 240, 120))
    elif o == "sweater":
        p.poly(shape, c)
        p.chord(0, top, 6, 4.6, 0, 180, shade(c, 0.8))
        for i in range(3):
            p.line([(-wa + 1, bot - 3 - i * 1.4), (wa - 1, bot - 3 - i * 1.4)], 0.5, shade(c, 0.85))
    elif o == "uniform":
        p.poly(shape, c)
        p.poly([(-4, top), (0, top + 5), (4, top)], shade(c, 0.75))
        p.rect(-sh + 3.5, top + 7, -sh + 8.5, top + 11, shade(c, 0.85), r=1)
        p.rect(sh - 8.5, top + 7, sh - 3.5, top + 11, shade(c, 0.85), r=1)
        p.rect(-wa, bot - 3.8, wa, bot - 1, (40, 40, 48), r=1)
        if "badge" in lk.extras:
            p.star(-sh + 6, top + 6.5, 2.6, 1.2, GOLD)
    elif o == "tunic":
        p.poly(shape, c)
        p.rect(-wa, bot - 4, wa, bot - 1, (130, 86, 50), r=1)
        p.poly([(-4, top), (0, top + 4), (4, top)], shade(c, 0.8))
    elif o == "dress":
        p.poly(_torso_shape(sh - 1, wa - 1.5, top, bot), c)
        p.chord(0, top, 5.5, 4, 0, 180, shade(c, 0.85))
        p.rect(-wa + 1.5, bot - 3.5, wa - 1.5, bot - 1, shade(c, 0.8), r=1)
    else:  # shirt, tshirt
        p.poly(shape, c)
        if o == "tshirt":
            p.chord(0, top, 5.5, 4.5, 0, 180, shade(skin, 0.95))
        else:
            p.poly(
                [(-4.5, top), (0, top + 5.5), (4.5, top), (3, top - 0.5), (0, top + 3), (-3, top - 0.5)],
                shade(c, 1.2),
            )
            for i in range(3):
                p.circle(0, top + 9 + i * 5, 0.8, shade(c, 0.7))
    if "tie" in lk.extras and o not in ("suit",):
        p.poly([(-1.4, top + 1), (1.4, top + 1), (2, top + 12), (0, top + 14), (-2, top + 12)], lk.accent)
    if "stethoscope" in lk.extras:
        p.line(bez((-5, top), (-7, top + 14), (5, top + 14), (5, top)), 0.9, (60, 60, 70))
        p.circle(2, top + 13, 1.6, (170, 170, 180))
    p.soft(lambda q: q.poly([(wa - 4, bot), (sh - 1.5, top + 8), (sh, top + 10), (wa, bot)], (0, 0, 0, 28)))
    return pen_sprite(p, (0, 0), shadow=0.22 * (paper > 0), paper=paper, seed=seed, shadow_scale=k / 4.4)


def lower_kind(lk: Look) -> str:
    if lk.body == "ghost":
        return "ghost"
    if lk.body == "mermaid":
        return "tail"
    o = lk.outfit
    if o in ("robe", "royal", "coat") and lk.kind not in ("scientist", "doctor", "detective"):
        return "long"
    if o in ("dress",):
        return "long" if lk.kind in ("queen", "princess", "witch", "old_woman") else "dress"
    if o in ("tunic", "toga"):
        return "tunic"
    return "pants"


def draw_hips(lk: Look, bd: Body, k: float, paper: float, seed: int) -> Sprite:
    """Parte de baixo (cintura até a barra da roupa). Pivô no quadril."""
    lw = lower_kind(lk)
    wa = bd.waist_w
    foot = -bd.hip_y  # distância do quadril até o chão
    p = Pen((-wa - 14, -8, wa + 14, foot + 4), k)
    c = lk.top
    if lw == "ghost":
        col = lk.top
        pts = [(-wa - 4, -bd.sh_w - 30)] + bez(
            (-wa - 6, -10), (-wa - 9, foot * 0.6), (-wa - 8, foot - 4), n=10
        )
        for i in range(5):
            x0 = -wa - 8 + i * (2 * wa + 16) / 5
            x1 = -wa - 8 + (i + 1) * (2 * wa + 16) / 5
            pts += bez((x0, foot - 4), ((x0 + x1) / 2, foot + (3 if i % 2 else -1)), (x1, foot - 4), n=6)[1:]
        pts += bez((wa + 8, foot - 4), (wa + 9, foot * 0.6), (wa + 6, -10), n=10)[1:] + [
            (wa + 4, -bd.sh_w - 30)
        ]
        p2 = Pen((-wa - 14, -bd.sh_w - 34, wa + 14, foot + 6), k)
        p2.poly(pts, col)
        p2.soft(
            lambda q: q.poly(
                [(wa, -10), (wa + 7, foot * 0.6), (wa + 4, foot - 3), (wa - 3, foot - 2)], (0, 0, 0, 22)
            )
        )
        for s in (-1, 1):
            p2.ellipse(s * (wa + 7), -bd.sh_w - 8, 4, 6, col)
        return pen_sprite(p2, (0, 0), shadow=0.18 * (paper > 0), paper=paper, seed=seed, shadow_scale=k / 4.4)
    if lw == "tail":
        p.poly(bez((-wa, -4), (-wa - 3, foot * 0.6), (-2, foot - 5), n=10) + bez((2, foot - 5), (wa + 3, foot * 0.6), (wa, -4), n=10),
               (60, 180, 160))  # fmt: skip
        p.poly(
            [(-2, foot - 6), (-12, foot + 2), (0, foot - 1), (12, foot + 2), (2, foot - 6)], (40, 150, 140)
        )
        for i in range(4):
            p.arc(0, i * 5 + 2, wa - 2, 3, 20, 160, 0.8, (40, 150, 140))
        return pen_sprite(p, (0, 0), shadow=0.18 * (paper > 0), paper=paper, seed=seed, shadow_scale=k / 4.4)
    if lw == "long":
        hem = foot - 4
        col = c if lk.outfit != "coat" else (250, 250, 250)
        pts = [(-wa, -4)] + bez((-wa - 2, hem * 0.5), (-wa - 6, hem - 2), (-wa - 6.5, hem), n=8)
        pts += bez((wa + 6.5, hem), (wa + 6, hem - 2), (wa + 2, hem * 0.5), n=8) + [(wa, -4)]
        p.poly(pts, col)
        trim = GOLD if lk.outfit == "royal" else shade(col, 0.82)
        p.poly([(-wa - 6.5, hem - 3), (wa + 6.5, hem - 3), (wa + 6.5, hem), (-wa - 6.5, hem)], trim)
        if lk.outfit == "royal":
            p.rect(-2, -4, 2, hem - 3, shade(GOLD, 0.95))
        p.soft(
            lambda q: q.poly(
                [(wa - 3, -4), (wa + 5, hem - 3), (wa + 1, hem - 3), (wa - 6, -4)], (0, 0, 0, 26)
            )
        )
    elif lw == "dress":
        hem = foot * 0.55
        pts = [(-wa + 1.5, -4)] + bez((-wa - 3, hem * 0.5), (-wa - 8, hem), (-wa - 8, hem + 1), n=8)
        pts += bez((wa + 8, hem + 1), (wa + 8, hem), (wa + 3, hem * 0.5), n=8) + [(wa - 1.5, -4)]
        p.poly(pts, c)
        p.line(bez((-wa - 7.5, hem - 1), (0, hem + 2), (wa + 7.5, hem - 1)), 1.4, shade(c, 0.82))
    elif lw == "tunic":
        hem = foot * 0.32
        pts = [(-wa, -4), (-wa - 2.5, hem), (wa + 2.5, hem), (wa, -4)]
        p.poly(pts, c)
        if lk.outfit == "toga":
            p.poly([(-wa, -4), (wa, hem), (wa - 6, hem), (-wa + 2, -4)], lk.accent)
        for i in range(5):
            x = -wa + 1 + i * (2 * wa - 2) / 4
            p.line([(x, hem * 0.5), (x, hem)], 0.6, shade(c, 0.8))
    else:
        p.poly([(-wa, -4), (wa, -4), (wa + 0.4, 4.5), (-wa - 0.4, 4.5)], lk.bottom)
        p.line([(0, -1), (0, 4.5)], 0.6, shade(lk.bottom, 0.8))
    return pen_sprite(p, (0, 0), shadow=0.2 * (paper > 0), paper=paper, seed=seed, shadow_scale=k / 4.4)


def draw_leg(lk: Look, bd: Body, side: int, k: float, paper: float, seed: int) -> Sprite | None:
    """Perna (pivô no quadril). Com roupa longa só aparece o pé."""
    lw = lower_kind(lk)
    if lw in ("ghost", "tail"):
        return None
    L = bd.leg_len
    foot = -bd.hip_y
    p = Pen((-8, -2, 8, foot + 3), k)
    out = side * 1.2
    if lw == "long":
        p.rect(-3.4, foot - 7, 3.4, foot - 2, shade(lk.skin, 0.95), r=1.6)
    elif lw in ("dress", "tunic"):
        p.capsule(0, 2, 0, foot - 3, 3.4, lk.skin)
    else:
        p.capsule(0, 0, 0, L - 2, 4.1, lk.bottom)
        p.capsule(0, L - 4, 0, foot - 3, 3.6, shade(lk.bottom, 0.95))
    shoe = lk.shoes
    if lk.outfit in ("robe", "tunic", "toga") or lk.kind in (
        "jesus",
        "prophet",
        "shepherd",
        "disciple",
        "mary",
    ):
        p.rect(-4.6 + out, foot - 3.6, 4.6 + out, foot, (150, 100, 60), r=1.8)
        p.line([(-3.6 + out, foot - 3.2), (3.6 + out, foot - 3.2)], 0.9, (110, 70, 40))
    elif lk.outfit == "space":
        p.rect(-5.6 + out, foot - 5.5, 5.6 + out, foot, (230, 230, 236), r=2.4)
    else:
        p.rect(-5.4 + out, foot - 5.2, 5.6 + out, foot, shoe, r=2.6)
        p.soft(lambda q: q.rect(-4.2 + out, foot - 4.6, 1 + out, foot - 3.6, (255, 255, 255, 60), r=0.6))
    return pen_sprite(p, (0, 0), shadow=0.18 * (paper > 0), paper=paper, seed=seed, shadow_scale=k / 4.4)


def _sleeve(lk: Look) -> str:
    if lk.outfit in ("tshirt", "dress", "tunic", "toga") or lk.body == "ghost":
        return "short"
    if lk.outfit in ("robe", "royal", "wizard"):
        return "wide"
    return "long"


def arm_color(lk: Look) -> tuple:
    if lk.outfit == "coat":
        return (250, 250, 250)
    if lk.outfit == "armor":
        return lk.accent if lk.kind != "soldier" else (205, 170, 70)
    if lk.body == "robot":
        return shade(lk.top, 0.9)
    return lk.top


def draw_upper_arm(lk: Look, bd: Body, k: float, paper: float, seed: int) -> Sprite:
    L = bd.upper
    p = Pen((-7, -6, 7, L + 5), k)
    sl = _sleeve(lk)
    col = arm_color(lk)
    if lk.body == "ghost":
        return pen_sprite(p, (0, 0))
    if sl == "short":
        p.capsule(0, 0, 0, L, 3.3, lk.skin)
        p.capsule(0, 0, 0, 3.5, 4.2, col)
    elif sl == "wide":
        p.capsule(0, 0, 0, L, 4.4, col)
    else:
        p.capsule(0, 0, 0, L, 3.9, col)
    return pen_sprite(p, (0, 0), shadow=0.2 * (paper > 0), paper=paper, seed=seed, shadow_scale=k / 4.4)


def draw_forearm(lk: Look, bd: Body, k: float, paper: float, seed: int) -> Sprite:
    L = bd.fore
    hr = bd.hand_r
    p = Pen((-9, -5, 9, L + hr + 6), k)
    sl = _sleeve(lk)
    col = arm_color(lk)
    skin = lk.skin if lk.body != "robot" else (150, 160, 176)
    if lk.body == "ghost":
        p.ellipse(0, 2, 5, 6, lk.top)
        return pen_sprite(p, (0, 0), shadow=0.18 * (paper > 0), paper=paper, seed=seed, shadow_scale=k / 4.4)
    if sl == "short":
        p.capsule(0, 0, 0, L, 3.2, skin)
    elif sl == "wide":
        p.capsule(0, 0, 0, L - 3, 3.0, skin)
        p.poly([(-4.2, -1), (4.2, -1), (6.4, L - 1), (-6.4, L - 1)], col)
        p.line([(-6.4, L - 1.2), (6.4, L - 1.2)], 1.3, shade(col, 0.8))
    else:
        p.capsule(0, 0, 0, L - 1, 3.5, col)
        p.line([(-3.6, L - 1.6), (3.6, L - 1.6)], 1.4, shade(col, 0.8))
    p.circle(0, L + hr * 0.55, hr, skin)
    p.ellipse(-hr * 0.85, L + hr * 0.2, hr * 0.42, hr * 0.62, skin)
    return pen_sprite(p, (0, 0), shadow=0.2 * (paper > 0), paper=paper, seed=seed, shadow_scale=k / 4.4)


HOLD_ITEMS = ("staff", "scepter", "book", "bible", "phone", "sword", "mic", "candle", "torch", "flag", "sign",
              "briefcase", "flower", "scroll", "cup", "magnifier", "lantern", "star", "balloon", "money", "bag")  # fmt: skip


def draw_held(item: str, bd: Body, k: float, paper: float, seed: int, color=None) -> Sprite | None:
    """Objeto na mão (coordenadas da mão: origem no centro da mão)."""
    if item not in HOLD_ITEMS:
        return None
    p = Pen((-22, -60, 22, 70), k)
    c = rgb(color, (200, 60, 60)) if color is not None else None
    if item == "staff":
        p.line(bez((0, 30), (1, -6), (-1, -44), n=8), 2.4, (150, 100, 60))
        p.line(bez((-1, -44), (-2, -56), (9, -58), (9, -48), 12), 2.4, (150, 100, 60))
    elif item == "scepter":
        p.line([(0, 16), (0, -22)], 2.0, GOLD)
        p.circle(0, -25, 4.2, (214, 48, 49))
        p.circle(0, -25, 4.2, None, outline=GOLD, width=1.2)
    elif item in ("book", "bible"):
        col = c or ((120, 60, 40) if item == "bible" else (52, 120, 219))
        p.rect(-8, -6, 8, 8, col, r=1.2)
        p.rect(-7, -5, 7, -3.6, (250, 245, 230))
        if item == "bible":
            p.line([(0, -2), (0, 6)], 1.2, GOLD)
            p.line([(-2.6, 0.4), (2.6, 0.4)], 1.2, GOLD)
    elif item == "phone":
        p.rect(-4.4, -12, 4.4, 4, (34, 34, 42), r=1.6)
        p.rect(-3.4, -10.6, 3.4, 2.4, (90, 170, 240), r=0.8)
    elif item == "sword":
        p.poly([(-1.6, -6), (1.6, -6), (1.6, -40), (0, -44), (-1.6, -40)], (220, 225, 235))
        p.rect(-6, -7, 6, -4.6, GOLD, r=1)
        p.rect(-1.4, -4.6, 1.4, 4, (120, 80, 50), r=0.6)
    elif item == "mic":
        p.rect(-1.4, -6, 1.4, 6, (40, 40, 48), r=0.8)
        p.circle(0, -9, 3.6, (90, 90, 100))
    elif item in ("candle", "torch"):
        if item == "torch":
            p.poly([(-2, -2), (2, -2), (1.2, 12), (-1.2, 12)], (130, 86, 50))
            base = -2
        else:
            p.rect(-2.4, -10, 2.4, 2, (250, 245, 225), r=0.8)
            base = -10
        p.poly(bez((0, base - 11), (5, base - 4), (0, base), (-5, base - 4), 10), (255, 170, 40))
        p.poly(bez((0, base - 7), (2.6, base - 3), (0, base), (-2.6, base - 3), 10), (255, 236, 120))
    elif item == "flag":
        p.line([(0, 14), (0, -34)], 1.4, (120, 80, 50))
        p.poly([(0, -34), (16, -30), (0, -24)], c or (231, 76, 60))
    elif item == "sign":
        p.line([(0, 14), (0, -14)], 1.6, (130, 86, 50))
        p.rect(-14, -32, 14, -14, (250, 245, 230), r=1.4)
        p.rect(-14, -32, 14, -14, None, r=1.4, outline=(130, 86, 50), width=1)
    elif item in ("briefcase", "bag"):
        p.rect(-8, 2, 8, 14, c or (110, 70, 40), r=1.6)
        p.arc(0, 2, 3.6, 3, 180, 360, 1.2, shade(c or (110, 70, 40), 0.7))
    elif item == "flower":
        p.line([(0, 6), (0, -14)], 1.0, (70, 150, 70))
        for i in range(5):
            a = math.radians(i * 72)
            p.circle(math.cos(a) * 3, -16 + math.sin(a) * 3, 2.4, c or (240, 100, 150))
        p.circle(0, -16, 1.8, (250, 210, 60))
    elif item == "scroll":
        p.rect(-7, -10, 7, 6, (246, 232, 196), r=1)
        p.rect(-8.5, -12, 8.5, -9, (220, 196, 150), r=1.5)
        p.rect(-8.5, 5, 8.5, 8, (220, 196, 150), r=1.5)
    elif item == "cup":
        p.poly([(-4, -8), (4, -8), (3, 2), (-3, 2)], c or (250, 250, 250))
        p.arc(4.2, -4, 2.4, 2.6, 270, 450, 1.0, c or (220, 220, 225))
    elif item == "magnifier":
        p.line([(0, 6), (0, -6)], 1.8, (120, 80, 50))
        p.circle(0, -12, 6, None, outline=(80, 80, 90), width=1.6)
        p.soft(lambda q: q.circle(0, -12, 5.2, (200, 230, 255, 110)))
    elif item == "lantern":
        p.rect(-4, -12, 4, 0, (60, 60, 70), r=1)
        p.rect(-3, -10.5, 3, -1.5, (255, 220, 110), r=0.6)
        p.arc(0, -12, 3, 3, 180, 360, 1.0, (60, 60, 70))
    elif item == "star":
        p.star(0, -10, 7, 3.2, (250, 210, 60))
    elif item == "balloon":
        p.line(bez((0, 4), (3, -14), (-2, -30)), 0.6, (90, 90, 90))
        p.ellipse(-2, -40, 7, 8.4, c or (231, 76, 60))
    elif item == "money":
        p.rect(-9, -5, 9, 5, (110, 190, 100), r=1)
        p.circle(0, 0, 2.6, (80, 150, 80))
    return pen_sprite(p, (0, 0), shadow=0.18 * (paper > 0), paper=paper, seed=seed, shadow_scale=k / 4.4)


def draw_wings(lk: Look, bd: Body, k: float, paper: float, seed: int) -> Sprite:
    p = Pen((-40, -40, 40, 30), k)
    col = (250, 250, 252) if lk.body != "robot" else (200, 210, 230)
    for s in (-1, 1):
        pts = bez((s * 4, -2), (s * 30, -38), (s * 38, -10), n=12) + bez(
            (s * 38, -10), (s * 30, 6), (s * 6, 10), n=10
        )
        p.poly(pts, col)
        for i in range(3):
            p.arc(
                s * (16 + i * 6),
                -4 + i * 3,
                6,
                3,
                20 if s > 0 else 160,
                160 if s > 0 else 20,
                0.7,
                (220, 220, 230),
            )
    return pen_sprite(p, (0, 0), shadow=0.16 * (paper > 0), paper=paper, seed=seed, shadow_scale=k / 4.4)


def draw_cape(lk: Look, bd: Body, k: float, paper: float, seed: int) -> Sprite:
    sh = bd.sh_w
    L = -bd.neck_y - 4
    p = Pen((-sh - 12, -6, sh + 12, L + 4), k)
    pts = [(-sh + 2, 0), (sh - 2, 0)] + bez((sh + 2, 4), (sh + 8, L * 0.6), (sh + 9, L), n=10)
    pts += bez((sh + 9, L), (0, L + 3), (-sh - 9, L), n=10) + bez(
        (-sh - 9, L), (-sh - 8, L * 0.6), (-sh - 2, 4), n=10
    )
    p.poly(pts, shade(lk.cape, 0.9))
    return pen_sprite(p, (0, 0), shadow=0.14 * (paper > 0), paper=paper, seed=seed, shadow_scale=k / 4.4)


# ------------------------------------------------------------------ animais
def critter_spec(kind: str) -> tuple[str, dict]:
    if kind in ANIMALS:
        return "quad", ANIMALS[kind]
    if kind in BIRDS:
        return "bird", BIRDS[kind]
    return kind, OTHER_CRITTERS.get(kind, OTHER_CRITTERS["fish"])


def draw_critter_body(kind: str, k: float, paper: float, seed: int, color=None) -> Sprite:
    """Corpo do animal com as patas (pivô no chão, centro)."""
    fam, sp = critter_spec(kind)
    c = rgb(color, sp["c"]) if color is not None else sp["c"]
    b = sp["b"]
    dark = shade(c, 0.78)
    if fam == "quad":
        p = Pen((-46, -70, 46, 6), k)
        if sp.get("wings"):
            for s in (-1, 1):
                p.poly([(s * 8, -40), (s * 44, -66), (s * 40, -40), (s * 30, -30)], shade(c, 0.85))
        for s in (-1, 1):
            p.capsule(s * 17, -18, s * 18, -2, 5.2, dark)
        if sp.get("fluffy"):
            for i in range(10):
                a = math.radians(i * 36)
                p.circle(math.cos(a) * 20, -30 + math.sin(a) * 14, 9, c)
            p.ellipse(0, -30, 22, 16, c)
        else:
            p.ellipse(0, -30, 26, 19, c)
        if sp.get("hump"):
            p.ellipse(0, -46, 13, 9, c)
        p.ellipse(0, -24, 15, 11, b)
        if sp.get("spots"):
            for x, y, r in ((-14, -36, 6), (10, -40, 5), (16, -24, 4.5), (-6, -20, 3.5)):
                p.ellipse(x, y, r, r * 0.8, (50, 46, 50))
        if sp.get("stripes"):
            for x in (-16, -8, 8, 16):
                p.line([(x, -46), (x * 0.8, -36)], 2.0, (50, 40, 40))
        if sp.get("panda"):
            for s in (-1, 1):
                p.ellipse(s * 15, -38, 9, 9, (40, 40, 48))
        if sp.get("spikes"):
            for i in range(5):
                x = -14 + i * 7
                p.poly([(x - 3, -46), (x, -54), (x + 3, -46)], shade(c, 0.7))
        for s in (-1, 1):
            p.capsule(s * 9, -16, s * 9, -2, 5.0, c)
            p.ellipse(s * 9, -1.5, 5.6, 3, shade(c, 0.7))
    elif fam == "bird":
        p = Pen((-30, -46, 30, 4), k)
        for s in (-1, 1):
            p.line([(s * 4, -8), (s * 5, -1)], 1.4, sp["beak"] if not sp.get("penguin") else (250, 160, 40))
            p.line([(s * 5, -1), (s * 8, 0)], 1.4, sp["beak"])
        if sp.get("penguin"):
            p.ellipse(0, -22, 15, 20, c)
            p.ellipse(0, -18, 10.5, 15, b)
        else:
            p.ellipse(0, -18, 14, 13, c)
            p.ellipse(0, -15, 9, 9, b)
            if sp.get("bat"):
                for s in (-1, 1):
                    p.poly([(s * 8, -20), (s * 28, -30), (s * 24, -18), (s * 28, -10), (s * 10, -12)], c)
        if kind == "flamingo":
            p.line([(-2, -8), (-2, 0)], 1.2, c)
    elif fam == "turtle":
        p = Pen((-34, -40, 34, 4), k)
        for s in (-1, 1):
            p.ellipse(s * 16, -3, 6, 4, shade(c, 0.9))
        p.chord(0, -6, 26, 24, 180, 360, b)
        for x, y in ((-12, -14), (0, -20), (12, -14), (-6, -8), (6, -8)):
            p.circle(x, y, 5, shade(b, 1.12))
        p.rect(-26, -8, 26, -4, shade(b, 0.8), r=2)
    elif fam in ("fish", "goldfish", "shark", "whale", "dolphin"):
        p = Pen((-40, -30, 40, 10), k)
        L = 34 if fam in ("whale",) else 28
        p.poly([(L * 0.55, -10), (L * 1.05, -22), (L * 0.95, -10), (L * 1.05, 2)], shade(c, 0.85))
        p.ellipse(0, -10, L * 0.7, 12 if fam != "whale" else 15, c)
        p.ellipse(-2, -6, L * 0.5, 5, b)
        if fam in ("shark", "dolphin"):
            p.poly([(-4, -20), (6, -32), (8, -20)], shade(c, 0.85))
    elif fam == "snake":
        p = Pen((-40, -30, 40, 6), k)
        pts = [(x, -6 + math.sin(x / 7) * 5) for x in range(-30, 24, 3)]
        p.line(pts, 7, c)
        p.line(pts, 2.5, b)
    elif fam in ("butterfly", "bee", "ladybug", "spider", "crab", "octopus"):
        p = Pen((-30, -40, 30, 6), k)
        if fam == "octopus":
            for i in range(6):
                x = -12 + i * 4.8
                p.line(bez((x, -10), (x * 1.4, -2), (x * 1.6, 2)), 3.4, c)
            p.ellipse(0, -18, 13, 14, c)
        elif fam == "crab":
            for s in (-1, 1):
                p.line([(s * 8, -6), (s * 16, 0)], 1.6, c)
                p.circle(s * 18, -16, 4.6, c)
            p.ellipse(0, -10, 13, 8, c)
        elif fam == "spider":
            for s in (-1, 1):
                for i in range(4):
                    p.line([(s * 4, -10 + i * 2), (s * 14, -18 + i * 6), (s * 20, -4 + i * 2)], 1.0, c)
            p.circle(0, -10, 7, c)
        elif fam == "ladybug":
            p.chord(0, -4, 12, 10, 180, 360, c)
            p.line([(0, -14), (0, -4)], 0.8, (30, 30, 30))
            for x, y in ((-5, -8), (5, -8), (-6, -4), (6, -4)):
                p.circle(x, y, 1.5, (30, 30, 30))
        else:
            p.ellipse(0, -12, 3.2, 9, b)
            if fam == "bee":
                p.ellipse(0, -12, 7, 8, c)
                for y in (-14, -10):
                    p.line([(-6.5, y), (6.5, y)], 1.6, (40, 40, 40))
    else:
        p = Pen((-20, -20, 20, 4), k)
        p.circle(0, -10, 10, c)
    return pen_sprite(p, (0, 0), shadow=0.2 * (paper > 0), paper=paper, seed=seed, shadow_scale=k / 4.4)


def draw_critter_head(
    kind: str, expr: str, t: float, k: float, paper: float, seed: int, color=None
) -> Sprite:
    """Cabeça do animal (pivô no pescoço). Peixes, cobras etc. têm o rosto no próprio corpo."""
    fam, sp = critter_spec(kind)
    c = rgb(color, sp["c"]) if color is not None else sp["c"]
    b = sp["b"]
    p = Pen((-36, -60, 36, 20), k)
    dx = t * 2.6
    if fam == "quad":
        r = 16 if kind not in ("elephant", "horse", "camel", "unicorn", "donkey", "deer") else 15
        cy = -14
        ear = sp["ear"]
        if sp.get("mane") and kind == "lion":
            for i in range(14):
                a = math.radians(i * 360 / 14)
                p.circle(math.cos(a) * (r + 3), cy + math.sin(a) * (r + 3), 6.5, sp["mane"])
        elif sp.get("mane"):
            for i in range(5):
                a = math.radians(205 + i * 22)
                p.circle(math.cos(a) * (r - 1), cy + math.sin(a) * (r - 1), 5.5, sp["mane"])
        if ear == "pointy":
            for s in (-1, 1):
                p.poly([(s * 6, cy - r + 3), (s * 14, cy - r - 10), (s * 16, cy - r + 6)], c)
                p.poly(
                    [(s * 8.5, cy - r + 2), (s * 13.5, cy - r - 5), (s * 14.5, cy - r + 4)], (250, 170, 180)
                )
        elif ear in ("round", "big_round", "side_round", "tiny"):
            rr = {"round": 5.5, "big_round": 9, "side_round": 6, "tiny": 3}[ear]
            for s in (-1, 1):
                ex, ey = (s * (r - 2), cy - r + 3) if ear != "side_round" else (s * (r + 2), cy)
                p.circle(ex, ey, rr, c)
                p.circle(ex, ey, rr * 0.55, (250, 180, 190) if ear != "tiny" else c)
        elif ear == "floppy":
            for s in (-1, 1):
                p.ellipse(s * (r - 1), cy + 2, 5.5, 11, shade(c, 0.75))
        elif ear == "long":
            for s in (-1, 1):
                p.ellipse(s * 6, cy - r - 10, 4.6, 13, c)
                p.ellipse(s * 6, cy - r - 9, 2.4, 10, (250, 180, 190))
        elif ear == "side":
            for s in (-1, 1):
                p.ellipse(s * (r + 3), cy - 4, 7, 3.4, shade(c, 0.9))
        elif ear == "elephant":
            for s in (-1, 1):
                p.ellipse(s * (r + 6), cy, 12, 15, shade(c, 0.92))
                p.ellipse(s * (r + 6), cy, 8, 11, (230, 180, 190))
        elif ear == "horns":
            for s in (-1, 1):
                p.poly([(s * 6, cy - r + 4), (s * 12, cy - r - 12), (s * 13, cy - r + 6)], (250, 240, 210))
        elif ear == "frog":
            for s in (-1, 1):
                p.circle(s * 8, cy - r + 2, 7, c)
        if sp.get("horns"):
            for s in (-1, 1):
                p.poly(bez((s * 5, cy - r + 3), (s * 14, cy - r - 4), (s * 12, cy - r - 10), n=8) + [(s * 9, cy - r + 4)],
                       (250, 240, 210))  # fmt: skip
        if sp.get("antlers"):
            for s in (-1, 1):
                p.line(
                    [(s * 6, cy - r + 2), (s * 12, cy - r - 14), (s * 18, cy - r - 20)], 2.0, (150, 100, 60)
                )
                p.line([(s * 10, cy - r - 9), (s * 4, cy - r - 18)], 1.8, (150, 100, 60))
        long = kind in ("horse", "unicorn", "donkey", "camel", "deer", "goat")
        if long:
            p.ellipse(0, cy, r, r, c)
            p.ellipse(dx * 0.6, cy + 10, 10, 9, shade(c, 1.12) if not sp.get("beard") else b)
        else:
            p.ellipse(0, cy, r + 1, r, c)
        if sp.get("panda"):
            for s in (-1, 1):
                p.ellipse(s * 6 + dx, cy - 1, 5, 6, (40, 40, 48))
        sn = sp["snout"]
        if sn == "dark_face":
            p.ellipse(0, cy + 1, r - 3, r - 2, (60, 56, 64))
        if sn in ("muzzle", "pink_muzzle", "monkey", "koala"):
            col = {
                "muzzle": shade(b, 1.05),
                "pink_muzzle": (250, 190, 200),
                "monkey": b,
                "koala": shade(c, 1.1),
            }[sn]
            p.ellipse(dx, cy + 6, 9 if sn != "monkey" else 11, 6.5, col)
        for s in (-1, 1):
            ex = s * 6.2 + dx
            ey = cy - 2 + (0 if not long else -2)
            if expr in ("blink", "sleep"):
                p.arc(ex, ey, 2.6, 1.6, 20, 160, 1.1, EYE)
            elif expr in ("happy", "love"):
                p.arc(ex, ey + 1.2, 2.6, 2.2, 200, 340, 1.2, EYE)
            else:
                rr = 2.8 if expr not in ("surprised", "scared") else 3.4
                p.ellipse(ex, ey, rr, rr * 1.2, EYE if sn != "dark_face" else (250, 250, 250))
                p.circle(ex + 0.8, ey - 1.1, rr * 0.35, WHITE if sn != "dark_face" else EYE)
        nose_y = cy + 4 if not long else cy + 8
        if sn == "pig":
            p.ellipse(dx, cy + 5, 6, 4.4, (240, 140, 160))
            for s in (-1, 1):
                p.ellipse(dx + s * 2, cy + 5, 1.1, 1.6, (180, 80, 100))
        elif sn == "trunk":
            p.line(bez((dx, cy + 2), (dx + 2, cy + 18), (dx + 9, cy + 22)), 6, c)
        elif sn == "frog":
            p.arc(dx, cy + 3, 8, 4, 20, 160, 1.2, (60, 110, 50))
        else:
            p.poly([(dx - 2.6, nose_y), (dx + 2.6, nose_y), (dx, nose_y + 2.6)], (60, 46, 50))
            p.arc(dx - 2, nose_y + 3, 2, 1.6, 0, 160, 0.9, (60, 46, 50))
            p.arc(dx + 2, nose_y + 3, 2, 1.6, 20, 180, 0.9, (60, 46, 50))
        if expr == "talk":
            p.ellipse(dx, nose_y + 5.2, 2.4, 2.0, MOUTH)
        if sp.get("whisk"):
            for s in (-1, 1):
                for i in range(2):
                    p.line(
                        [(dx + s * 5, nose_y + 1 + i * 2), (dx + s * 14, nose_y - 1 + i * 3.4)],
                        0.5,
                        (80, 70, 70),
                    )
        if sp.get("horn"):
            p.poly([(-2.6, cy - r + 2), (0, cy - r - 13), (2.6, cy - r + 2)], GOLD)
        if sp.get("beard"):
            p.poly([(dx - 3, cy + 15), (dx, cy + 24), (dx + 3, cy + 15)], b)
        p.soft(lambda q: [q.ellipse(s * 11 + dx, cy + 4, 3, 1.8, (*BLUSH, 90)) for s in (-1, 1)])
    elif fam == "bird":
        cy = -10
        r = 10 if not sp.get("owl") else 12
        if sp.get("penguin"):
            p.circle(0, cy, r + 1, c)
            p.ellipse(dx, cy + 2, r - 3, r - 3.5, (250, 250, 250))
        else:
            p.circle(0, cy, r, c)
        if sp.get("owl"):
            for s in (-1, 1):
                p.poly([(s * 5, cy - r + 2), (s * 10, cy - r - 6), (s * 11, cy - r + 4)], c)
                p.circle(s * 4.6 + dx, cy, 5.4, (250, 240, 210))
        if sp.get("comb"):
            for i in range(3):
                p.circle(-3 + i * 3, cy - r - 1, 2.6, (230, 50, 50))
            p.ellipse(dx + 1, cy + 8, 1.8, 2.8, (230, 50, 50))
        for s in (-1, 1):
            ex = s * 4.4 + dx
            if expr in ("blink", "sleep"):
                p.arc(ex, cy - 1, 2.2, 1.4, 20, 160, 1.0, EYE)
            else:
                p.ellipse(ex, cy - 1, 2.2, 2.6, EYE)
                p.circle(ex + 0.7, cy - 2, 0.7, WHITE)
        bk = sp["beak"]
        if sp.get("flat"):
            p.ellipse(dx, cy + 4, 5, 2.4, bk)
        elif sp.get("big_beak"):
            p.poly([(dx - 3, cy + 1), (dx + 16, cy + 4), (dx - 2, cy + 7)], bk)
        elif not sp.get("bat"):
            p.poly([(dx - 2.6, cy + 2), (dx + 2.6, cy + 2), (dx, cy + 6.4)], bk)
        else:
            for s in (-1, 1):
                p.poly([(s * 4, cy - r + 2), (s * 9, cy - r - 6), (s * 9, cy - r + 4)], c)
    elif fam == "turtle":
        cy = -8
        p.circle(0, cy, 8, sp["c"] if color is None else c)
        for s in (-1, 1):
            p.ellipse(s * 3 + dx, cy - 1, 1.6, 2.0, EYE)
        p.arc(dx, cy + 2, 2.6, 1.6, 20, 160, 0.8, MOUTH)
    elif fam in ("fish", "goldfish", "shark", "whale", "dolphin"):
        cy = -10
        p.circle(-12, cy - 3, 2.4, WHITE)
        p.circle(-12.4, cy - 3, 1.4, EYE)
        if fam == "shark":
            for i in range(4):
                p.poly([(-16 + i * 2.4, cy + 4), (-15 + i * 2.4, cy + 6.4), (-14 + i * 2.4, cy + 4)], WHITE)
        else:
            p.arc(-17, cy + 2, 2, 1.4, 300, 420, 0.8, MOUTH)
    elif fam == "snake":
        cy = -10
        p.ellipse(0, cy, 7, 5.5, c)
        for s in (-1, 1):
            p.circle(s * 2.6 + dx, cy - 1.4, 1.2, EYE)
        p.line([(dx, cy + 4), (dx, cy + 8), (dx - 1.6, cy + 10)], 0.6, (220, 40, 60))
    else:
        cy = -10
        if fam == "butterfly":
            p.circle(0, cy, 4, b)
            for s in (-1, 1):
                p.line([(s * 1.5, cy - 3), (s * 5, cy - 10)], 0.5, b)
        elif fam in ("bee", "ladybug", "spider", "crab", "octopus"):
            r = 5 if fam != "octopus" else 0
            if r:
                p.circle(0, cy + 2, r, b if fam != "crab" else c)
            for s in (-1, 1):
                p.circle(
                    s * 2 + dx, cy + 1 if fam != "octopus" else -18, 1.5 if fam != "octopus" else 2.4, WHITE
                )
                p.circle(
                    s * 2 + dx, cy + 1 if fam != "octopus" else -18, 0.8 if fam != "octopus" else 1.3, EYE
                )
    return pen_sprite(p, (0, 0), shadow=0.2 * (paper > 0), paper=paper, seed=seed, shadow_scale=k / 4.4)


def draw_critter_wing(kind: str, k: float, paper: float, seed: int, color=None) -> Sprite | None:
    fam, sp = critter_spec(kind)
    c = rgb(color, sp["c"]) if color is not None else sp["c"]
    if fam == "bird" and not sp.get("penguin") and not sp.get("bat"):
        p = Pen((-4, -10, 18, 10), k)
        p.poly(bez((0, -3), (10, -8), (16, 0), n=8) + bez((16, 0), (9, 6), (0, 3), n=8), shade(c, 0.88))
        return pen_sprite(p, (0, 0), shadow=0.15 * (paper > 0), paper=paper, seed=seed, shadow_scale=k / 4.4)
    if fam in ("butterfly", "bee"):
        p = Pen((-2, -18, 22, 14), k)
        if fam == "butterfly":
            p.ellipse(9, -6, 10, 9, c)
            p.ellipse(8, 6, 7, 6, shade(c, 0.85))
            p.circle(10, -6, 3, (250, 240, 120))
        else:
            p.soft(lambda q: q.ellipse(8, -6, 9, 6, (220, 240, 255, 170)))
        return pen_sprite(p, (0, 0), shadow=0.1 * (paper > 0), paper=paper, seed=seed, shadow_scale=k / 4.4)
    return None


def draw_critter_tail(kind: str, k: float, paper: float, seed: int, color=None) -> Sprite | None:
    fam, sp = critter_spec(kind)
    if fam != "quad":
        return None
    c = rgb(color, sp["c"]) if color is not None else sp["c"]
    tail = sp["tail"]
    if tail == "none":
        return None
    p = Pen((-6, -40, 40, 10), k)
    if tail == "thin":
        p.line(bez((0, 0), (14, 0), (18, -16), (12, -26), 14), 3.0, c)
    elif tail == "bushy":
        p.poly(
            bez((0, -2), (18, 4), (32, -14), (20, -30), 14) + bez((20, -30), (22, -14), (10, -6), (0, 4), 12),
            c,
        )
        p.poly(bez((24, -26), (29, -18), (26, -12), n=6) + [(20, -18)], (255, 245, 235))
    elif tail == "puff":
        p.circle(6, -4, 6, shade(c, 1.1))
    elif tail == "curly":
        p.line(bez((0, 0), (10, -2), (12, -10), (6, -10), 12) + bez((6, -10), (2, -6), (6, -2), n=6), 2.0, c)
    elif tail == "tuft":
        p.line(bez((0, 0), (12, 2), (20, -8)), 2.2, c)
        p.ellipse(22, -12, 4, 5, sp.get("mane") or shade(c, 0.6))
    elif tail == "long":
        p.poly([(0, -8), (36, 2), (0, 6)], c)
    elif tail == "curl":
        p.line(bez((0, 0), (20, 6), (28, -18), (16, -22), 16), 2.6, c)
    return pen_sprite(p, (0, 0), shadow=0.18 * (paper > 0), paper=paper, seed=seed, shadow_scale=k / 4.4)


def critter_height(kind: str) -> float:
    """Altura do animal em relação a um adulto (100)."""
    _fam, sp = critter_spec(kind)
    return float(sp.get("h", 40))


# altura do desenho de cada família (unidades da caneta), para converter em pixels
CRITTER_DRAW_H = {"quad": 78.0, "bird": 48.0, "penguin": 62.0, "turtle": 34.0, "fish": 32.0, "goldfish": 32.0,
                  "shark": 34.0, "whale": 36.0, "dolphin": 34.0, "snake": 24.0, "butterfly": 30.0, "bee": 26.0,
                  "ladybug": 18.0, "spider": 26.0, "crab": 28.0, "octopus": 34.0}  # fmt: skip


def critter_family(kind: str) -> str:
    if kind in ANIMALS:
        return "quad"
    if kind in BIRDS:
        return "penguin" if BIRDS[kind].get("penguin") else "bird"
    return kind


# ------------------------------------------------------------------ boneco montado
@dataclass
class Rig:
    """Sprites do personagem prontos para animar (as expressões são criadas sob demanda)."""

    look: Look
    body: Body
    k: float
    paper: float
    seed: int
    critter: str = ""
    color: tuple | None = None
    parts: dict = field(default_factory=dict)
    heads: dict = field(default_factory=dict)

    def head(self, expr: str, turn: float) -> Sprite:
        tq = 0.0 if abs(turn) < 0.25 else (0.7 if turn > 0 else -0.7)
        key = (expr, abs(tq))
        spr = self.heads.get(key)
        if spr is None:
            if self.critter:
                spr = draw_critter_head(
                    self.critter, expr, abs(tq), self.k, self.paper, self.seed, self.color
                )
            else:
                spr = draw_head(self.look, self.body, expr, abs(tq), self.k, self.paper, self.seed)
            self.heads[key] = spr
        return spr


def build_rig(look: Look, height_px: float, paper: float = 0.0, seed: int = 0, color=None) -> Rig:
    """Desenha as partes do personagem para a altura (px) pedida."""
    if look.kind in CRITTERS:
        hgt = critter_height(look.kind)
        k = height_px / CRITTER_DRAW_H.get(critter_family(look.kind), 40.0)
        rig = Rig(
            look, Body(height=hgt), k, paper, seed, critter=look.kind, color=rgb(color) if color else None
        )
        rig.parts["body"] = draw_critter_body(look.kind, k, paper, seed, color)
        rig.parts["tail"] = draw_critter_tail(look.kind, k, paper, seed, color)
        rig.parts["wing"] = draw_critter_wing(look.kind, k, paper, seed, color)
        return rig
    bd = body_for(look.age)
    k = height_px / bd.height
    rig = Rig(look, bd, k, paper, seed)
    rig.parts["hair_back"] = draw_hair_back(look, bd, k, paper, seed)
    rig.parts["torso"] = draw_torso(look, bd, k, paper, seed)
    rig.parts["hips"] = draw_hips(look, bd, k, paper, seed)
    rig.parts["leg_l"] = draw_leg(look, bd, -1, k, paper, seed)
    rig.parts["leg_r"] = draw_leg(look, bd, 1, k, paper, seed)
    rig.parts["upper"] = draw_upper_arm(look, bd, k, paper, seed)
    rig.parts["fore"] = draw_forearm(look, bd, k, paper, seed)
    rig.parts["held"] = draw_held(look.hold, bd, k, paper, seed) if look.hold else None
    rig.parts["wings"] = draw_wings(look, bd, k, paper, seed) if "wings" in look.extras else None
    rig.parts["cape"] = draw_cape(look, bd, k, paper, seed) if "cape" in look.extras else None
    return rig


def with_overrides(lk: Look, **kw) -> Look:
    return replace(lk, **{k: v for k, v in kw.items() if v is not None and hasattr(lk, k)})


def rig_preview(kinds: list[str], h: int = 360) -> np.ndarray:  # pragma: no cover - ferramenta de inspeção
    """Folha com vários personagens parados (para conferir o visual)."""
    from .draw import affine, blit, sprite_matrix

    W = 220 * len(kinds)
    img = np.full((h + 80, W, 3), 236, np.uint8)
    for i, kind in enumerate(kinds):
        rig = build_rig(make_look(kind, str(i)), h * 0.8, paper=1.0, seed=i)
        from .scene import draw_rig_static

        draw_rig_static(img, rig, 110 + i * 220, h + 40)
    _ = (affine, blit, sprite_matrix)
    return img
