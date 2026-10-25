"""Vendor contracts (AMC) and the service visit log. Needs the 'maintenance' plan feature.
Who: the building admin and secretary manage contracts; the caretaker logs visits; committee and auditor can read."""
import secrets
from datetime import date, timedelta

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from .. import config
from ..audit import audit
from ..services.uploads import safe_filename
from ..db import get_db
from ..deps import Ctx, property_ctx
from ..models.contracts import Contract, ContractDoc, ContractVisit
from ..models.finance import Expense, Vendor
from ..permissions import COMMITTEE, MANAGE
from .finance import DUAL_ABOVE, REQUEST

router = APIRouter(prefix="/api/contracts", tags=["contracts"])
KINDS = ("lift", "generator", "cctv", "fire", "pest", "other")
KIND_PAT = "^(" + "|".join(KINDS) + ")$"
READ = MANAGE | COMMITTEE | {"AUDITOR", "CARETAKER"}
WRITE = MANAGE | {"SECRETARY"}
LOG_VISIT = MANAGE | {"SECRETARY", "CARETAKER"}
RENEW_DAYS = 60
ALLOWED = {"image/jpeg": ("jpg", b"\xff\xd8"), "image/png": ("png", b"\x89PNG"), "application/pdf": ("pdf", b"%PDF")}


def _gate(ctx: Ctx, *roles: str) -> None:
    ctx.feature("maintenance")
    ctx.need(*(roles or READ))


def _log(db: Session, ctx: Ctx, action: str, eid, meta: dict | None = None) -> None:
    audit(db, user_id=ctx.user.id, org_id=ctx.property.org_id, property_id=ctx.property.id, action=action, entity="contract", entity_id=eid, meta=meta or {})


def flags(c: Contract, last_visit: date | None, today: date) -> dict:
    """Pure date logic (tested directly). Renewal alert from 60 days before the end date; the next visit is due interval_days after the last one."""
    days_left = (c.end_date - today).days
    base = last_visit or c.start_date
    next_due = base + timedelta(days=max(1, c.interval_days))
    live = c.status == "active"
    return {"days_left": days_left, "expired": live and days_left < 0, "renewal_due": live and 0 <= days_left <= RENEW_DAYS,
            "next_due": next_due.isoformat() if live and days_left >= 0 else None, "visit_overdue": live and days_left >= 0 and next_due < today,
            "visit_due_soon": live and days_left >= 0 and 0 <= (next_due - today).days <= 14}


def _vendor(db: Session, c: Contract) -> tuple[str, str]:
    v = db.get(Vendor, c.vendor_id) if c.vendor_id else None
    return (v.name, v.name_bn) if v else (c.vendor_name, "")


def _row(db: Session, c: Contract, today: date) -> dict:
    last = db.scalar(select(func.max(ContractVisit.visited_on)).where(ContractVisit.contract_id == c.id))
    n = db.scalar(select(func.count()).select_from(ContractVisit).where(ContractVisit.contract_id == c.id)) or 0
    name, name_bn = _vendor(db, c)
    return {"id": c.id, "kind": c.kind, "title": c.title, "vendor_id": c.vendor_id, "vendor": name, "vendor_bn": name_bn, "start_date": c.start_date.isoformat(), "end_date": c.end_date.isoformat(),
            "annual_cost": c.annual_cost, "interval_days": c.interval_days, "status": c.status, "note": c.note, "visits": n, "last_visit": last.isoformat() if last else None,
            **flags(c, last, today)}


def _visit(v: ContractVisit) -> dict:
    return {"id": v.id, "contract_id": v.contract_id, "visited_on": v.visited_on.isoformat(), "technician": v.technician, "notes": v.notes, "cost": v.cost, "expense_id": v.expense_id}


def _doc(d: ContractDoc) -> dict:
    return {"id": d.id, "visit_id": d.visit_id, "kind": d.kind, "filename": d.filename, "size": d.size, "content_type": d.content_type, "at": d.created_at.isoformat()}


def _get(db: Session, ctx: Ctx, cid: int) -> Contract:
    c = db.get(Contract, cid)
    if not c or c.property_id != ctx.property.id:
        raise HTTPException(404, "Contract not found")
    return c


