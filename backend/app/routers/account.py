"""Account security: token refresh, sign-out, password change / reset, e-mail verification, the Sessions list, audit-chain check.

Browsers keep the refresh token in an HttpOnly, SameSite=Lax cookie scoped to /api/auth. The cookie is only honoured together with the
header X-Requested-With: fetch (a cross-site page cannot add it without a CORS pre-flight), which is the CSRF protection. API clients may
send the refresh token in the JSON body instead; that needs no CSRF check because a forged request cannot know the token.
"""
import re

from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import auditchain, config
from ..audit import audit
from ..db import get_db
from ..deps import current_auth, require_saas
from ..models.core import Membership, User, now
from ..models.saas import Subscription
from ..models.security import AuthSession
from ..netutil import client_ip
from ..security import hash_password, hash_token, read_access_token, verify_password
from ..services import antispam, authmail, passwords, ratelimit, sessions

router = APIRouter(prefix="/api", tags=["account"])
NEUTRAL_RESET = "If an account matches, we have sent a link to reset the password."
BAD_LINK = "This link is not valid or has expired."


# ------------------------------------------------------------------ refresh / logout
class RefreshIn(BaseModel):
    refresh_token: str = Field(default="", max_length=200)


def _source(request: Request, body: RefreshIn | None) -> tuple[str, bool]:
    """(refresh token, came_from_cookie)."""
    if body and body.refresh_token:
        return body.refresh_token, False
    return request.cookies.get(sessions.COOKIE, ""), True


def _expired() -> JSONResponse:
    r = JSONResponse({"detail": "Your session has ended. Please sign in again."}, status_code=401)
    sessions.clear_cookie(r)
    return r


@router.post("/auth/refresh", dependencies=[Depends(ratelimit.limit("refresh", 120, 600))])
def refresh(request: Request, response: Response, body: RefreshIn | None = None, x_requested_with: str = Header(default=""), db: Session = Depends(get_db)):
    raw, from_cookie = _source(request, body)
    if not raw:
        return _expired()
    if from_cookie and x_requested_with.lower() != "fetch":
        raise HTTPException(403, "Missing request header")      # CSRF guard for the cookie path
    try:
        user, sess, new_raw = sessions.refresh(db, raw, request)
    except sessions.RefreshError:
        db.rollback()
        return _expired()
    db.commit()
    if new_raw and from_cookie:
        sessions.set_cookie(response, new_raw)
    return sessions.payload(user, sess, new_raw)


@router.post("/auth/logout")
def logout(request: Request, response: Response, body: RefreshIn | None = None, authorization: str = Header(default=""), db: Session = Depends(get_db)):
    """Revokes this device's session (found by the access token, or by the refresh token when the access token has expired). Always succeeds."""
    scheme, _, tok = authorization.partition(" ")
    claims = read_access_token(tok.strip()) if scheme.lower() == "bearer" else None
    sess = db.get(AuthSession, claims["sid"]) if claims else None
    if sess is not None and claims and sess.user_id != claims["uid"]:
        sess = None
    if sess is None:
        raw, _c = _source(request, body)
        if raw:
            h = hash_token(raw)
            sess = db.scalar(select(AuthSession).where((AuthSession.token_hash == h) | (AuthSession.prev_hash == h)))
    if sess is not None and sess.revoked_at is None:
        sessions.revoke(db, sess, "logout")
        audit(db, user_id=sess.user_id, action="auth.logout", entity="session", entity_id=sess.id)
        db.commit()
    sessions.clear_cookie(response)
    return {"ok": True}


# ------------------------------------------------------------------ change / reset password
class ChangeIn(BaseModel):
    current_password: str = Field(max_length=200)
    new_password: str = Field(max_length=200)


