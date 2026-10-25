"""Data export: CSV downloads for key lists, and one ZIP of CSVs with the whole building.

Everything is produced synchronously. Rows are read first (inside the request, with the caller's permissions) and then streamed.
"""
import os
import tempfile
import zipfile
from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..audit import audit
from ..db import get_db
from ..deps import Ctx, property_ctx
from ..models.amenities import Amenity, Booking
from ..models.billing import Invoice, InvoiceLine, Payment
from ..models.core import AuditLog, User, now
from ..models.finance import Account, Expense, Journal, JournalLine, Vendor
from ..models.notice import Notice, Receipt
from ..models.parking import Vehicle
from ..models.property import Occupancy, Unit
from ..models.requests import ServiceRequest
from ..models.staff import Staff
from ..models.visitors import Visit
from ..permissions import MONEY_VIEW, SEE_CONTACTS
from ..services.csvio import BOM, _Row, bdt, csv_response, slug

router = APIRouter(prefix="/api/export", tags=["export"])

ZIP_ROLES = {"PROPERTY_ADMIN", "AGENCY_MANAGER", "PRESIDENT"}
ZIP_PER_DAY = int(os.getenv("EXPORT_BUILDING_PER_DAY", "3"))
Rows = tuple[list[str], list[list]]


# ---------------- data sets. Each returns (headers, rows). `units` limits to some flats (a resident's own), None means all.
def _unit_map(db: Session, pid: int) -> dict[int, Unit]:
    return {u.id: u for u in db.scalars(select(Unit).where(Unit.property_id == pid))}


def ds_flats(db: Session, ctx: Ctx, **_) -> Rows:
    pid = ctx.property.id
    occ: dict[int, list[Occupancy]] = {}
    for o in db.scalars(select(Occupancy).join(Unit, Unit.id == Occupancy.unit_id).where(Unit.property_id == pid, Occupancy.active)):
        occ.setdefault(o.unit_id, []).append(o)
    rows = []
    for u in db.scalars(select(Unit).where(Unit.property_id == pid).order_by(Unit.floor, Unit.block, Unit.number)):
        names = lambda k: "; ".join(o.name for o in occ.get(u.id, []) if o.kind == k)  # noqa: E731
        rows.append([u.number, u.block, u.floor, u.area_sqft, u.bedrooms, u.status, names("owner"), names("tenant")])
    return ["flat_number", "block", "floor", "area_sqft", "bedrooms", "status", "owners", "tenants"], rows


def ds_people(db: Session, ctx: Ctx, history: bool = False, **_) -> Rows:
    contacts = ctx.has(*SEE_CONTACTS)
    stmt = select(Occupancy, Unit).join(Unit, Unit.id == Occupancy.unit_id).where(Unit.property_id == ctx.property.id).order_by(Unit.floor, Unit.number, Occupancy.id)
    if not history:
        stmt = stmt.where(Occupancy.active)
    rows = [[o.kind, o.name, o.name_bn, u.number, o.phone if contacts else "", o.email if contacts else "", o.resides, o.user_id is not None, o.start_date, o.end_date, o.active]
            for o, u in db.execute(stmt)]
    return ["type", "name", "name_bn", "flat_number", "phone", "email", "lives_here", "has_login", "since", "until", "current"], rows


def ds_invoices(db: Session, ctx: Ctx, units: set[int] | None = None, **_) -> Rows:
    um = _unit_map(db, ctx.property.id)
    stmt = select(Invoice).where(Invoice.property_id == ctx.property.id).order_by(Invoice.period.desc(), Invoice.unit_id)
    if units is not None:
        stmt = stmt.where(Invoice.unit_id.in_(units))
    today, rows = date.today(), []
    for i in db.scalars(stmt):
        status = i.status if i.status in ("paid", "void") else ("overdue" if i.due_date < today else i.status)
        rows.append([i.number, i.period, um[i.unit_id].number if i.unit_id in um else "", i.issue_date, i.due_date, bdt(i.total), bdt(i.paid), bdt(max(0, i.total - i.paid)), status])
    return ["invoice_no", "period", "flat_number", "issue_date", "due_date", "total_bdt", "paid_bdt", "balance_bdt", "status"], rows


def ds_invoice_lines(db: Session, ctx: Ctx, **_) -> Rows:
    rows = [[inv.number, l.description, l.description_bn, bdt(l.amount)] for l, inv in db.execute(
        select(InvoiceLine, Invoice).join(Invoice, Invoice.id == InvoiceLine.invoice_id).where(Invoice.property_id == ctx.property.id).order_by(Invoice.period.desc(), Invoice.id, InvoiceLine.id))]
    return ["invoice_no", "description", "description_bn", "amount_bdt"], rows


