"""CI temporário: vídeo 3D completo com a voz real (Kokoro) e efeitos, sem banco e sem IA."""

import shutil
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
sys.path.insert(0, "/app")

from app.openrouter import OpenRouter  # noqa: E402
from app.pipelines import Ctx, prompt3d  # noqa: E402

SCRIPT = {
    "title": "A tartaruguinha que sonhava em voar",
    "caption": "Uma fábula sobre sonhos",
    "hashtags": ["#fabula", "#3d"],
    "scenes": [
        {
            "text": "Era uma vez uma tartaruguinha sonhadora",
            "narration": "Era uma vez uma tartaruguinha que sonhava em voar.",
            "scene3d": {
                "setting": "forest",
                "camera": "dolly_in",
                "actors": [
                    {"type": "turtle", "color": "#5cb85c", "actions": ["walk", "look"]},
                    {"type": "bird", "count": 3, "actions": ["fly"], "position": "sky"},
                ],
            },
        },
        {
            "text": "Ela via os pássaros e pensava",
            "narration": "Todo dia ela via os pássaros e pensava: um dia eu chego lá!",
            "scene3d": {
                "setting": "forest",
                "camera": "low_angle",
                "actors": [
                    {"type": "turtle", "color": "#5cb85c", "actions": ["look"]},
                    {"type": "lightbulb", "actions": ["pop", "glow"], "position": "right"},
                ],
            },
        },
        {
            "text": "Então juntou blocos para subir alto",
            "narration": "Então empilhou blocos coloridos, um por um, até o céu.",
            "scene3d": {
                "setting": "park",
                "time": "sunset",
                "camera": "crane_up",
                "actors": [
                    {"type": "block", "count": 10, "actions": ["stack"], "position": "right"},
                    {"type": "turtle", "color": "#5cb85c", "actions": ["jump"]},
                ],
            },
        },
        {
            "text": "E ganhou um balão mágico!",
            "narration": "E no fim, um balão mágico levou ela bem alto!",
            "scene3d": {
                "setting": "sky",
                "time": "sunset",
                "weather": "sparkles",
                "camera": "orbit",
                "actors": [
                    {"type": "turtle", "color": "#5cb85c", "actions": ["float"]},
                    {"type": "balloon", "count": 4, "actions": ["float"], "formation": "circle"},
                ],
            },
        },
    ],
}


def fake_chat(self, models, system, user):
    assert "fala" in system.lower() or "narra" in system.lower(), "regra da narração ausente"
    return SCRIPT, 0.0, "ci/roteiro-fixo"


OpenRouter.chat_json = fake_chat


def main() -> int:
    dest = Path(sys.argv[1]).resolve()
    voice = sys.argv[2] if len(sys.argv) > 2 else "pf_dora"
    name = sys.argv[3] if len(sys.argv) > 3 else f"amostra_{voice}"
    dest.mkdir(parents=True, exist_ok=True)
    base = Path("/tmp/postop-ci") / name
    shutil.rmtree(base, ignore_errors=True)
    work, out = base / "work", base / "out"
    work.mkdir(parents=True)
    out.mkdir(parents=True)
    t0 = time.time()
    logs: list[str] = []
    params = {
        "prompt": "A tartaruguinha que sonhava em voar",
        "scenes": 4,
        "seconds_per_scene": 3.5,
        "theme": "fabula",
        "style": "pixar3d",
        "narration": True,
        "voice": voice,
        "sfx": True,
        "captions": True,
    }
    ctx = Ctx(
        job_id=11,
        params=params,
        settings={"openrouter_api_key": "sk-or-ci"},
        report=lambda p, m: print(f"{time.time() - t0:6.1f}s [{p:3d}%] {m}", flush=True),
        add_cost=lambda c: None,
        log=lambda m: (logs.append(m), print("LOG", m, flush=True)),
    )
    res = prompt3d.run(ctx, work, out)[0]
    video = dest / f"{name}.mp4"
    shutil.copy(res["file"], video)
    shutil.copy(work / "mix.wav", dest / f"{name}_mix.wav")
    print(f"total {time.time() - t0:.1f}s · duração {res['duration']:.2f}s · {video}")
    probe = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "stream=codec_type,codec_name,sample_rate,channels",
            "-of",
            "compact",
            str(video),
        ],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    print(probe)
    ok = any("Narração gerada" in m for m in logs) and "codec_type=audio" in probe
    if not ok:
        print("FALHOU: narração não gerada ou vídeo sem áudio", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
