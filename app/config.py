"""Configuração vinda das variáveis de ambiente (definidas na stack do Portainer)."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


def _read_secret(name: str, default: str = "") -> str:
    """Lê NAME ou NAME_FILE (para Docker secrets)."""
    file_path = os.getenv(f"{name}_FILE")
    if file_path and Path(file_path).exists():
        return Path(file_path).read_text().strip()
    return os.getenv(name, default)


@dataclass
class Config:
    app_name: str = "PostOp"
    version: str = field(default_factory=lambda: os.getenv("APP_VERSION", _version_file()))
    database_url: str = field(
        default_factory=lambda: _read_secret("DATABASE_URL", "sqlite:///./data/postop.db")
    )
    data_dir: Path = field(default_factory=lambda: Path(os.getenv("DATA_DIR", "./data")))
    admin_user: str = field(default_factory=lambda: os.getenv("ADMIN_USER", "admin"))
    admin_password: str = field(default_factory=lambda: _read_secret("ADMIN_PASSWORD", "admin"))
    secret_key: str = field(default_factory=lambda: _read_secret("SECRET_KEY", "dev-secret-change-me"))
    public_url: str = field(
        default_factory=lambda: os.getenv("PUBLIC_URL", "http://localhost:8000").rstrip("/")
    )
    session_days: int = field(default_factory=lambda: int(os.getenv("SESSION_DAYS", "7")))
    worker_poll_seconds: float = field(default_factory=lambda: float(os.getenv("WORKER_POLL_SECONDS", "3")))

    def insecure_defaults(self) -> list[str]:
        """Avisos de configuração insegura (aparecem no log ao subir)."""
        out = []
        weak = {"", "dev-secret-change-me", "gere-com-openssl-rand-hex-32"}
        if self.secret_key.startswith("TROQUE"):
            weak.add(self.secret_key)
        if self.secret_key in weak or len(self.secret_key) < 16:
            out.append("SECRET_KEY padrão/curta. Gere uma com: openssl rand -hex 32")
        if self.admin_password in {"admin", "troque-esta-senha", "TROQUE_SENHA_DO_PAINEL", ""}:
            out.append("ADMIN_PASSWORD padrão. Troque na stack.")
        if self.public_url.startswith("http://") and "localhost" not in self.public_url:
            out.append("PUBLIC_URL sem https: o TikTok exige https no Redirect URI.")
        return out

    @property
    def media_dir(self) -> Path:
        return self.data_dir / "media"

    @property
    def work_dir(self) -> Path:
        return self.data_dir / "work"

    @property
    def models_dir(self) -> Path:
        return self.data_dir / "models"

    @property
    def tiktok_redirect_uri(self) -> str:
        return f"{self.public_url}/api/tiktok/callback"


def _version_file() -> str:
    p = Path(__file__).resolve().parent.parent / "VERSION"
    return p.read_text().strip() if p.exists() else "dev"


config = Config()
