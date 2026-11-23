"""Modo 2: prompt -> roteiro -> imagens 3D (OpenRouter) -> vídeo vertical animado."""

from __future__ import annotations

from pathlib import Path

from ..media import (
    MOVES,
    build_scene_ass,
    concat_xfade,
    duration_of,
    finalize,
    ken_burns,
    normalize_clip,
    thumbnail,
)
from ..openrouter import OpenRouter, OpenRouterError
from . import Cancelled, Ctx

STYLES = {
    "pixar3d": "3D animated movie style, Pixar-like, soft global illumination, subsurface scattering, "
    "expressive characters, octane render, cinematic depth of field",
    "realista3d": "photorealistic 3D CGI render, Unreal Engine 5, ray tracing, cinematic lighting, "
    "ultra detailed, volumetric light",
    "anime3d": "3D anime style, cel-shaded, vibrant colors, dynamic composition, studio quality render",
    "lowpoly": "low poly 3D isometric diorama, clean geometric shapes, soft pastel lighting, blender render",
    "clay": "claymation 3D style, plasticine textures, handcrafted miniature set, tilt-shift, soft light",
    "neon": "futuristic 3D render, cyberpunk neon lights, glossy reflections, dark atmosphere, octane render",
}

SCRIPT_SYSTEM = """Você é roteirista de vídeos curtos virais para TikTok em formato vertical 9:16.
A partir da ideia do usuário, crie um roteiro dividido em cenas. Para cada cena gere:
- image_prompt: prompt DETALHADO EM INGLÊS para um gerador de imagens (descreva personagem,
  cenário, ângulo de câmera, iluminação). Repita a descrição física completa dos personagens em
  TODAS as cenas para manter consistência. Composição vertical, assunto centralizado.
- motion_prompt: em inglês, como a câmera/personagem se move nessa cena (para um modelo de vídeo).
- text: frase curta (máx. 8 palavras) que aparece na tela, no idioma do usuário.
Responda APENAS com JSON:
{"title": "...", "caption": "legenda do post com emoji e chamada", "hashtags": ["#..."],
 "scenes": [{"image_prompt": "...", "motion_prompt": "...", "text": "..."}]}"""


def write_script(ctx: Ctx, client: OpenRouter) -> dict:
    p = ctx.params
    n = int(p.get("scenes", 6))
    user = (
        f"Ideia: {p['prompt']}\nNúmero de cenas: {n}\n"
        f"Estilo visual: {p.get('style', 'pixar3d')}\n"
        f"Duração por cena: {p.get('seconds_per_scene', 3.5)} segundos"
    )
    data, cost, model = client.chat_json(
        [ctx.settings.get("text_model", ""), ctx.settings.get("text_fallback_model", "")], SCRIPT_SYSTEM, user
    )
    ctx.add_cost(cost)
    ctx.log(f"Roteiro criado por {model}")
    if not isinstance(data, dict) or not data.get("scenes"):
        raise OpenRouterError("O modelo não retornou cenas")
    data["scenes"] = [s for s in data["scenes"] if isinstance(s, dict) and s.get("image_prompt")][:n]
    if not data["scenes"]:
        raise OpenRouterError("Roteiro sem cenas válidas")
    return data


def image_prompt(scene: dict, style_key: str, custom_style: str) -> str:
    style = custom_style.strip() or STYLES.get(style_key, STYLES["pixar3d"])
    return (
        f"{scene['image_prompt']}. Style: {style}. Vertical 9:16 portrait composition, "
        f"main subject centered, no text, no watermark, no letters."
    )


def make_image(ctx: Ctx, client: OpenRouter, prompt: str, out: Path) -> Path:
    errors = []
    for model in [ctx.settings.get("image_model", ""), ctx.settings.get("image_fallback_model", "")]:
        if not model:
            continue
        try:
            data, cost = client.generate_image(model, prompt, aspect_ratio="9:16")
            ctx.add_cost(cost)
            out.write_bytes(data)
            return out
        except OpenRouterError as exc:
            errors.append(f"{model}: {exc}")
            ctx.log(f"Imagem falhou em {model}: {exc}")
    raise OpenRouterError("Nenhum modelo de imagem funcionou: " + " | ".join(errors)[-1200:])


