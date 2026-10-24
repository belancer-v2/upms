"""Service charge API. Money is integer paisa everywhere."""
from collections import defaultdict
from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..audit import audit
from ..db import get_db
from ..deps import Ctx, property_ctx
from ..models.billing import ChargeRule, Invoice, InvoiceLine, Message, Payment
from ..models.core import now
from ..models.property import Occupancy, Unit
from ..permissions import COMMITTEE, MANAGE, MONEY_VIEW
from ..services.messaging import deliver

router = APIRouter(prefix="/api/billing", tags=["billing"])
MONEY_ROLES = MANAGE | {"TREASURER"}
STEPS = [("before", -3), ("due", 0), ("o7", 7), ("o15", 15), ("o30", 30)]


def _gate(ctx: Ctx):
    ctx.feature("billing")


def _can_see_all(ctx: Ctx) -> bool:
    return ctx.has(*MONEY_VIEW)


def _period_ok(p: str) -> bool:
    return len(p) == 7 and p[4] == "-" and p[:4].isdigit() and p[5:].isdigit() and 1 <= int(p[5:]) <= 12


def _refresh(db: Session, inv: Invoice) -> None:
    inv.paid = int(db.scalar(select(func.coalesce(func.sum(Payment.amount), 0)).where(Payment.invoice_id == inv.id, Payment.status == "verified")) or 0)
    if inv.status != "void":
        inv.status = "paid" if inv.paid >= inv.total else "partial" if inv.paid > 0 else "open"


def _view_status(inv: Invoice, today: date) -> str:
    if inv.status in ("paid", "void"):
        return inv.status
    return "overdue" if inv.due_date < today else inv.status


def _inv(db: Session, i: Invoice, unit: Unit | None = None, lines: bool = False) -> dict:
    unit = unit or db.get(Unit, i.unit_id)
    d = {"id": i.id, "number": i.number, "unit_id": i.unit_id, "unit": unit.number if unit else "", "floor": unit.floor if unit else 0, "period": i.period,
         "issue_date": i.issue_date.isoformat(), "due_date": i.due_date.isoformat(), "total": i.total, "paid": i.paid, "balance": max(0, i.total - i.paid),
         "status": _view_status(i, date.today())}
    if lines:
        d["lines"] = [{"description": l.description, "description_bn": l.description_bn, "amount": l.amount} for l in db.scalars(select(InvoiceLine).where(InvoiceLine.invoice_id == i.id).order_by(InvoiceLine.id))]
        d["payments"] = [_pay(p) for p in db.scalars(select(Payment).where(Payment.invoice_id == i.id).order_by(Payment.id))]
        owners = db.scalars(select(Occupancy).where(Occupancy.unit_id == i.unit_id, Occupancy.active)).all()
        d["people"] = [{"kind": o.kind, "name": o.name, "name_bn": o.name_bn} for o in owners]
    return d


def _pay(p: Payment) -> dict:
    return {"id": p.id, "invoice_id": p.invoice_id, "unit_id": p.unit_id, "amount": p.amount, "method": p.method, "trx_id": p.trx_id, "paid_on": p.paid_on.isoformat(), "status": p.status,
            "receipt_no": p.receipt_no, "note": p.note}


def _scoped(ctx: Ctx, stmt):
    if _can_see_all(ctx):
        return stmt
    if not ctx.unit_ids:
        raise HTTPException(403, "No flat is linked to your sign-in")
    return stmt.where(Invoice.unit_id.in_(ctx.unit_ids))


# ---------------- rules
class RuleIn(BaseModel):
    name: str = Field(min_length=2)
    name_bn: str = ""
    kind: str = Field(pattern="^(flat|per_sqft)$")
    amount: int = Field(ge=0)
    active: bool = True


def _rule(r: ChargeRule) -> dict:
    return {"id": r.id, "name": r.name, "name_bn": r.name_bn, "kind": r.kind, "amount": r.amount, "active": r.active}


@router.get("/rules")
def rules(ctx: Ctx = Depends(property_ctx), db: Session = Depends(get_db)):
    _gate(ctx)
    ctx.need(*MONEY_VIEW)
    return [_rule(r) for r in db.scalars(select(ChargeRule).where(ChargeRule.property_id == ctx.property.id).order_by(ChargeRule.id))]


@router.post("/rules", status_code=201)
def add_rule(body: RuleIn, ctx: Ctx = Depends(property_ctx), db: Session = Depends(get_db)):
    _gate(ctx)
    ctx.need(*MONEY_ROLES)
    r = ChargeRule(property_id=ctx.property.id, **body.model_dump())
    db.add(r)
    db.flush()
    audit(db, user_id=ctx.user.id, org_id=ctx.property.org_id, property_id=ctx.property.id, action="billing.rule.add", entity="rule", entity_id=r.id, meta=body.model_dump())
    db.commit()
    return _rule(r)


