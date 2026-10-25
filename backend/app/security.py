"""Password hashing and signed tokens.

Access tokens are short-lived JWTs (HS256) that name the user, the sign-in session (sid) and the user's token_version (tv). They are only
accepted while that session is alive and tv still matches, so logout, password change and role removal take effect at once.
Refresh tokens and one-time tokens are random 256-bit strings; only their SHA-256 is stored.
"""
import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt

from . import config

# JWTs are signed with a key derived from SECRET_KEY so that no other HMAC use of SECRET_KEY (mail links, gateway callbacks) can mint one.
JWT_KEY = hmac.new(config.SECRET_KEY.encode(), b"flatwise:jwt:v1", hashlib.sha256).hexdigest()
MAX_PASSWORD_BYTES = 72  # bcrypt ignores (or, in newer versions, rejects) anything longer


def hash_password(pw: str) -> str:
    return bcrypt.hashpw(pw.encode()[:MAX_PASSWORD_BYTES], bcrypt.gensalt()).decode()


def verify_password(pw: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(pw.encode()[:MAX_PASSWORD_BYTES], hashed.encode())
    except ValueError:
        return False


_dummy: str | None = None


def verify_password_or_dummy(pw: str, hashed: str | None) -> bool:
    """Always spends one bcrypt check, so an unknown account takes as long as a wrong password (no user enumeration by timing)."""
    global _dummy
    if hashed is None:
        if _dummy is None:
            _dummy = hash_password(secrets.token_urlsafe(16))
        verify_password(pw, _dummy)
        return False
    return verify_password(pw, hashed)


def make_access_token(user_id: int, session_id: int, token_version: int) -> str:
    t = datetime.now(timezone.utc)
    claims = {"sub": str(user_id), "sid": session_id, "tv": token_version, "typ": "access", "jti": secrets.token_hex(8),
              "iat": t, "exp": t + timedelta(minutes=config.ACCESS_TOKEN_MINUTES)}
    return jwt.encode(claims, JWT_KEY, algorithm="HS256")


def read_access_token(token: str) -> dict | None:
    """Verified claims {uid, sid, tv}, or None. Expired, forged and wrong-type tokens all give None."""
    try:
        d = jwt.decode(token, JWT_KEY, algorithms=["HS256"], options={"require": ["exp", "sub", "sid", "tv"]})
        if d.get("typ") != "access":
            return None
        return {"uid": int(d["sub"]), "sid": int(d["sid"]), "tv": int(d["tv"])}
    except (jwt.PyJWTError, KeyError, ValueError, TypeError):
        return None


def new_secret_token() -> tuple[str, str]:
    """(raw, sha256 hex). Hand out the raw value once; store only the hash."""
    raw = secrets.token_urlsafe(32)
    return raw, hash_token(raw)


def hash_token(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()
