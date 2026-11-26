"""Ligação com o TikTok (Content Posting API) com respostas simuladas, sem rede e sem banco."""

import json
import time

import pytest

from app import media, tiktok


class Resp:
    def __init__(self, body, status=200):
        self.status_code, self._body, self.text = status, body, json.dumps(body)

    def json(self):
        return self._body


OK = {"code": "ok", "message": ""}


class FakeClient:
    """Responde por final de URL; uma lista de respostas é usada em ordem."""

    def __init__(self, routes):
        self.routes, self.calls = routes, []

    def _answer(self, url):
        for suffix, answer in self.routes.items():
            if url.endswith(suffix):
                return answer.pop(0) if isinstance(answer, list) else answer
        raise AssertionError(f"URL inesperada: {url}")

    def request(self, method, url, headers=None, json=None, params=None, **_):
        self.calls.append((method, url, headers, json))
        return self._answer(url)

    def post(self, url, data=None, headers=None, **_):
        self.calls.append(("POST", url, headers, data))
        return self._answer(url)

    def put(self, url, content=None, headers=None, **_):
        self.calls.append(("PUT", url, headers, len(content)))
        return Resp({}, 201)

    def close(self):
        pass


@pytest.fixture
def store(monkeypatch):
    data = {"tiktok_access_token": "tok", "tiktok_expires_at": str(int(time.time()) + 3600)}
    monkeypatch.setattr(tiktok.st, "get", lambda key, db=None: data.get(key, ""))
    monkeypatch.setattr(
        tiktok.st, "set_many", lambda values, db=None: data.update({k: str(v) for k, v in values.items()})
    )
    return data


@pytest.fixture
def video(tmp_path, monkeypatch):
    f = tmp_path / "v.mp4"
    f.write_bytes(b"0" * 1000)
    monkeypatch.setattr(media, "duration_of", lambda p: 30.0)
    return f


CREATOR = Resp({"data": {"creator_username": "canal", "creator_nickname": "Canal",
                         "privacy_level_options": ["PUBLIC_TO_EVERYONE", "SELF_ONLY"], "duet_disabled": True,
                         "max_video_post_duration_sec": 60}, "error": OK})  # fmt: skip
INIT = Resp({"data": {"publish_id": "p1", "upload_url": "https://upload.example/u"}, "error": OK})


def test_utf16_trim_counts_like_tiktok():
    assert tiktok.utf16_trim("a" * 3000) == "a" * 2200
    emojis = tiktok.utf16_trim("😀" * 1500)
    assert len(emojis) == 1100 and len(emojis.encode("utf-16-le")) == 2 * 2200
    assert tiktok.utf16_trim("ok 😀", 4) == "ok "  # não corta um emoji no meio


def test_errors_are_explained():
    with pytest.raises(tiktok.TikTokError) as e:
        tiktok._check(
            Resp(
                {"error": {"code": "unaudited_client_can_only_post_to_private_accounts", "message": "x"}}, 403
            ),
            "Post",
        )
    assert "PRIVADA" in str(e.value) and e.value.code == "unaudited_client_can_only_post_to_private_accounts"
    with pytest.raises(tiktok.TikTokError) as e:
        tiktok._check(Resp({"error": "invalid_grant", "error_description": "expired"}, 400), "Token")
    assert e.value.code == "invalid_grant" and "Conecte a conta de novo" in str(e.value)
    with pytest.raises(tiktok.TikTokError, match="codigo_novo"):
        tiktok._check(Resp({"error": {"code": "codigo_novo", "message": "algo"}}, 400), "Post")
    assert tiktok._check(Resp({"data": {"a": 1}, "error": OK}), "x")["data"] == {"a": 1}


def test_keeps_the_latest_refresh_token(store):
    tiktok._save_tokens({"access_token": "a1", "refresh_token": "r1", "expires_in": 86400, "open_id": "o1",
                         "refresh_expires_in": 31536000, "scope": "video.publish"})  # fmt: skip
    tiktok._save_tokens({"access_token": "a2", "expires_in": 86400})  # sem refresh_token novo: mantém o atual
    assert store["tiktok_access_token"] == "a2" and store["tiktok_refresh_token"] == "r1"
    assert store["tiktok_open_id"] == "o1" and store["tiktok_scope"] == "video.publish"


