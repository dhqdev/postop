from fastapi.testclient import TestClient

from app.main import app


def client():
    c = TestClient(app, base_url="https://testserver")
    c.__enter__()
    return c


def login(c):
    r = c.post("/api/login", json={"username": "tester", "password": "s3nha-forte"})
    assert r.status_code == 200
    return c


def test_health_and_auth_required():
    c = client()
    assert c.get("/api/health").json()["ok"]
    assert c.get("/api/jobs").status_code == 401
    assert c.post("/api/login", json={"username": "tester", "password": "errada"}).status_code == 401


def test_settings_flow_keeps_secret_when_blank():
    c = login(client())
    r = c.put(
        "/api/settings",
        json={"values": {"openrouter_api_key": "sk-or-abcdefghijkl", "whisper_model": "small"}},
    )
    assert r.status_code == 200
    r = c.put("/api/settings", json={"values": {"openrouter_api_key": "", "whisper_model": "base"}})
    fields = {f["key"]: f for f in r.json()["fields"]}
    assert fields["openrouter_api_key"]["is_set"]
    assert fields["whisper_model"]["value"] == "base"
    assert r.json()["tiktok"]["redirect_uri"] == "https://postop.example.com/api/tiktok/callback"


def test_create_jobs_and_cancel():
    c = login(client())
    assert c.post("/api/jobs/youtube", json={"url": "https://vimeo.com/1"}).status_code == 400
    j = c.post("/api/jobs/youtube", json={"url": "https://youtu.be/dQw4w9WgXcQ", "max_clips": 3}).json()
    assert j["status"] == "queued" and j["kind"] == "youtube"
    j2 = c.post("/api/jobs/prompt3d", json={"prompt": "gato astronauta", "scenes": 3}).json()
    assert j2["kind"] == "prompt3d"
    assert c.post(f"/api/jobs/{j['id']}/cancel").json()["status"] == "canceled"
    ids = [x["id"] for x in c.get("/api/jobs").json()]
    assert j["id"] in ids and j2["id"] in ids
    assert c.get("/api/stats").json()["jobs"]


def test_tiktok_connect_requires_client_key():
    c = login(client())
    r = c.get("/api/tiktok/connect", follow_redirects=False)
    assert r.status_code == 302 and "tiktok_error" in r.headers["location"]
    c.put("/api/settings", json={"values": {"tiktok_client_key": "abc", "tiktok_client_secret": "xyz"}})
    r = c.get("/api/tiktok/connect", follow_redirects=False)
    loc = r.headers["location"]
    assert loc.startswith("https://www.tiktok.com/v2/auth/authorize/")
    assert "video.publish" in loc and "client_key=abc" in loc


def test_tiktok_callback_rejects_bad_state():
    c = login(client())
    r = c.get("/api/tiktok/callback?code=x&state=y", follow_redirects=False)
    assert r.status_code == 302 and "tiktok_error" in r.headers["location"]


def test_media_path_traversal_blocked():
    c = login(client())
    assert c.get("/media/../test.db").status_code == 404


def test_public_pages():
    c = client()
    assert c.get("/termos").status_code == 200
    assert c.get("/privacidade").status_code == 200
    assert "PostOp" in c.get("/").text


def test_themes_and_prompt3d_with_theme():
    c = login(client())
    data = c.get("/api/themes").json()
    keys = {t["key"] for t in data["themes"]}
    styles = {s["key"] for s in data["styles"]}
    assert {"curiosidades", "terror"} <= keys and len(keys) >= 10
    assert all(t["style"] in styles and t["ideas"] for t in data["themes"])
    j = c.post(
        "/api/jobs/prompt3d", json={"prompt": "elevador às 3h", "theme": "terror", "style": "sombrio"}
    ).json()
    assert j["title"].startswith("Terror:") and j["params"]["theme"] == "terror"
    assert c.post("/api/jobs/prompt3d", json={"prompt": "abc", "theme": "nao-existe"}).status_code == 400
    assert c.post("/api/jobs/prompt3d", json={"prompt": "abc", "style": "nao-existe"}).status_code == 400
    # campos antigos (modo de imagem/vídeo por IA) são ignorados
    old = c.post(
        "/api/jobs/prompt3d", json={"prompt": "abc", "animation": "ai", "custom_style": "glossy toys"}
    )
    assert old.status_code == 200 and "animation" not in old.json()["params"]
    params = old.json()["params"]
    assert params["narration"] is True and params["sfx"] is True and params["voice"] == "pf_dora"
    assert c.post("/api/jobs/prompt3d", json={"prompt": "abc", "voice": "nao-existe"}).status_code == 400
    assert {v["key"] for v in data["voices"]} == {"pf_dora", "pm_alex", "pm_santa"}


def test_settings_have_only_text_models():
    c = login(client())
    keys = {f["key"] for f in c.get("/api/settings").json()["fields"]}
    assert {"text_model", "text_fallback_model"} <= keys
    assert not keys & {"image_model", "image_fallback_model", "video_model"}


def test_index_uses_versioned_assets():
    html = client().get("/").text
    assert "/static/app.js?v=" in html and "{{v}}" not in html


