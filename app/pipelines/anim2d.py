"""Modo 3: ideia → roteiro (uma IA de texto, poucos tokens) → animação 2D desenhada por código → vídeo 9:16.

Estilo dos vídeos de animação explicativa do TikTok: personagens de recorte de papel com rótulo,
faixa de título, cartões, adesivos, checklist, contador e legenda palavra por palavra. Só o roteiro
usa IA; personagens, objetos, cenários e animações são desenhados pelo motor 2D (`app/render2d`).
Sem API key (ou se a IA falhar) o roteiro é montado automaticamente a partir da ideia.
"""

from __future__ import annotations

from pathlib import Path

from ..media import concat_cuts, duration_of, finalize, thumbnail
from ..openrouter import OpenRouter, OpenRouterError
from ..render2d import (
    STYLE2D_NAMES,
    STYLES2D,
    catalog_text,
    describe,
    normalize_story,
    offline_story,
    render_scene2d,
)
from ..render3d import init_worker
from ..render3d.sound import SR, mix_soundtrack, read_wav, write_wav
from . import Cancelled, Ctx
from .prompt3d import VOICE_DELAY, _render_parallel, merge_hashtags, narrate_scenes, render_workers
from .themes import THEME_MAP

FPS = 30

STORY_SYSTEM = """Você é roteirista de vídeos curtos de ANIMAÇÃO 2D (desenho de recorte de papel) para TikTok 9:16.
O vídeo é narrado e conta uma história com começo, meio e fim; cada cena ilustra exatamente o que a narração diz.
Regras:
- Cena 1 é o gancho: uma frase que prende nos 3 primeiros segundos.
- narration: 1 ou 2 frases curtas (até {nwords} palavras), no idioma do usuário, sem emoji nem hashtag.
- Personagens que se repetem vão em "cast" (id curto, type, name, color #RRGGBB). Nas cenas use o id.
- show: 1 a 4 elementos por cena (personagem pelo id ou type; objeto em "prop"). O primeiro é o principal.
- do: 1 a 3 ações em ordem. Ações curtas acontecem uma vez; o personagem fica natural no resto da cena.
- Use banner (título de 2 a 4 palavras) nas cenas-chave; card (subtítulo) e tag (referência) são opcionais.
- Quando ajudar a explicar use: sticker (exclamação curta), say (fala curta num balão), label (nome sobre o
  personagem), list (até 4 itens), number (número de impacto, ex.: "281.999.045 homens"), chart (up/down) e fx.
- Use SOMENTE nomes do catálogo.

{catalog}

Responda APENAS com JSON:
{"title":"...","caption":"legenda do post com emoji","hashtags":["#..."],
 "cast":[{"id":"ana","type":"girl","name":"Ana","color":"#e74c3c"}],
 "scenes":[{"narration":"...","place":"street","time":"day","banner":"...","show":[{"id":"ana","do":["walk_in","wave"],"at":"center","label":true},{"prop":"phone","at":"right","do":["pop"]}],"fx":"hearts"}]}"""


def story_prompts(params: dict) -> tuple[str, str]:
    """Monta (system, user) do roteirista 2D, com as regras do tema escolhido."""
    theme = THEME_MAP.get(params.get("theme") or "")
    n = int(params.get("scenes", 6))
    secs = float(params.get("seconds_per_scene", 4))
    system = STORY_SYSTEM.replace("{nwords}", str(max(10, int(secs * 3.2)))).replace(
        "{catalog}", catalog_text()
    )
    if theme:
        system += (
            f"\n\nGÊNERO DO VÍDEO: {theme.name}. Regras do gênero: {theme.guide}"
            f"\nCenário que combina com o gênero (use se a ideia não pedir outro): {theme.place2d}"
        )
    style = params.get("style") if params.get("style") in STYLES2D else "papel"
    user = (
        f"Ideia: {params['prompt']}\nNúmero de cenas: {n}\n"
        f"Estilo: {STYLE2D_NAMES.get(style, style)}\nDuração por cena: {secs:g} segundos"
    )
    return system, user


def make_story(ctx: Ctx) -> tuple[dict, bool]:
    """Roteiro pela IA; sem chave ou se a IA falhar, roteiro automático. Devolve (roteiro, veio_da_ia)."""
    p = ctx.params
    theme = THEME_MAP.get(p.get("theme") or "")
    n = int(p.get("scenes", 6))
    api_key = ctx.settings.get("openrouter_api_key", "")
    if api_key:
        system, user = story_prompts(p)
        try:
            data, cost, model = OpenRouter(api_key).chat_json(
                [ctx.settings.get("text_model", ""), ctx.settings.get("text_fallback_model", "")],
                system,
                user,
                max_tokens=min(4000, 500 + 230 * n),
            )
            ctx.add_cost(cost)
            ctx.log(f"Roteiro criado por {model}")
            if isinstance(data, dict) and isinstance(data.get("scenes"), list) and data["scenes"]:
                return data, True
            ctx.log("A IA não devolveu cenas; usando o roteiro automático")
        except OpenRouterError as exc:
            ctx.log(f"IA do roteiro falhou ({exc}); usando o roteiro automático")
    else:
        ctx.log("Sem API key do OpenRouter: roteiro automático montado a partir da ideia")
    return (
        offline_story(
            p["prompt"],
            n,
            theme.place2d if theme else "plain",
            theme.actor2d if theme else "person",
            theme.hashtags if theme else (),
        ),
        False,
    )


