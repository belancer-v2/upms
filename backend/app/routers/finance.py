"""Expenses with approval, vendors, budget, the ledger, fixed assets and reports."""
from collections import defaultdict
from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..audit import audit
from ..db import get_db
from ..deps import Ctx, property_ctx
from ..models.billing import Payment
from ..models.core import User, now
from ..models.finance import Account, Asset, Budget, Expense, Journal, JournalLine, Vendor
from ..permissions import MANAGE, MONEY_VIEW
from ..services import ledger
from . import billing as B

router = APIRouter(prefix="/api/finance", tags=["finance"])
DUAL_ABOVE = 5_000_000          # BDT 50,000
CATEGORIES = ["utilities", "repairs", "salary", "fuel", "services", "other"]
REQUEST = MANAGE | {"TREASURER", "SECRETARY", "CARETAKER"}
APPROVE = MANAGE | {"PRESIDENT", "TREASURER"}
PAY = MANAGE | {"TREASURER"}


def _post_payment(db: Session, ctx: Ctx, p: Payment) -> None:
    ledger.post(db, p.property_id, p.paid_on, f"Service charge receipt {p.receipt_no}", [(ledger.METHOD_ACCOUNT[p.method], p.amount, 0), ("4010", 0, p.amount)], "payment", p.id, ctx.user.id)


B.POST_VERIFY.append(_post_payment)   # every confirmed payment lands in the ledger


def _exp(db: Session, e: Expense, vendors: dict, users: dict) -> dict:
    v = vendors.get(e.vendor_id)
    return {"id": e.id, "category": e.category, "title": e.title, "amount": e.amount, "spent_on": e.spent_on.isoformat(), "status": e.status, "needs_two": e.needs_two,
            "approvals": e.approvals, "approvals_needed": 2 if e.needs_two else 1, "requested_by": users.get(e.requested_by, ""), "requested_by_id": e.requested_by,
            "vendor": v.name if v else "", "vendor_bn": v.name_bn if v else "", "method": e.method, "paid_on": e.paid_on.isoformat() if e.paid_on else None, "reason": e.reason}


def _ctx_maps(db: Session, ctx: Ctx):
    return ({v.id: v for v in db.scalars(select(Vendor).where(Vendor.property_id == ctx.property.id))}, {u.id: u.name for u in db.scalars(select(User))})


# ---------------- vendors
class VendorIn(BaseModel):
    name: str = Field(min_length=2)
    name_bn: str = ""
    phone: str = ""
    category: str = "other"


@router.get("/vendors")
def vendors(ctx: Ctx = Depends(property_ctx), db: Session = Depends(get_db)):
    ctx.feature("expenses")
    ctx.need(*(MONEY_VIEW | REQUEST))
    return [{"id": v.id, "name": v.name, "name_bn": v.name_bn, "phone": v.phone, "category": v.category} for v in db.scalars(select(Vendor).where(Vendor.property_id == ctx.property.id).order_by(Vendor.name))]


@router.post("/vendors", status_code=201)
def add_vendor(body: VendorIn, ctx: Ctx = Depends(property_ctx), db: Session = Depends(get_db)):
    ctx.feature("expenses")
    ctx.need(*REQUEST)
    v = Vendor(property_id=ctx.property.id, **body.model_dump())
    db.add(v)
    db.commit()
    return {"id": v.id, "name": v.name, "name_bn": v.name_bn, "phone": v.phone, "category": v.category}


# ---------------- expenses
class ExpenseIn(BaseModel):
    category: str = Field(pattern="^(utilities|repairs|salary|fuel|services|other)$")
    title: str = Field(min_length=3, max_length=160)
    amount: int = Field(gt=0)
    spent_on: date | None = None
    vendor_id: int | None = None


@router.get("/expenses")
def expenses(status: str = "", ctx: Ctx = Depends(property_ctx), db: Session = Depends(get_db)):
    ctx.feature("expenses")
    stmt = select(Expense).where(Expense.property_id == ctx.property.id).order_by(Expense.id.desc()).limit(300)
    if not ctx.has(*MONEY_VIEW):
        ctx.need(*REQUEST)
        stmt = stmt.where(Expense.requested_by == ctx.user.id)
    if status:
        stmt = stmt.where(Expense.status == status)
    vendors_, users = _ctx_maps(db, ctx)
    return [_exp(db, e, vendors_, users) for e in db.scalars(stmt)]


