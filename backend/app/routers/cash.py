"""Cash collection. A caretaker takes cash, the payer confirms (code by SMS or a tap in the app), the cash counts as custody until the treasurer accepts the hand-over."""
import hashlib
import hmac
import secrets
from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import config
from ..audit import audit
from ..db import get_db
from ..deps import Ctx, property_ctx
from ..models.billing import Invoice, Message, Payment
from ..models.cash import CashEntry, Remittance
from ..models.core import User, now
from ..models.property import Occupancy, Unit
from ..permissions import MANAGE, MONEY_VIEW
from ..services.messaging import deliver
from . import billing as B

router = APIRouter(prefix="/api/cash", tags=["cash"])
CUSTODY_LIMIT = 5_000_000          # BDT 50,000 in paisa
OTP_SECONDS, MAX_TRIES, LOCK_MINUTES = 300, 3, 60
COLLECTORS = {"CARETAKER"} | MANAGE
DECIDERS = MANAGE | {"TREASURER"}


def _aware(d):
    return d if d is None or d.tzinfo else d.replace(tzinfo=now().tzinfo)


def _hash(eid: int, code: str) -> str:
    return hashlib.sha256(f"{eid}:{code}:{config.SECRET_KEY}".encode()).hexdigest()


def _gate(ctx: Ctx):
    ctx.feature("billing")
    ctx.feature("caretaker_app")


def _custody(db: Session, pid: int, collector: int) -> int:
    return int(db.scalar(select(func.coalesce(func.sum(CashEntry.amount), 0)).where(CashEntry.property_id == pid, CashEntry.collector_id == collector, CashEntry.status.in_(("pending", "held")))) or 0)


def _entry(db: Session, e: CashEntry, units: dict, users: dict) -> dict:
    return {"id": e.id, "unit": units.get(e.unit_id, ""), "unit_id": e.unit_id, "amount": e.amount, "status": e.status, "mode": e.mode, "collector": users.get(e.collector_id, ""),
            "collector_id": e.collector_id, "at": e.created_at.isoformat(), "confirmed_at": e.confirmed_at.isoformat() if e.confirmed_at else None,
            "locked": bool(e.locked_until and _aware(e.locked_until) > now()), "locked_until": e.locked_until.isoformat() if e.locked_until else None,
            "expired": bool(e.status == "pending" and e.mode == "otp" and e.code_expires and _aware(e.code_expires) < now()), "tries_left": max(0, MAX_TRIES - e.attempts), "payment_id": e.payment_id}


def _maps(db: Session, ctx: Ctx):
    units = {u.id: u.number for u in db.scalars(select(Unit).where(Unit.property_id == ctx.property.id))}
    users = dict(db.execute(select(User.id, User.name)).all())
    return units, users


class EntryIn(BaseModel):
    invoice_id: int
    amount: int = Field(gt=0)


def _send_code(db: Session, ctx: Ctx, e: CashEntry, invoice: Invoice) -> str:
    code = f"{secrets.randbelow(900000) + 100000}"
    e.code_hash, e.code_expires = _hash(e.id, code), now() + timedelta(seconds=OTP_SECONDS)
    occ = db.scalars(select(Occupancy).where(Occupancy.unit_id == e.unit_id, Occupancy.active).order_by(Occupancy.kind.desc())).first()
    usr = db.get(User, occ.user_id) if occ and occ.user_id else None
    lang = usr.lang if usr else "bn"
    amt = f"BDT {e.amount / 100:,.0f}"
    body = (f"{ctx.property.name}: আপনি {amt} নগদ দিয়েছেন? কোড {code}। ৫ মিনিট বৈধ। কাউকে কোড বলবেন না।" if lang == "bn"
            else f"{ctx.property.name}: did you hand over {amt} in cash? Code {code}. Valid 5 minutes. Do not share it.")
    if occ:
        m = Message(property_id=ctx.property.id, unit_id=e.unit_id, to_name=occ.name, to_phone=occ.phone, template="cash_otp", lang=lang, idem_key=f"cash{e.id}:{secrets.token_hex(4)}", body=body.replace(code, "••••••"))
        db.add(m)
        deliver(db, ctx.property.org_id, m)
    return code


