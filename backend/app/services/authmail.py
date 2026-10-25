"""One-time tokens (password reset, e-mail verification) and how they reach the person.

E-mail goes through the mailer provider (sandbox until SMTP/SES is wired), SMS through services/messaging.deliver. The secret link is
handed to the provider and never kept: the copy recorded in mail_outbox / messages has the token replaced by [removed]. The link puts the
token in the URL fragment (#token=...), which browsers do not send to servers, proxies or Referer headers.
"""
import logging
from datetime import timedelta, timezone

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from .. import config
from ..models.billing import Message
from ..models.core import Membership, Property, User, now
from ..models.mail import MailOutbox
from ..models.security import AuthToken
from ..security import hash_token, new_secret_token
from . import mailer as M
from .messaging import deliver

log = logging.getLogger("flatwise.security")

COPY = {
    "reset": {
        "en": {"subject": "Reset your FlatWise password", "head": "Reset your password", "body": "We received a request to reset the password for your FlatWise account. This link works once and expires in {mins} minutes. If you did not ask for it, ignore this email: your password stays as it is.", "btn": "Choose a new password",
               "sms": "FlatWise: reset your password (valid {mins} min, one use): {link}"},
        "bn": {"subject": "আপনার ফ্ল্যাটওয়াইজ পাসওয়ার্ড রিসেট করুন", "head": "পাসওয়ার্ড রিসেট করুন", "body": "আপনার ফ্ল্যাটওয়াইজ অ্যাকাউন্টের পাসওয়ার্ড রিসেটের অনুরোধ পেয়েছি। লিংকটি একবারই কাজ করবে এবং {mins} মিনিট পর মেয়াদ শেষ হবে। আপনি অনুরোধ না করলে এই ইমেইল উপেক্ষা করুন, আপনার পাসওয়ার্ড অপরিবর্তিত থাকবে।", "btn": "নতুন পাসওয়ার্ড দিন",
               "sms": "ফ্ল্যাটওয়াইজ: পাসওয়ার্ড রিসেট লিংক ({mins} মিনিট, একবার): {link}"},
    },
    "verify": {
        "en": {"subject": "Confirm your email for FlatWise", "head": "Confirm your email", "body": "Welcome to FlatWise. Confirm this email address to start your free trial. The link works once and expires in {mins} hours.", "btn": "Confirm my email", "sms": ""},
        "bn": {"subject": "ফ্ল্যাটওয়াইজের জন্য আপনার ইমেইল নিশ্চিত করুন", "head": "ইমেইল নিশ্চিত করুন", "body": "ফ্ল্যাটওয়াইজে স্বাগতম। বিনামূল্যে ট্রায়াল শুরু করতে এই ইমেইল ঠিকানা নিশ্চিত করুন। লিংকটি একবারই কাজ করবে এবং {mins} ঘণ্টা পর মেয়াদ শেষ হবে।", "btn": "আমার ইমেইল নিশ্চিত করুন", "sms": ""},
    },
}
PAGE = {"reset": "reset-password", "verify": "verify-email"}


def _aware(d):
    return d.replace(tzinfo=timezone.utc) if d is not None and d.tzinfo is None else d


def issue(db: Session, user: User, kind: str, ip: str = "") -> str:
    """Creates a token (older unused ones of the same kind stop working). Returns the raw value; only its hash is stored."""
    db.execute(update(AuthToken).where(AuthToken.user_id == user.id, AuthToken.kind == kind, AuthToken.used_at.is_(None)).values(used_at=now()))
    raw, h = new_secret_token()
    life = timedelta(minutes=config.RESET_TOKEN_MINUTES) if kind == "reset" else timedelta(hours=config.VERIFY_TOKEN_HOURS)
    db.add(AuthToken(user_id=user.id, kind=kind, token_hash=h, expires_at=now() + life, ip=ip[:45]))
    db.flush()
    return raw


def find(db: Session, raw: str, kind: str) -> AuthToken | None:
    """Looks a token up (row locked). None if unknown, used or expired. The caller burns it by setting used_at once the action has succeeded."""
    t = db.scalar(select(AuthToken).where(AuthToken.token_hash == hash_token(raw or ""), AuthToken.kind == kind).with_for_update())
    if not t or t.used_at is not None or _aware(t.expires_at) < now():
        return None
    return t


def link(kind: str, raw: str) -> str:
    return f"{M.APP_URL}/{PAGE[kind]}#token={raw}"


def _copy(kind: str, lang: str) -> dict:
    c = COPY[kind]["en" if lang == "en" else "bn"]
    mins = config.RESET_TOKEN_MINUTES if kind == "reset" else config.VERIFY_TOKEN_HOURS
    return {k: v.replace("{mins}", str(mins)) for k, v in c.items()}


def send_email(db: Session, user: User, kind: str, raw: str) -> bool:
    """True if the provider accepted it. Never raises: the caller answers the person the same way either way."""
    lang = "en" if user.lang == "en" else "bn"
    c = _copy(kind, lang)
    if M.block_reason(db, user.email, "transactional", now()):
        return False
    blocks = [{"type": "heading", "text": c["head"]}, {"type": "paragraph", "text": c["body"]}, {"type": "button", "label": c["btn"], "url": "{{link}}"}]
    vars_ = {"name": user.name, "link": link(kind, raw)}
    prov = M.get_provider()
    try:
        real = M.render_email(c["subject"], blocks, vars_, lang, "transactional", email=user.email, outbox_id=0)   # outbox_id 0: no tracking wrapper around the secret link
        prov.send(M.Mail(user.email, real.subject, real.html, real.text))
        status, reason = "sent", ""
    except Exception as e:  # noqa: BLE001
        log.warning("auth e-mail not sent (%s): %s", kind, type(e).__name__)
        status, reason = "failed", type(e).__name__[:60]
    safe = M.render_email(c["subject"], blocks, {"name": user.name, "link": link(kind, "[removed]")}, lang, "transactional", email=user.email, outbox_id=0)
    t = now()
    db.add(MailOutbox(template_key=("password_reset" if kind == "reset" else "verify_email"), kind="transactional", to_email=user.email, to_name=user.name, lang=lang, org_id=None,
                      subject=safe.subject, html=safe.html, text=safe.text, vars={"name": user.name}, status=status, reason=reason, provider=prov.name,
                      sent_at=t if status == "sent" else None, delivered_at=t if status == "sent" and prov.simulates else None))
    return status == "sent"


def send_sms(db: Session, user: User, kind: str, raw: str) -> bool:
    """SMS through the existing message log and the building's SMS credit. Needs a phone number and one building the person belongs to."""
    c = _copy(kind, "en" if user.lang == "en" else "bn")
    if not user.phone or not c["sms"]:
        return False
    m = db.scalars(select(Membership).where(Membership.user_id == user.id).order_by(Membership.id)).first()
    if not m:
        return False
    pid = m.property_id or db.scalar(select(Property.id).where(Property.org_id == m.org_id).order_by(Property.id).limit(1))
    if not pid:
        return False
    body = c["sms"].replace("{link}", link(kind, raw))
    msg = Message(property_id=pid, to_name=user.name, to_phone=user.phone, channel="sms", template="password_reset", lang=user.lang if user.lang in ("en", "bn") else "bn",
                  body=body, idem_key=f"pwreset:{user.id}:{hash_token(raw)[:16]}")
    db.add(msg)
    deliver(db, m.org_id, msg)
    if msg.status == "sent":
        msg.body = c["sms"].replace("{link}", link(kind, "[removed]"))   # the secret is gone from our records once the provider has it
    return msg.status == "sent"