@router.put("/rules/{rid}")
def edit_rule(rid: int, body: RuleIn, ctx: Ctx = Depends(property_ctx), db: Session = Depends(get_db)):
    _gate(ctx)
    ctx.need(*MONEY_ROLES)
    r = db.get(ChargeRule, rid)
    if not r or r.property_id != ctx.property.id:
        raise HTTPException(404, "Not found")
    for k, v in body.model_dump().items():
        setattr(r, k, v)
    audit(db, user_id=ctx.user.id, org_id=ctx.property.org_id, property_id=ctx.property.id, action="billing.rule.edit", entity="rule", entity_id=r.id, meta=body.model_dump())
    db.commit()
    return _rule(r)


# ---------------- invoices
class RunIn(BaseModel):
    period: str
    due_day: int = Field(default=10, ge=1, le=28)


@router.post("/run")
def run(body: RunIn, ctx: Ctx = Depends(property_ctx), db: Session = Depends(get_db)):
    """Creates one invoice per flat for the period. Pressing it twice creates nothing new."""
    _gate(ctx)
    ctx.need(*MONEY_ROLES)
    if not _period_ok(body.period):
        raise HTTPException(422, "Period must look like 2026-10")
    rule_rows = db.scalars(select(ChargeRule).where(ChargeRule.property_id == ctx.property.id, ChargeRule.active).order_by(ChargeRule.id)).all()
    if not rule_rows:
        raise HTTPException(422, "Add at least one charge rule first")
    y, m = int(body.period[:4]), int(body.period[5:])
    made, total_all = 0, 0
    for u in db.scalars(select(Unit).where(Unit.property_id == ctx.property.id).order_by(Unit.id)):
        if db.scalar(select(Invoice.id).where(Invoice.unit_id == u.id, Invoice.period == body.period)):
            continue
        lines = [(r, int(round(r.amount * u.area_sqft)) if r.kind == "per_sqft" else r.amount) for r in rule_rows]
        total = sum(a for _, a in lines)
        inv = Invoice(property_id=ctx.property.id, unit_id=u.id, period=body.period, number=f"INV-{ctx.property.id}-{body.period}-{u.number}", issue_date=date(y, m, 1), due_date=date(y, m, body.due_day), total=total)
        db.add(inv)
        db.flush()
        for r, a in lines:
            db.add(InvoiceLine(invoice_id=inv.id, description=r.name, description_bn=r.name_bn, amount=a))
        made, total_all = made + 1, total_all + total
    audit(db, user_id=ctx.user.id, org_id=ctx.property.org_id, property_id=ctx.property.id, action="billing.run", entity="period", entity_id=body.period, meta={"created": made, "total": total_all})
    db.commit()
    return {"created": made, "total": total_all}


@router.get("/invoices")
def invoices(period: str = "", status: str = "", ctx: Ctx = Depends(property_ctx), db: Session = Depends(get_db)):
    _gate(ctx)
    stmt = _scoped(ctx, select(Invoice).where(Invoice.property_id == ctx.property.id).order_by(Invoice.period.desc(), Invoice.unit_id))
    if period:
        stmt = stmt.where(Invoice.period == period)
    units = {u.id: u for u in db.scalars(select(Unit).where(Unit.property_id == ctx.property.id))}
    out = [_inv(db, i, units.get(i.unit_id)) for i in db.scalars(stmt)]
    return [i for i in out if not status or i["status"] == status]


@router.get("/invoices/{iid}")
def invoice(iid: int, ctx: Ctx = Depends(property_ctx), db: Session = Depends(get_db)):
    _gate(ctx)
    i = db.get(Invoice, iid)
    if not i or i.property_id != ctx.property.id or (not _can_see_all(ctx) and i.unit_id not in ctx.unit_ids):
        raise HTTPException(404, "Not found")
    return _inv(db, i, lines=True)


@router.post("/invoices/{iid}/void")
def void(iid: int, ctx: Ctx = Depends(property_ctx), db: Session = Depends(get_db)):
    _gate(ctx)
    ctx.need(*MANAGE)
    i = db.get(Invoice, iid)
    if not i or i.property_id != ctx.property.id or i.paid > 0:
        raise HTTPException(422, "Only an unpaid invoice can be voided")
    i.status = "void"
    audit(db, user_id=ctx.user.id, org_id=ctx.property.org_id, property_id=ctx.property.id, action="billing.invoice.void", entity="invoice", entity_id=i.id)
    db.commit()
    return _inv(db, i)


