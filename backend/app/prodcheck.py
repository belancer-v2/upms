"""Production safety checks. In ENV=production the API refuses to start with unsafe settings.

`problems()` returns a list of human readable problems (empty list = safe). `enforce()` raises SystemExit
with the full list. `forbid_in_production()` guards demo-only code paths (seeding, demo accounts).
"""
import base64
import os

from . import config

DEFAULT_SECRET = "dev-only-change-me-flatwise-secret-key-32b"
REQUIRED_ENV = ("SECRET_KEY", "NID_KEY", "DATABASE_URL", "APP_URL")


def problems(env: dict | None = None) -> list[str]:
    """Checks the live config module; `env` is only used to tell 'missing' from 'defaulted'."""
    env = os.environ if env is None else env
    out: list[str] = []
    for name in REQUIRED_ENV:
        if not env.get(name, "").strip():
            out.append(f"{name} is not set (required in production)")
    if config.SECRET_KEY == DEFAULT_SECRET:
        out.append("SECRET_KEY is the built-in development default; set a random value of 32+ characters")
    elif len(config.SECRET_KEY) < 32:
        out.append("SECRET_KEY is shorter than 32 characters")
    if config.DEMO:
        out.append("DEMO=1 is not allowed (demo accounts and seeding must stay off)")
    if not config.NID_KEY:
        out.append("NID_KEY is empty; NID numbers would be encrypted with a key derived from SECRET_KEY")
    else:
        try:
            if len(base64.urlsafe_b64decode(config.NID_KEY.encode())) != 32:
                raise ValueError
        except Exception:
            out.append("NID_KEY is not a valid Fernet key (urlsafe base64 of 32 bytes); generate one with: python -c \"from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())\"")
    if "*" in config.CORS_ORIGINS:
        out.append("CORS_ORIGINS contains '*' (wildcard); list the exact web origins")
    if config.DATABASE_URL.startswith("sqlite"):
        out.append("DATABASE_URL points at SQLite; use MySQL/MariaDB (mysql://user:pass@localhost/db) or PostgreSQL (postgresql://user:pass@host:5432/db)")
    elif not config.DATABASE_URL.startswith(("mysql", "postgresql")):
        out.append("DATABASE_URL must be a mysql:// or postgresql:// URL")
    app_url = env.get("APP_URL", "")
    if app_url and not app_url.startswith("https://"):
        out.append("APP_URL must be the public https:// address of the web app")
    return out


def enforce() -> None:
    if not config.PRODUCTION:
        return
    bad = problems()
    if bad:
        msg = "FlatWise refuses to start in ENV=production:\n" + "\n".join(f"  - {b}" for b in bad)
        raise SystemExit(msg)


def forbid_in_production(what: str) -> None:
    if config.PRODUCTION:
        raise RuntimeError(f"{what} is disabled when ENV=production")
