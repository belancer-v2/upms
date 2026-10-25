"""Public provider webhooks (no sign-in; the signature or token is the proof).

POST /api/webhooks/sms/{provider}   SMS delivery report. Auth: header X-Signature = hex HMAC-SHA256(raw body, SMS_DLR_SECRET), or ?token=SMS_DLR_TOKEN.
POST /api/webhooks/ses              Amazon SES bounce / complaint / delivery notifications through SNS. Auth: SNS message signature (certificate from amazonaws.com).
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import os
import re
from urllib.parse import parse_qsl, urlparse

import httpx
from cryptography import x509
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_db
from ..models.billing import Message
from ..models.core import Property, now
from ..models.jobs import SmsDispatch
from ..models.mail import MailOutbox
from ..models.saas import SmsLedger
from ..services import mailer as M

router = APIRouter(prefix="/api/webhooks", tags=["webhooks"])
log = logging.getLogger("flatwise.webhooks")


# ------------------------------------------------------------------ SMS delivery reports
def _csv(name: str, default: str) -> set[str]:
    return {x.strip().lower() for x in os.getenv(name, default).split(",") if x.strip()}


def _authorised(request: Request, body: bytes) -> bool:
    secret, token = os.getenv("SMS_DLR_SECRET", ""), os.getenv("SMS_DLR_TOKEN", "")
    sig = request.headers.get("x-signature", "").strip().lower().removeprefix("sha256=")
    if secret and sig and hmac.compare_digest(sig, hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()):
        return True
    got = request.query_params.get("token", "")
    return bool(token and got and hmac.compare_digest(got, token))


@router.post("/sms/{provider}")
async def sms_dlr(provider: str, request: Request, db: Session = Depends(get_db)):
    if not (os.getenv("SMS_DLR_SECRET") or os.getenv("SMS_DLR_TOKEN")):
        raise HTTPException(503, "Delivery reports are not configured")
    raw = await request.body()
    if not _authorised(request, raw):
        raise HTTPException(403, "Bad signature")
    try:
        data = json.loads(raw) if raw[:1] in (b"{", b"[") else dict(parse_qsl(raw.decode("utf-8", "replace")))
    except ValueError:
        raise HTTPException(422, "Unreadable body")
    if isinstance(data, list):
        data = data[0] if data and isinstance(data[0], dict) else {}
    ref = str(data.get(os.getenv("SMS_DLR_REF_FIELD", "ref"), "")).strip()
    state = str(data.get(os.getenv("SMS_DLR_STATUS_FIELD", "status"), "")).strip().lower()
    detail = str(data.get(os.getenv("SMS_DLR_DETAIL_FIELD", "reason"), ""))[:120]
    if not ref or not state:
        raise HTTPException(422, "Missing reference or status")
    outcome = "delivered" if state in _csv("SMS_DLR_DELIVERED", "delivered,delivrd,success,ok,sent") else "undelivered" if state in _csv("SMS_DLR_FAILED", "failed,undelivered,undeliv,rejected,expired,error") else ""
    if not outcome:
        return {"ok": True, "ignored": True}
    d = db.scalar(select(SmsDispatch).where(SmsDispatch.provider_ref == ref))
    if not d:
        m = db.scalar(select(Message).where(Message.idem_key == ref))
        d = db.get(SmsDispatch, m.id) if m else None
    if not d:
        raise HTTPException(404, "Unknown message")
    if d.dlr_status == outcome:
        return {"ok": True, "replayed": True}
    d.dlr_status, d.dlr_detail, d.dlr_at = outcome, detail, now()
    msg = db.get(Message, d.message_id)
    if outcome == "undelivered":
        msg.status, msg.error = "failed", ("Undelivered: " + detail)[:120]
        if os.getenv("SMS_REFUND_UNDELIVERED", "1") == "1" and not d.refunded:
            prop = db.get(Property, msg.property_id)
            db.add(SmsLedger(org_id=prop.org_id, delta=d.credits, reason=f"Refund {msg.template}"[:60]))
            d.refunded = True
    db.commit()
    return {"ok": True, "status": outcome}


# ------------------------------------------------------------------ SES through SNS
_HOST = re.compile(r"^sns\.[a-z0-9-]+\.amazonaws\.com(\.cn)?$")


def fetch_cert(url: str) -> bytes:       # replaced in tests
    r = httpx.get(url, timeout=10, follow_redirects=False)
    r.raise_for_status()
    return r.content


def _string_to_sign(m: dict) -> bytes:
    keys = (["Message", "MessageId", "SubscribeURL", "Timestamp", "Token", "TopicArn", "Type"] if m.get("Type") != "Notification"
            else ["Message", "MessageId", "Subject", "Timestamp", "TopicArn", "Type"])
    return "".join(f"{k}\n{m[k]}\n" for k in keys if k in m).encode()


def verify_sns(m: dict) -> bool:
    url = str(m.get("SigningCertURL", ""))
    u = urlparse(url)
    if u.scheme != "https" or not _HOST.match(u.hostname or "") or not u.path.endswith(".pem"):
        return False
    try:
        cert = x509.load_pem_x509_certificate(fetch_cert(url))
        h = hashes.SHA256() if str(m.get("SignatureVersion")) == "2" else hashes.SHA1()
        cert.public_key().verify(base64.b64decode(m["Signature"]), _string_to_sign(m), padding.PKCS1v15(), h)
        return True
    except (InvalidSignature, ValueError, KeyError, httpx.HTTPError, TypeError):
        return False


def _latest_row(db: Session, email: str) -> MailOutbox | None:
    return db.scalar(select(MailOutbox).where(MailOutbox.to_email == email.lower(), MailOutbox.status.in_(("sent", "bounced"))).order_by(MailOutbox.id.desc()).limit(1))


def handle_ses_event(db: Session, ev: dict) -> dict:
    kind = str(ev.get("notificationType") or ev.get("eventType") or "")
    n = 0
    if kind == "Bounce":
        b = ev.get("bounce", {})
        for r in b.get("bouncedRecipients", []):
            email = str(r.get("emailAddress", "")).strip().lower()
            if not email or b.get("bounceType") != "Permanent":
                continue            # a soft bounce (mailbox full, server busy) is not a reason to stop writing to someone
            M.add_suppression(db, email, "bounce", f"SES {b.get('bounceSubType', '')} bounce")
            row = _latest_row(db, email)
            if row:
                row.status, row.bounced_at, row.delivered_at = "bounced", now(), None
            n += 1
    elif kind == "Complaint":
        for r in ev.get("complaint", {}).get("complainedRecipients", []):
            email = str(r.get("emailAddress", "")).strip().lower()
            if email:
                M.add_suppression(db, email, "complaint", "SES complaint")
                n += 1
    elif kind == "Delivery":
        for email in ev.get("delivery", {}).get("recipients", []):
            row = _latest_row(db, str(email))
            if row and row.delivered_at is None and row.status == "sent":
                row.delivered_at = now()
                n += 1
    return {"type": kind, "handled": n}


@router.post("/ses")
async def ses(request: Request, db: Session = Depends(get_db)):
    try:
        m = json.loads(await request.body())     # SNS posts JSON with content-type text/plain
        assert isinstance(m, dict)
    except (ValueError, AssertionError):
        raise HTTPException(422, "Unreadable body")
    if os.getenv("SES_WEBHOOK_VERIFY", "1") != "0" and not verify_sns(m):
        raise HTTPException(403, "Bad signature")
    topic = os.getenv("SES_SNS_TOPIC_ARN", "")
    if topic and m.get("TopicArn") != topic:
        raise HTTPException(403, "Unexpected topic")
    t = m.get("Type")
    if t == "SubscriptionConfirmation":
        u = urlparse(str(m.get("SubscribeURL", "")))
        if u.scheme == "https" and _HOST.match(u.hostname or ""):
            try:
                httpx.get(m["SubscribeURL"], timeout=10)
            except httpx.HTTPError:
                raise HTTPException(502, "Could not confirm the subscription")
        return {"ok": True, "confirmed": True}
    if t != "Notification":
        return {"ok": True, "ignored": True}
    try:
        ev = json.loads(m.get("Message", "{}"))
    except ValueError:
        raise HTTPException(422, "Unreadable notification")
    out = handle_ses_event(db, ev)
    db.commit()
    return {"ok": True, **out}
