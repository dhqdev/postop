"""Modo 2: ideia → roteiro (uma IA de texto) → cenas 3D montadas e animadas por código → vídeo 9:16.

Só o roteiro usa IA. As cenas são desenhadas pelo motor 3D do próprio PostOp (`app/render3d`):
cenários, pessoas, animais e objetos vêm do catálogo do motor e a IA apenas escolhe o que entra
em cada cena e o que cada um faz. Sem API key (ou se a IA falhar) o roteiro é montado
automaticamente a partir da ideia, então o vídeo sai mesmo assim.

Som (opcional): narração com voz local (`app/tts.py`), efeitos e ambiente gerados por código
(`app/render3d/sound.py`) e a música enviada, que abaixa sozinha quando a narração fala.
"""

from __future__ import annotations

import gc
import multiprocessing
import os
import time
from dataclasses import asdict
from pathlib import Path

from ..media import build_ass, build_scene_ass, concat_xfade, duration_of, finalize, thumbnail
from ..openrouter import OpenRouter, OpenRouterError
from ..render3d import catalog_text, describe, init_worker, normalize_scene, offline_script, render_scene
from ..render3d.sound import SR, mix_soundtrack, read_wav, resample, write_wav
from . import Cancelled, Ctx
from .themes import STYLE_NAMES, STYLES, THEME_MAP

VOICE_DELAY = 0.3  # a fala começa um pouco depois do início da cena
VOICE_TAIL = 0.45  # respiro depois da fala antes da próxima cena
MAX_SCENE = 12.0  # cena com fala longa demais acelera a voz em vez de passar disso

SCRIPT_SYSTEM = """Você é roteirista e diretor de vídeos curtos virais para TikTok em formato vertical 9:16.
O vídeo é uma animação 3D montada por um motor com um catálogo fixo de cenários, personagens,
animais, objetos, ações e movimentos de câmera. A partir da ideia do usuário, divida a história
em cenas. Para cada cena gere:
- text: frase curta (máx. {words} palavras) que aparece na tela, no idioma do usuário.
{narration_rule}- scene3d: o que aparece na cena, usando SOMENTE nomes do catálogo abaixo.

Regras de direção:
- 1 a 4 grupos de atores por cena. O primeiro é o protagonista e fica no centro.
- Mantenha o MESMO protagonista (mesmo "type" e mesma "color") em todas as cenas.
- Escolha ações que mostrem o que o texto diz (andar, pular, empilhar blocos, foguete decolando...).
- Cada ator faz 1 a 3 ações em sequência, com começo e fim (ex.: ["walk", "wave"]). Ações curtas (jump, wave...)
  acontecem uma vez e o motor completa a cena com o personagem parado de forma natural. Não repita a mesma ação.
- Dois personagens conversando: use facing "center" (um de frente para o outro).
- Para ideias abstratas use objetos-símbolo do catálogo (lightbulb, brain, heart, coin, clock, dna,
  atom, planet, trophy, gear, book...). Para grupos de objetos use "count" e uma ação de grupo.
- Varie a câmera entre as cenas e combine cenário, horário e clima com o clima da história.

{catalog}

Responda APENAS com JSON:
{"title": "...", "caption": "legenda do post com emoji e chamada", "hashtags": ["#..."],
 "scenes": [{"text": "...", {narration_field}"scene3d": {"setting": "...", "time": "...", "weather": "...", "camera": "...",
   "actors": [{"type": "...", "actions": ["..."], "count": 1, "color": "#RRGGBB", "position": "center"}]}}]}"""

NARRATION_RULE = (
    "- narration: o que o narrador fala em voz alta nessa cena (1 ou 2 frases curtas, até {nwords} palavras, "
    "no idioma do usuário). Escreva para ser ouvido: natural, envolvente, sem emojis, hashtags nem marcações. "
    "O texto da tela resume a fala.\n"
)