def _check_vendor(db: Session, ctx: Ctx, vid: int | None) -> None:
    if vid and not db.scalar(select(Vendor.id).where(Vendor.id == vid, Vendor.property_id == ctx.property.id)):
        raise HTTPException(422, "Unknown vendor")


# ---------------- list and summary
@router.get("/summary")
def summary(ctx: Ctx = Depends(property_ctx), db: Session = Depends(get_db)):
    _gate(ctx)
    today = date.today()
    rows = [_row(db, c, today) for c in db.scalars(select(Contract).where(Contract.property_id == ctx.property.id, Contract.status == "active"))]
    return {"active": len(rows), "annual_cost": sum(r["annual_cost"] for r in rows), "renewal": sum(r["renewal_due"] for r in rows), "expired": sum(r["expired"] for r in rows),
            "visit_overdue": sum(r["visit_overdue"] for r in rows), "visit_soon": sum(r["visit_due_soon"] for r in rows),
            "alerts": [{"id": r["id"], "title": r["title"], "kind": r["kind"], "days_left": r["days_left"], "why": "expired" if r["expired"] else "renewal" if r["renewal_due"] else "visit"}
                       for r in rows if r["expired"] or r["renewal_due"] or r["visit_overdue"]][:10]}


@router.get("")
def contracts(q: str = "", status: str = "", kind: str = "", page: int = Query(1, ge=1), size: int = Query(10, ge=1, le=100), ctx: Ctx = Depends(property_ctx), db: Session = Depends(get_db)):
    _gate(ctx)
    stmt = select(Contract).where(Contract.property_id == ctx.property.id)
    if status in ("active", "ended"):
        stmt = stmt.where(Contract.status == status)
    if kind in KINDS:
        stmt = stmt.where(Contract.kind == kind)
    if q.strip():
        like = f"%{q.strip()}%"
        stmt = stmt.where(or_(Contract.title.ilike(like), Contract.vendor_name.ilike(like), Contract.vendor_id.in_(select(Vendor.id).where(Vendor.name.ilike(like) | Vendor.name_bn.ilike(like)))))
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = db.scalars(stmt.order_by(Contract.status, Contract.end_date, Contract.id).offset((page - 1) * size).limit(size)).all()
    today = date.today()
    return {"items": [_row(db, c, today) for c in rows], "total": total, "page": page, "size": size}


class ContractIn(BaseModel):
    kind: str = Field(pattern=KIND_PAT)
    title: str = Field(min_length=3, max_length=160)
    vendor_id: int | None = None
    vendor_name: str = Field(default="", max_length=100)
    start_date: date
    end_date: date
    annual_cost: int = Field(default=0, ge=0, le=10**11)
    interval_days: int = Field(default=90, ge=7, le=366)
    note: str = Field(default="", max_length=1000)


@router.post("", status_code=201)
def add_contract(body: ContractIn, ctx: Ctx = Depends(property_ctx), db: Session = Depends(get_db)):
    _gate(ctx, *WRITE)
    if body.end_date < body.start_date:
        raise HTTPException(422, "The end date is before the start date")
    _check_vendor(db, ctx, body.vendor_id)
    if not body.vendor_id and len(body.vendor_name.strip()) < 2:
        raise HTTPException(422, "Choose a vendor or type the vendor's name")
    c = Contract(property_id=ctx.property.id, created_by=ctx.user.id, **{**body.model_dump(), "title": body.title.strip(), "vendor_name": body.vendor_name.strip(), "note": body.note.strip()})
    db.add(c)
    db.flush()
    _log(db, ctx, "contract.add", c.id, {"kind": c.kind, "annual_cost": c.annual_cost})
    db.commit()
    return _row(db, c, date.today())


class ContractEdit(BaseModel):
    title: str | None = Field(default=None, min_length=3, max_length=160)
    vendor_id: int | None = None
    vendor_name: str | None = Field(default=None, max_length=100)
    start_date: date | None = None
    end_date: date | None = None
    annual_cost: int | None = Field(default=None, ge=0, le=10**11)
    interval_days: int | None = Field(default=None, ge=7, le=366)
    status: str | None = Field(default=None, pattern="^(active|ended)$")
    note: str | None = Field(default=None, max_length=1000)


