"""Settings loading and redacted validation (spec 13.2). Never prints secret values."""
from __future__ import annotations

import secrets
from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import make_url

BACKEND_DIR = Path(__file__).resolve().parents[2]
ENV_FILE = BACKEND_DIR / ".env"
PLACEHOLDERS = {"", "changeme", "change-me", "placeholder", "secret"}
SAFE_SSL = {"require", "verify-ca", "verify-full"}


class ConfigError(RuntimeError):
    pass


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=str(ENV_FILE), extra="ignore")

    app_env: str = "development"
    database_url: str = ""
    migration_database_url: str = ""
    session_pepper: str = ""
    artifact_root: str = "./artifacts"
    default_timezone: str = "Asia/Kolkata"
    default_currency: str = "INR"
    allowed_origins: str = "http://localhost:3000,http://127.0.0.1:3000"
    cookie_secure: bool = False
    log_level: str = "INFO"

    # Small pool per process; total connections must fit the Neon plan.
    pool_size: int = Field(5, ge=1)
    max_overflow: int = Field(0, ge=0)
    connect_timeout_s: int = Field(60, ge=1)  # Neon computes can take ~1 min to resume from idle

    @property
    def origins(self) -> list[str]:
        return [o.strip() for o in self.allowed_origins.split(",") if o.strip()]


def _psycopg_url(raw: str):
    """Parse a provider URL and force the psycopg3 dialect without echoing it."""
    return make_url(raw).set(drivername="postgresql+psycopg")


def async_database_url(s: Settings):
    return _psycopg_url(s.database_url)


def migration_database_url(s: Settings):
    return _psycopg_url(s.migration_database_url or s.database_url)


def config_report(s: Settings) -> dict[str, str]:
    """Return only 'configured' / 'missing' / redacted failure codes."""
    rep: dict[str, str] = {}
    for name in ("database_url", "migration_database_url"):
        val = getattr(s, name)
        if not val:
            rep[name] = "missing"
            continue
        try:
            u = _psycopg_url(val)
            if not (u.host and u.database):
                rep[name] = "invalid_url"
            elif u.query.get("sslmode") not in SAFE_SSL:
                rep[name] = "tls_not_enforced"
            else:
                rep[name] = "configured"
        except Exception:
            rep[name] = "invalid_url"
    rep["session_pepper"] = "missing" if s.session_pepper.lower() in PLACEHOLDERS else "configured"
    if s.app_env == "production":
        if not s.cookie_secure:
            rep["cookie_secure"] = "insecure_in_production"
        if "*" in s.allowed_origins or not s.origins:
            rep["allowed_origins"] = "unrestricted_in_production"
        if rep["session_pepper"] != "configured":
            rep["session_pepper"] = "placeholder_in_production"
    return rep


def ensure_dev_pepper() -> None:
    """Development only: generate SESSION_PEPPER locally into the git-ignored .env (never printed)."""
    s = get_settings()
    if s.app_env == "production" or s.session_pepper.lower() not in PLACEHOLDERS:
        return
    lines = ENV_FILE.read_text().splitlines() if ENV_FILE.exists() else []
    lines = [ln for ln in lines if not ln.startswith("SESSION_PEPPER=")]
    lines.append(f"SESSION_PEPPER={secrets.token_urlsafe(48)}")
    ENV_FILE.write_text("\n".join(lines) + "\n")
    get_settings.cache_clear()


@lru_cache
def get_settings() -> Settings:
    return Settings()
