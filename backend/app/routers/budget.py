"""Monthly budget: a 12-month by category grid, copy-forward, month locks and budget against actual."""
from calendar import monthrange
from collections import defaultdict
from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..audit import audit
from ..db import get_db
from ..deps import Ctx, property_ctx
from ..models.budget import BudgetLock, BudgetMonth
from ..models.finance import Account, Budget, Journal, JournalLine
from ..permissions import MANAGE, MONEY_VIEW
from ..services import ledger
from .finance import CATEGORIES

router = APIRouter(prefix="/api/finance/budget/monthly", tags=["budget"])
EDIT = MANAGE | {"TREASURER"}
LOCK = MANAGE | {"PRESIDENT"}
OVERRIDE = MANAGE | {"TREASURER", "PRESIDENT"}   # may change a locked month, with the override flag
NEAR = 90


def split_year(total: int) -> list[int]:
    """A yearly total split evenly into 12 whole-paisa parts that add back up exactly."""
    base, extra = divmod(total, 12)
    return [base + (1 if i < extra else 0) for i in range(12)]


def _ym(year: int, month: int | None = None) -> None:
    if not 2000 <= year <= 2100 or (month is not None and not 1 <= month <= 12):
        raise HTTPException(422, "Bad year or month")


def _state(db: Session, pid: int, year: int):
    rows = defaultdict(dict)
    for r in db.scalars(select(BudgetMonth).where(BudgetMonth.property_id == pid, BudgetMonth.year == year)):
        rows[r.month][r.category] = r
    yearly = {b.category: b.amount for b in db.scalars(select(Budget).where(Budget.property_id == pid, Budget.year == year))}
    locks = {l.month for l in db.scalars(select(BudgetLock).where(BudgetLock.property_id == pid, BudgetLock.year == year))}
    return rows, yearly, locks


def effective(rows: dict, yearly: dict) -> dict[int, dict[str, int]]:
    """Monthly lines: stored rows where the month has any, otherwise the yearly figure / 12."""
    parts = {c: split_year(yearly.get(c, 0)) for c in CATEGORIES}
    return {m: ({c: rows[m][c].amount if c in rows[m] else 0 for c in CATEGORIES} if m in rows else {c: parts[c][m - 1] for c in CATEGORIES}) for m in range(1, 13)}


def _view(db: Session, pid: int, year: int) -> dict:
    rows, yearly, locks = _state(db, pid, year)
    eff = effective(rows, yearly)
    return {"year": year, "categories": CATEGORIES, "yearly": {c: yearly.get(c, 0) for c in CATEGORIES},
            "months": [{"month": m, "locked": m in locks, "source": "monthly" if m in rows else "yearly", "lines": eff[m], "total": sum(eff[m].values())} for m in range(1, 13)],
            "total": sum(sum(v.values()) for v in eff.values())}


def _write(db: Session, pid: int, year: int, month: int, lines: dict[str, int]) -> None:
    """Store a whole month: every category gets a row so the month stops following the yearly figure."""
    have = {r.category: r for r in db.scalars(select(BudgetMonth).where(BudgetMonth.property_id == pid, BudgetMonth.year == year, BudgetMonth.month == month))}
    for c in CATEGORIES:
        a = lines.get(c, have[c].amount if c in have else 0)
        if c in have:
            have[c].amount = a
        else:
            db.add(BudgetMonth(property_id=pid, year=year, month=month, category=c, amount=a))


def _clean(lines: dict[str, int]) -> None:
    for c, a in lines.items():
        if c not in CATEGORIES or a < 0:
            raise HTTPException(422, "Bad budget line")


def _check_locked(ctx: Ctx, db: Session, locked: set, months: list[int], override: bool, year: int) -> list[int]:
    """Raise 423 if a locked month is touched without an allowed override; else return the locked months that are overridden."""
    hit = [m for m in months if m in locked]
    if hit:
        if not override:
            raise HTTPException(423, f"Month {hit[0]} is locked. Use override to change it.")
        ctx.need(*OVERRIDE)
        audit(db, user_id=ctx.user.id, org_id=ctx.property.org_id, property_id=ctx.property.id, action="budget.month.edit_locked", entity="budget_month", entity_id=f"{year}-{hit[0]:02d}", meta={"year": year, "months": hit})
    return hit


@router.get("")
def monthly(year: int = 0, ctx: Ctx = Depends(property_ctx), db: Session = Depends(get_db)):
    ctx.feature("expenses")
    ctx.need(*MONEY_VIEW)
    y = year or date.today().year
    _ym(y)
    return _view(db, ctx.property.id, y)


class MonthlyIn(BaseModel):
    year: int
    months: dict[int, dict[str, int]] = Field(min_length=1)   # {1: {"utilities": 3000000, ...}, ...} one month or the whole grid
    override: bool = False


@router.put("")
def set_monthly(body: MonthlyIn, ctx: Ctx = Depends(property_ctx), db: Session = Depends(get_db)):
    ctx.feature("expenses")
    ctx.need(*EDIT)
    _ym(body.year)
    for m, lines in body.months.items():
        _ym(body.year, m)
        _clean(lines)
    pid = ctx.property.id
    rows, yearly, locks = _state(db, pid, body.year)
    _check_locked(ctx, db, locks, list(body.months), body.override, body.year)
    eff = effective(rows, yearly)
    for m, lines in body.months.items():
        _write(db, pid, body.year, m, {**eff[m], **lines})
    audit(db, user_id=ctx.user.id, org_id=ctx.property.org_id, property_id=pid, action="budget.month.set", entity="budget_month", entity_id=body.year, meta={"months": sorted(body.months)})
    db.commit()
    return _view(db, pid, body.year)