@router.put("/{cid}")
def edit_contract(cid: int, body: ContractEdit, ctx: Ctx = Depends(property_ctx), db: Session = Depends(get_db)):
    _gate(ctx, *WRITE)
    c = _get(db, ctx, cid)
    data = body.model_dump(exclude_none=True)
    if "vendor_id" in data:
        _check_vendor(db, ctx, data["vendor_id"])
    for k, v in data.items():
        setattr(c, k, v.strip() if isinstance(v, str) else v)
    if c.end_date < c.start_date:
        raise HTTPException(422, "The end date is before the start date")
    _log(db, ctx, "contract.edit", c.id, {k: v for k, v in data.items() if k != "note"})
    db.commit()
    return _row(db, c, date.today())


@router.get("/{cid}")
def contract(cid: int, ctx: Ctx = Depends(property_ctx), db: Session = Depends(get_db)):
    _gate(ctx)
    c = _get(db, ctx, cid)
    visits = db.scalars(select(ContractVisit).where(ContractVisit.contract_id == c.id).order_by(ContractVisit.visited_on.desc(), ContractVisit.id.desc())).all()
    docs = db.scalars(select(ContractDoc).where(ContractDoc.contract_id == c.id).order_by(ContractDoc.id.desc())).all()
    return {**_row(db, c, date.today()), "visit_list": [_visit(v) for v in visits], "docs": [_doc(d) for d in docs],
            "can_write": ctx.has(*WRITE), "can_log": ctx.has(*LOG_VISIT), "can_expense": ctx.has(*REQUEST)}


# ---------------- visits
class VisitIn(BaseModel):
    visited_on: date | None = None
    technician: str = Field(default="", max_length=100)
    notes: str = Field(default="", max_length=2000)
    cost: int = Field(default=0, ge=0, le=10**10)


@router.post("/{cid}/visits", status_code=201)
def add_visit(cid: int, body: VisitIn, ctx: Ctx = Depends(property_ctx), db: Session = Depends(get_db)):
    _gate(ctx, *LOG_VISIT)
    c = _get(db, ctx, cid)
    on = body.visited_on or date.today()
    if on > date.today():
        raise HTTPException(422, "A visit cannot be in the future")
    v = ContractVisit(contract_id=c.id, visited_on=on, technician=body.technician.strip(), notes=body.notes.strip(), cost=body.cost, created_by=ctx.user.id)
    db.add(v)
    db.flush()
    _log(db, ctx, "contract.visit", c.id, {"visit": v.id, "on": on.isoformat()})
    db.commit()
    return _visit(v)


@router.delete("/{cid}/visits/{vid}")
def del_visit(cid: int, vid: int, ctx: Ctx = Depends(property_ctx), db: Session = Depends(get_db)):
    _gate(ctx, *WRITE)
    c = _get(db, ctx, cid)
    v = db.get(ContractVisit, vid)
    if not v or v.contract_id != c.id:
        raise HTTPException(404, "Visit not found")
    if v.expense_id:
        raise HTTPException(409, "An expense was already created for this visit")
    for d in db.scalars(select(ContractDoc).where(ContractDoc.visit_id == v.id)):
        _unlink(c, d)
        db.delete(d)
    db.delete(v)
    _log(db, ctx, "contract.visit.delete", c.id, {"visit": vid})
    db.commit()
    return {"ok": True}


class VisitExpenseIn(BaseModel):
    amount: int | None = Field(default=None, gt=0, le=10**10)


