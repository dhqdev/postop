"""Integração com a TikTok Content Posting API (OAuth + upload de vídeo)."""

from __future__ import annotations

import time
from pathlib import Path
from urllib.parse import urlencode

import httpx

from . import settings_store as st
from .config import config

AUTH_URL = "https://www.tiktok.com/v2/auth/authorize/"
API = "https://open.tiktokapis.com/v2"
SCOPES = "user.info.basic,video.publish,video.upload"
MIN_CHUNK = 5 * 1024 * 1024
MAX_SINGLE = 64 * 1024 * 1024
CHUNK = 10 * 1024 * 1024


class TikTokError(RuntimeError):
    pass


def authorize_url(state: str) -> str:
    key = st.get("tiktok_client_key")
    if not key:
        raise TikTokError("Preencha o Client Key do TikTok em Configurações > TikTok.")
    q = {
        "client_key": key,
        "scope": SCOPES,
        "response_type": "code",
        "redirect_uri": config.tiktok_redirect_uri,
        "state": state,
    }
    return f"{AUTH_URL}?{urlencode(q)}"


def _check(resp: httpx.Response, what: str) -> dict:
    try:
        body = resp.json()
    except Exception as exc:
        raise TikTokError(f"{what}: HTTP {resp.status_code} {resp.text[:300]}") from exc
    err = body.get("error")
    if isinstance(err, dict) and err.get("code") not in (None, "ok"):
        raise TikTokError(f"{what}: {err.get('code')} - {err.get('message')}")
    if isinstance(err, str) and err:
        raise TikTokError(f"{what}: {err} - {body.get('error_description', '')}")
    if resp.status_code >= 400:
        raise TikTokError(f"{what}: HTTP {resp.status_code} {body}")
    return body


def _save_tokens(body: dict) -> None:
    now = int(time.time())
    st.set_many(
        {
            "tiktok_access_token": body["access_token"],
            "tiktok_refresh_token": body.get("refresh_token", ""),
            "tiktok_open_id": body.get("open_id", ""),
            "tiktok_scope": body.get("scope", ""),
            "tiktok_expires_at": str(now + int(body.get("expires_in", 86400))),
            "tiktok_refresh_expires_at": str(now + int(body.get("refresh_expires_in", 0) or 0)),
        }
    )


