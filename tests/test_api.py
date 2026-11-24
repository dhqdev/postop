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
    ok = c.post("/api/jobs/prompt3d", json={"prompt": "abc", "style": "x", "custom_style": "glossy toys"})
    assert ok.status_code == 200


def test_index_uses_versioned_assets():
    html = client().get("/").text
    assert "/static/app.js?v=" in html and "{{v}}" not in html