def ds_payments(db: Session, ctx: Ctx, units: set[int] | None = None, **_) -> Rows:
    um = _unit_map(db, ctx.property.id)
    stmt = select(Payment, Invoice).join(Invoice, Invoice.id == Payment.invoice_id).where(Payment.property_id == ctx.property.id).order_by(Payment.id.desc())
    if units is not None:
        stmt = stmt.where(Payment.unit_id.in_(units))
    rows = [[p.receipt_no, i.number, i.period, um[p.unit_id].number if p.unit_id in um else "", bdt(p.amount), p.method, p.trx_id, p.paid_on, p.status, p.verified_at, p.note]
            for p, i in db.execute(stmt)]
    return ["receipt_no", "invoice_no", "period", "flat_number", "amount_bdt", "method", "transaction_id", "paid_on", "status", "verified_at", "note"], rows


def ds_dues(db: Session, ctx: Ctx, **_) -> Rows:
    from .billing import dues
    d = dues(ctx=ctx, db=db)
    rows = [[r["unit"], r["name"], r["phone"], bdt(r["outstanding"]), r["months"], r["oldest_days"], r["bucket"], " ".join(r["periods"])] for r in d["rows"]]
    return ["flat_number", "name", "phone", "outstanding_bdt", "months_overdue", "oldest_days_late", "age_bucket", "periods"], rows


def ds_ledger(db: Session, ctx: Ctx, start: date | None = None, end: date | None = None, **_) -> Rows:
    stmt = (select(Journal, JournalLine, Account).join(JournalLine, JournalLine.journal_id == Journal.id).join(Account, Account.id == JournalLine.account_id)
            .where(Journal.property_id == ctx.property.id).order_by(Journal.date, Journal.id, JournalLine.id))
    if start:
        stmt = stmt.where(Journal.date >= start)
    if end:
        stmt = stmt.where(Journal.date <= end)
    rows = [[j.id, j.date, j.memo, j.source, j.source_id, a.code, a.name, bdt(l.debit), bdt(l.credit)] for j, l, a in db.execute(stmt)]
    return ["journal_id", "date", "memo", "source", "source_id", "account_code", "account_name", "debit_bdt", "credit_bdt"], rows


def ds_expenses(db: Session, ctx: Ctx, own_only: bool = False, **_) -> Rows:
    vendors = {v.id: v.name for v in db.scalars(select(Vendor).where(Vendor.property_id == ctx.property.id))}
    stmt = select(Expense).where(Expense.property_id == ctx.property.id).order_by(Expense.spent_on.desc(), Expense.id.desc())
    if own_only:
        stmt = stmt.where(Expense.requested_by == ctx.user.id)
    rows = [[e.id, e.spent_on, e.category, e.title, vendors.get(e.vendor_id, ""), bdt(e.amount), e.status, len(e.approvals or []), e.method, e.paid_on, e.reason] for e in db.scalars(stmt)]
    return ["id", "date", "category", "title", "vendor", "amount_bdt", "status", "approvals", "paid_with", "paid_on", "reason"], rows


def ds_staff(db: Session, ctx: Ctx, **_) -> Rows:
    """No National ID, not even the last four digits."""
    rows = [[s.id, s.name, s.name_bn, s.role, s.phone, s.joined, bdt(s.salary), s.status] for s in db.scalars(select(Staff).where(Staff.property_id == ctx.property.id).order_by(Staff.id))]
    return ["id", "name", "name_bn", "job", "phone", "joined", "monthly_pay_bdt", "status"], rows


def ds_notices(db: Session, ctx: Ctx, **_) -> Rows:
    counts = {nid: (t, r) for nid, t, r in db.execute(select(Receipt.notice_id, func.count(Receipt.id), func.count(Receipt.read_at)).join(Notice, Notice.id == Receipt.notice_id)
                                                   .where(Notice.property_id == ctx.property.id).group_by(Receipt.notice_id))}
    rows = [[n.id, n.created_at, n.title, n.title_bn, n.body, n.body_bn, n.audience, n.priority, n.pinned, n.status, counts.get(n.id, (0, 0))[0], counts.get(n.id, (0, 0))[1]]
            for n in db.scalars(select(Notice).where(Notice.property_id == ctx.property.id).order_by(Notice.id))]
    return ["id", "published_at", "title", "title_bn", "message", "message_bn", "audience", "priority", "pinned", "status", "recipients", "read_by"], rows


