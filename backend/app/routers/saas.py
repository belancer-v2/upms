"""SaaS console API. Only FlatWise staff (users with a saas_role) can call these."""
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..audit import audit
from ..db import get_db
from ..deps import current_user, require_saas
from ..models.core import AuditLog, Membership, Organization, Property, SAAS_ROLES, User, now
from ..models.saas import FeatureOverride, Lead, LeadNote, Plan, SaasInvoice, SmsLedger, Subscription
from ..security import hash_password
from ..services import saas_docs as _m21  # M21: history events and credit notes
from ..services.entitlements import ALL_FEATURES, current_subscription, org_features, sms_balance

router = APIRouter(prefix="/api/saas", tags=["saas"], dependencies=[Depends(require_saas())])
ADMINISH = ("SUPER_ADMIN", "SAAS_ADMIN")
MONEY = ("SUPER_ADMIN", "SAAS_ADMIN", "SAAS_FINANCE")
LEADERS = ("SUPER_ADMIN", "SAAS_ADMIN", "SAAS_SALES")
LEAD_STATUSES = ["new", "contacted", "demo", "trial", "won", "lost"]


def monthly_price(db: Session, sub: Subscription) -> int:
    plan = db.get(Plan, sub.plan_key)
    base = (plan.monthly.get(sub.band, 0) if plan else 0)
    return int(base * (100 - sub.discount_pct) / 100)


def _aware(dt):
    return dt.replace(tzinfo=timezone.utc) if dt and dt.tzinfo is None else dt


def _org_row(db: Session, o: Organization) -> dict:
    sub = current_subscription(db, o.id)
    props = db.scalar(select(func.count()).select_from(Property).where(Property.org_id == o.id)) or 0
    users = db.scalar(select(func.count(func.distinct(Membership.user_id))).where(Membership.org_id == o.id)) or 0
    live = sub and sub.status in ("active", "past_due")
    return {"id": o.id, "name": o.name, "name_bn": o.name_bn, "city": o.city, "kind": o.kind, "status": o.status,
            "plan": sub.plan_key if sub else "", "band": sub.band if sub else "", "cycle": sub.cycle if sub else "",
            "flats": sub.flats if sub else 0, "sub_status": sub.status if sub else "", "discount_pct": sub.discount_pct if sub else 0,
            "trial_ends": sub.trial_ends.isoformat() if sub and sub.trial_ends else None,
            "mrr": monthly_price(db, sub) if live else 0, "sms_balance": sms_balance(db, o.id),
            "properties": props, "users": users, "created_at": o.created_at.isoformat()}


@router.get("/overview")
def overview(user: User = Depends(current_user), db: Session = Depends(get_db)):
    orgs = db.scalars(select(Organization).order_by(Organization.id)).all()
    rows = [_org_row(db, o) for o in orgs]
    money_ok = user.saas_role in MONEY
    soon = now() + timedelta(days=7)
    trials = [r for r in rows if r["sub_status"] == "trial" and r["trial_ends"] and _aware(datetime.fromisoformat(r["trial_ends"])) <= soon]
    by_plan: dict[str, int] = {}
    for r in rows:
        if r["mrr"]:
            by_plan[r["plan"]] = by_plan.get(r["plan"], 0) + r["mrr"]
    overdue = db.scalars(select(SaasInvoice).where(SaasInvoice.status == "issued", SaasInvoice.due_at < now())).all()
    leads = {s: 0 for s in LEAD_STATUSES}
    for s, c in db.execute(select(Lead.status, func.count()).group_by(Lead.status)):
        leads[s] = c
    return {
        "buildings": {"total": len(rows), "trial": sum(r["sub_status"] == "trial" for r in rows), "active": sum(r["sub_status"] == "active" for r in rows),
                      "past_due": sum(r["sub_status"] == "past_due" for r in rows), "suspended": sum(r["sub_status"] == "suspended" for r in rows)},
        "flats": sum(r["flats"] for r in rows),
        "mrr": sum(r["mrr"] for r in rows) if money_ok else None, "mrr_by_plan": by_plan if money_ok else None,
        "overdue": {"count": len(overdue), "amount": sum(i.amount for i in overdue)} if money_ok else None,
        "trials_ending": [{"id": r["id"], "name": r["name"], "trial_ends": r["trial_ends"], "plan": r["plan"]} for r in trials],
        "leads": leads, "sms_low": [{"id": r["id"], "name": r["name"], "balance": r["sms_balance"]} for r in rows if r["sub_status"] in ("active", "past_due", "trial") and r["sms_balance"] < 100],
        "recent": [{"id": r["id"], "name": r["name"], "plan": r["plan"], "status": r["sub_status"], "created_at": r["created_at"]} for r in sorted(rows, key=lambda x: x["created_at"], reverse=True)[:6]],
    }


