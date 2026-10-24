"""M19: buying SMS and email credits from FlatWise. Sandbox gateway only; see services/gateway.py.

`router`  /api/credits       building side (PROPERTY_ADMIN, AGENCY_MANAGER, TREASURER, PRESIDENT)
`console` /api/saas/credits  SaaS console (finance/admin edit and verify; every SaaS role can read packs and balances)
Balances are ledger sums. Every grant is a ledger row linked to the SaaS invoice that paid for it.
"""
import secrets
from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, or_, select, update
from sqlalchemy.orm import Session

from ..audit import audit
from ..db import get_db
from ..deps import Ctx, current_user, property_ctx, require_saas
from ..models.core import Membership, Organization, User, now
from ..models.credits import CreditPack, CreditPurchase, CreditSetting, EmailLedger, PlatformSetting
from ..models.saas import SaasInvoice, SmsLedger
from ..services import gateway as gw
from ..services.entitlements import email_balance, sms_balance

router = APIRouter(prefix="/api/credits", tags=["credits"])
console = APIRouter(prefix="/api/saas/credits", tags=["credits-console"], dependencies=[Depends(require_saas())])

BUYERS = {"PROPERTY_ADMIN", "AGENCY_MANAGER", "TREASURER", "PRESIDENT"}
ADMINS = {"PROPERTY_ADMIN", "AGENCY_MANAGER"}
MONEY = ("SUPER_ADMIN", "SAAS_ADMIN", "SAAS_FINANCE")
KINDS = ("sms", "email")
MANUAL_METHODS = ("bkash", "nagad", "bank")
DEFAULT_LOW = 100
PURPOSES = {"due_": "reminders", "rent_remind": "reminders", "notice": "notices", "cash_otp": "otp", "otp": "otp", "payslip": "payslips", "tenant_form": "onboarding"}
SETTING_KEYS = ("vat_bps", "pay_bkash", "pay_nagad", "pay_bank")


def _aware(d):
    return d if d.tzinfo else d.replace(tzinfo=now().tzinfo)


# ---------------- shared helpers
def get_setting(db: Session, key: str, default: str = "") -> str:
    r = db.get(PlatformSetting, key)
    return r.value if r else default


def vat_bps(db: Session) -> int:
    try:
        return max(0, int(get_setting(db, "vat_bps", "0")))
    except ValueError:
        return 0


def vat_for(price: int, bps: int) -> int:
    """VAT in whole paisa, rounded half up. Integer maths only."""
    return (price * bps + 5000) // 10000


def balance(db: Session, org_id: int, kind: str) -> int:
    return sms_balance(db, org_id) if kind == "sms" else email_balance(db, org_id)


def _ledger(kind: str):
    return SmsLedger if kind == "sms" else EmailLedger


def thresholds(db: Session, org_id: int) -> tuple[int, int]:
    s = db.scalar(select(CreditSetting).where(CreditSetting.org_id == org_id))
    return (s.sms_low, s.email_low) if s else (DEFAULT_LOW, DEFAULT_LOW)


def purpose_of(reason: str) -> str:
    tpl = reason.split(" ", 1)[1] if reason.startswith(("SMS ", "Email ")) and " " in reason else ""
    for k, v in PURPOSES.items():
        if tpl == k or (k.endswith("_") and tpl.startswith(k)):
            return v
    return "other"


def usage30(db: Session, org_id: int, kind: str) -> dict:
    L = _ledger(kind)
    rows = db.execute(select(L.reason, func.sum(L.delta)).where(L.org_id == org_id, L.delta < 0, L.at >= now() - timedelta(days=30)).group_by(L.reason)).all()
    by: dict[str, int] = {}
    for reason, d in rows:
        p = purpose_of(reason)
        by[p] = by.get(p, 0) + int(-d)
    return {"total": sum(by.values()), "by_purpose": by}


