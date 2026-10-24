"""Sends messages and keeps the SMS credit balance honest. The provider is simulated until a real SMS gateway is chosen."""
from sqlalchemy.orm import Session

from ..models.billing import Message
from ..models.core import now
from ..models.saas import SmsLedger
from .entitlements import sms_balance


def deliver(db: Session, org_id: int, msg: Message) -> Message:
    """Marks the message sent and spends one SMS credit. With no credit it fails visibly instead of being lost."""
    if msg.channel == "sms":
        if not msg.to_phone:
            msg.status, msg.error = "failed", "No phone number"
            return msg
        if sms_balance(db, org_id) < 1:
            msg.status, msg.error = "failed", "No SMS credit"
            return msg
        db.add(SmsLedger(org_id=org_id, delta=-1, reason=f"SMS {msg.template}"))
    msg.status, msg.sent_at = "sent", now()
    return msg