def test_index_has_logo_and_icons():
    c = client()
    html = c.get("/").text
    assert "/static/logo.svg?v=" in html and "/static/favicon.svg?v=" in html and "apple-touch-icon" in html
    for name in ("logo.svg", "favicon.svg", "favicon-32.png", "apple-touch-icon.png", "icon-192.png", "icon-512.png",
                 "manifest.webmanifest"):  # fmt: skip
        assert c.get(f"/static/{name}").status_code == 200, name


def test_anim2d_jobs_and_themes():
    c = login(client())
    data = c.get("/api/themes").json()
    assert {s["key"] for s in data["styles2d"]} == {"papel", "flat"}
    modes = {t["key"]: t["modes"] for t in data["themes"]}
    assert "2d" in modes["biblia"] and "2d" in modes["terror"] and modes["satisfatorio"] == ["3d"]
    j = c.post("/api/jobs/anim2d", json={"prompt": "Daniel na cova dos leões", "theme": "biblia"}).json()
    assert (
        j["kind"] == "anim2d"
        and j["params"]["style"] == "papel"
        and j["title"].startswith("Histórias da Bíblia:")
    )
    assert j["params"]["narration"] is True and j["params"]["seconds_per_scene"] == 4.0
    assert c.post("/api/jobs/anim2d", json={"prompt": "abc", "theme": "satisfatorio"}).status_code == 400
    assert c.post("/api/jobs/anim2d", json={"prompt": "abc", "style": "pixar3d"}).status_code == 400
    assert c.post("/api/jobs/anim2d", json={"prompt": "abc", "voice": "nao-existe"}).status_code == 400


def test_youtube_modes_validation_and_preview():
    c = login(client())
    url = "https://youtu.be/dQw4w9WgXcQ"
    r = c.post("/api/jobs/youtube", json={"url": url, "mode": "manual", "clips": ""})
    assert r.status_code == 400 and "pelo menos um corte" in r.json()["detail"]
    r = c.post("/api/jobs/youtube", json={"url": url, "mode": "manual", "clips": "2:00-1:00"})
    assert r.status_code == 400 and "Linha 1" in r.json()["detail"]
    r = c.post("/api/jobs/youtube", json={"url": url, "mode": "ai", "start": "5:00", "end": "4:00"})
    assert r.status_code == 400 and "depois do início" in r.json()["detail"]
    assert c.post("/api/jobs/youtube", json={"url": url, "mode": "outro"}).status_code == 422
    j = c.post(
        "/api/jobs/youtube",
        json={"url": url, "mode": "parts", "start": "2:00", "end": "14:30", "part_seconds": 60},
    ).json()
    assert j["title"].startswith("Partes:") and j["params"]["part_label"] is True
    j = c.post(
        "/api/jobs/youtube", json={"url": url, "mode": "manual", "clips": "1:20-2:05 Melhor parte"}
    ).json()
    assert j["title"].startswith("Trechos:") and j["params"]["clips"] == "1:20-2:05 Melhor parte"
    p = c.post(
        "/api/youtube/preview", json={"mode": "manual", "clips": "1:20-2:05 Melhor\n10:00 a 10:45"}
    ).json()
    assert p["error"] == "" and [(x["start"], x["title"]) for x in p["clips"]] == [(80, "Melhor"), (600, "")]
    p = c.post(
        "/api/youtube/preview", json={"mode": "parts", "start": "2:00", "end": "14:30", "part_seconds": 60}
    ).json()
    assert p["error"] == "" and p["parts"] == 13
    assert (
        "depois do início"
        in c.post("/api/youtube/preview", json={"mode": "ai", "start": "5:00", "end": "4:00"}).json()["error"]
    )


def test_post_options_follow_tiktok_rules():
    from app import settings_store as st
    from app.db import Video, init_db, session_scope

    init_db()
    c = login(client())
    with session_scope() as s:
        v = Video(kind="anim2d", title="t", caption="c", file_path="x/v.mp4")
        s.add(v)
        s.flush()
        vid = v.id
    st.set_many({"tiktok_access_token": "tok"})
    try:
        r = c.post(
            f"/api/videos/{vid}/tiktok",
            json={"mode": "direct", "privacy": "SELF_ONLY", "brand_content": True},
        )
        assert r.status_code == 400 and "Só eu" in r.json()["detail"]
        assert c.post(f"/api/videos/{vid}/tiktok", json={"privacy": "TODO_MUNDO"}).status_code == 422
        j = c.post(
            f"/api/videos/{vid}/tiktok",
            json={
                "mode": "direct",
                "privacy": "PUBLIC_TO_EVERYONE",
                "brand_organic": True,
                "disable_comment": True,
            },
        ).json()
        assert j["kind"] == "tiktok_post" and j["params"]["video_id"] == vid
        assert j["params"]["brand_organic"] is True and j["params"]["brand_content"] is False
        assert j["params"]["disable_comment"] is True and j["params"]["privacy"] == "PUBLIC_TO_EVERYONE"
    finally:
        st.set_many({"tiktok_access_token": ""})
