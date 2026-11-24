"""Modo 2: ideia → roteiro (uma IA de texto) → cenas 3D montadas e animadas por código → vídeo 9:16.

Só o roteiro usa IA. As cenas são desenhadas pelo motor 3D do próprio PostOp (`app/render3d`):
cenários, pessoas, animais e objetos vêm do catálogo do motor e a IA apenas escolhe o que entra
em cada cena e o que cada um faz. Sem API key (ou se a IA falhar) o roteiro é montado
automaticamente a partir da ideia, então o vídeo sai mesmo assim.
"""

from __future__ import annotations

import multiprocessing
import os
import time
from dataclasses import asdict
from pathlib import Path

from ..media import build_scene_ass, concat_xfade, duration_of, finalize, thumbnail
from ..openrouter import OpenRouter, OpenRouterError
from ..render3d import catalog_text, describe, init_worker, normalize_scene, offline_script, render_scene
from . import Cancelled, Ctx
from .themes import STYLE_NAMES, STYLES, THEME_MAP

SCRIPT_SYSTEM = """Você é roteirista e diretor de vídeos curtos virais para TikTok em formato vertical 9:16.
O vídeo é uma animação 3D montada por um motor com um catálogo fixo de cenários, personagens,
animais, objetos, ações e movimentos de câmera. A partir da ideia do usuário, divida a história
em cenas. Para cada cena gere:
- text: frase curta (máx. {words} palavras) que aparece na tela, no idioma do usuário.
- scene3d: o que aparece na cena, usando SOMENTE nomes do catálogo abaixo.

Regras de direção:
- 1 a 4 grupos de atores por cena. O primeiro é o protagonista e fica no centro.
- Mantenha o MESMO protagonista (mesmo "type" e mesma "color") em todas as cenas.
- Escolha ações que mostrem o que o texto diz (andar, pular, empilhar blocos, foguete decolando...).
- Para ideias abstratas use objetos-símbolo do catálogo (lightbulb, brain, heart, coin, clock, dna,
  atom, planet, trophy, gear, book...). Para grupos de objetos use "count" e uma ação de grupo.
- Varie a câmera entre as cenas e combine cenário, horário e clima com o clima da história.

{catalog}

Responda APENAS com JSON:
{"title": "...", "caption": "legenda do post com emoji e chamada", "hashtags": ["#..."],
 "scenes": [{"text": "...", "scene3d": {"setting": "...", "time": "...", "weather": "...", "camera": "...",
   "actors": [{"type": "...", "actions": ["..."], "count": 1, "color": "#RRGGBB", "position": "center"}]}}]}"""


def script_prompts(params: dict) -> tuple[str, str]:
    """Monta (system, user) do roteirista, com as regras do tema escolhido."""
    theme = THEME_MAP.get(params.get("theme") or "")
    n = int(params.get("scenes", 6))
    system = SCRIPT_SYSTEM.replace("{words}", str(theme.words if theme else 8)).replace(
        "{catalog}", catalog_text()
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


def _render_parallel(ctx: Ctx, jobs: list, workers: int, seconds: float, on_done) -> list[int]:
    """Renderiza em processos separados. Devolve as cenas que sobraram (para fazer em série)."""
    n = len(jobs)
    try:
        pool = multiprocessing.get_context("spawn").Pool(workers, initializer=init_worker)
    except (OSError, ValueError) as exc:  # ambiente sem multiprocessamento
        ctx.log(f"Renderização em paralelo indisponível ({exc}); seguindo em série")
        return list(range(n))
    results = {i: pool.apply_async(render_scene, jobs[i]) for i in range(n)}
    left = set(results)
    # folga bem maior que o normal (~3 s de render por segundo de cena em 1 núcleo)
    deadline = time.monotonic() + 120 + seconds * n * 20 / workers
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


def render_clips(ctx: Ctx, specs: list, work: Path, seconds: float, style: str) -> list[Path]:
    """Renderiza as cenas (em paralelo quando há mais de um núcleo)."""
    n = len(specs)
    jobs = [
        (spec, str(work / f"clip{i + 1:02d}.mp4"), seconds, style, ctx.job_id * 101 + i, i)
        for i, spec in enumerate(specs)
    ]
    done = 0

    def tick() -> None:
        nonlocal done
        ctx.report(12 + int(73 * done / n), f"Animando cenas 3D ({done}/{n})")

    def on_done() -> None:
        nonlocal done
        done += 1
        tick()

    tick()
    workers = render_workers(n)
    pending = _render_parallel(ctx, jobs, workers, seconds, on_done) if workers > 1 else list(range(n))
    for i in pending:
        if ctx.cancelled():
            raise Cancelled()
        render_scene(*jobs[i])
        on_done()
    return [Path(j[1]) for j in jobs]


def run(ctx: Ctx, work: Path, out_dir: Path) -> list[dict]:
    p = ctx.params
    seconds = float(p.get("seconds_per_scene", 3.5))
    style = p.get("style") if p.get("style") in STYLES else "pixar3d"
    theme = THEME_MAP.get(p.get("theme") or "")

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

    clips = render_clips(ctx, specs, work, seconds + 0.5, style)

    ctx.report(88, "Montando o vídeo final")
    joined = work / "joined.mp4"
    fade = 0.5
    concat_xfade(clips, joined, fade=fade)

    ass = None
    if p.get("captions", True):
        timeline = []
        t = 0.0
        for i, c in enumerate(clips):
            d = duration_of(c)
            start = t
            end = t + d - (fade if i < len(clips) - 1 else 0)
            timeline.append((start + 0.15, end, str(scenes[i].get("text", ""))))
            t = end
        ass = work / "scenes.ass"
        ass.write_text(build_scene_ass(timeline), encoding="utf-8")

    music = Path(p["music_path"]) if p.get("music_path") and Path(p["music_path"]).exists() else None
    out = out_dir / "video_3d.mp4"
    finalize(joined, out, ass, music)
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
                "scenes": [
                    {"text": str(s.get("text", "")), "scene3d": asdict(sp)}
                    for s, sp in zip(scenes, specs, strict=True)
                ],
            },
        }
    ]