@router.post("/entries", status_code=201)
def create(body: EntryIn, ctx: Ctx = Depends(property_ctx), db: Session = Depends(get_db)):
    _gate(ctx)
    ctx.need(*COLLECTORS)
    inv = db.get(Invoice, body.invoice_id)
    if not inv or inv.property_id != ctx.property.id or inv.status in ("paid", "void"):
        raise HTTPException(422, "This invoice cannot take a payment")
    if body.amount > inv.total - inv.paid:
        raise HTTPException(422, "Amount is more than the balance")
    if _custody(db, ctx.property.id, ctx.user.id) + body.amount > CUSTODY_LIMIT:
        raise HTTPException(409, "Cash in your hand is over the limit. Hand it to the treasurer first.")
    otp = "cash_otp" in ctx.features
    e = CashEntry(property_id=ctx.property.id, invoice_id=inv.id, unit_id=inv.unit_id, amount=body.amount, collector_id=ctx.user.id, mode="otp" if otp else "link")
    db.add(e)
    db.flush()
    code = _send_code(db, ctx, e, inv) if otp else ""
    audit(db, user_id=ctx.user.id, org_id=ctx.property.org_id, property_id=ctx.property.id, action="cash.entry.create", entity="cash", entity_id=e.id, meta={"amount": e.amount, "unit": e.unit_id, "mode": e.mode})
    db.commit()
    units, users = _maps(db, ctx)
    return {**_entry(db, e, units, users), "demo_code": code if config.DEMO and code else ""}


def _finish(db: Session, ctx: Ctx, e: CashEntry) -> None:
    inv = db.get(Invoice, e.invoice_id)
    p = Payment(property_id=e.property_id, invoice_id=e.invoice_id, unit_id=e.unit_id, amount=e.amount, method="cash", paid_on=date.today(), status="verified", submitted_by=e.collector_id,
                verified_by=e.collector_id, verified_at=now(), note=f"Cash entry {e.id}")
    db.add(p)
    db.flush()
    p.receipt_no = B._receipt_no(db, e.property_id)
    db.flush()
    B._refresh(db, inv)
    for hook in B.POST_VERIFY:
        hook(db, ctx, p)
    e.status, e.payment_id, e.confirmed_at = "held", p.id, now()


def _mine(ctx: Ctx, e: CashEntry | None, db: Session) -> CashEntry:
    if not e or e.property_id != ctx.property.id:
        raise HTTPException(404, "Not found")
    return e


class CodeIn(BaseModel):
    code: str = Field(min_length=6, max_length=6)


@router.post("/entries/{eid}/code")
def enter_code(eid: int, body: CodeIn, ctx: Ctx = Depends(property_ctx), db: Session = Depends(get_db)):
    _gate(ctx)
    ctx.need(*COLLECTORS)
    e = _mine(ctx, db.get(CashEntry, eid), db)
    if e.status != "pending" or e.mode != "otp":
        raise HTTPException(422, "Nothing to confirm")
    if e.locked_until and _aware(e.locked_until) > now():
        raise HTTPException(423, "Too many wrong codes. Try again after one hour or ask the payer to confirm in the app.")
    if not e.code_expires or _aware(e.code_expires) < now():
        raise HTTPException(410, "The code has expired. Send a new one.")
    if not hmac.compare_digest(_hash(e.id, body.code), e.code_hash or ""):
        e.attempts += 1
        if e.attempts >= MAX_TRIES:
            e.locked_until = now() + timedelta(minutes=LOCK_MINUTES)
        audit(db, user_id=ctx.user.id, org_id=ctx.property.org_id, property_id=ctx.property.id, action="cash.code.wrong", entity="cash", entity_id=e.id)
        db.commit()
        raise HTTPException(422, "Wrong code" + ("" if e.attempts >= MAX_TRIES else f". {MAX_TRIES - e.attempts} tries left."))
    _finish(db, ctx, e)
    audit(db, user_id=ctx.user.id, org_id=ctx.property.org_id, property_id=ctx.property.id, action="cash.entry.confirm", entity="cash", entity_id=e.id, meta={"by": "code"})
    db.commit()
    units, users = _maps(db, ctx)
    return _entry(db, e, units, users)


