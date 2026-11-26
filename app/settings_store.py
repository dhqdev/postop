"""Configurações editáveis pela tela "Configurações" (guardadas no Postgres).

Campos secretos (API key, tokens, client secret, cookies) são criptografados com
uma chave derivada de SECRET_KEY. Se você trocar SECRET_KEY, precisará salvar
esses campos de novo.
"""

from __future__ import annotations

import base64
import hashlib
from dataclasses import dataclass

from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy.orm import Session

from .config import config
from .db import Setting, session_scope


@dataclass(frozen=True)
class Field:
    key: str
    label: str
    default: str = ""
    secret: bool = False
    group: str = "geral"
    help: str = ""
    kind: str = "text"  # text | password | select | textarea | number
    options: tuple[str, ...] = ()


FIELDS: tuple[Field, ...] = (
    # --- OpenRouter ---
    Field(
        "openrouter_api_key",
        "OpenRouter API key",
        secret=True,
        group="openrouter",
        kind="password",
        help="Crie em https://openrouter.ai/keys. Fica criptografada no banco.",
    ),
    Field(
        "text_model",
        "Modelo de texto (escolher cortes / roteiro do vídeo 3D)",
        "google/gemini-2.5-flash-lite",
        group="openrouter",
        help="Barato (US$ 0,10/0,40 por milhão de tokens) e bom com JSON. Para zero custo use openrouter/free.",
    ),
    Field(
        "text_fallback_model",
        "Modelo de texto reserva",
        "openrouter/free",
        group="openrouter",
        help="Usado se o principal falhar. 'openrouter/free' sorteia um modelo grátis (50 pedidos/dia sem créditos).",
    ),
    # --- Vídeo / legendas ---
    Field(
        "whisper_model",
        "Modelo de transcrição (local, grátis)",
        "small",
        group="video",
        kind="select",
        options=("tiny", "base", "small", "medium", "turbo"),
        help="Roda no servidor, sem custo. 'small' é o equilíbrio para português; 'turbo' (large-v3-turbo) "
        "é o mais preciso, mas pede ~2 GB de RAM e é bem mais lento em CPU.",
    ),
    Field(
        "whisper_language",
        "Idioma do áudio",
        "pt",
        group="video",
        help="Código do idioma (pt, en, es...) ou 'auto'.",
    ),
    Field(
        "subtitle_style",
        "Estilo da legenda",
        "highlight",
        group="video",
        kind="select",
        options=("highlight", "simple", "none"),
        help="highlight = palavra atual em amarelo (estilo TikTok).",
    ),
    Field("subtitle_color", "Cor de destaque (hex)", "#FFE14D", group="video"),
    Field(
        "youtube_cookies",
        "Cookies do YouTube (cookies.txt)",
        secret=True,
        group="video",
        kind="textarea",
        help="Opcional. Cole o cookies.txt se o YouTube bloquear downloads do servidor.",
    ),
    # --- TikTok ---
    Field("tiktok_client_key", "TikTok Client Key", group="tiktok"),
    Field("tiktok_client_secret", "TikTok Client Secret", secret=True, group="tiktok", kind="password"),
    Field(
        "tiktok_default_mode",
        "Modo de envio padrão",
        "direct",
        group="tiktok",
        kind="select",
        options=("direct", "inbox"),
        help="direct = publica direto; inbox = vai para rascunhos/notificações do app do TikTok.",
    ),
    Field(
        "tiktok_default_privacy",
        "Privacidade padrão",
        "SELF_ONLY",
        group="tiktok",
        kind="select",
        options=("SELF_ONLY", "MUTUAL_FOLLOW_FRIENDS", "FOLLOWER_OF_CREATOR", "PUBLIC_TO_EVERYONE"),
        help="Usada nos posts automáticos. Enquanto o app não for aprovado pelo TikTok, só SELF_ONLY funciona "
        "(e a conta do TikTok precisa estar privada).",
    ),
)

# Chaves internas (não aparecem no formulário)
INTERNAL_SECRET_KEYS = {"tiktok_access_token", "tiktok_refresh_token"}
INTERNAL_KEYS = INTERNAL_SECRET_KEYS | {
    "tiktok_open_id",
    "tiktok_expires_at",
    "tiktok_refresh_expires_at",
    "tiktok_scope",
    "tiktok_display_name",
    "tiktok_avatar_url",
    "tiktok_username",
}

FIELD_MAP = {f.key: f for f in FIELDS}

# Modelos que saíram do OpenRouter -> substituto. Vale também para valores já salvos.
RETIRED_MODELS: dict[str, str] = {}
MODEL_KEYS = {"text_model", "text_fallback_model"}


def _fernet() -> Fernet:
    digest = hashlib.sha256(("postop-settings:" + config.secret_key).encode()).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def encrypt(value: str) -> str:
    return _fernet().encrypt(value.encode()).decode()


def decrypt(value: str) -> str:
    try:
        return _fernet().decrypt(value.encode()).decode()
    except InvalidToken:
        return ""


def _is_secret(key: str) -> bool:
    f = FIELD_MAP.get(key)
    return bool(f and f.secret) or key in INTERNAL_SECRET_KEYS


def get(key: str, db: Session | None = None) -> str:
    def _get(s: Session) -> str:
        row = s.get(Setting, key)
        if row is None or row.value == "":
            f = FIELD_MAP.get(key)
            return f.default if f else ""
        value = decrypt(row.value) if row.encrypted else row.value
        return RETIRED_MODELS.get(value, value) if key in MODEL_KEYS else value

    if db is not None:
        return _get(db)
    with session_scope() as s:
        return _get(s)


def get_many(keys: list[str] | None = None) -> dict[str, str]:
    keys = keys or [f.key for f in FIELDS]
    with session_scope() as s:
        return {k: get(k, s) for k in keys}


def set_many(values: dict[str, str], db: Session | None = None) -> None:
    def _set(s: Session) -> None:
        for key, value in values.items():
            if key not in FIELD_MAP and key not in INTERNAL_KEYS:
                continue
            value = "" if value is None else str(value)
            secret = _is_secret(key)
            row = s.get(Setting, key)
            stored = encrypt(value) if (secret and value) else value
            if row is None:
                s.add(Setting(key=key, value=stored, encrypted=secret and bool(value)))
            else:
                row.value = stored
                row.encrypted = secret and bool(value)

    if db is not None:
        _set(db)
        db.commit()
        return
    with session_scope() as s:
        _set(s)


def public_view() -> list[dict]:
    """Valores para a tela. Segredos aparecem só como 'definido' e últimos 4 caracteres."""
    values = get_many()
    out = []
    for f in FIELDS:
        v = values.get(f.key, "")
        item = {
            "key": f.key,
            "label": f.label,
            "group": f.group,
            "help": f.help,
            "kind": f.kind,
            "options": list(f.options),
            "secret": f.secret,
            "default": f.default,
        }
        if f.secret:
            item["value"] = ""
            item["is_set"] = bool(v)
            item["hint"] = (
                ("••••" + v[-4:])
                if (v and f.kind == "password" and len(v) > 8)
                else ("definido" if v else "")
            )
        else:
            item["value"] = v
        out.append(item)
    return out