def ds_requests(db: Session, ctx: Ctx, **_) -> Rows:
    um = _unit_map(db, ctx.property.id)
    names = {u.id: u.name for u in db.scalars(select(User).where(User.id.in_(select(ServiceRequest.raised_by).where(ServiceRequest.property_id == ctx.property.id))))}
    rows = [[r.id, r.created_at, um[r.unit_id].number if r.unit_id in um else "", names.get(r.raised_by, ""), r.category, r.title, r.text, r.status, r.sla_hours, r.due_at, r.resolved_at, r.closed_at, r.rating]
            for r in db.scalars(select(ServiceRequest).where(ServiceRequest.property_id == ctx.property.id).order_by(ServiceRequest.id))]
    return ["id", "raised_at", "flat_number", "raised_by", "category", "title", "details", "status", "sla_hours", "due_at", "resolved_at", "closed_at", "rating"], rows


def ds_visitors(db: Session, ctx: Ctx, **_) -> Rows:
    um = _unit_map(db, ctx.property.id)
    rows = [[v.id, v.created_at, um[v.unit_id].number if v.unit_id in um else "", v.name, v.phone, v.purpose, v.people, v.vehicle, v.kind, v.status, v.in_at, v.out_at, v.decision_via, v.note]
            for v in db.scalars(select(Visit).where(Visit.property_id == ctx.property.id).order_by(Visit.id))]
    return ["id", "logged_at", "flat_number", "visitor_name", "visitor_phone", "purpose", "people", "vehicle", "kind", "status", "in_at", "out_at", "decided_via", "note"], rows


def ds_bookings(db: Session, ctx: Ctx, **_) -> Rows:
    um = _unit_map(db, ctx.property.id)
    am = {a.id: a.name for a in db.scalars(select(Amenity).where(Amenity.property_id == ctx.property.id))}
    rows = [[b.id, am.get(b.amenity_id, ""), um[b.unit_id].number if b.unit_id in um else "", b.on_date, b.slot, b.purpose, b.guests, b.status, bdt(b.fee), bdt(b.ext_fee), bdt(b.cleaning), bdt(b.generator), bdt(b.deposit), bdt(b.total), b.created_at]
            for b in db.scalars(select(Booking).where(Booking.property_id == ctx.property.id).order_by(Booking.id))]
    return ["id", "amenity", "flat_number", "date", "slot", "purpose", "guests", "status", "slot_fee_bdt", "extra_hours_bdt", "cleaning_bdt", "generator_bdt", "deposit_bdt", "total_bdt", "requested_at"], rows


def ds_vehicles(db: Session, ctx: Ctx, **_) -> Rows:
    um = _unit_map(db, ctx.property.id)
    rows = [[v.id, um[v.unit_id].number if v.unit_id in um else "", v.reg_no, v.kind, v.make_model, v.colour, v.sticker, v.holder_kind, v.temporary, v.status]
            for v in db.scalars(select(Vehicle).where(Vehicle.property_id == ctx.property.id).order_by(Vehicle.id))]
    return ["id", "flat_number", "registration_no", "kind", "make_model", "colour", "sticker", "holder", "temporary_permit", "status"], rows


# The whole-building ZIP. File name (without .csv) -> data set.
BUILDING_SET = {
    "flats": ds_flats, "people": lambda db, ctx: ds_people(db, ctx, history=True), "invoices": ds_invoices, "invoice_lines": ds_invoice_lines,
    "payments": ds_payments, "ledger_journal_lines": ds_ledger, "expenses": ds_expenses, "staff": ds_staff, "notices": ds_notices,
    "requests": ds_requests, "visitors": ds_visitors, "bookings": ds_bookings, "vehicles": ds_vehicles,
}
README = """FlatWise data export
Building: {name}
Exported: {at} UTC by {who}

Every file is a CSV in UTF-8 with a byte-order mark, so Excel shows Bangla text correctly.
Money columns end in _bdt and are decimal taka (1250.50), never paisa.
Dates are YYYY-MM-DD, times are YYYY-MM-DDTHH:MM:SS in UTC.
Staff National ID numbers are not included. Notice and policy read proof is summarised as counts.

Files and row counts:
{files}
"""


class ExportStatus(BaseModel):
    allowed_roles: list[str]
    per_day: int
    used_today: int
    left_today: int
    can_export: bool


def _used_today(db: Session, pid: int) -> int:
    since = now() - timedelta(hours=24)
    return int(db.scalar(select(func.count()).select_from(AuditLog).where(AuditLog.property_id == pid, AuditLog.action == "export.building", AuditLog.at >= since)) or 0)


def _can_zip(ctx: Ctx) -> bool:
    return bool(ctx.roles & ZIP_ROLES)


@router.get("/status", response_model=ExportStatus, summary="How many whole-building exports are left today")
def status(ctx: Ctx = Depends(property_ctx), db: Session = Depends(get_db)):
    used = _used_today(db, ctx.property.id)
    return ExportStatus(allowed_roles=sorted(ZIP_ROLES), per_day=ZIP_PER_DAY, used_today=used, left_today=max(0, ZIP_PER_DAY - used), can_export=_can_zip(ctx))