@router.post("/entries/{eid}/resend")
def resend(eid: int, ctx: Ctx = Depends(property_ctx), db: Session = Depends(get_db)):
    _gate(ctx)
    ctx.need(*COLLECTORS)
    e = _mine(ctx, db.get(CashEntry, eid), db)
    if e.status != "pending" or e.mode != "otp" or (e.locked_until and _aware(e.locked_until) > now()):
        raise HTTPException(422, "Cannot send a new code")
    code = _send_code(db, ctx, e, db.get(Invoice, e.invoice_id))
    db.commit()
    return {"demo_code": code if config.DEMO else ""}


@router.post("/entries/{eid}/confirm")
def payer_confirm(eid: int, ctx: Ctx = Depends(property_ctx), db: Session = Depends(get_db)):
    """The payer taps Confirm in their own account. Works with or without the code, and is the way out of a lockout."""
    ctx.feature("cash_confirm")
    e = _mine(ctx, db.get(CashEntry, eid), db)
    if e.status != "pending" or e.unit_id not in ctx.unit_ids:
        raise HTTPException(403, "Your role cannot do this")
    _finish(db, ctx, e)
    audit(db, user_id=ctx.user.id, org_id=ctx.property.org_id, property_id=ctx.property.id, action="cash.entry.confirm", entity="cash", entity_id=e.id, meta={"by": "payer"})
    db.commit()
    units, users = _maps(db, ctx)
    return _entry(db, e, units, users)


@router.post("/entries/{eid}/cancel")
def cancel(eid: int, ctx: Ctx = Depends(property_ctx), db: Session = Depends(get_db)):
    _gate(ctx)
    e = _mine(ctx, db.get(CashEntry, eid), db)
    if e.status != "pending" or (e.collector_id != ctx.user.id and not ctx.has(*MANAGE)):
        raise HTTPException(403, "Your role cannot do this")
    e.status = "cancelled"
    audit(db, user_id=ctx.user.id, org_id=ctx.property.org_id, property_id=ctx.property.id, action="cash.entry.cancel", entity="cash", entity_id=e.id)
    db.commit()
    return {"ok": True}


@router.get("/open-invoices")
def open_invoices(ctx: Ctx = Depends(property_ctx), db: Session = Depends(get_db)):
    """Unpaid invoices a caretaker can take cash against. Shows flat and balance only, no contact details."""
    _gate(ctx)
    ctx.need(*COLLECTORS)
    units = {u.id: u for u in db.scalars(select(Unit).where(Unit.property_id == ctx.property.id))}
    rows = db.scalars(select(Invoice).where(Invoice.property_id == ctx.property.id, Invoice.status.in_(("open", "partial"))).order_by(Invoice.unit_id, Invoice.period)).all()
    return [{"id": i.id, "unit": units[i.unit_id].number, "period": i.period, "balance": i.total - i.paid, "overdue": i.due_date < date.today()} for i in rows]


@router.get("/entries")
def entries(ctx: Ctx = Depends(property_ctx), db: Session = Depends(get_db)):
    ctx.feature("billing")
    stmt = select(CashEntry).where(CashEntry.property_id == ctx.property.id).order_by(CashEntry.id.desc()).limit(200)
    if ctx.has(*MONEY_VIEW):
        pass
    elif ctx.has("CARETAKER"):
        stmt = stmt.where(CashEntry.collector_id == ctx.user.id)
    elif ctx.unit_ids:
        stmt = stmt.where(CashEntry.unit_id.in_(ctx.unit_ids))
    else:
        raise HTTPException(403, "Your role cannot do this")
    units, users = _maps(db, ctx)
    return [_entry(db, e, units, users) for e in db.scalars(stmt)]