@router.get("/orgs")
def orgs(status: str = "", db: Session = Depends(get_db)):
    rows = [_org_row(db, o) for o in db.scalars(select(Organization).order_by(Organization.id))]
    return [r for r in rows if not status or r["sub_status"] == status or r["status"] == status]


@router.get("/orgs/{org_id}")
def org_detail(org_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    o = db.get(Organization, org_id)
    if not o:
        raise HTTPException(404, "Not found")
    sub = current_subscription(db, org_id)
    plan = db.get(Plan, sub.plan_key) if sub else None
    plan_feats = set(plan.features if plan else [])
    over = {f.key: f.enabled for f in db.scalars(select(FeatureOverride).where(FeatureOverride.org_id == org_id))}
    invoices = db.scalars(select(SaasInvoice).where(SaasInvoice.org_id == org_id).order_by(SaasInvoice.id.desc()).limit(12)).all() if user.saas_role in MONEY else []
    ledger = db.scalars(select(SmsLedger).where(SmsLedger.org_id == org_id).order_by(SmsLedger.id.desc()).limit(10)).all()
    props = db.scalars(select(Property).where(Property.org_id == org_id)).all()
    admins = db.execute(select(User.name, User.email, Membership.role).join(Membership, Membership.user_id == User.id).where(Membership.org_id == org_id, Membership.role.in_(("PROPERTY_ADMIN", "AGENCY_MANAGER", "PRESIDENT")))).all()
    return {**_org_row(db, o),
            "buildings": [{"id": p.id, "name": p.name, "city": p.city, "floors": p.floors} for p in props],
            "contacts": [{"name": n, "email": e, "role": r} for n, e, r in admins],
            "features": [{"key": k, "plan": k in plan_feats, "override": over.get(k), "on": k in org_features(db, org_id)} for k in ALL_FEATURES],
            "invoices": [_inv(db, i) for i in invoices],
            "sms_ledger": [{"id": l.id, "delta": l.delta, "reason": l.reason, "at": l.at.isoformat()} for l in ledger]}


class StatusIn(BaseModel):
    status: str


@router.post("/orgs/{org_id}/status")
def set_status(org_id: int, body: StatusIn, user: User = Depends(require_saas(*ADMINISH)), db: Session = Depends(get_db)):
    o, sub = db.get(Organization, org_id), current_subscription(db, org_id)
    if not o or not sub or body.status not in ("trial", "active", "suspended"):
        raise HTTPException(422, "Bad request")
    o.status, sub.status = body.status, body.status
    _m21.record_event(db, sub, {"active": "activate", "suspended": "suspend"}.get(body.status, "trial_start"), user.id)
    if body.status == "active":
        plan = db.get(Plan, sub.plan_key)
        has_setup = db.scalar(select(SaasInvoice.id).where(SaasInvoice.org_id == org_id, SaasInvoice.kind == "setup", SaasInvoice.status != "void"))
        if plan and not has_setup and sub.cycle == "monthly" and sub.band in plan.setup:
            _new_invoice(db, org_id, "setup", "", f"One-time setup, {plan.name}", plan.setup[sub.band], 7)
    audit(db, user_id=user.id, org_id=org_id, action=f"saas.org.{body.status}", entity="organization", entity_id=org_id)
    db.commit()
    return _org_row(db, o)


class PlanChangeIn(BaseModel):
    plan: str
    band: str
    cycle: str = "monthly"
    flats: int | None = None
    discount_pct: int = Field(default=0, ge=0, le=100)


@router.post("/orgs/{org_id}/plan")
def change_plan(org_id: int, body: PlanChangeIn, user: User = Depends(require_saas(*LEADERS)), db: Session = Depends(get_db)):
    sub = current_subscription(db, org_id)
    if not sub or not db.get(Plan, body.plan) or body.band not in ("S", "M", "L", "XL") or body.cycle not in ("monthly", "yearly"):
        raise HTTPException(422, "Bad request")
    if user.saas_role == "SAAS_SALES" and sub.status != "trial":
        raise HTTPException(403, "Sales can change plans during a trial only")
    old = (sub.plan_key, sub.band, sub.cycle, sub.discount_pct)
    sub.plan_key, sub.band, sub.cycle, sub.discount_pct = body.plan, body.band, body.cycle, body.discount_pct
    if body.flats:
        sub.flats = body.flats
    _m21.record_event(db, sub, "plan_change", user.id)
    audit(db, user_id=user.id, org_id=org_id, action="saas.plan.change", entity="subscription", entity_id=sub.id, meta={"from": old, "to": [body.plan, body.band, body.cycle, body.discount_pct]})
    db.commit()
    return _org_row(db, db.get(Organization, org_id))


class TrialIn(BaseModel):
    days: int = Field(ge=1, le=60)


@router.post("/orgs/{org_id}/trial")
def extend_trial(org_id: int, body: TrialIn, user: User = Depends(require_saas(*LEADERS)), db: Session = Depends(get_db)):
    sub = current_subscription(db, org_id)
    if not sub or sub.status != "trial":
        raise HTTPException(422, "Not on a trial")
    base = max(_aware(sub.trial_ends) or now(), now())
    sub.trial_ends = base + timedelta(days=body.days)
    audit(db, user_id=user.id, org_id=org_id, action="saas.trial.extend", entity="subscription", entity_id=sub.id, meta={"days": body.days})
    db.commit()
    return {"trial_ends": sub.trial_ends.isoformat()}


class FeatureIn(BaseModel):
    key: str
    enabled: bool


@router.put("/orgs/{org_id}/features")
def set_feature(org_id: int, body: FeatureIn, user: User = Depends(require_saas(*ADMINISH)), db: Session = Depends(get_db)):
    if body.key not in ALL_FEATURES:
        raise HTTPException(422, "Unknown feature")
    sub = current_subscription(db, org_id)
    plan = db.get(Plan, sub.plan_key) if sub else None
    in_plan = body.key in (plan.features if plan else [])
    ov = db.scalar(select(FeatureOverride).where(FeatureOverride.org_id == org_id, FeatureOverride.key == body.key))
    if body.enabled == in_plan:
        if ov:
            db.delete(ov)
    elif ov:
        ov.enabled = body.enabled
    else:
        db.add(FeatureOverride(org_id=org_id, key=body.key, enabled=body.enabled))
    audit(db, user_id=user.id, org_id=org_id, action="saas.feature", entity="feature", entity_id=body.key, meta={"enabled": body.enabled})
    db.commit()
    return {"ok": True}


class SmsIn(BaseModel):
    count: int = Field(ge=1, le=100000)
    reason: str = "SMS pack"
    bill: bool = True


@router.post("/orgs/{org_id}/sms")
def add_sms(org_id: int, body: SmsIn, user: User = Depends(require_saas(*MONEY)), db: Session = Depends(get_db)):
    if not db.get(Organization, org_id):
        raise HTTPException(404, "Not found")
    db.add(SmsLedger(org_id=org_id, delta=body.count, reason=body.reason, by_user_id=user.id))
    if body.bill:
        _new_invoice(db, org_id, "sms", "", f"{body.count} SMS credits", int(body.count / 1000 * 80000), 7)
    audit(db, user_id=user.id, org_id=org_id, action="saas.sms.topup", entity="sms", meta={"count": body.count, "bill": body.bill})
    db.commit()
    return {"balance": sms_balance(db, org_id)}


# ---------------- invoices
def _new_invoice(db: Session, org_id: int, kind: str, period: str, desc: str, amount: int, due_days: int) -> SaasInvoice:
    n = (db.scalar(select(func.count()).select_from(SaasInvoice)) or 0) + 1
    inv = SaasInvoice(number=f"FW-{now():%Y%m}-{n:04d}", org_id=org_id, kind=kind, period=period, description=desc, amount=amount,
                      issued_at=now(), due_at=now() + timedelta(days=due_days))
    db.add(inv)
    db.flush()
    return inv


def _inv(db: Session, i: SaasInvoice) -> dict:
    org = db.get(Organization, i.org_id)
    overdue = i.status == "issued" and _aware(i.due_at) < now()
    return {"id": i.id, "number": i.number, "org_id": i.org_id, "org": org.name if org else "", "kind": i.kind, "period": i.period,
            "description": i.description, "amount": i.amount, "status": "overdue" if overdue else i.status, "issued_at": i.issued_at.isoformat(),
            "due_at": i.due_at.isoformat(), "paid_at": i.paid_at.isoformat() if i.paid_at else None, "method": i.method, "trx_id": i.trx_id}


@router.get("/invoices")
def invoices(status: str = "", user: User = Depends(require_saas(*MONEY)), db: Session = Depends(get_db)):
    rows = [_inv(db, i) for i in db.scalars(select(SaasInvoice).order_by(SaasInvoice.id.desc()))]
    return [r for r in rows if not status or r["status"] == status]


class RunIn(BaseModel):
    period: str = Field(pattern=r"^\d{4}-\d{2}$")


@router.post("/invoices/run")
def run_invoices(body: RunIn, user: User = Depends(require_saas(*MONEY)), db: Session = Depends(get_db)):
    """Monthly run. Safe to press twice: an organization is billed once per period."""
    made, total = 0, 0
    for sub in db.scalars(select(Subscription).where(Subscription.status.in_(("active", "past_due")))):
        plan = db.get(Plan, sub.plan_key)
        if not plan or sub.band not in plan.monthly:
            continue
        yearly = sub.cycle == "yearly"
        period = body.period[:4] if yearly else body.period
        if yearly and body.period[5:] != f"{sub.started_at:%m}":
            continue
        if db.scalar(select(SaasInvoice.id).where(SaasInvoice.org_id == sub.org_id, SaasInvoice.kind == "subscription", SaasInvoice.period == period, SaasInvoice.status != "void")):
            continue
        amt = int(monthly_price(db, sub) * (10 if yearly else 1))
        _new_invoice(db, sub.org_id, "subscription", period, f"{plan.name} · {sub.band} · {period}", amt, 10)
        db.add(SmsLedger(org_id=sub.org_id, delta=plan.sms_included.get(sub.band, 0), reason=f"Monthly allowance {body.period}", by_user_id=user.id))
        if (plan.email_included or {}).get(sub.band, 0) > 0:
            from ..models.credits import EmailLedger
            db.add(EmailLedger(org_id=sub.org_id, delta=plan.email_included[sub.band], reason=f"Monthly allowance {body.period}", by_user_id=user.id))
        made, total = made + 1, total + amt
    audit(db, user_id=user.id, action="saas.invoices.run", entity="period", entity_id=body.period, meta={"created": made, "total": total})
    db.commit()
    return {"created": made, "total": total}


class PayIn(BaseModel):
    method: str = Field(pattern="^(bkash|nagad|bank|cash)$")
    trx_id: str = ""


@router.post("/invoices/{invoice_id}/pay")
def pay_invoice(invoice_id: int, body: PayIn, user: User = Depends(require_saas(*MONEY)), db: Session = Depends(get_db)):
    inv = db.get(SaasInvoice, invoice_id)
    if not inv or inv.status != "issued":
        raise HTTPException(422, "Invoice is not open")
    inv.status, inv.paid_at, inv.method, inv.trx_id = "paid", now(), body.method, body.trx_id
    sub = current_subscription(db, inv.org_id)
    if sub and sub.status == "past_due" and not db.scalar(select(SaasInvoice.id).where(SaasInvoice.org_id == inv.org_id, SaasInvoice.status == "issued", SaasInvoice.due_at < now(), SaasInvoice.id != inv.id)):
        sub.status = "active"
    audit(db, user_id=user.id, org_id=inv.org_id, action="saas.invoice.paid", entity="invoice", entity_id=inv.id, meta={"method": body.method, "trx": body.trx_id})
    db.commit()
    return _inv(db, inv)


@router.post("/invoices/{invoice_id}/void")
def void_invoice(invoice_id: int, user: User = Depends(require_saas(*MONEY)), db: Session = Depends(get_db)):
    inv = db.get(SaasInvoice, invoice_id)
    if not inv or inv.status != "issued":
        raise HTTPException(422, "Only open invoices can be voided")
    inv.status = "void"
    _m21.void_with_credit_note(db, inv, user.id)  # the row stays; a credit note is issued
    audit(db, user_id=user.id, org_id=inv.org_id, action="saas.invoice.void", entity="invoice", entity_id=inv.id)
    db.commit()
    return _inv(db, inv)


# ---------------- plans
@router.get("/plans")
def plans(db: Session = Depends(get_db)):
    return {"all_features": ALL_FEATURES, "plans": [
        {"key": p.key, "name": p.name, "name_bn": p.name_bn, "monthly": p.monthly, "setup": p.setup, "sms_included": p.sms_included, "email_included": p.email_included or {}, "features": p.features,
         "subscribers": db.scalar(select(func.count()).select_from(Subscription).where(Subscription.plan_key == p.key)) or 0}
        for p in db.scalars(select(Plan).order_by(Plan.sort))]}


class PlanIn(BaseModel):
    monthly: dict[str, int]
    setup: dict[str, int]
    sms_included: dict[str, int]
    email_included: dict[str, int] | None = None
    features: list[str]


@router.put("/plans/{key}")
def update_plan(key: str, body: PlanIn, user: User = Depends(require_saas("SUPER_ADMIN")), db: Session = Depends(get_db)):
    p = db.get(Plan, key)
    if not p:
        raise HTTPException(404, "Not found")
    p.monthly, p.setup, p.sms_included = body.monthly, body.setup, body.sms_included
    if body.email_included is not None:
        p.email_included = body.email_included
    p.features = [f for f in body.features if f in ALL_FEATURES]
    audit(db, user_id=user.id, action="saas.plan.edit", entity="plan", entity_id=key)
    db.commit()
    return {"ok": True}


# ---------------- leads
def _lead(db: Session, l: Lead) -> dict:
    owner = db.get(User, l.owner_id) if l.owner_id else None
    notes = db.scalars(select(LeadNote).where(LeadNote.lead_id == l.id).order_by(LeadNote.id.desc())).all()
    return {"id": l.id, "name": l.name, "phone": l.phone, "email": l.email, "building": l.building, "flats": l.flats, "city": l.city, "message": l.message,
            "source": l.source, "status": l.status, "owner_id": l.owner_id, "owner": owner.name if owner else "", "created_at": l.created_at.isoformat(),
            "notes": [{"id": n.id, "text": n.text, "at": n.at.isoformat(), "by": (db.get(User, n.user_id).name if n.user_id else "")} for n in notes]}


@router.get("/leads")
def leads(user: User = Depends(require_saas(*LEADERS)), db: Session = Depends(get_db)):
    return [_lead(db, l) for l in db.scalars(select(Lead).order_by(Lead.id.desc()))]


class LeadPatch(BaseModel):
    status: str | None = None
    owner_id: int | None = None


@router.patch("/leads/{lead_id}")
def patch_lead(lead_id: int, body: LeadPatch, user: User = Depends(require_saas(*LEADERS)), db: Session = Depends(get_db)):
    l = db.get(Lead, lead_id)
    if not l:
        raise HTTPException(404, "Not found")
    if body.status:
        if body.status not in LEAD_STATUSES:
            raise HTTPException(422, "Bad status")
        l.status = body.status
        _m21.record_lead_stage(db, l.id, body.status)
    if body.owner_id is not None:
        l.owner_id = body.owner_id or None
    audit(db, user_id=user.id, action="saas.lead.update", entity="lead", entity_id=lead_id, meta=body.model_dump(exclude_none=True))
    db.commit()
    return _lead(db, l)


class NoteIn(BaseModel):
    text: str = Field(min_length=1, max_length=2000)


@router.post("/leads/{lead_id}/notes", status_code=201)
def add_note(lead_id: int, body: NoteIn, user: User = Depends(require_saas(*LEADERS)), db: Session = Depends(get_db)):
    if not db.get(Lead, lead_id):
        raise HTTPException(404, "Not found")
    db.add(LeadNote(lead_id=lead_id, user_id=user.id, text=body.text))
    db.commit()
    return _lead(db, db.get(Lead, lead_id))


# ---------------- SaaS staff
@router.get("/staff")
def staff(user: User = Depends(require_saas(*ADMINISH)), db: Session = Depends(get_db)):
    return [{"id": u.id, "name": u.name, "name_bn": u.name_bn, "email": u.email, "phone": u.phone, "role": u.saas_role, "active": u.is_active}
            for u in db.scalars(select(User).where(User.saas_role.is_not(None)).order_by(User.id))]


class StaffIn(BaseModel):
    name: str = Field(min_length=2)
    email: str
    role: str
    password: str = Field(min_length=8)
    phone: str = ""


@router.post("/staff", status_code=201)
def add_staff(body: StaffIn, user: User = Depends(require_saas("SUPER_ADMIN")), db: Session = Depends(get_db)):
    if body.role not in SAAS_ROLES:
        raise HTTPException(422, "Unknown role")
    email = body.email.strip().lower()
    if db.scalar(select(User).where(User.email == email)):
        raise HTTPException(409, "Email already used")
    u = User(email=email, name=body.name, phone=body.phone, password_hash=hash_password(body.password), saas_role=body.role)
    db.add(u)
    db.flush()
    audit(db, user_id=user.id, action="saas.staff.add", entity="user", entity_id=u.id, meta={"role": body.role})
    db.commit()
    return {"id": u.id}


class StaffPatch(BaseModel):
    active: bool | None = None
    role: str | None = None


@router.patch("/staff/{uid}")
def patch_staff(uid: int, body: StaffPatch, user: User = Depends(require_saas("SUPER_ADMIN")), db: Session = Depends(get_db)):
    u = db.get(User, uid)
    if not u or not u.saas_role:
        raise HTTPException(404, "Not found")
    if u.id == user.id:
        raise HTTPException(422, "You cannot change your own access")
    if body.role:
        if body.role not in SAAS_ROLES:
            raise HTTPException(422, "Unknown role")
        u.saas_role = body.role
    if body.active is not None:
        u.is_active = body.active
    audit(db, user_id=user.id, action="saas.staff.update", entity="user", entity_id=uid, meta=body.model_dump(exclude_none=True))
    db.commit()
    return {"ok": True}