def _pick_duration(client: OpenRouter, model: str, seconds: float) -> int:
    try:
        for m in client.video_models():
            if m.get("id") == model and m.get("supported_durations"):
                options = sorted(int(d) for d in m["supported_durations"])
                bigger = [d for d in options if d >= seconds]
                return bigger[0] if bigger else options[-1]
    except Exception:
        pass
    return max(4, int(round(seconds)))


def run(ctx: Ctx, work: Path, out_dir: Path) -> list[dict]:
    api_key = ctx.settings.get("openrouter_api_key", "")
    if not api_key:
        raise OpenRouterError(
            "Configure a API key do OpenRouter em Configurações para usar o modo Prompt 3D."
        )
    client = OpenRouter(api_key)
    p = ctx.params
    seconds = float(p.get("seconds_per_scene", 3.5))
    animation = p.get("animation", "local")

    ctx.report(3, "Escrevendo roteiro com IA")
    script = write_script(ctx, client)
    scenes = script["scenes"]

    images: list[Path] = []
    for i, scene in enumerate(scenes, start=1):
        if ctx.cancelled():
            raise Cancelled()
        ctx.report(8 + int(40 * (i - 1) / len(scenes)), f"Gerando imagem {i}/{len(scenes)}")
        images.append(
            make_image(
                ctx,
                client,
                image_prompt(scene, p.get("style", "pixar3d"), p.get("custom_style", "")),
                work / f"scene{i:02d}.png",
            )
        )

    clips: list[Path] = []
    duration_ai = (
        _pick_duration(client, ctx.settings.get("video_model", ""), seconds) if animation == "ai" else 0
    )
    for i, (scene, img) in enumerate(zip(scenes, images, strict=True), start=1):
        if ctx.cancelled():
            raise Cancelled()
        clip = work / f"clip{i:02d}.mp4"
        done = False
        if animation == "ai":
            ctx.report(
                50 + int(35 * (i - 1) / len(scenes)), f"Animando cena {i}/{len(scenes)} com IA (vídeo)"
            )
            try:
                job = client.submit_video(
                    ctx.settings.get("video_model", ""),
                    scene.get("motion_prompt") or scene["image_prompt"],
                    first_frame=img.read_bytes(),
                    duration=duration_ai,
                )
                raw, cost = client.wait_video(job)
                ctx.add_cost(cost)
                raw_path = work / f"ai{i:02d}.mp4"
                raw_path.write_bytes(raw)
                normalize_clip(raw_path, clip)
                done = True
            except OpenRouterError as exc:
                if not p.get("ai_fallback", True):
                    raise
                ctx.log(f"Vídeo IA falhou na cena {i} ({exc}); usando animação local")
        if not done:
            ctx.report(
                50 + int(35 * (i - 1) / len(scenes)), f"Animando cena {i}/{len(scenes)} (efeito 3D local)"
            )
            ken_burns(img, clip, seconds + 0.5, MOVES[(i - 1) % len(MOVES)])
        clips.append(clip)

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
    thumb = thumbnail(out, out_dir / "video_3d.jpg", at=1.0)
    tags = script.get("hashtags") or []
    if isinstance(tags, str):
        tags = tags.split()
    return [
        {
            "file": out,
            "thumb": thumb,
            "title": str(script.get("title", "Vídeo 3D"))[:200],
            "caption": str(script.get("caption", "")),
            "hashtags": " ".join(t if t.startswith("#") else f"#{t}" for t in tags[:8]),
            "duration": duration_of(out),
            "score": 0.0,
            "meta": {
                "prompt": p["prompt"],
                "style": p.get("style"),
                "animation": animation,
                "scenes": scenes,
            },
        }
    ]