@router.post("/auth/change-password")
def change_password(body: ChangeIn, request: Request, response: Response, auth: tuple[User, AuthSession] = Depends(current_auth), db: Session = Depends(get_db)):
    """Needs the current password. Signs every other device out and returns fresh tokens for this one. Allowed while a password change is forced."""
    user, _sess = auth
    key = f"chpw:{user.id}"
    wait = ratelimit.locked_for(key)
    if wait:
        raise ratelimit.too_many(wait, "Too many wrong passwords. Please wait a few minutes.")
    if not verify_password(body.current_password, user.password_hash):
        ratelimit.fail(key, 5, 900, 60, 1800)
        raise HTTPException(400, "Your current password is not right.")
    if body.new_password == body.current_password:
        raise HTTPException(422, "Choose a password you have not used just now.")
    bad = passwords.check(body.new_password, email=user.email, name=user.name, phone=user.phone)
    if bad:
        raise HTTPException(422, bad)
    ratelimit.clear(key)
    user.password_hash, user.must_change_password, user.password_changed_at = hash_password(body.new_password), False, now()
    sessions.revoke_all(db, user.id, "password_change")
    toks = sessions.login_tokens(db, user, request, response)
    audit(db, user_id=user.id, action="auth.password_change", entity="user", entity_id=user.id, meta={"ip": client_ip(request)})
    db.commit()
    return toks


class ForgotIn(BaseModel):
    identifier: str = Field(min_length=3, max_length=160)   # e-mail address or mobile number


def _find_by_identifier(db: Session, ident: str) -> User | None:
    if "@" in ident:
        return db.scalar(select(User).where(User.email == ident.lower(), User.is_active == True))  # noqa: E712
    digits = re.sub(r"\D", "", ident)
    if len(digits) < 7:
        return None
    tail = digits[-10:]
    hits = [u for u in db.scalars(select(User).where(User.phone.like(f"%{digits[-4:]}%"), User.is_active == True))  # noqa: E712
            if re.sub(r"\D", "", u.phone or "")[-10:] == tail]
    return hits[0] if len(hits) == 1 else None      # a number shared by two accounts is ambiguous: send nothing


@router.post("/auth/forgot-password", dependencies=[Depends(ratelimit.limit("forgot", 8, 3600))])
def forgot_password(body: ForgotIn, request: Request, db: Session = Depends(get_db)):
    """Always answers the same, whether or not the account exists. At most 3 links per hour per account, 8 per hour per address."""
    out = {"ok": True, "message": NEUTRAL_RESET}
    ident = body.identifier.strip()
    if ratelimit.consume(f"forgot:id:{ratelimit.hkey(ident)}", 3, 3600):
        return out
    user = _find_by_identifier(db, ident)
    if not user:
        return out
    ip = client_ip(request)
    raw = authmail.issue(db, user, "reset", ip)
    sent = authmail.send_email(db, user, "reset", raw) if "@" in ident else authmail.send_sms(db, user, "reset", raw)
    audit(db, user_id=user.id, action="auth.reset_requested", entity="user", entity_id=user.id, meta={"via": "email" if "@" in ident else "sms", "sent": sent, "ip": ip})
    db.commit()
    if config.DEMO and not config.PRODUCTION:
        out["demo_link"] = authmail.link("reset", raw)       # demo only: there is no real mailbox. Never present in production.
    return out


class ResetIn(BaseModel):
    token: str = Field(min_length=10, max_length=200)
    new_password: str = Field(max_length=200)


@router.post("/auth/reset-password", dependencies=[Depends(ratelimit.limit("reset", 15, 3600))])
def reset_password(body: ResetIn, request: Request, db: Session = Depends(get_db)):
    tok = authmail.find(db, body.token, "reset")
    user = db.get(User, tok.user_id) if tok else None
    if not tok or not user or not user.is_active:
        raise HTTPException(400, BAD_LINK)
    bad = passwords.check(body.new_password, email=user.email, name=user.name, phone=user.phone)
    if bad:
        raise HTTPException(422, bad)
    tok.used_at = now()
    user.password_hash, user.must_change_password, user.password_changed_at = hash_password(body.new_password), False, now()
    sessions.revoke_all(db, user.id, "password_reset")
    ratelimit.clear(f"login:a:{ratelimit.hkey(user.email)}")
    audit(db, user_id=user.id, action="auth.password_reset", entity="user", entity_id=user.id, meta={"ip": client_ip(request)})
    db.commit()
    return {"ok": True}


# ------------------------------------------------------------------ e-mail verification
class TokenIn(BaseModel):
    token: str = Field(min_length=10, max_length=200)