def script_prompts(params: dict) -> tuple[str, str]:
    """Monta (system, user) do roteirista, com as regras do tema escolhido."""
    theme = THEME_MAP.get(params.get("theme") or "")
    n = int(params.get("scenes", 6))
    narrate = bool(params.get("narration"))
    secs = float(params.get("seconds_per_scene", 3.5))
    rule = NARRATION_RULE.replace("{nwords}", str(max(12, int(secs * 3.2)))) if narrate else ""
    system = (
        SCRIPT_SYSTEM.replace("{words}", str(theme.words if theme else 8))
        .replace("{narration_rule}", rule)
        .replace("{narration_field}", '"narration": "...", ' if narrate else "")
        .replace("{catalog}", catalog_text())
    )
    if theme:
        system += (
            f"\n\nGÊNERO DO VÍDEO: {theme.name}. Regras do gênero: {theme.guide}"
            f"\nCenário que combina com o gênero (use se a ideia não pedir outro): {theme.world}"
        )
    style = params.get("style") if params.get("style") in STYLES else "pixar3d"
    user = (
        f"Ideia: {params['prompt']}\nNúmero de cenas: {n}\n"
        f"Estilo visual: {STYLE_NAMES.get(style, style)} ({STYLES[style]})\n"
        f"Duração por cena: {params.get('seconds_per_scene', 3.5)} segundos"
    )
    return system, user


def merge_hashtags(script_tags: object, theme_key: str, limit: int = 8) -> str:
    tags = script_tags.split() if isinstance(script_tags, str) else list(script_tags or [])
    theme = THEME_MAP.get(theme_key or "")
    if theme:  # as do roteiro são mais específicas; as do tema garantem o nicho
        tags = tags[: limit - len(theme.hashtags)] + list(theme.hashtags)
    out: list[str] = []
    for t in tags:
        t = str(t).strip()
        if not t:
            continue
        t = t if t.startswith("#") else f"#{t}"
        if t.lower() not in (x.lower() for x in out):
            out.append(t)
    return " ".join(out[:limit])


def write_script(ctx: Ctx, client: OpenRouter) -> dict:
    p = ctx.params
    n = int(p.get("scenes", 6))
    system, user = script_prompts(p)
    data, cost, model = client.chat_json(
        [ctx.settings.get("text_model", ""), ctx.settings.get("text_fallback_model", "")], system, user
    )
    ctx.add_cost(cost)
    ctx.log(f"Roteiro criado por {model}")
    if not isinstance(data, dict) or not isinstance(data.get("scenes"), list):
        raise OpenRouterError("O modelo não retornou cenas")
    scenes = [s for s in data["scenes"] if isinstance(s, dict) and (s.get("scene3d") or s.get("text"))][:n]
    if not scenes:
        raise OpenRouterError("Roteiro sem cenas válidas")
    data["scenes"] = scenes
    return data


def make_script(ctx: Ctx) -> dict:
    """Roteiro pela IA; sem API key ou se a IA falhar, roteiro automático a partir da ideia."""
    p = ctx.params
    theme = THEME_MAP.get(p.get("theme") or "")
    api_key = ctx.settings.get("openrouter_api_key", "")
    if api_key:
        try:
            return write_script(ctx, OpenRouter(api_key))
        except OpenRouterError as exc:
            ctx.log(f"IA do roteiro falhou ({exc}); usando o roteiro automático")
    else:
        ctx.log("Sem API key do OpenRouter: roteiro automático montado a partir da ideia")
    return offline_script(
        p["prompt"],
        int(p.get("scenes", 6)),
        theme.world if theme else "studio",
        theme.words if theme else 8,
        theme.hashtags if theme else (),
    )


def render_workers(n: int) -> int:
    env = os.environ.get("RENDER_WORKERS", "").strip()
    if env.isdigit() and int(env) > 0:
        return min(int(env), n)
    return max(1, min(n, os.cpu_count() or 1, 3))


def _render_parallel(
    ctx: Ctx, jobs: list, workers: int, seconds: float, on_done, fn=render_scene
) -> list[int]:
    """Renderiza em processos separados. Devolve as cenas que sobraram (para fazer em série)."""
    n = len(jobs)
    try:
        pool = multiprocessing.get_context("spawn").Pool(workers, initializer=init_worker)
    except (OSError, ValueError) as exc:  # ambiente sem multiprocessamento
        ctx.log(f"Renderização em paralelo indisponível ({exc}); seguindo em série")
        return list(range(n))
    results = {i: pool.apply_async(fn, jobs[i]) for i in range(n)}
    left = set(results)
    # folga bem maior que o normal (~3 s de render por segundo de cena em 1 núcleo)
    deadline = time.monotonic() + 120 + seconds * 20 / workers
    try:
        while left:
            if ctx.cancelled():
                raise Cancelled()
            if time.monotonic() > deadline:
                ctx.log(
                    "A renderização em paralelo parou de responder; terminando as cenas restantes em série"
                )
                break
            for i in sorted(left):
                if results[i].ready():
                    results[i].get()  # repassa o erro da cena, se houver
                    left.discard(i)
                    on_done()
            time.sleep(0.3)
    finally:
        pool.terminate()
        pool.join()
    return sorted(left)