def test_direct_post_sends_every_required_field(store, video):
    client = FakeClient({"/creator_info/query/": CREATOR, "/post/publish/video/init/": INIT})
    pid = tiktok.publish(
        video, "😀" * 1500, privacy="FOLLOWER_OF_CREATOR", is_aigc=True, brand_organic=True, client=client
    )
    assert pid == "p1" and store["tiktok_username"] == "canal"
    body = next(c[3] for c in client.calls if c[1].endswith("/post/publish/video/init/"))
    info = body["post_info"]
    assert info["privacy_level"] == "SELF_ONLY"  # a privacidade pedida não está nas opções da conta
    assert (
        info["brand_organic_toggle"] is True
        and info["brand_content_toggle"] is False
        and info["is_aigc"] is True
    )
    # dueto desligado na própria conta
    assert info["disable_duet"] is True and info["disable_comment"] is False
    assert len(info["title"]) == 1100  # 2.200 unidades UTF-16
    assert body["source_info"] == {
        "source": "FILE_UPLOAD",
        "video_size": 1000,
        "chunk_size": 1000,
        "total_chunk_count": 1,
    }
    put = next(c for c in client.calls if c[0] == "PUT")
    assert put[2]["Content-Range"] == "bytes 0-999/1000" and put[3] == 1000


def test_direct_post_checks_duration_and_branded_privacy(store, video, monkeypatch):
    monkeypatch.setattr(media, "duration_of", lambda p: 200.0)
    with pytest.raises(tiktok.TikTokError, match="até 60 s"):
        tiktok.publish(video, "t", client=FakeClient({"/creator_info/query/": CREATOR}))
    monkeypatch.setattr(media, "duration_of", lambda p: 30.0)
    with pytest.raises(tiktok.TikTokError, match="Só eu"):
        tiktok.publish(
            video,
            "t",
            privacy="SELF_ONLY",
            brand_content=True,
            client=FakeClient({"/creator_info/query/": CREATOR}),
        )


def test_inbox_upload_sends_only_the_file(store, video):
    client = FakeClient({"/post/publish/inbox/video/init/": INIT})
    assert tiktok.publish(video, "t", mode="inbox", client=client) == "p1"
    assert set(client.calls[0][3]) == {"source_info"}


def test_expired_token_is_renewed_and_the_call_retried(store):
    store.update(tiktok_refresh_token="r1", tiktok_client_key="k", tiktok_client_secret="s")
    bad = Resp({"error": {"code": "access_token_invalid", "message": "expired"}}, 401)
    done = Resp({"data": {"status": "PUBLISH_COMPLETE", "publicaly_available_post_id": [123]}, "error": OK})
    client = FakeClient({
        "/post/publish/status/fetch/": [bad, done],
        "/oauth/token/": Resp({"access_token": "new", "refresh_token": "r2", "expires_in": 86400, "refresh_expires_in": 9}),
    })  # fmt: skip
    data = tiktok.publish_status("p1", client=client)
    assert data["status"] == "PUBLISH_COMPLETE"
    assert store["tiktok_access_token"] == "new" and store["tiktok_refresh_token"] == "r2"
    auths = [c[2]["Authorization"] for c in client.calls if c[1].endswith("/status/fetch/")]
    assert auths == ["Bearer tok", "Bearer new"]
    store["tiktok_username"] = "canal"
    assert tiktok.post_url(data) == "https://www.tiktok.com/@canal/video/123"


def test_disconnect_revokes_access_on_tiktok(store, monkeypatch):
    store.update(tiktok_refresh_token="r1", tiktok_client_key="k", tiktok_client_secret="s")
    client = FakeClient({"/oauth/revoke/": Resp({})})
    monkeypatch.setattr(tiktok, "_client", lambda timeout=30.0: client)
    tiktok.disconnect()
    assert client.calls[0][1].endswith("/oauth/revoke/") and client.calls[0][3]["token"] == "tok"
    assert store["tiktok_access_token"] == "" and store["tiktok_refresh_token"] == ""