def new_invoice_number(db: Session) -> str:
    n = (db.scalar(select(func.count()).select_from(SaasInvoice)) or 0) + 1
    while True:
        num = f"FW-{now():%Y%m}-{n:04d}"
        if not db.scalar(select(SaasInvoice.id).where(SaasInvoice.number == num)):
            return num
        n += 1


def _pack_out(p: CreditPack) -> dict:
    return {"id": p.id, "kind": p.kind, "name": p.name, "name_bn": p.name_bn, "credits": p.credits, "price": p.price, "active": p.active, "sort": p.sort}


def _items(p: CreditPurchase) -> list[dict]:
    return [{"kind": p.kind, "name": p.pack_name, "name_bn": p.pack_name_bn, "credits": p.credits, "amount": p.price}]


def _purchase_out(db: Session, p: CreditPurchase, org: bool = False) -> dict:
    inv = db.get(SaasInvoice, p.invoice_id) if p.invoice_id else None
    d = {"id": p.id, "kind": p.kind, "pack_name": p.pack_name, "pack_name_bn": p.pack_name_bn, "credits": p.credits, "price": p.price, "vat": p.vat, "total": p.total, "mode": p.mode,
         "method": p.method, "status": p.status, "trx_id": p.trx_id, "claimed_amount": p.claimed_amount, "invoice_id": p.invoice_id, "invoice": inv.number if inv else "",
         "created_at": p.created_at.isoformat(), "completed_at": p.completed_at.isoformat() if p.completed_at else None, "note": p.note}
    if org:
        o = db.get(Organization, p.org_id)
        u = db.get(User, p.user_id)
        d.update({"org_id": p.org_id, "org": o.name if o else "", "by": u.name if u else ""})
    return d


def _new_purchase(db: Session, ctx: Ctx, pack: CreditPack, mode: str, method: str) -> CreditPurchase:
    bps = vat_bps(db)
    vat = vat_for(pack.price, bps)
    token = secrets.token_urlsafe(24)
    p = CreditPurchase(token=token, org_id=ctx.property.org_id, property_id=ctx.property.id, user_id=ctx.user.id, pack_id=pack.id, kind=pack.kind, pack_name=pack.name, pack_name_bn=pack.name_bn,
                       credits=pack.credits, price=pack.price, vat_bps=bps, vat=vat, total=pack.price + vat, mode=mode, method=method, idem_key=f"cr:{token}",
                       status="created" if mode == "gateway" else "pending")
    if mode == "gateway":
        p.provider_ref = gw.provider(method).create_checkout(None, p.total)["provider_ref"] if method in gw.PROVIDERS else ""   # type: ignore[arg-type]
        p.expires_at = now() + timedelta(minutes=gw.SESSION_MINUTES)
    db.add(p)
    db.flush()
    return p


def settle(db: Session, p: CreditPurchase, *, method: str, trx_id: str, by_user: int | None) -> SaasInvoice:
    """Marks the invoice paid and appends ONE ledger grant. Callers must have claimed the purchase first (status guard), so this runs once."""
    inv = db.get(SaasInvoice, p.invoice_id) if p.invoice_id else None
    if not inv:
        inv = SaasInvoice(number=new_invoice_number(db), org_id=p.org_id, kind="credits", period="", issued_at=now(), due_at=now())
        db.add(inv)
    inv.description = f"{p.credits} {p.kind.upper()} credits, {p.pack_name}"[:200]
    inv.amount, inv.status, inv.paid_at, inv.method, inv.trx_id = p.total, "paid", now(), method, trx_id[:40]
    inv.items, inv.vat_bps, inv.vat_amount = _items(p), p.vat_bps, p.vat
    db.flush()
    db.add(_ledger(p.kind)(org_id=p.org_id, delta=p.credits, reason=f"Pack {p.credits} · {inv.number}"[:60], by_user_id=by_user, invoice_id=inv.id))
    p.invoice_id, p.status, p.trx_id, p.completed_at = inv.id, "paid", trx_id[:40], now()
    return inv