@router.post("/{cid}/visits/{vid}/expense", status_code=201)
def visit_expense(cid: int, vid: int, body: VisitExpenseIn | None = None, ctx: Ctx = Depends(property_ctx), db: Session = Depends(get_db)):
    """'Create expense for this visit': a pending finance Expense (services) that goes through the normal approval."""
    ctx.feature("maintenance")
    ctx.feature("expenses")
    ctx.need(*REQUEST)
    c = _get(db, ctx, cid)
    v = db.get(ContractVisit, vid)
    if not v or v.contract_id != c.id:
        raise HTTPException(404, "Visit not found")
    if v.expense_id:
        raise HTTPException(409, "An expense was already created for this visit")
    amount = (body.amount if body and body.amount else None) or v.cost
    if not amount:
        raise HTTPException(422, "Enter the amount for this visit")
    name, _ = _vendor(db, c)
    e = Expense(property_id=ctx.property.id, category="services" if c.kind != "other" else "other", vendor_id=c.vendor_id, title=f"{c.title}: service visit {v.visited_on.isoformat()}"[:160],
                amount=amount, spent_on=v.visited_on, needs_two=amount > DUAL_ABOVE, requested_by=ctx.user.id)
    db.add(e)
    db.flush()
    v.expense_id, v.cost = e.id, amount
    audit(db, user_id=ctx.user.id, org_id=ctx.property.org_id, property_id=ctx.property.id, action="expense.request", entity="expense", entity_id=e.id, meta={"amount": amount, "category": e.category, "contract": c.id})
    _log(db, ctx, "contract.visit.expense", c.id, {"visit": v.id, "expense": e.id})
    db.commit()
    return {"expense_id": e.id, "amount": amount, "vendor": name}


# ---------------- documents
def _folder(c: Contract):
    return config.UPLOAD_DIR / "contracts" / str(c.property_id)


def _unlink(c: Contract, d: ContractDoc) -> None:
    (_folder(c) / (d.stored or "x")).unlink(missing_ok=True)


@router.post("/{cid}/docs", status_code=201)
async def add_doc(cid: int, kind: str = Form("contract", pattern="^(contract|report|other)$"), visit_id: int | None = Form(None), file: UploadFile = File(...),
                  ctx: Ctx = Depends(property_ctx), db: Session = Depends(get_db)):
    _gate(ctx, *LOG_VISIT)
    c = _get(db, ctx, cid)
    if visit_id:
        v = db.get(ContractVisit, visit_id)
        if not v or v.contract_id != c.id:
            raise HTTPException(404, "Visit not found")
    spec = ALLOWED.get(file.content_type or "")
    if not spec:
        raise HTTPException(422, "Upload a photo (JPG or PNG) or a PDF")
    data = await file.read(config.MAX_UPLOAD_BYTES + 1)
    if len(data) > config.MAX_UPLOAD_BYTES:
        raise HTTPException(413, "The file is bigger than 3 MB")
    if not data or not data.startswith(spec[1]):
        raise HTTPException(422, "The file is empty or does not look like its type")
    folder = _folder(c)
    folder.mkdir(parents=True, exist_ok=True)
    stored = f"{secrets.token_hex(10)}.{spec[0]}"
    (folder / stored).write_bytes(data)
    d = ContractDoc(contract_id=c.id, visit_id=visit_id, kind=kind, filename=safe_filename(file.filename, f"document.{spec[0]}"), stored=stored, content_type=file.content_type, size=len(data), created_by=ctx.user.id)
    db.add(d)
    db.flush()
    _log(db, ctx, "contract.doc.add", c.id, {"doc": d.id, "kind": kind})
    db.commit()
    return _doc(d)


@router.get("/{cid}/docs/{did}")
def get_doc(cid: int, did: int, ctx: Ctx = Depends(property_ctx), db: Session = Depends(get_db)):
    _gate(ctx)
    c = _get(db, ctx, cid)
    d = db.get(ContractDoc, did)
    path = _folder(c) / d.stored if d and d.contract_id == c.id else None
    if not d or not path or not path.exists():
        raise HTTPException(404, "Not found")
    return FileResponse(path, media_type=d.content_type, filename=d.filename, headers={"X-Content-Type-Options": "nosniff"})


@router.delete("/{cid}/docs/{did}")
def del_doc(cid: int, did: int, ctx: Ctx = Depends(property_ctx), db: Session = Depends(get_db)):
    _gate(ctx, *WRITE)
    c = _get(db, ctx, cid)
    d = db.get(ContractDoc, did)
    if not d or d.contract_id != c.id:
        raise HTTPException(404, "Not found")
    _unlink(c, d)
    db.delete(d)
    _log(db, ctx, "contract.doc.delete", c.id, {"doc": did})
    db.commit()
    return {"ok": True}