class CopyIn(BaseModel):
    year: int
    mode: str = Field(default="month", pattern="^(month|even_split)$")
    from_month: int = 1
    to_months: list[int] | None = None   # default: every month after from_month (month) or all 12 (even_split)
    override: bool = False


@router.post("/copy-forward")
def copy_forward(body: CopyIn, ctx: Ctx = Depends(property_ctx), db: Session = Depends(get_db)):
    """mode=month copies one month's lines to the following months; mode=even_split spreads the yearly total over 12 months. Locked months are skipped unless overridden."""
    ctx.feature("expenses")
    ctx.need(*EDIT)
    _ym(body.year, body.from_month)
    pid = ctx.property.id
    rows, yearly, locks = _state(db, pid, body.year)
    eff = effective(rows, yearly)
    if body.mode == "month":
        targets = body.to_months if body.to_months is not None else list(range(body.from_month + 1, 13))
        targets = [m for m in targets if m != body.from_month]
        source = {m: dict(eff[body.from_month]) for m in targets}
    else:
        targets = body.to_months if body.to_months is not None else list(range(1, 13))
        total = {c: yearly[c] if c in yearly else sum(eff[m][c] for m in range(1, 13)) for c in CATEGORIES}
        parts = {c: split_year(total[c]) for c in CATEGORIES}
        source = {m: {c: parts[c][m - 1] for c in CATEGORIES} for m in targets}
    for m in targets:
        _ym(body.year, m)
    skipped = [m for m in targets if m in locks and not body.override]
    if body.override:
        _check_locked(ctx, db, locks, targets, True, body.year)
    done = [m for m in targets if m not in skipped]
    for m in done:
        _write(db, pid, body.year, m, source[m])
    audit(db, user_id=ctx.user.id, org_id=ctx.property.org_id, property_id=pid, action="budget.month.copy", entity="budget_month", entity_id=body.year, meta={"mode": body.mode, "from": body.from_month, "to": done, "skipped_locked": skipped})
    db.commit()
    return {**_view(db, pid, body.year), "copied": done, "skipped": skipped}


class LockIn(BaseModel):
    year: int
    month: int
    locked: bool = True


@router.post("/lock")
def lock(body: LockIn, ctx: Ctx = Depends(property_ctx), db: Session = Depends(get_db)):
    ctx.feature("expenses")
    ctx.need(*LOCK)
    _ym(body.year, body.month)
    pid = ctx.property.id
    row = db.scalar(select(BudgetLock).where(BudgetLock.property_id == pid, BudgetLock.year == body.year, BudgetLock.month == body.month))
    if body.locked:
        if date(body.year, body.month, monthrange(body.year, body.month)[1]) >= date.today():
            raise HTTPException(422, "A month can be locked only after it has closed")
        if not row:
            db.add(BudgetLock(property_id=pid, year=body.year, month=body.month, locked_by=ctx.user.id))
    elif row:
        db.delete(row)
    audit(db, user_id=ctx.user.id, org_id=ctx.property.org_id, property_id=pid, action="budget.month.lock" if body.locked else "budget.month.unlock", entity="budget_month", entity_id=f"{body.year}-{body.month:02d}")
    db.commit()
    return _view(db, pid, body.year)


def status_of(budget: int, actual: int) -> str:
    if actual > budget:
        return "over"
    if budget and actual * 100 >= budget * NEAR:
        return "near"
    return "under"


@router.get("/vs-actual")
def vs_actual(year: int = 0, ctx: Ctx = Depends(property_ctx), db: Session = Depends(get_db)):
    ctx.feature("expenses")
    ctx.need(*MONEY_VIEW)
    y = year or date.today().year
    _ym(y)
    pid = ctx.property.id
    ledger.ensure_chart(db, pid)
    acc_cat = {v: k for k, v in ledger.CATEGORY_ACCOUNT.items()}
    act: dict[tuple[int, str], int] = defaultdict(int)
    for d, code, dr, cr in db.execute(select(Journal.date, Account.code, JournalLine.debit, JournalLine.credit).join(JournalLine, JournalLine.journal_id == Journal.id).join(Account, Account.id == JournalLine.account_id)
                                      .where(Journal.property_id == pid, Account.type == "expense", Journal.date >= date(y, 1, 1), Journal.date <= date(y, 12, 31))):
        if code in acc_cat:
            act[(d.month, acc_cat[code])] += dr - cr
    rows, yearly, locks = _state(db, pid, y)
    eff = effective(rows, yearly)
    months = []
    for m in range(1, 13):
        cats = {c: {"budget": eff[m][c], "actual": act[(m, c)], "pct": round(100 * act[(m, c)] / eff[m][c]) if eff[m][c] else (100 if act[(m, c)] else 0), "status": status_of(eff[m][c], act[(m, c)])} for c in CATEGORIES}
        b, a = sum(eff[m].values()), sum(act[(m, c)] for c in CATEGORIES)
        months.append({"month": m, "locked": m in locks, "budget": b, "actual": a, "pct": round(100 * a / b) if b else (100 if a else 0), "status": status_of(b, a), "categories": cats})
    return {"year": y, "months": months, "near_pct": NEAR}