def _claim(db: Session, p: CreditPurchase, frm: str) -> bool:
    """Atomic status flip so a replayed callback or a double click can never grant twice."""
    r = db.execute(update(CreditPurchase).where(CreditPurchase.id == p.id, CreditPurchase.status == frm).values(status="settling"))
    db.refresh(p)
    return r.rowcount == 1


# ---------------- building side
def _need(ctx: Ctx) -> None:
    ctx.need(*BUYERS)


@router.get("/summary")
def summary(ctx: Ctx = Depends(property_ctx), db: Session = Depends(get_db)):
    _need(ctx)
    org = ctx.property.org_id
    lo_s, lo_e = thresholds(db, org)
    bal = {"sms": sms_balance(db, org), "email": email_balance(db, org)}
    low = {"sms": lo_s, "email": lo_e}
    packs = db.scalars(select(CreditPack).where(CreditPack.active == True).order_by(CreditPack.kind, CreditPack.sort, CreditPack.credits)).all()  # noqa: E712
    bps = vat_bps(db)
    return {"can_manage": ctx.has(*ADMINS), "vat_bps": bps, "providers": list(gw.PROVIDERS), "manual_methods": list(MANUAL_METHODS),
            "pay_to": {"bkash": get_setting(db, "pay_bkash"), "nagad": get_setting(db, "pay_nagad"), "bank": get_setting(db, "pay_bank")},
            **{k: {"balance": bal[k], "threshold": low[k], "is_low": bal[k] < low[k], **usage30(db, org, k)} for k in KINDS},
            "packs": [{**_pack_out(p), "vat": vat_for(p.price, bps), "total": p.price + vat_for(p.price, bps)} for p in packs]}


class ThresholdIn(BaseModel):
    sms_low: int = Field(ge=0, le=1000000)
    email_low: int = Field(ge=0, le=1000000)


@router.put("/threshold")
def set_threshold(body: ThresholdIn, ctx: Ctx = Depends(property_ctx), db: Session = Depends(get_db)):
    ctx.need(*ADMINS)
    s = db.scalar(select(CreditSetting).where(CreditSetting.org_id == ctx.property.org_id))
    if not s:
        s = CreditSetting(org_id=ctx.property.org_id)
        db.add(s)
    s.sms_low, s.email_low = body.sms_low, body.email_low
    audit(db, user_id=ctx.user.id, org_id=ctx.property.org_id, property_id=ctx.property.id, action="credits.threshold", entity="credit_setting", entity_id=ctx.property.org_id, meta=body.model_dump())
    db.commit()
    return {"sms_low": s.sms_low, "email_low": s.email_low}


@router.get("/purchases")
def purchases(page: int = Query(1, ge=1), size: int = Query(10, ge=1, le=100), q: str = "", ctx: Ctx = Depends(property_ctx), db: Session = Depends(get_db)):
    _need(ctx)
    stmt = select(CreditPurchase).where(CreditPurchase.org_id == ctx.property.org_id, CreditPurchase.status != "created")
    if q.strip():
        like = f"%{q.strip()}%"
        stmt = stmt.where(or_(CreditPurchase.pack_name.ilike(like), CreditPurchase.trx_id.ilike(like), CreditPurchase.method.ilike(like), CreditPurchase.status.ilike(like)))
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = db.scalars(stmt.order_by(CreditPurchase.id.desc()).offset((page - 1) * size).limit(size)).all()
    return {"total": total, "page": page, "size": size, "rows": [_purchase_out(db, p) for p in rows]}


def _active_pack(db: Session, pack_id: int) -> CreditPack:
    pack = db.get(CreditPack, pack_id)
    if not pack or not pack.active:
        raise HTTPException(404, "Pack not found")
    return pack


class CheckoutIn(BaseModel):
    pack_id: int
    provider: str = Field(pattern="^(bkash|nagad|card)$")


