"""Login único da plataforma (usuário/senha definidos na stack)."""

from __future__ import annotations

import hmac
import time
from collections import defaultdict

from fastapi import HTTPException, Request
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

from .config import config

COOKIE_NAME = "postop_session"
_serializer = URLSafeTimedSerializer(config.secret_key, salt="postop-session")
_failures: dict[str, list[float]] = defaultdict(list)


def check_credentials(username: str, password: str) -> bool:
    ok_user = hmac.compare_digest(username.encode(), config.admin_user.encode())
    ok_pass = hmac.compare_digest(password.encode(), config.admin_password.encode())
    return ok_user and ok_pass


def too_many_failures(ip: str) -> bool:
    now = time.time()
    _failures[ip] = [t for t in _failures[ip] if now - t < 600]
    return len(_failures[ip]) >= 10


def register_failure(ip: str) -> None:
    _failures[ip].append(time.time())


def client_ip(request: Request) -> str:
    """IP real do cliente atrás do Traefik.

    O Traefik ACRESCENTA o IP de quem conectou no fim do X-Forwarded-For; o começo
    do cabeçalho pode ser inventado pelo cliente (e burlaria o limite de tentativas).
    """
    xff = request.headers.get("x-forwarded-for", "")
    parts = [p.strip() for p in xff.split(",") if p.strip()]
    if parts:
        return parts[-1]
    return request.client.host if request.client else "?"


def make_token(username: str) -> str:
    return _serializer.dumps({"u": username})


def read_token(token: str) -> str | None:
    try:
        data = _serializer.loads(token, max_age=config.session_days * 86400)
    except (BadSignature, SignatureExpired):
        return None
    user = data.get("u") if isinstance(data, dict) else None
    return user if user == config.admin_user else None


def current_user(request: Request) -> str | None:
    token = request.cookies.get(COOKIE_NAME)
    return read_token(token) if token else None


def require_user(request: Request) -> str:
    user = current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Não autenticado")
    return user


def cookie_secure() -> bool:
    return config.public_url.startswith("https://")