@router.post("/expenses", status_code=201)
def add_expense(body: ExpenseIn, ctx: Ctx = Depends(property_ctx), db: Session = Depends(get_db)):
    ctx.feature("expenses")
    ctx.need(*REQUEST)
    if body.vendor_id and not db.scalar(select(Vendor.id).where(Vendor.id == body.vendor_id, Vendor.property_id == ctx.property.id)):
        raise HTTPException(422, "Unknown vendor")
    e = Expense(property_id=ctx.property.id, category=body.category, vendor_id=body.vendor_id, title=body.title, amount=body.amount, spent_on=body.spent_on or date.today(),
                needs_two=body.amount > DUAL_ABOVE, requested_by=ctx.user.id)
    db.add(e)
    db.flush()
    audit(db, user_id=ctx.user.id, org_id=ctx.property.org_id, property_id=ctx.property.id, action="expense.request", entity="expense", entity_id=e.id, meta={"amount": e.amount, "category": e.category})
    db.commit()
    return _exp(db, e, *_ctx_maps(db, ctx))


def _open(db: Session, ctx: Ctx, eid: int) -> Expense:
    ctx.feature("expenses")
    e = db.get(Expense, eid)
    if not e or e.property_id != ctx.property.id:
        raise HTTPException(404, "Not found")
    return e


@router.post("/expenses/{eid}/approve")
def approve(eid: int, ctx: Ctx = Depends(property_ctx), db: Session = Depends(get_db)):
    ctx.need(*APPROVE)
    e = _open(db, ctx, eid)
    if e.status != "pending":
        raise HTTPException(422, "This request is already decided")
    if e.requested_by == ctx.user.id:
        raise HTTPException(403, "You cannot approve your own request")
    if any(a["user_id"] == ctx.user.id for a in e.approvals):
        raise HTTPException(422, "You already approved this. A second person must approve it.")
    e.approvals = [*e.approvals, {"user_id": ctx.user.id, "name": ctx.user.name, "at": now().isoformat()}]
    if len(e.approvals) >= (2 if e.needs_two else 1):
        e.status = "approved"
    audit(db, user_id=ctx.user.id, org_id=ctx.property.org_id, property_id=ctx.property.id, action="expense.approve", entity="expense", entity_id=e.id, meta={"amount": e.amount, "n": len(e.approvals)})
    db.commit()
    return _exp(db, e, *_ctx_maps(db, ctx))


class ReasonIn(BaseModel):
    reason: str = ""


@router.post("/expenses/{eid}/reject")
def reject(eid: int, body: ReasonIn, ctx: Ctx = Depends(property_ctx), db: Session = Depends(get_db)):
    ctx.need(*APPROVE)
    e = _open(db, ctx, eid)
    if e.status != "pending":
        raise HTTPException(422, "This request is already decided")
    e.status, e.reason = "rejected", body.reason[:200]
    audit(db, user_id=ctx.user.id, org_id=ctx.property.org_id, property_id=ctx.property.id, action="expense.reject", entity="expense", entity_id=e.id)
    db.commit()
    return _exp(db, e, *_ctx_maps(db, ctx))


class PayIn(BaseModel):
    method: str = Field(pattern="^(cash|bank|bkash|nagad)$")
    paid_on: date | None = None


@router.post("/expenses/{eid}/pay")
def pay(eid: int, body: PayIn, ctx: Ctx = Depends(property_ctx), db: Session = Depends(get_db)):
    ctx.need(*PAY)
    e = _open(db, ctx, eid)
    if e.status != "approved":
        raise HTTPException(422, "Only an approved expense can be paid")
    e.status, e.method, e.paid_on = "paid", body.method, body.paid_on or date.today()
    ledger.post(db, e.property_id, e.paid_on, e.title, [(ledger.CATEGORY_ACCOUNT[e.category], e.amount, 0), (ledger.METHOD_ACCOUNT[body.method], 0, e.amount)], "expense", e.id, ctx.user.id)
    audit(db, user_id=ctx.user.id, org_id=ctx.property.org_id, property_id=ctx.property.id, action="expense.pay", entity="expense", entity_id=e.id, meta={"amount": e.amount, "method": body.method})
    db.commit()
    return _exp(db, e, *_ctx_maps(db, ctx))


# ---------------- budget and summary
def _year(y: int | None) -> int:
    return y or date.today().year


class BudgetIn(BaseModel):
    year: int
    lines: dict[str, int]


@router.get("/budget")
def budget(year: int = 0, ctx: Ctx = Depends(property_ctx), db: Session = Depends(get_db)):
    ctx.feature("expenses")
    ctx.need(*MONEY_VIEW)
    y = _year(year)
    have = {b.category: b.amount for b in db.scalars(select(Budget).where(Budget.property_id == ctx.property.id, Budget.year == y))}
    return {"year": y, "lines": {c: have.get(c, 0) for c in CATEGORIES}}