@router.get("/custody")
def custody(ctx: Ctx = Depends(property_ctx), db: Session = Depends(get_db)):
    _gate(ctx)
    ctx.need(*(MONEY_VIEW | {"CARETAKER"}))
    users = dict(db.execute(select(User.id, User.name)).all())
    rows = []
    for cid in sorted(set(db.scalars(select(CashEntry.collector_id).where(CashEntry.property_id == ctx.property.id)))):
        if not ctx.has(*MONEY_VIEW) and cid != ctx.user.id:
            continue
        held = int(db.scalar(select(func.coalesce(func.sum(CashEntry.amount), 0)).where(CashEntry.property_id == ctx.property.id, CashEntry.collector_id == cid, CashEntry.status == "held")) or 0)
        hand = int(db.scalar(select(func.coalesce(func.sum(CashEntry.amount), 0)).where(CashEntry.property_id == ctx.property.id, CashEntry.collector_id == cid, CashEntry.status == "handover")) or 0)
        pend = int(db.scalar(select(func.coalesce(func.sum(CashEntry.amount), 0)).where(CashEntry.property_id == ctx.property.id, CashEntry.collector_id == cid, CashEntry.status == "pending")) or 0)
        rows.append({"collector_id": cid, "name": users.get(cid, ""), "held": held, "handover": hand, "pending": pend, "limit": CUSTODY_LIMIT})
    return {"limit": CUSTODY_LIMIT, "rows": rows}


@router.post("/remittances", status_code=201)
def hand_over(ctx: Ctx = Depends(property_ctx), db: Session = Depends(get_db)):
    """The caretaker hands all confirmed cash to the treasurer."""
    _gate(ctx)
    ctx.need(*COLLECTORS)
    held = db.scalars(select(CashEntry).where(CashEntry.property_id == ctx.property.id, CashEntry.collector_id == ctx.user.id, CashEntry.status == "held")).all()
    if not held:
        raise HTTPException(422, "No confirmed cash to hand over")
    r = Remittance(property_id=ctx.property.id, collector_id=ctx.user.id, amount=sum(e.amount for e in held))
    db.add(r)
    db.flush()
    for e in held:
        e.status, e.remittance_id = "handover", r.id
    audit(db, user_id=ctx.user.id, org_id=ctx.property.org_id, property_id=ctx.property.id, action="cash.remit.submit", entity="remittance", entity_id=r.id, meta={"amount": r.amount, "entries": len(held)})
    db.commit()
    return _rem(r, {ctx.user.id: ctx.user.name}, len(held))


def _rem(r: Remittance, users: dict, n: int = 0) -> dict:
    return {"id": r.id, "collector": users.get(r.collector_id, ""), "amount": r.amount, "status": r.status, "at": r.created_at.isoformat(), "decided_at": r.decided_at.isoformat() if r.decided_at else None, "entries": n}


@router.get("/remittances")
def remittances(ctx: Ctx = Depends(property_ctx), db: Session = Depends(get_db)):
    _gate(ctx)
    ctx.need(*(MONEY_VIEW | {"CARETAKER"}))
    users = dict(db.execute(select(User.id, User.name)).all())
    stmt = select(Remittance).where(Remittance.property_id == ctx.property.id).order_by(Remittance.id.desc()).limit(100)
    if not ctx.has(*MONEY_VIEW):
        stmt = stmt.where(Remittance.collector_id == ctx.user.id)
    return [_rem(r, users, db.scalar(select(func.count()).select_from(CashEntry).where(CashEntry.remittance_id == r.id)) or 0) for r in db.scalars(stmt)]


@router.post("/remittances/{rid}/{action}")
def decide(rid: int, action: str, ctx: Ctx = Depends(property_ctx), db: Session = Depends(get_db)):
    _gate(ctx)
    ctx.need(*DECIDERS)
    r = db.get(Remittance, rid)
    if not r or r.property_id != ctx.property.id or r.status != "submitted" or action not in ("accept", "reject"):
        raise HTTPException(422, "Nothing to decide")
    r.status, r.decided_by, r.decided_at = ("accepted" if action == "accept" else "rejected"), ctx.user.id, now()
    for e in db.scalars(select(CashEntry).where(CashEntry.remittance_id == r.id)):
        e.status = "remitted" if action == "accept" else "held"
        if action == "reject":
            e.remittance_id = None
    audit(db, user_id=ctx.user.id, org_id=ctx.property.org_id, property_id=ctx.property.id, action=f"cash.remit.{action}", entity="remittance", entity_id=r.id, meta={"amount": r.amount})
    db.commit()
    return _rem(r, {u.id: u.name for u in db.scalars(select(User).where(User.id == r.collector_id))})