@router.post("/auth/verify-email", dependencies=[Depends(ratelimit.limit("verify", 30, 3600))])
def verify_email(body: TokenIn, db: Session = Depends(get_db)):
    """Confirms the address and starts the free trial clock for the buildings this person signed up."""
    from datetime import timedelta
    tok = authmail.find(db, body.token, "verify")
    user = db.get(User, tok.user_id) if tok else None
    if not tok or not user:
        raise HTTPException(400, BAD_LINK)
    tok.used_at = now()
    if not user.email_verified:
        user.email_verified = True
        from .public import TRIAL_DAYS
        for m in db.scalars(select(Membership).where(Membership.user_id == user.id, Membership.role == "PROPERTY_ADMIN")):
            sub = db.scalar(select(Subscription).where(Subscription.org_id == m.org_id).order_by(Subscription.id.desc()))
            if sub and sub.status == "trial":
                sub.trial_ends = now() + timedelta(days=TRIAL_DAYS)
    audit(db, user_id=user.id, action="auth.email_verified", entity="user", entity_id=user.id)
    db.commit()
    return {"ok": True}


class ResendIn(BaseModel):
    email: str = Field(min_length=5, max_length=160)


@router.post("/auth/resend-verification", dependencies=[Depends(ratelimit.limit("resend", 8, 3600))])
def resend_verification(body: ResendIn, request: Request, db: Session = Depends(get_db)):
    out = {"ok": True, "message": "If this address is waiting for confirmation, we have sent the link again."}
    email = body.email.strip().lower()
    if ratelimit.consume(f"resend:id:{ratelimit.hkey(email)}", 3, 3600):
        return out
    user = db.scalar(select(User).where(User.email == email))
    if user and user.is_active and not user.email_verified:
        raw = authmail.issue(db, user, "verify", client_ip(request))
        authmail.send_email(db, user, "verify", raw)
        db.commit()
        if config.DEMO and not config.PRODUCTION:
            out["demo_link"] = authmail.link("verify", raw)
    return out


# ------------------------------------------------------------------ sessions (My profile)
def _session_row(s: AuthSession, current_id: int) -> dict:
    return {"id": s.id, "device": s.device, "ip": s.ip, "created_at": s.created_at.isoformat(), "last_used_at": s.last_used_at.isoformat(), "current": s.id == current_id}


@router.get("/me/sessions")
def my_sessions(auth: tuple[User, AuthSession] = Depends(current_auth), db: Session = Depends(get_db)):
    user, cur = auth
    rows = db.scalars(select(AuthSession).where(AuthSession.user_id == user.id, AuthSession.revoked_at.is_(None), AuthSession.expires_at > now())
                      .order_by(AuthSession.last_used_at.desc())).all()
    return [_session_row(s, cur.id) for s in rows]


@router.delete("/me/sessions/{sid}")
def revoke_session(sid: int, auth: tuple[User, AuthSession] = Depends(current_auth), db: Session = Depends(get_db)):
    user, cur = auth
    s = db.get(AuthSession, sid)
    if not s or s.user_id != user.id or s.revoked_at is not None:
        raise HTTPException(404, "Not found")
    sessions.revoke(db, s, "user_revoked")
    audit(db, user_id=user.id, action="auth.session_revoked", entity="session", entity_id=s.id, meta={"device": s.device, "self": s.id == cur.id})
    db.commit()
    return {"ok": True, "signed_out_here": s.id == cur.id}


class RevokeAllIn(BaseModel):
    keep_current: bool = False


@router.post("/me/sessions/revoke-all")
def revoke_all_sessions(body: RevokeAllIn | None = None, auth: tuple[User, AuthSession] = Depends(current_auth), db: Session = Depends(get_db)):
    """Sign out of all devices. With keep_current the device you are on stays signed in."""
    user, cur = auth
    keep = bool(body and body.keep_current)
    n = sessions.revoke_all(db, user.id, "user_revoked_all", bump=not keep, keep=cur.id if keep else None)
    audit(db, user_id=user.id, action="auth.sessions_revoked_all", entity="user", entity_id=user.id, meta={"count": n, "kept_current": keep})
    db.commit()
    return {"ok": True, "revoked": n}


# ------------------------------------------------------------------ public form token, audit chain
@router.get("/public/form-token")
def form_token():
    """A signed timestamp the public forms send back; a submission that arrives in under 3 seconds is treated as a bot."""
    return {"ft": antispam.issue()}


@router.get("/audit/verify")
def audit_verify(user: User = Depends(require_saas("SUPER_ADMIN", "SAAS_ADMIN")), db: Session = Depends(get_db)):
    """Re-computes the audit hash chain. ok=false names the first row that was changed, inserted or removed."""
    return auditchain.verify_chain(db)
