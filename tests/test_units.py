from app import settings_store as st
from app.db import init_db
from app.media import Word, build_ass, build_scene_ass, group_words, reframe_filter, words_to_segments
from app.openrouter import parse_json, summarize_models
from app.pipelines.prompt3d import merge_hashtags, script_prompts
from app.pipelines.themes import STYLES, THEMES
from app.pipelines.youtube_clips import clean_clips, heuristic_clips, is_youtube_url
from app.tiktok import CHUNK, chunk_plan


def _words(text, start=0.0, step=0.4):
    out = []
    t = start
    for w in text.split():
        out.append(Word(t, t + step - 0.05, " " + w))
        t += step
    return out


def test_parse_json_variants():
    assert parse_json('{"a": 1}') == {"a": 1}
    assert parse_json('```json\n{"a": 2}\n```') == {"a": 2}
    assert parse_json('Claro! Aqui está: {"clips": []} espero que ajude') == {"clips": []}


def test_group_words_breaks_on_punctuation_and_size():
    groups = group_words(_words("um dois três quatro. cinco seis"))
    assert [len(g) for g in groups] == [3, 1, 2]


def test_build_ass_highlight_has_one_event_per_word():
    ass = build_ass(_words("olá mundo bonito"), style="highlight", highlight="#FF0000")
    events = [line for line in ass.splitlines() if line.startswith("Dialogue:")]
    assert len(events) == 3
    assert "&H000000FF" in ass  # vermelho em BGR
    assert "OLÁ" in ass


def test_build_ass_none_and_simple():
    assert "Dialogue" not in build_ass(_words("a b"), style="none")
    simple = build_ass(_words("a b"), style="simple")
    assert simple.count("Dialogue:") == 1


def test_scene_ass_escapes_braces():
    ass = build_scene_ass([(0, 2, "texto {perigoso}")])
    assert "{perigoso}" not in ass and "(perigoso)" in ass


def test_words_to_segments():
    segs = words_to_segments(_words("frase um. frase dois!"))
    assert len(segs) == 2 and segs[0]["text"].endswith("um.")


def test_clean_clips_clamps_and_removes_overlap():
    words = _words(" ".join(["palavra"] * 300))  # ~120s
    raw = [
        {"start": 10, "end": 200, "title": "longo", "hashtags": "viral fyp"},
        {"start": 20, "end": 50, "title": "sobreposto"},
        {"start": 80, "end": 100, "title": "ok", "hashtags": ["#a"]},
        {"start": 5, "end": 2, "title": "inválido"},
    ]
    clips = clean_clips(raw, words, total=120, n=5, min_s=15, max_s=40)
    assert [c["title"] for c in clips] == ["longo", "ok"]
    assert clips[0]["end"] - clips[0]["start"] <= 41
    assert clips[0]["hashtags"] == ["#viral", "#fyp"]


def test_heuristic_clips():
    words = _words(" ".join(f"w{i}." for i in range(200)), step=0.5)
    segs = words_to_segments(words)
    clips = heuristic_clips(segs, n=3, min_s=10, max_s=30)
    assert 1 <= len(clips) <= 3
    assert all(10 <= c["end"] - c["start"] <= 30 for c in clips)


def test_is_youtube_url():
    assert is_youtube_url("https://www.youtube.com/watch?v=abc")
    assert is_youtube_url("https://youtu.be/abc")
    assert is_youtube_url("https://youtube.com/shorts/abc")
    assert not is_youtube_url("https://vimeo.com/1")


def test_reframe_filter_modes():
    assert "boxblur" in reframe_filter(1920, 1080, "blur", None)
    assert "boxblur" in reframe_filter(1920, 1080, "auto", None)
    f = reframe_filter(1920, 1080, "auto", 0.9)
    assert "crop=1080:1920:" in f and "boxblur" not in f
    assert reframe_filter(1080, 1920, "blur", None).startswith("scale=1080:1920")


def test_chunk_plan():
    assert chunk_plan(3_000_000) == (3_000_000, 1)
    size = 150 * 1024 * 1024
    cs, n = chunk_plan(size)
    assert cs == CHUNK and n == size // CHUNK
    assert size - cs * (n - 1) <= 128 * 1024 * 1024  # último pedaço dentro do limite


def test_summarize_models():
    data = [
        {
            "id": "a/txt",
            "pricing": {"prompt": "0.0000001", "completion": "0.0000004"},
            "architecture": {"output_modalities": ["text"]},
        },
        {
            "id": "b/free:free",
            "pricing": {"prompt": "0", "completion": "0"},
            "architecture": {"output_modalities": ["text"]},
        },
        {
            "id": "c/img",
            "pricing": {"prompt": "0.0000003"},
            "architecture": {"output_modalities": ["image", "text"]},
        },
    ]
    g = summarize_models(data)
    assert [m["id"] for m in g["text"]] == ["b/free:free", "a/txt"]  # modelos de imagem ficam de fora
    assert list(g) == ["text"]
    assert g["text"][1]["prompt_per_m"] == 0.1


def test_settings_encryption_roundtrip():
    init_db()
    st.set_many({"openrouter_api_key": "sk-or-123456789", "text_model": "x/y"})
    assert st.get("openrouter_api_key") == "sk-or-123456789"
    assert st.get("text_model") == "x/y"
    from app.db import Setting, session_scope

    with session_scope() as s:
        row = s.get(Setting, "openrouter_api_key")
        assert row.encrypted and "sk-or" not in row.value
    view = {f["key"]: f for f in st.public_view()}
    assert view["openrouter_api_key"]["value"] == "" and view["openrouter_api_key"]["is_set"]


def test_script_prompts_apply_theme_rules():
    system, user = script_prompts({"prompt": "boneca do brechó", "theme": "terror", "scenes": 5})
    assert "GÊNERO DO VÍDEO: Terror" in system and "máx. 10 palavras" in system
    assert "boneca do brechó" in user and "Número de cenas: 5" in user
    plain, _ = script_prompts({"prompt": "gato astronauta"})
    assert "GÊNERO" not in plain and "máx. 8 palavras" in plain
    assert '{"title"' in plain  # o JSON de exemplo continua intacto


def test_merge_hashtags_keeps_theme_tags():
    tags = merge_hashtags(["medo", "#Terror", "#a", "#b", "#c", "#d", "#e", "#f"], "terror").split()
    assert len(tags) <= 8
    assert {"#terror", "#historiasdeterror", "#medo"} <= {t.lower() for t in tags}
    assert len({t.lower() for t in tags}) == len(tags)
    assert merge_hashtags("viral fyp", "") == "#viral #fyp"


def test_themes_are_consistent():
    from app.render3d.models import REGISTRY
    from app.render3d.world import SETTINGS

    assert len({t.key for t in THEMES}) == len(THEMES)
    for t in THEMES:
        assert t.style in STYLES and len(t.ideas) >= 3 and 1 <= t.scenes <= 15 and 2 <= t.seconds <= 10
        assert t.world in SETTINGS and t.actor in REGISTRY


def test_script_prompt_has_3d_catalog():
    system, user = script_prompts({"prompt": "gato", "style": "neon"})
    assert "CATÁLOGO 3D" in system and "scene3d" in system and "astronaut" in system and "stack" in system
    assert "Neon" in user


def test_retired_model_is_replaced(monkeypatch):
    init_db()
    monkeypatch.setitem(st.RETIRED_MODELS, "velho/modelo:free", "novo/modelo")
    st.set_many({"text_model": "velho/modelo:free"})
    assert st.get("text_model") == "novo/modelo"
    st.set_many({"text_model": ""})