def render_clips(
    ctx: Ctx, specs: list, work: Path, durations: list[float], style: str, sfx: bool = False
) -> tuple[list[Path], list[Path | None]]:
    """Renderiza as cenas (em paralelo quando há mais de um núcleo). Devolve (vídeos, trilhas de efeitos)."""
    n = len(specs)
    jobs = []
    for i, spec in enumerate(specs):
        audio = str(work / f"clip{i + 1:02d}.wav") if sfx else None
        jobs.append(
            (
                spec,
                str(work / f"clip{i + 1:02d}.mp4"),
                durations[i],
                style,
                ctx.job_id * 101 + i,
                i,
                1080,
                1920,
                30,
                audio,
            )
        )
    done = 0

    def tick() -> None:
        ctx.report(14 + int(72 * done / n), f"Animando cenas 3D ({done}/{n})")

    def on_done() -> None:
        nonlocal done
        done += 1
        tick()

    tick()
    workers = render_workers(n)
    pending = _render_parallel(ctx, jobs, workers, sum(durations), on_done) if workers > 1 else list(range(n))
    for i in pending:
        if ctx.cancelled():
            raise Cancelled()
        render_scene(*jobs[i])
        on_done()
    return [Path(j[1]) for j in jobs], [Path(j[9]) if j[9] else None for j in jobs]


def narrate_scenes(ctx: Ctx, lines: list[str], voice: str, base: float) -> tuple[list, list[float]]:
    """Gera a fala de cada cena. Devolve (áudios a 44,1 kHz ou None, duração de cada cena)."""
    from ..tts import VOICES, Narrator, TTSError, clean_text

    durations = [base] * len(lines)
    audios: list = [None] * len(lines)
    try:
        narrator = Narrator(voice, report=lambda msg: ctx.report(8, msg))
        for i, line in enumerate(lines):
            if ctx.cancelled():
                raise Cancelled()
            text = clean_text(line)
            if not text:
                continue
            ctx.report(8 + int(5 * i / max(len(lines), 1)), f"Gerando a narração ({i + 1}/{len(lines)})")
            audio, sr = narrator.say(text)
            dur = len(audio) / sr
            limit = MAX_SCENE - VOICE_DELAY - VOICE_TAIL
            if dur > limit:  # fala comprida: acelera um pouco a voz
                audio, sr = narrator.say(text, speed=min(1.5, narrator.speed * dur / limit))
                dur = len(audio) / sr
            audios[i] = resample(audio, sr, SR)
            durations[i] = max(base, dur + VOICE_DELAY + VOICE_TAIL)
        ctx.log(f"Narração gerada com a voz {VOICES.get(narrator.voice, narrator.voice)}")
        del narrator
        gc.collect()
    except (TTSError, OSError) as exc:
        ctx.log(f"Narração indisponível ({exc}); o vídeo sai sem voz")
        return [None] * len(lines), [base] * len(lines)
    return audios, durations