def exchange_code(code: str, client: httpx.Client | None = None) -> dict:
    client = client or httpx.Client(timeout=30)
    resp = client.post(
        f"{API}/oauth/token/",
        data={
            "client_key": st.get("tiktok_client_key"),
            "client_secret": st.get("tiktok_client_secret"),
            "code": code,
            "grant_type": "authorization_code",
            "redirect_uri": config.tiktok_redirect_uri,
        },
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    body = _check(resp, "Token TikTok")
    _save_tokens(body)
    try:
        info = user_info(client)
        st.set_many(
            {
                "tiktok_display_name": info.get("display_name", ""),
                "tiktok_avatar_url": info.get("avatar_url", ""),
            }
        )
    except TikTokError:
        pass
    return body


def refresh(client: httpx.Client | None = None) -> str:
    client = client or httpx.Client(timeout=30)
    rt = st.get("tiktok_refresh_token")
    if not rt:
        raise TikTokError("Conta do TikTok não conectada.")
    resp = client.post(
        f"{API}/oauth/token/",
        data={
            "client_key": st.get("tiktok_client_key"),
            "client_secret": st.get("tiktok_client_secret"),
            "grant_type": "refresh_token",
            "refresh_token": rt,
        },
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    body = _check(resp, "Renovar token TikTok")
    _save_tokens(body)
    return body["access_token"]


def access_token(client: httpx.Client | None = None) -> str:
    token = st.get("tiktok_access_token")
    if not token:
        raise TikTokError("Conta do TikTok não conectada. Vá em Configurações > TikTok > Conectar.")
    try:
        expires = int(st.get("tiktok_expires_at") or 0)
    except ValueError:
        expires = 0
    if expires and expires - time.time() < 300:
        token = refresh(client)
    return token


def disconnect() -> None:
    st.set_many({k: "" for k in st.INTERNAL_KEYS})


def status() -> dict:
    connected = bool(st.get("tiktok_access_token"))
    return {
        "configured": bool(st.get("tiktok_client_key") and st.get("tiktok_client_secret")),
        "connected": connected,
        "display_name": st.get("tiktok_display_name"),
        "avatar_url": st.get("tiktok_avatar_url"),
        "scope": st.get("tiktok_scope"),
        "redirect_uri": config.tiktok_redirect_uri,
        "expires_at": st.get("tiktok_expires_at"),
    }


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json; charset=UTF-8"}


def user_info(client: httpx.Client | None = None) -> dict:
    client = client or httpx.Client(timeout=30)
    resp = client.get(
        f"{API}/user/info/",
        params={"fields": "open_id,avatar_url,display_name"},
        headers=_auth(access_token(client)),
    )
    return _check(resp, "Usuário TikTok").get("data", {}).get("user", {})


def creator_info(client: httpx.Client | None = None) -> dict:
    client = client or httpx.Client(timeout=30)
    resp = client.post(
        f"{API}/post/publish/creator_info/query/", headers=_auth(access_token(client)), json={}
    )
    return _check(resp, "Creator info").get("data", {})


def chunk_plan(size: int) -> tuple[int, int]:
    """(chunk_size, total_chunk_count) segundo as regras da API."""
    if size <= MAX_SINGLE:
        return size, 1
    count = size // CHUNK
    return CHUNK, count


def upload(upload_url: str, path: Path, client: httpx.Client) -> None:
    size = path.stat().st_size
    chunk_size, count = chunk_plan(size)
    with path.open("rb") as fh:
        for i in range(count):
            start = i * chunk_size
            end = size - 1 if i == count - 1 else start + chunk_size - 1
            fh.seek(start)
            data = fh.read(end - start + 1)
            resp = client.put(
                upload_url,
                content=data,
                headers={
                    "Content-Type": "video/mp4",
                    "Content-Length": str(len(data)),
                    "Content-Range": f"bytes {start}-{end}/{size}",
                },
            )
            if resp.status_code not in (200, 201, 206):
                raise TikTokError(
                    f"Upload falhou (parte {i + 1}/{count}): HTTP {resp.status_code} {resp.text[:300]}"
                )


def publish(
    path: Path,
    title: str,
    mode: str = "direct",
    privacy: str = "SELF_ONLY",
    disable_comment: bool = False,
    disable_duet: bool = False,
    disable_stitch: bool = False,
    is_aigc: bool = False,
    client: httpx.Client | None = None,
) -> str:
    """Envia o vídeo. Retorna o publish_id."""
    client = client or httpx.Client(timeout=httpx.Timeout(60, write=600, read=120))
    token = access_token(client)
    size = path.stat().st_size
    chunk_size, count = chunk_plan(size)
    source = {
        "source": "FILE_UPLOAD",
        "video_size": size,
        "chunk_size": chunk_size,
        "total_chunk_count": count,
    }
    if mode == "inbox":
        url = f"{API}/post/publish/inbox/video/init/"
        payload: dict = {"source_info": source}
    else:
        info = creator_info(client)
        options = info.get("privacy_level_options") or []
        if options and privacy not in options:
            privacy = "SELF_ONLY" if "SELF_ONLY" in options else options[0]
        url = f"{API}/post/publish/video/init/"
        payload = {
            "post_info": {
                "title": title[:2200],
                "privacy_level": privacy,
                "disable_comment": disable_comment or bool(info.get("comment_disabled")),
                "disable_duet": disable_duet or bool(info.get("duet_disabled")),
                "disable_stitch": disable_stitch or bool(info.get("stitch_disabled")),
                "video_cover_timestamp_ms": 1000,
                "is_aigc": is_aigc,
            },
            "source_info": source,
        }
    body = _check(client.post(url, headers=_auth(token), json=payload), "Iniciar post TikTok")
    data = body.get("data", {})
    publish_id, upload_url = data.get("publish_id"), data.get("upload_url")
    if not publish_id or not upload_url:
        raise TikTokError(f"Resposta inesperada do TikTok: {body}")
    upload(upload_url, path, client)
    return publish_id


def publish_status(publish_id: str, client: httpx.Client | None = None) -> dict:
    client = client or httpx.Client(timeout=30)
    resp = client.post(
        f"{API}/post/publish/status/fetch/",
        headers=_auth(access_token(client)),
        json={"publish_id": publish_id},
    )
    return _check(resp, "Status do post").get("data", {})
