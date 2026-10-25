"""Sign-in sessions: create, refresh (rotating tokens with reuse detection), revoke.

One AuthSession row = one signed-in device. The refresh token is a random 256-bit value; only its SHA-256 is stored. Each refresh replaces
it. Presenting an older token (a stolen copy) after the grace window revokes the whole session. A second tab that races the first within
the grace window is not punished: it just gets a fresh access token.
"""
import re
from datetime import timedelta, timezone

from fastapi import Request, Response
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from .. import config
from ..audit import audit
from ..models.core import User, now
from ..models.security import AuthSession
from ..netutil import client_ip
from ..security import hash_token, make_access_token, new_secret_token

COOKIE = "fw_refresh"
COOKIE_PATH = "/api/auth"
GRACE_SECONDS = 20


def _aware(d):
    return d.replace(tzinfo=timezone.utc) if d is not None and d.tzinfo is None else d


def device_label(ua: str, given: str = "") -> str:
    if given.strip():
        return re.sub(r"[\x00-\x1f<>]", "", given.strip())[:80]
    ua = ua or ""
    browser = next((n for n, rx in (("Edge", r"Edg/"), ("Opera", r"OPR/|Opera"), ("Firefox", r"Firefox/"), ("Chrome", r"Chrome/|CriOS/"), ("Safari", r"Safari/")) if re.search(rx, ua)), "")
    system = next((n for n, rx in (("Android", r"Android"), ("iPhone", r"iPhone"), ("iPad", r"iPad"), ("Windows", r"Windows"), ("Mac", r"Macintosh|Mac OS"), ("Linux", r"Linux|X11")) if re.search(rx, ua)), "")
    return f"{browser or 'Browser'} on {system}" if system else (browser or "Unknown device")


def _expiry():
    return now() + timedelta(days=config.REFRESH_TOKEN_DAYS)


def start(db: Session, user: User, request: Request, device: str = "") -> tuple[AuthSession, str]:
    raw, h = new_secret_token()
    s = AuthSession(user_id=user.id, token_hash=h, device=device_label(request.headers.get("user-agent", ""), device), ip=client_ip(request),
                    user_agent=request.headers.get("user-agent", "")[:200], expires_at=_expiry())
    db.add(s)
    db.flush()
    return s, raw


def payload(user: User, sess: AuthSession, raw_refresh: str | None) -> dict:
    out = {"token": make_access_token(user.id, sess.id, user.token_version), "token_type": "bearer", "expires_in": config.ACCESS_TOKEN_MINUTES * 60,
           "must_change_password": bool(user.must_change_password)}
    if raw_refresh:
        out["refresh_token"] = raw_refresh
    return out


def set_cookie(response: Response, raw_refresh: str, secure: bool | None = None) -> None:
    if not config.REFRESH_COOKIE:
        return
    response.set_cookie(COOKIE, raw_refresh, max_age=config.REFRESH_TOKEN_DAYS * 86400, path=COOKIE_PATH, httponly=True,
                        samesite="lax", secure=config.PRODUCTION if secure is None else secure)


def clear_cookie(response: Response) -> None:
    response.delete_cookie(COOKIE, path=COOKIE_PATH, httponly=True, samesite="lax", secure=config.PRODUCTION)


def login_tokens(db: Session, user: User, request: Request, response: Response, device: str = "") -> dict:
    sess, raw = start(db, user, request, device)
    set_cookie(response, raw)
    return payload(user, sess, raw)


def revoke(db: Session, sess: AuthSession, reason: str) -> None:
    if sess.revoked_at is None:
        sess.revoked_at, sess.revoked_reason = now(), reason


def revoke_all(db: Session, user_id: int, reason: str, *, bump: bool = True, keep: int | None = None) -> int:
    """Signs the person out everywhere (except session `keep`). bump=True also invalidates every access token already issued."""
    q = update(AuthSession).where(AuthSession.user_id == user_id, AuthSession.revoked_at.is_(None))
    if keep is not None:
        q = q.where(AuthSession.id != keep)
    n = db.execute(q.values(revoked_at=now(), revoked_reason=reason)).rowcount
    if bump:
        u = db.get(User, user_id)
        if u:
            u.token_version = (u.token_version or 0) + 1
    return n or 0


class RefreshError(Exception):
    pass


def refresh(db: Session, raw: str, request: Request) -> tuple[User, AuthSession, str | None]:
    """Validate and rotate. Returns (user, session, new_raw_refresh). new_raw_refresh is None inside the grace window (the other tab already got it)."""
    h = hash_token(raw)
    s = db.scalar(select(AuthSession).where(AuthSession.token_hash == h).with_for_update())
    t = now()
    if s is not None:
        user = db.get(User, s.user_id)
        if s.revoked_at is not None or _aware(s.expires_at) < t or not user or not user.is_active:
            raise RefreshError()
        new_raw, new_hash = new_secret_token()
        s.prev_hash, s.token_hash, s.rotated_at, s.last_used_at = s.token_hash, new_hash, t, t
        s.ip = client_ip(request)
        s.expires_at = _expiry()
        return user, s, new_raw
    old = db.scalar(select(AuthSession).where(AuthSession.prev_hash == h).with_for_update())
    if old is None or old.revoked_at is not None:
        raise RefreshError()
    user = db.get(User, old.user_id)
    if old.rotated_at is not None and (t - _aware(old.rotated_at)).total_seconds() <= GRACE_SECONDS and user and user.is_active:
        return user, old, None
    revoke(db, old, "refresh_reuse")
    audit(db, user_id=old.user_id, action="auth.refresh_reuse", entity="session", entity_id=old.id, meta={"ip": client_ip(request), "device": old.device})
    db.commit()
    raise RefreshError()