# ---------------- payments
class PayIn(BaseModel):
    amount: int = Field(gt=0)
    method: str = Field(pattern="^(bkash|nagad|bank|cash)$")
    trx_id: str = Field(default="", max_length=40)
    paid_on: date | None = None
    note: str = ""


def _receipt_no(db: Session, pid: int) -> str:
    n = (db.scalar(select(func.count()).select_from(Payment).where(Payment.property_id == pid, Payment.receipt_no != "")) or 0) + 1
    return f"RC-{pid}-{n:05d}"


def _verify(db: Session, ctx: Ctx, p: Payment) -> None:
    p.status, p.verified_by, p.verified_at, p.receipt_no = "verified", ctx.user.id, now(), _receipt_no(db, ctx.property.id)
    db.flush()
    _refresh(db, db.get(Invoice, p.invoice_id))
    for hook in POST_VERIFY:  # the ledger (M6) registers itself here
        hook(db, ctx, p)


POST_VERIFY: list = []


@router.post("/invoices/{iid}/payments", status_code=201)
def add_payment(iid: int, body: PayIn, ctx: Ctx = Depends(property_ctx), db: Session = Depends(get_db)):
    """Treasurer or admin records a payment: it counts at once. A resident submits one: it waits for the treasurer."""
    _gate(ctx)
    i = db.get(Invoice, iid)
    if not i or i.property_id != ctx.property.id or i.status == "void":
        raise HTTPException(404, "Not found")
    staff = ctx.has(*MONEY_ROLES)
    if not staff and i.unit_id not in ctx.unit_ids:
        raise HTTPException(403, "Your role cannot do this")
    if body.method in ("bkash", "nagad") and not body.trx_id.strip():
        raise HTTPException(422, "Enter the transaction ID from the payment message")
    if body.trx_id and db.scalar(select(Payment.id).where(Payment.property_id == ctx.property.id, Payment.trx_id == body.trx_id.strip(), Payment.status != "rejected")):
        raise HTTPException(409, "This transaction ID was already used")
    if body.amount > (i.total - i.paid) * 1 and i.status == "paid":
        raise HTTPException(422, "This invoice is already paid")
    p = Payment(property_id=ctx.property.id, invoice_id=i.id, unit_id=i.unit_id, amount=body.amount, method=body.method, trx_id=body.trx_id.strip(), paid_on=body.paid_on or date.today(),
                submitted_by=ctx.user.id, note=body.note)
    db.add(p)
    db.flush()
    if staff:
        _verify(db, ctx, p)
    audit(db, user_id=ctx.user.id, org_id=ctx.property.org_id, property_id=ctx.property.id, action="billing.payment.add" if staff else "billing.payment.submit", entity="payment", entity_id=p.id, meta={"amount": body.amount, "method": body.method, "unit": i.unit_id})
    db.commit()
    return _pay(p)


@router.get("/payments")
def payments(status: str = "", ctx: Ctx = Depends(property_ctx), db: Session = Depends(get_db)):
    _gate(ctx)
    stmt = select(Payment, Unit).join(Unit, Unit.id == Payment.unit_id).where(Payment.property_id == ctx.property.id).order_by(Payment.id.desc())
    if not _can_see_all(ctx):
        if not ctx.unit_ids:
            raise HTTPException(403, "No flat is linked to your sign-in")
        stmt = stmt.where(Payment.unit_id.in_(ctx.unit_ids))
    if status:
        stmt = stmt.where(Payment.status == status)
    return [{**_pay(p), "unit": u.number, "period": db.get(Invoice, p.invoice_id).period} for p, u in db.execute(stmt.limit(300))]


@router.post("/payments/{pid}/{action}")
def decide(pid: int, action: str, ctx: Ctx = Depends(property_ctx), db: Session = Depends(get_db)):
    _gate(ctx)
    ctx.need(*MONEY_ROLES)
    p = db.get(Payment, pid)
    if not p or p.property_id != ctx.property.id or action not in ("verify", "reject") or p.status != "pending":
        raise HTTPException(422, "Nothing to decide")
    if action == "verify":
        _verify(db, ctx, p)
    else:
        p.status, p.verified_by, p.verified_at = "rejected", ctx.user.id, now()
    audit(db, user_id=ctx.user.id, org_id=ctx.property.org_id, property_id=ctx.property.id, action=f"billing.payment.{action}", entity="payment", entity_id=p.id)
    db.commit()
    return _pay(p)