@router.put("/budget")
def set_budget(body: BudgetIn, ctx: Ctx = Depends(property_ctx), db: Session = Depends(get_db)):
    ctx.feature("expenses")
    ctx.need(*(MANAGE | {"TREASURER"}))
    for c, a in body.lines.items():
        if c not in CATEGORIES or a < 0:
            raise HTTPException(422, "Bad budget line")
        row = db.scalar(select(Budget).where(Budget.property_id == ctx.property.id, Budget.year == body.year, Budget.category == c))
        if row:
            row.amount = a
        else:
            db.add(Budget(property_id=ctx.property.id, year=body.year, category=c, amount=a))
    audit(db, user_id=ctx.user.id, org_id=ctx.property.org_id, property_id=ctx.property.id, action="budget.set", entity="budget", entity_id=body.year, meta=body.lines)
    db.commit()
    return budget(body.year, ctx, db)


@router.get("/summary")
def summary(year: int = 0, ctx: Ctx = Depends(property_ctx), db: Session = Depends(get_db)):
    ctx.feature("reports")
    ctx.need(*MONEY_VIEW)
    y = _year(year)
    ledger.ensure_chart(db, ctx.property.id)
    rows = db.execute(select(Journal.date, Account.code, Account.type, JournalLine.debit, JournalLine.credit).join(JournalLine, JournalLine.journal_id == Journal.id).join(Account, Account.id == JournalLine.account_id)
                      .where(Journal.property_id == ctx.property.id, Journal.date >= date(y, 1, 1), Journal.date <= date(y, 12, 31))).all()
    monthly = defaultdict(lambda: {"income": 0, "expense": 0})
    by_account = defaultdict(int)
    for d, code, typ, dr, cr in rows:
        k = f"{d.year}-{d.month:02d}"
        if typ == "income":
            monthly[k]["income"] += cr - dr
        elif typ == "expense":
            monthly[k]["expense"] += dr - cr
            by_account[code] += dr - cr
    acc_cat = {v: k for k, v in ledger.CATEGORY_ACCOUNT.items()}
    bud = {b.category: b.amount for b in db.scalars(select(Budget).where(Budget.property_id == ctx.property.id, Budget.year == y))}
    cats = [{"category": c, "actual": by_account.get(ledger.CATEGORY_ACCOUNT[c], 0), "budget": bud.get(c, 0)} for c in CATEGORIES]
    all_bal = ledger.balances(db, ctx.property.id)
    cash = {c: all_bal[c]["debit"] - all_bal[c]["credit"] for c in ("1010", "1020", "1030") if c in all_bal}
    income, expense = sum(m["income"] for m in monthly.values()), sum(m["expense"] for m in monthly.values())
    pending = db.scalar(select(func.count()).select_from(Expense).where(Expense.property_id == ctx.property.id, Expense.status == "pending")) or 0
    approved = db.scalar(select(func.count()).select_from(Expense).where(Expense.property_id == ctx.property.id, Expense.status == "approved")) or 0
    return {"year": y, "income": income, "expense": expense, "net": income - expense, "monthly": [{"month": k, **v} for k, v in sorted(monthly.items())], "categories": cats,
            "cash": cash, "cash_total": sum(cash.values()), "pending": pending, "to_pay": approved, "acc_cat": acc_cat}


# ---------------- ledger
@router.get("/ledger")
def journal(limit: int = 25, offset: int = 0, q: str = "", ctx: Ctx = Depends(property_ctx), db: Session = Depends(get_db)):
    ctx.feature("reports")
    ctx.need(*MONEY_VIEW)
    stmt = select(Journal).where(Journal.property_id == ctx.property.id)
    if q:
        stmt = stmt.where(Journal.memo.ilike(f"%{q}%"))
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    accs = {a.id: a for a in db.scalars(select(Account).where(Account.property_id == ctx.property.id))}
    out = []
    for j in db.scalars(stmt.order_by(Journal.date.desc(), Journal.id.desc()).limit(min(limit, 100)).offset(offset)):
        lines = db.scalars(select(JournalLine).where(JournalLine.journal_id == j.id).order_by(JournalLine.id)).all()
        out.append({"id": j.id, "date": j.date.isoformat(), "memo": j.memo, "source": j.source, "lines": [{"code": accs[l.account_id].code, "name": accs[l.account_id].name, "name_bn": accs[l.account_id].name_bn, "debit": l.debit, "credit": l.credit} for l in lines]})
    return {"total": total, "rows": out}


