"""Sends messages and keeps the SMS credit balance honest. The provider is simulated until a real SMS gateway is chosen."""
from sqlalchemy import inspect
from sqlalchemy.orm import Session

from ..models.billing import Message
from ..models.core import now
from ..models.saas import SmsLedger
from ..models.credits import EmailLedger
from ..models.jobs import SmsDispatch
from . import sms
from .entitlements import email_balance, sms_balance


def deliver(db: Session, org_id: int, msg: Message) -> Message:
    """Marks the message sent and spends one SMS credit. With no credit it fails visibly instead of being lost."""
    channel = msg.channel or "sms"      # the column default only applies at flush, so an unflushed Message has none yet
    if channel == "sms":
        if not msg.to_phone:
            msg.status, msg.error = "failed", "No phone number"
            return msg
        credits, seg, enc = sms.credits_for(msg.body)          # per segment: Bangla text is 70 characters per SMS, not 160
        if sms_balance(db, org_id) < credits:
            msg.status, msg.error = "failed", "No SMS credit"
            return msg
        prov = sms.get_provider()
        res = prov.send_one(msg.to_phone, msg.body, msg.idem_key)
        if not res.ok:                                           # nothing is charged for a message the provider refused
            msg.status, msg.error = "failed", (res.error or "SMS provider error")[:120]
            return msg
        db.add(SmsLedger(org_id=org_id, delta=-credits, reason=f"SMS {msg.template}"))
        if not inspect(msg).transient:      # a Message that is not kept (e.g. a private rental reminder) has no dispatch row either
            db.flush()
            db.add(SmsDispatch(message_id=msg.id, provider=prov.name, provider_ref=(res.ref or "")[:80], segments=seg, encoding=enc, credits=credits))
    elif channel == "email":
        if not msg.to_email:
            msg.status, msg.error = "failed", "No email address"
            return msg
        if email_balance(db, org_id) < 1:
            msg.status, msg.error = "failed", "No email credit"
            return msg
        db.add(EmailLedger(org_id=org_id, delta=-1, reason=f"Email {msg.template}"[:60]))
    msg.status, msg.sent_at = "sent", now()
    return msg
