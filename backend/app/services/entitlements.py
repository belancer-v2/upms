"""Which features an organization can use. Plan features, then per-organization overrides."""
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models.saas import FeatureOverride, Plan, Subscription

ALL_FEATURES = ["billing", "expenses", "notices", "resident_web", "reports", "staff", "assets", "tenant_dmp", "reminders",
                "caretaker_app", "cash_confirm", "policies", "resident_portal", "visitor", "amenities", "parking",
                "maintenance", "cash_otp", "priority_support", "gateway", "committee", "rental_records"]


def current_subscription(db: Session, org_id: int) -> Subscription | None:
    return db.scalar(select(Subscription).where(Subscription.org_id == org_id).order_by(Subscription.id.desc()))


def org_features(db: Session, org_id: int) -> set[str]:
    sub = current_subscription(db, org_id)
    if not sub:
        return set()
    # A cancelled building keeps its plan's screens so its data stays readable; writes stop after the grace window (see cancel_state).
    plan = db.get(Plan, sub.plan_key)
    feats = set(plan.features if plan else [])
    for o in db.scalars(select(FeatureOverride).where(FeatureOverride.org_id == org_id)):
        (feats.add if o.enabled else feats.discard)(o.key)
    return feats


def email_balance(db: Session, org_id: int) -> int:
    from sqlalchemy import func
    from ..models.credits import EmailLedger
    return int(db.scalar(select(func.coalesce(func.sum(EmailLedger.delta), 0)).where(EmailLedger.org_id == org_id)) or 0)


def sms_balance(db: Session, org_id: int) -> int:
    from sqlalchemy import func
    from ..models.saas import SmsLedger
    return int(db.scalar(select(func.coalesce(func.sum(SmsLedger.delta), 0)).where(SmsLedger.org_id == org_id)) or 0)


GRACE_DAYS = 30


def cancel_state(db: Session, org_id: int) -> dict | None:
    """None while the subscription is not cancelled. Otherwise when it ended, when it turns read-only, and whether it is read-only now.
    For 30 days after the end date everything keeps working (time to export). After that the data stays readable but nothing can be changed."""
    from datetime import datetime, timedelta, timezone
    from ..models.core import now
    from ..models.saas import CancellationRequest
    sub = current_subscription(db, org_id)
    if not sub or sub.status != "cancelled":
        return None
    req = db.scalar(select(CancellationRequest).where(CancellationRequest.org_id == org_id, CancellationRequest.status == "approved").order_by(CancellationRequest.id.desc()))
    ended = (req.decided_at if req and req.decided_at else None) or sub.started_at
    if ended.tzinfo is None:
        ended = ended.replace(tzinfo=timezone.utc)
    ro_from = ended + timedelta(days=GRACE_DAYS)
    return {"ended_at": ended, "readonly_from": ro_from, "readonly": now() >= ro_from, "days_left": max(0, (ro_from - now()).days)}