@router.post("/checkout", status_code=201)
def checkout(body: CheckoutIn, ctx: Ctx = Depends(property_ctx), db: Session = Depends(get_db)):
    _need(ctx)
    p = _new_purchase(db, ctx, _active_pack(db, body.pack_id), "gateway", body.provider)
    audit(db, user_id=ctx.user.id, org_id=p.org_id, property_id=ctx.property.id, action="credits.checkout", entity="credit_purchase", entity_id=p.id, meta={"provider": body.provider, "total": p.total, "credits": p.credits})
    db.commit()
    return {"session_id": p.token, "redirect_url": f"/pay/credits/{p.token}", "total": p.total}


def _mine(db: Session, token: str, user: User) -> CreditPurchase:
    p = db.scalar(select(CreditPurchase).where(CreditPurchase.token == token, CreditPurchase.mode == "gateway"))
    if not p or p.user_id != user.id:
        raise HTTPException(404, "Not found")
    return p


@router.get("/sandbox/{token}")
def sandbox(token: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    """The practice 'provider' page asks for its details and gets the signed payloads a real provider would post to the callback."""
    p = _mine(db, token, user)
    trx = gw.provider(p.method).sandbox_trx(p.token)
    payload = lambda st: {"session": p.token, "status": st, "trx_id": trx if st == "success" else "", "amount": p.total, "sig": gw.sign(p.token, st, p.total, trx if st == "success" else "")}  # noqa: E731
    return {**_purchase_out(db, p), "pay": payload("success"), "fail": payload("failed")}


class CallbackIn(BaseModel):
    status: str
    trx_id: str = ""
    amount: int
    sig: str


@router.post("/callback/{token}")
def callback(token: str, body: CallbackIn, db: Session = Depends(get_db)):
    """Called by the provider (in the sandbox: by the hosted page). No sign-in; the signed payload is the proof. One credit grant per session."""
    p = db.scalar(select(CreditPurchase).where(CreditPurchase.token == token, CreditPurchase.mode == "gateway"))
    if not p:
        raise HTTPException(404, "Not found")
    res = gw.provider(p.method).verify({"session": token, **body.model_dump()})
    if not res["valid"]:
        raise HTTPException(403, "Bad signature")
    if p.status == "paid":
        return {"status": "paid", "invoice_id": p.invoice_id, "replayed": True}
    if p.status in ("failed", "expired"):
        raise HTTPException(409, f"This payment session is {p.status}")
    if p.expires_at and _aware(p.expires_at) < now():
        p.status, p.completed_at = "expired", now()
        db.commit()
        raise HTTPException(410, "This payment session expired")
    if not res["ok"]:
        if _claim(db, p, "created"):
            p.status, p.completed_at = "failed", now()
            audit(db, user_id=p.user_id, org_id=p.org_id, action="credits.failed", entity="credit_purchase", entity_id=p.id)
        db.commit()
        return {"status": p.status, "invoice_id": None}
    if res["amount"] != p.total:
        raise HTTPException(422, "Amount does not match the checkout")
    if not _claim(db, p, "created"):
        db.rollback()
        db.refresh(p)
        return {"status": p.status, "invoice_id": p.invoice_id, "replayed": True}
    inv = settle(db, p, method=p.method, trx_id=res["trx_id"], by_user=p.user_id)
    audit(db, user_id=p.user_id, org_id=p.org_id, action="credits.paid", entity="credit_purchase", entity_id=p.id, meta={"credits": p.credits, "kind": p.kind, "total": p.total, "invoice": inv.number})
    db.commit()
    return {"status": "paid", "invoice_id": inv.id, "invoice": inv.number}


class ManualIn(BaseModel):
    pack_id: int
    method: str = Field(pattern="^(bkash|nagad|bank)$")
    trx_id: str = Field(min_length=4, max_length=40)
    amount: int = Field(gt=0)   # paisa the admin says they sent
    note: str = Field(default="", max_length=200)


@router.post("/manual", status_code=201)
def manual(body: ManualIn, ctx: Ctx = Depends(property_ctx), db: Session = Depends(get_db)):
    """Pay by transfer outside the app. Creates a PENDING invoice; credits come only after SaaS finance verifies."""
    ctx.need(*BUYERS)
    trx = body.trx_id.strip()
    if db.scalar(select(CreditPurchase.id).where(CreditPurchase.mode == "manual", CreditPurchase.trx_id == trx, CreditPurchase.status.in_(("pending", "paid")))):
        raise HTTPException(409, "This transaction ID was already submitted")
    p = _new_purchase(db, ctx, _active_pack(db, body.pack_id), "manual", body.method)
    p.trx_id, p.claimed_amount, p.note = trx, body.amount, body.note.strip()
    inv = SaasInvoice(number=new_invoice_number(db), org_id=p.org_id, kind="credits", description=f"{p.credits} {p.kind.upper()} credits, {p.pack_name}"[:200], amount=p.total, status="pending",
                      issued_at=now(), due_at=now() + timedelta(days=7), method=p.method, trx_id=trx, items=_items(p), vat_bps=p.vat_bps, vat_amount=p.vat)
    db.add(inv)
    db.flush()
    p.invoice_id = inv.id
    audit(db, user_id=ctx.user.id, org_id=p.org_id, property_id=ctx.property.id, action="credits.manual", entity="credit_purchase", entity_id=p.id, meta={"method": body.method, "trx": trx, "claimed": body.amount, "total": p.total})
    db.commit()
    return _purchase_out(db, p)


def _invoice_out(db: Session, i: SaasInvoice) -> dict:
    o = db.get(Organization, i.org_id)
    sub = (i.amount or 0) - (i.vat_amount or 0)
    return {"id": i.id, "number": i.number, "kind": i.kind, "status": i.status, "description": i.description, "issued_at": i.issued_at.isoformat(), "paid_at": i.paid_at.isoformat() if i.paid_at else None,
            "method": i.method, "trx_id": i.trx_id, "items": i.items or [], "subtotal": sub, "vat_bps": i.vat_bps or 0, "vat": i.vat_amount or 0, "total": i.amount,
            "buyer": {"name": o.name if o else "", "name_bn": o.name_bn if o else "", "city": o.city if o else ""}, "seller": {"name": "FlatWise", "city": "Dhaka"}}


@router.get("/invoices/{invoice_id}")
def invoice(invoice_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Printable invoice or receipt. Buyer-side credit roles of that organization, or SaaS staff with money access."""
    i = db.get(SaasInvoice, invoice_id)
    if not i or i.kind != "credits":
        raise HTTPException(404, "Not found")
    ok = user.saas_role in MONEY
    if not ok:
        ok = bool(db.scalar(select(Membership.id).where(Membership.user_id == user.id, Membership.org_id == i.org_id, Membership.role.in_(BUYERS))))
    if not ok:
        raise HTTPException(404, "Not found")
    return _invoice_out(db, i)


# ---------------- console
class PackIn(BaseModel):
    kind: str = Field(pattern="^(sms|email)$")
    name: str = Field(min_length=1, max_length=80)
    name_bn: str = Field(min_length=1, max_length=80)
    credits: int = Field(ge=1, le=10_000_000)
    price: int = Field(ge=1, le=1_000_000_000)   # paisa
    active: bool = True
    sort: int = 0


@console.get("/packs")
def packs(db: Session = Depends(get_db)):
    return [_pack_out(p) for p in db.scalars(select(CreditPack).order_by(CreditPack.kind, CreditPack.sort, CreditPack.credits))]


@console.post("/packs", status_code=201)
def add_pack(body: PackIn, user: User = Depends(require_saas(*MONEY)), db: Session = Depends(get_db)):
    p = CreditPack(**body.model_dump())
    db.add(p)
    db.flush()
    audit(db, user_id=user.id, action="credits.pack.add", entity="credit_pack", entity_id=p.id, meta=body.model_dump())
    db.commit()
    return _pack_out(p)


@console.put("/packs/{pack_id}")
def edit_pack(pack_id: int, body: PackIn, user: User = Depends(require_saas(*MONEY)), db: Session = Depends(get_db)):
    p = db.get(CreditPack, pack_id)
    if not p:
        raise HTTPException(404, "Not found")
    before = _pack_out(p)
    for k, v in body.model_dump().items():
        setattr(p, k, v)
    audit(db, user_id=user.id, action="credits.pack.edit", entity="credit_pack", entity_id=p.id, meta={"from": before, "to": body.model_dump()})
    db.commit()
    return _pack_out(p)


class SettingsIn(BaseModel):
    vat_bps: int = Field(ge=0, le=5000)
    pay_bkash: str = Field(default="", max_length=200)
    pay_nagad: str = Field(default="", max_length=200)
    pay_bank: str = Field(default="", max_length=200)


def _settings_out(db: Session) -> dict:
    return {"vat_bps": vat_bps(db), "pay_bkash": get_setting(db, "pay_bkash"), "pay_nagad": get_setting(db, "pay_nagad"), "pay_bank": get_setting(db, "pay_bank")}


@console.get("/settings")
def get_settings(db: Session = Depends(get_db)):
    return _settings_out(db)


@console.put("/settings")
def put_settings(body: SettingsIn, user: User = Depends(require_saas(*MONEY)), db: Session = Depends(get_db)):
    before = _settings_out(db)
    for k, v in body.model_dump().items():
        r = db.get(PlatformSetting, k)
        if r:
            r.value = str(v)
        else:
            db.add(PlatformSetting(key=k, value=str(v)))
    audit(db, user_id=user.id, action="credits.settings", entity="platform_setting", entity_id="credits", meta={"from": before, "to": body.model_dump()})
    db.commit()
    return _settings_out(db)


def _paged(db: Session, stmt, page: int, size: int):
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    return total, db.scalars(stmt.order_by(CreditPurchase.id.desc()).offset((page - 1) * size).limit(size)).all()


@console.get("/sales")
def sales(page: int = Query(1, ge=1), size: int = Query(10, ge=1, le=100), q: str = "", status: str = "", kind: str = "", user: User = Depends(require_saas(*MONEY)), db: Session = Depends(get_db)):
    stmt = select(CreditPurchase).join(Organization, Organization.id == CreditPurchase.org_id).where(CreditPurchase.status != "created")
    if status:
        stmt = stmt.where(CreditPurchase.status == status)
    if kind:
        stmt = stmt.where(CreditPurchase.kind == kind)
    if q.strip():
        like = f"%{q.strip()}%"
        stmt = stmt.where(or_(Organization.name.ilike(like), CreditPurchase.trx_id.ilike(like), CreditPurchase.pack_name.ilike(like)))
    total, rows = _paged(db, stmt, page, size)
    paid = db.scalar(select(func.coalesce(func.sum(CreditPurchase.total), 0)).where(CreditPurchase.status == "paid")) or 0
    return {"total": total, "page": page, "size": size, "paid_total": int(paid), "rows": [_purchase_out(db, p, org=True) for p in rows]}


@console.get("/queue")
def queue(page: int = Query(1, ge=1), size: int = Query(10, ge=1, le=100), user: User = Depends(require_saas(*MONEY)), db: Session = Depends(get_db)):
    stmt = select(CreditPurchase).where(CreditPurchase.mode == "manual", CreditPurchase.status == "pending")
    total, rows = _paged(db, stmt, page, size)
    return {"total": total, "page": page, "size": size, "rows": [{**_purchase_out(db, p, org=True), "mismatch": p.claimed_amount != p.total} for p in rows]}


def _pending(db: Session, pid: int) -> CreditPurchase:
    p = db.get(CreditPurchase, pid)
    if not p or p.mode != "manual":
        raise HTTPException(404, "Not found")
    return p


@console.post("/purchases/{pid}/verify")
def verify(pid: int, user: User = Depends(require_saas(*MONEY)), db: Session = Depends(get_db)):
    p = _pending(db, pid)
    if p.status == "paid":
        return _purchase_out(db, p, org=True)           # already verified: no second grant
    if p.status != "pending":
        raise HTTPException(409, f"This purchase is {p.status}")
    if p.claimed_amount != p.total:
        raise HTTPException(422, "The amount sent does not match the invoice. Reject it or ask the building to pay the difference.")
    if not _claim(db, p, "pending"):
        db.rollback()
        db.refresh(p)
        return _purchase_out(db, p, org=True)
    p.verified_by = user.id
    inv = settle(db, p, method=p.method, trx_id=p.trx_id, by_user=user.id)
    audit(db, user_id=user.id, org_id=p.org_id, action="credits.verify", entity="credit_purchase", entity_id=p.id, meta={"credits": p.credits, "kind": p.kind, "total": p.total, "invoice": inv.number})
    db.commit()
    return _purchase_out(db, p, org=True)


class RejectIn(BaseModel):
    reason: str = Field(min_length=3, max_length=200)


@console.post("/purchases/{pid}/reject")
def reject(pid: int, body: RejectIn, user: User = Depends(require_saas(*MONEY)), db: Session = Depends(get_db)):
    p = _pending(db, pid)
    if p.status != "pending":
        raise HTTPException(409, f"This purchase is {p.status}")
    p.status, p.note, p.completed_at, p.verified_by = "rejected", body.reason, now(), user.id
    inv = db.get(SaasInvoice, p.invoice_id) if p.invoice_id else None
    if inv and inv.status == "pending":
        inv.status = "void"
    audit(db, user_id=user.id, org_id=p.org_id, action="credits.reject", entity="credit_purchase", entity_id=p.id, meta={"reason": body.reason})
    db.commit()
    return _purchase_out(db, p, org=True)


class GrantIn(BaseModel):
    org_id: int
    kind: str = Field(pattern="^(sms|email)$")
    credits: int = Field(ge=1, le=1_000_000)
    reason: str = Field(min_length=3, max_length=50)


@console.post("/grant", status_code=201)
def grant(body: GrantIn, user: User = Depends(require_saas(*MONEY)), db: Session = Depends(get_db)):
    """Bonus credits with a reason. A ledger row, never an edit of the balance."""
    if not db.get(Organization, body.org_id):
        raise HTTPException(404, "Not found")
    db.add(_ledger(body.kind)(org_id=body.org_id, delta=body.credits, reason=f"Bonus: {body.reason.strip()}"[:60], by_user_id=user.id))
    audit(db, user_id=user.id, org_id=body.org_id, action="credits.grant", entity=body.kind, entity_id=body.org_id, meta=body.model_dump(), note=body.reason)
    db.commit()
    return {"balance": balance(db, body.org_id, body.kind)}


@console.get("/balances")
def balances(page: int = Query(1, ge=1), size: int = Query(10, ge=1, le=100), q: str = "", low: bool = False, db: Session = Depends(get_db)):
    orgs = db.scalars(select(Organization).order_by(Organization.name)).all()
    rows = []
    for o in orgs:
        if q.strip() and q.strip().lower() not in f"{o.name} {o.name_bn} {o.city}".lower():
            continue
        lo_s, lo_e = thresholds(db, o.id)
        s, e = sms_balance(db, o.id), email_balance(db, o.id)
        is_low = s < lo_s or e < lo_e
        if low and not is_low:
            continue
        rows.append({"id": o.id, "name": o.name, "name_bn": o.name_bn, "city": o.city, "status": o.status, "sms": s, "email": e, "sms_low": lo_s, "email_low": lo_e, "low": is_low})
    return {"total": len(rows), "page": page, "size": size, "rows": rows[(page - 1) * size: page * size]}