def _iter_file(f, chunk: int = 64 * 1024):
    try:
        while True:
            b = f.read(chunk)
            if not b:
                break
            yield b
    finally:
        f.close()


@router.get("/building.zip", summary="Download the whole building as a ZIP of CSV files")
def building_zip(ctx: Ctx = Depends(property_ctx), db: Session = Depends(get_db)):
    """Property admin, agency manager and committee president only. Limited to a few per building per 24 hours (EXPORT_BUILDING_PER_DAY, default 3).
    The ZIP holds one CSV per topic (flats, people, invoices, payments, ledger journal lines, expenses, staff without National ID, notices, requests, visitors, bookings, vehicles)."""
    if not _can_zip(ctx):
        raise HTTPException(403, "Only the property admin, agency manager or president can export the whole building")
    used = _used_today(db, ctx.property.id)
    if used >= ZIP_PER_DAY:
        raise HTTPException(429, f"The limit is {ZIP_PER_DAY} full exports per building in 24 hours. Try again tomorrow.")
    tmp = tempfile.SpooledTemporaryFile(max_size=16 * 1024 * 1024)
    counts: dict[str, int] = {}
    with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as z:
        for name, fn in BUILDING_SET.items():
            headers, rows = fn(db, ctx)
            enc = _Row()
            with z.open(f"{name}.csv", "w") as f:
                f.write(BOM)
                f.write(enc.encode(headers))
                for r in rows:
                    f.write(enc.encode(r))
            counts[name] = len(rows)
        z.writestr("README.txt", README.format(name=ctx.property.name, at=now().strftime("%Y-%m-%d %H:%M"), who=ctx.user.name,
                                              files="\n".join(f"  {n}.csv  {c} rows" for n, c in counts.items())))
    size = tmp.tell()
    tmp.seek(0)
    audit(db, user_id=ctx.user.id, org_id=ctx.property.org_id, property_id=ctx.property.id, action="export.building", entity="property", entity_id=ctx.property.id, meta={"rows": counts, "bytes": size})
    db.commit()
    fname = f"flatwise-{slug(ctx.property.name)}-{date.today():%Y%m%d}.zip"
    return StreamingResponse(_iter_file(tmp), media_type="application/zip", headers={"Content-Disposition": f'attachment; filename="{fname}"', "Content-Length": str(size), "Cache-Control": "no-store"})


# ---------------- one list at a time
def _resident_units(ctx: Ctx) -> set[int]:
    if not ctx.unit_ids:
        raise HTTPException(403, "No flat is linked to your sign-in")
    return set(ctx.unit_ids)


CSV_NAMES = ["invoices", "payments", "dues", "ledger", "expenses", "people", "visitors"]


@router.get("/csv/{name}", summary="Download one list as a CSV file")
def csv_one(name: str, start: date | None = Query(default=None, description="ledger only: first date"), end: date | None = Query(default=None, description="ledger only: last date"),
            ctx: Ctx = Depends(property_ctx), db: Session = Depends(get_db)):
    """`name` is one of invoices, payments, dues, ledger, expenses, people, visitors. The same plan feature and role rules as the matching screen apply."""
    if name not in CSV_NAMES:
        raise HTTPException(404, "Unknown export")
    if name in ("invoices", "payments"):
        ctx.feature("billing")
        units = None if ctx.has(*MONEY_VIEW) else _resident_units(ctx)
        headers, rows = (ds_invoices if name == "invoices" else ds_payments)(db, ctx, units=units)
    elif name == "dues":
        ctx.feature("billing")
        headers, rows = ds_dues(db, ctx)
    elif name == "ledger":
        ctx.feature("reports")
        ctx.need(*MONEY_VIEW)
        headers, rows = ds_ledger(db, ctx, start=start, end=end)
    elif name == "expenses":
        from .finance import REQUEST
        ctx.feature("expenses")
        if not ctx.has(*MONEY_VIEW):
            ctx.need(*REQUEST)
        headers, rows = ds_expenses(db, ctx, own_only=not ctx.has(*MONEY_VIEW))
    elif name == "people":
        ctx.need(*(SEE_CONTACTS | {"AUDITOR"}))
        headers, rows = ds_people(db, ctx)
    else:
        from .visitors import READ_ALL
        ctx.feature("visitor")
        ctx.need(*READ_ALL)
        headers, rows = ds_visitors(db, ctx)
    audit(db, user_id=ctx.user.id, org_id=ctx.property.org_id, property_id=ctx.property.id, action="export.csv", entity="export", entity_id=name, meta={"rows": len(rows)})
    db.commit()
    return csv_response(f"flatwise-{slug(ctx.property.name)}-{name}-{date.today():%Y%m%d}.csv", headers, rows)
