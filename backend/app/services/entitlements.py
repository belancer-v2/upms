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
    if not sub or sub.status == "cancelled":
        return set()
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