def run(ctx: Ctx, work: Path, out_dir: Path) -> list[dict]:
    p = ctx.params
    seconds = float(p.get("seconds_per_scene", 3.5))
    style = p.get("style") if p.get("style") in STYLES else "pixar3d"
    theme = THEME_MAP.get(p.get("theme") or "")
    narrate = bool(p.get("narration"))
    sfx = bool(p.get("sfx"))

    ctx.report(3, "Escrevendo roteiro")
    script = make_script(ctx)
    scenes = script["scenes"]
    specs = []
    for i, s in enumerate(scenes):
        spec = normalize_scene(
            s.get("scene3d"),
            text=f"{s.get('text', '')} {p['prompt'] if i == 0 else ''}",
            theme_world=theme.world if theme else "studio",
            index=i,
            default_actor=theme.actor if theme else "person",
        )
        specs.append(spec)
        ctx.log(f"Cena {i + 1}: {describe(spec)}")
    if ctx.cancelled():
        raise Cancelled()

    lines = [str(s.get("narration") or s.get("text") or "") for s in scenes]
    voices: list = [None] * len(scenes)
    durations = [seconds] * len(scenes)
    if narrate:
        voices, durations = narrate_scenes(ctx, lines, str(p.get("voice") or ""), seconds)

    clips, tracks = render_clips(ctx, specs, work, [d + 0.5 for d in durations], style, sfx)

    ctx.report(88, "Montando o vídeo final")
    joined = work / "joined.mp4"
    fade = 0.5
    concat_xfade(clips, joined, fade=fade)
    clip_durs = [duration_of(c) for c in clips]
    offsets = [0.0]
    for d in clip_durs[:-1]:
        offsets.append(offsets[-1] + d - fade)
    total = offsets[-1] + clip_durs[-1]

    ass = None
    if p.get("captions", True):
        ass = work / "scenes.ass"
        if any(v is not None for v in voices):
            from ..tts import clean_text, word_timings

            words = []
            for i, off in enumerate(offsets):
                if voices[i] is not None:
                    words += word_timings(clean_text(lines[i]), len(voices[i]) / SR, off + VOICE_DELAY)
                elif scenes[i].get("text"):
                    visible = clip_durs[i] - (fade if i < len(clips) - 1 else 0)
                    words += word_timings(str(scenes[i]["text"]), max(0.6, visible - 0.5), off + 0.2)
            style_sub = ctx.settings.get("subtitle_style", "highlight")
            ass.write_text(
                build_ass(
                    words,
                    style="simple" if style_sub == "simple" else "highlight",
                    highlight=ctx.settings.get("subtitle_color", "#FFE14D") or "#FFE14D",
                ),
                encoding="utf-8",
            )
        else:
            timeline = []
            for i, off in enumerate(offsets):
                end = off + clip_durs[i] - (fade if i < len(clips) - 1 else 0)
                timeline.append((off + 0.15, end, str(scenes[i].get("text", ""))))
            ass.write_text(build_scene_ass(timeline), encoding="utf-8")

    music = Path(p["music_path"]) if p.get("music_path") and Path(p["music_path"]).exists() else None
    audio = None
    if sfx or music or any(v is not None for v in voices):
        ctx.report(92, "Mixando narração, efeitos e música")
        scene_tracks = [
            (off, read_wav(tr) if tr is not None and tr.exists() else None)
            for off, tr in zip(offsets, tracks, strict=True)
        ]
        spoken = [(offsets[i] + VOICE_DELAY, v) for i, v in enumerate(voices) if v is not None]
        mix = mix_soundtrack(
            total, scene_tracks, spoken, music, fade, offsets[1:] if sfx else [], seed=ctx.job_id
        )
        audio = write_wav(work / "mix.wav", mix)
    out = out_dir / "video_3d.mp4"
    finalize(joined, out, ass, music=None, audio=audio)
    thumb = thumbnail(out, out_dir / "video_3d.jpg", at=min(1.5, max(0.2, duration_of(out) / 3)))
    return [
        {
            "file": out,
            "thumb": thumb,
            "title": str(script.get("title", "Vídeo 3D"))[:200],
            "caption": str(script.get("caption", "")),
            "hashtags": merge_hashtags(script.get("hashtags"), p.get("theme", "")),
            "duration": duration_of(out),
            "score": 0.0,
            "meta": {
                "prompt": p["prompt"],
                "style": style,
                "theme": p.get("theme", ""),
                "engine": "render3d",
                "narration": any(v is not None for v in voices),
                "voice": str(p.get("voice") or "") if narrate else "",
                "sfx": sfx,
                "scenes": [
                    {
                        "text": str(s.get("text", "")),
                        "narration": lines[i] if narrate else "",
                        "scene3d": asdict(sp),
                    }
                    for i, (s, sp) in enumerate(zip(scenes, specs, strict=True))
                ],
            },
        }
    ]