@router.get("/receipts/{pid}")
def receipt(pid: int, ctx: Ctx = Depends(property_ctx), db: Session = Depends(get_db)):
    _gate(ctx)
    p = db.get(Payment, pid)
    if not p or p.property_id != ctx.property.id or p.status != "verified" or (not _can_see_all(ctx) and p.unit_id not in ctx.unit_ids):
        raise HTTPException(404, "Not found")
    inv, unit = db.get(Invoice, p.invoice_id), db.get(Unit, p.unit_id)
    who = db.scalars(select(Occupancy).where(Occupancy.unit_id == unit.id, Occupancy.active)).all()
    return {"receipt_no": p.receipt_no, "paid_on": p.paid_on.isoformat(), "amount": p.amount, "method": p.method, "trx_id": p.trx_id, "period": inv.period, "invoice": inv.number,
            "unit": unit.number, "balance_after": max(0, inv.total - inv.paid), "building": ctx.property.name, "building_bn": ctx.property.name_bn, "address": ctx.property.address,
            "people": [{"kind": o.kind, "name": o.name, "name_bn": o.name_bn} for o in who], "received_by": (db.get(__import__("app.models.core", fromlist=["User"]).User, p.verified_by).name if p.verified_by else "")}


# ---------------- dues, collection, reminders
@router.get("/dues")
def dues(ctx: Ctx = Depends(property_ctx), db: Session = Depends(get_db)):
    _gate(ctx)
    ctx.need(*MONEY_VIEW)
    today, rows = date.today(), defaultdict(lambda: {"outstanding": 0, "periods": [], "oldest": 0})
    for i in db.scalars(select(Invoice).where(Invoice.property_id == ctx.property.id, Invoice.status.in_(("open", "partial")), Invoice.due_date < today)):
        r = rows[i.unit_id]
        r["outstanding"] += i.total - i.paid
        r["periods"].append(i.period)
        r["oldest"] = max(r["oldest"], (today - i.due_date).days)
    units = {u.id: u for u in db.scalars(select(Unit).where(Unit.property_id == ctx.property.id))}
    out = []
    for uid, r in rows.items():
        who = db.scalars(select(Occupancy).where(Occupancy.unit_id == uid, Occupancy.active).order_by(Occupancy.kind.desc())).first()
        out.append({"unit_id": uid, "unit": units[uid].number, "name": who.name if who else "", "name_bn": who.name_bn if who else "", "phone": who.phone if who and ctx.has(*MONEY_ROLES) else "",
                    "outstanding": r["outstanding"], "months": len(r["periods"]), "periods": sorted(r["periods"]), "oldest_days": r["oldest"],
                    "bucket": "0-30" if r["oldest"] <= 30 else "31-60" if r["oldest"] <= 60 else "61+"})
    out.sort(key=lambda x: -x["outstanding"])
    buckets = {b: sum(x["outstanding"] for x in out if x["bucket"] == b) for b in ("0-30", "31-60", "61+")}
    return {"total": sum(x["outstanding"] for x in out), "buckets": buckets, "rows": out}


@router.get("/summary")
def summary(period: str = "", ctx: Ctx = Depends(property_ctx), db: Session = Depends(get_db)):
    _gate(ctx)
    ctx.need(*MONEY_VIEW)
    periods = sorted(set(db.scalars(select(Invoice.period).where(Invoice.property_id == ctx.property.id, Invoice.period.notlike("HALL-%")))), reverse=True)
    period = period or (periods[0] if periods else "")

    def agg(p: str):
        rows = db.scalars(select(Invoice).where(Invoice.property_id == ctx.property.id, Invoice.period == p, Invoice.status != "void")).all()
        billed, got = sum(r.total for r in rows), sum(r.paid for r in rows)
        return {"period": p, "billed": billed, "collected": got, "outstanding": billed - got, "pct": round(100 * got / billed) if billed else 0,
                "invoices": len(rows), "paid": sum(r.status == "paid" for r in rows)}
    methods = defaultdict(int)
    for m, a in db.execute(select(Payment.method, Payment.amount).join(Invoice, Invoice.id == Payment.invoice_id).where(Invoice.property_id == ctx.property.id, Invoice.period == period, Payment.status == "verified")):
        methods[m] += a
    pending = db.scalar(select(func.count()).select_from(Payment).where(Payment.property_id == ctx.property.id, Payment.status == "pending")) or 0
    return {"periods": periods, "current": agg(period) if period else None, "trend": [agg(p) for p in sorted(periods)[-6:]], "methods": dict(methods), "pending": pending}