def run(ctx: Ctx, work: Path, out_dir: Path) -> list[dict]:
    from ..tts import clean_text, word_timings

    p = ctx.params
    seconds = float(p.get("seconds_per_scene", 4))
    style = p.get("style") if p.get("style") in STYLES2D else "papel"
    theme = THEME_MAP.get(p.get("theme") or "")
    narrate = bool(p.get("narration"))
    sfx = bool(p.get("sfx"))
    n = int(p.get("scenes", 6))

    ctx.report(3, "Escrevendo roteiro")
    raw, from_ai = make_story(ctx)
    story = normalize_story(
        raw,
        n,
        theme.place2d if theme else "plain",
        theme.actor2d if theme else "person",
        banner_color=theme.banner2d if theme else 0,
    )
    if not story.scenes:
        raise RuntimeError("O roteiro não tem cenas")
    for i, sc in enumerate(story.scenes):
        ctx.log(f"Cena {i + 1}: {describe(sc)}")
    if ctx.cancelled():
        raise Cancelled()

    lines = [sc.narration for sc in story.scenes]
    voices: list = [None] * len(lines)
    durations = [max(seconds, 0.36 * len(line.split()) + 1.0) for line in lines]
    if narrate:
        voices, durations = narrate_scenes(ctx, lines, str(p.get("voice") or ""), seconds)
    # duração exata em quadros (cortes secos: o áudio precisa bater com o vídeo)
    durations = [round(d * FPS) / FPS for d in durations]

    cap_style = ctx.settings.get("subtitle_style", "highlight") if p.get("captions", True) else "none"
    cap_color = ctx.settings.get("subtitle_color", "#FFE14D") or "#FFE14D"
    jobs = []
    for i, sc in enumerate(story.scenes):
        words = None
        if cap_style != "none" and lines[i]:
            if voices[i] is not None:
                words = word_timings(clean_text(lines[i]), len(voices[i]) / SR, VOICE_DELAY)
            else:
                words = word_timings(lines[i], max(0.8, durations[i] - 0.7), 0.3)
        audio = str(work / f"clip{i + 1:02d}.wav") if sfx else None
        jobs.append((sc, str(work / f"clip{i + 1:02d}.mp4"), durations[i], style, ctx.job_id * 131 + i, i,
                     1080, 1920, FPS, audio, words, cap_style if cap_style in ("highlight", "simple") else "highlight",
                     cap_color))  # fmt: skip

    total_n = len(jobs)
    done = 0

    def tick() -> None:
        ctx.report(14 + int(72 * done / total_n), f"Animando cenas 2D ({done}/{total_n})")

    def on_done() -> None:
        nonlocal done
        done += 1
        tick()

    tick()
    workers = render_workers(total_n)
    pending = (
        _render_parallel(ctx, jobs, workers, sum(durations), on_done, fn=render_scene2d)
        if workers > 1
        else list(range(total_n))
    )
    if workers <= 1:
        init_worker()
    for i in pending:
        if ctx.cancelled():
            raise Cancelled()
        render_scene2d(*jobs[i])
        on_done()

    ctx.report(88, "Montando o vídeo final")
    clips = [Path(j[1]) for j in jobs]
    joined = work / "joined.mp4"
    concat_cuts(clips, joined)
    offsets = [0.0]
    for d in durations[:-1]:
        offsets.append(offsets[-1] + d)
    total = offsets[-1] + durations[-1]

    music = Path(p["music_path"]) if p.get("music_path") and Path(p["music_path"]).exists() else None
    audio = None
    if sfx or music or any(v is not None for v in voices):
        ctx.report(92, "Mixando narração, efeitos e música")
        tracks = [
            (off, read_wav(j[9]) if j[9] and Path(j[9]).exists() else None)
            for off, j in zip(offsets, jobs, strict=True)
        ]
        spoken = [(offsets[i] + VOICE_DELAY, v) for i, v in enumerate(voices) if v is not None]
        mix = mix_soundtrack(total, tracks, spoken, music, 0.04, offsets[1:] if sfx else [], seed=ctx.job_id)
        audio = write_wav(work / "mix.wav", mix)
    out = out_dir / "animacao_2d.mp4"
    finalize(joined, out, None, music=None, audio=audio, copy_video=True)
    thumb = thumbnail(out, out_dir / "animacao_2d.jpg", at=min(1.6, max(0.3, duration_of(out) / 3)))
    title = story.title or str(p["prompt"])[:90]
    return [
        {
            "file": out,
            "thumb": thumb,
            "title": title[:200],
            "caption": story.caption,
            "hashtags": merge_hashtags(story.hashtags, p.get("theme", "")),
            "duration": duration_of(out),
            "score": 0.0,
            "meta": {
                "prompt": p["prompt"],
                "style": style,
                "theme": p.get("theme", ""),
                "engine": "render2d",
                "script_by_ai": from_ai,
                "narration": any(v is not None for v in voices),
                "voice": str(p.get("voice") or "") if narrate else "",
                "sfx": sfx,
                "scenes": [{"narration": sc.narration, "summary": describe(sc)} for sc in story.scenes],
            },
        }
    ]