@router.get("/trial-balance")
def trial(start: date | None = None, end: date | None = None, ctx: Ctx = Depends(property_ctx), db: Session = Depends(get_db)):
    ctx.feature("reports")
    ctx.need(*MONEY_VIEW)
    ledger.ensure_chart(db, ctx.property.id)
    bal = ledger.balances(db, ctx.property.id, start, end)
    rows = []
    for code in sorted(bal):
        b = bal[code]
        net = b["debit"] - b["credit"]
        rows.append({**b, "debit": net if net > 0 else 0, "credit": -net if net < 0 else 0})
    return {"rows": rows, "debit": sum(r["debit"] for r in rows), "credit": sum(r["credit"] for r in rows)}


# ---------------- assets
class AssetIn(BaseModel):
    name: str = Field(min_length=2)
    name_bn: str = ""
    category: str = "equipment"
    cost: int = Field(gt=0)
    bought_on: date | None = None
    life_years: int = Field(default=10, ge=1, le=50)
    method: str = Field(default="bank", pattern="^(cash|bank|bkash|nagad)$")
    note: str = ""


def _asset(a: Asset) -> dict:
    months = max(0, (date.today().year - a.bought_on.year) * 12 + date.today().month - a.bought_on.month)
    dep = min(a.cost, round(a.cost * months / (a.life_years * 12) / 100) * 100) if a.capitalised else a.cost
    return {"id": a.id, "name": a.name, "name_bn": a.name_bn, "category": a.category, "cost": a.cost, "bought_on": a.bought_on.isoformat(), "life_years": a.life_years, "capitalised": a.capitalised,
            "status": a.status, "depreciation": dep if a.status == "in_use" else a.cost, "book_value": max(0, a.cost - dep) if a.status == "in_use" else 0, "note": a.note}


@router.get("/assets")
def assets(ctx: Ctx = Depends(property_ctx), db: Session = Depends(get_db)):
    ctx.feature("assets")
    ctx.need(*MONEY_VIEW)
    rows = [_asset(a) for a in db.scalars(select(Asset).where(Asset.property_id == ctx.property.id).order_by(Asset.bought_on.desc()))]
    cap = [r for r in rows if r["capitalised"] and r["status"] == "in_use"]
    return {"threshold": ledger.CAPITALISE_FROM, "rows": rows, "cost": sum(r["cost"] for r in cap), "book_value": sum(r["book_value"] for r in cap)}


@router.post("/assets", status_code=201)
def add_asset(body: AssetIn, ctx: Ctx = Depends(property_ctx), db: Session = Depends(get_db)):
    """An item at or above the threshold becomes an asset and is depreciated. A cheaper item is booked as an expense."""
    ctx.feature("assets")
    ctx.need(*PAY)
    on = body.bought_on or date.today()
    cap = body.cost >= ledger.CAPITALISE_FROM
    a = Asset(property_id=ctx.property.id, name=body.name, name_bn=body.name_bn, category=body.category, cost=body.cost, bought_on=on, life_years=body.life_years, capitalised=cap, note=body.note)
    db.add(a)
    db.flush()
    if cap:
        ledger.post(db, a.property_id, on, f"Bought {a.name}", [("1500", a.cost, 0), (ledger.METHOD_ACCOUNT[body.method], 0, a.cost)], "asset", a.id, ctx.user.id)
    else:
        ledger.post(db, a.property_id, on, f"Bought {a.name} (below asset threshold)", [("5020", a.cost, 0), (ledger.METHOD_ACCOUNT[body.method], 0, a.cost)], "asset", a.id, ctx.user.id)
    audit(db, user_id=ctx.user.id, org_id=ctx.property.org_id, property_id=ctx.property.id, action="asset.add", entity="asset", entity_id=a.id, meta={"cost": a.cost, "capitalised": cap})
    db.commit()
    return _asset(a)


@router.post("/assets/{aid}/dispose")
def dispose(aid: int, ctx: Ctx = Depends(property_ctx), db: Session = Depends(get_db)):
    ctx.feature("assets")
    ctx.need(*MANAGE)
    a = db.get(Asset, aid)
    if not a or a.property_id != ctx.property.id or a.status == "disposed":
        raise HTTPException(404, "Not found")
    a.status = "disposed"
    if a.capitalised:
        ledger.post(db, a.property_id, date.today(), f"Written off {a.name}", [("5090", a.cost, 0), ("1500", 0, a.cost)], "asset_off", a.id, ctx.user.id)
    audit(db, user_id=ctx.user.id, org_id=ctx.property.org_id, property_id=ctx.property.id, action="asset.dispose", entity="asset", entity_id=a.id)
    db.commit()
    return _asset(a)