@router.get("/map")
def collection_map(period: str, ctx: Ctx = Depends(property_ctx), db: Session = Depends(get_db)):
    """Status of every flat's invoice for a period: drives the colored building map."""
    _gate(ctx)
    ctx.need(*MONEY_VIEW)
    return {i.unit_id: {"status": _view_status(i, date.today()), "balance": max(0, i.total - i.paid), "invoice_id": i.id} for i in db.scalars(select(Invoice).where(Invoice.property_id == ctx.property.id, Invoice.period == period, Invoice.status != "void"))}


def _text(step: str, lang: str, b: str, amt: str, period: str, due: str) -> str:
    en = {"before": f"{b}: service charge {amt} for {period} is due on {due}. Thank you.", "due": f"{b}: service charge {amt} for {period} is due today. Thank you.",
          "o7": f"{b}: reminder. {amt} for {period} was due on {due}. Please pay this week.", "o15": f"{b}: {amt} for {period} is 15 days overdue. Please pay or call the office.",
          "o30": f"{b}: {amt} for {period} is 30 days overdue. Please contact the committee."}
    bn = {"before": f"{b}: {period} মাসের সার্ভিস চার্জ {amt}, {due} তারিখে দেয়। ধন্যবাদ।", "due": f"{b}: {period} মাসের সার্ভিস চার্জ {amt} আজ দেয়। ধন্যবাদ।",
          "o7": f"{b}: স্মরণ করিয়ে দিচ্ছি। {period} মাসের {amt}, {due} তারিখে দেয় ছিল। এই সপ্তাহে পরিশোধ করুন।", "o15": f"{b}: {period} মাসের {amt} ১৫ দিন বকেয়া। পরিশোধ করুন বা অফিসে ফোন করুন।",
          "o30": f"{b}: {period} মাসের {amt} ৩০ দিন বকেয়া। কমিটির সাথে যোগাযোগ করুন।"}
    return (bn if lang == "bn" else en)[step]


@router.post("/reminders/run")
def reminders(ctx: Ctx = Depends(property_ctx), db: Session = Depends(get_db)):
    """For each unpaid invoice, queues the latest reminder step that is due and not yet sent, then delivers it."""
    _gate(ctx)
    ctx.feature("reminders")
    ctx.need(*MONEY_ROLES)
    today, made, failed = date.today(), 0, 0
    from ..models.core import User
    for i in db.scalars(select(Invoice).where(Invoice.property_id == ctx.property.id, Invoice.status.in_(("open", "partial")))):
        offset = (today - i.due_date).days
        due_steps = [s for s, o in STEPS if offset >= o]
        if not due_steps:
            continue
        step = due_steps[-1]
        key = f"inv{i.id}:{step}"
        if db.scalar(select(Message.id).where(Message.idem_key == key)):
            continue
        occ = db.scalars(select(Occupancy).where(Occupancy.unit_id == i.unit_id, Occupancy.active).order_by(Occupancy.kind.desc())).first()  # tenant first, else owner
        if not occ:
            continue
        usr = db.get(User, occ.user_id) if occ.user_id else None
        lang = usr.lang if usr else "bn"
        amt = f"BDT {(i.total - i.paid) / 100:,.0f}"
        msg = Message(property_id=ctx.property.id, unit_id=i.unit_id, to_name=occ.name, to_phone=occ.phone, template=f"due_{step}", lang=lang, idem_key=key,
                      body=_text(step, lang, ctx.property.name_bn if lang == "bn" and ctx.property.name_bn else ctx.property.name, amt, i.period, i.due_date.strftime("%d %b")))
        db.add(msg)
        deliver(db, ctx.property.org_id, msg)
        made += msg.status == "sent"
        failed += msg.status == "failed"
    audit(db, user_id=ctx.user.id, org_id=ctx.property.org_id, property_id=ctx.property.id, action="billing.reminders.run", meta={"sent": made, "failed": failed})
    db.commit()
    return {"sent": made, "failed": failed}


@router.get("/messages")
def messages(ctx: Ctx = Depends(property_ctx), db: Session = Depends(get_db)):
    _gate(ctx)
    ctx.need(*(MONEY_VIEW))
    units = {u.id: u.number for u in db.scalars(select(Unit).where(Unit.property_id == ctx.property.id))}
    return [{"id": m.id, "at": (m.sent_at or m.created_at).isoformat(), "to": m.to_name, "phone": m.to_phone if ctx.has(*MONEY_ROLES) else "", "unit": units.get(m.unit_id, ""),
             "template": m.template, "lang": m.lang, "body": m.body, "status": m.status, "error": m.error} for m in db.scalars(select(Message).where(Message.property_id == ctx.property.id).order_by(Message.id.desc()).limit(200))]
