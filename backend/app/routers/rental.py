"""Owner rental records (M14). Private between a flat's owner and its current tenant, only when the owner switches it on.

The building admin and the committee can see that the add-on is on, never what is inside: every content call checks that the
caller is the owner side or the tenant of that very flat, on the server."""
import calendar
import secrets
from datetime import date, timedelta

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import config
from ..audit import audit
from ..db import get_db
from ..deps import Ctx, property_ctx
from ..models.billing import Message
from ..models.core import Membership, User, now
from ..models.property import Occupancy, Unit
from ..models.rental import (RentalAgreement, RentalComment, RentalFollowup, RentalIssue, RentalNote, RentalPayment, RentalSetting)
from ..permissions import MANAGE
from ..services.messaging import deliver

router = APIRouter(prefix="/api/rental", tags=["rental"])
ALLOWED = {"image/jpeg": ("jpg", b"\xff\xd8"), "image/png": ("png", b"\x89PNG"), "application/pdf": ("pdf", b"%PDF")}
ISSUE_STATUS = ("open", "in_progress", "fixed", "closed")
EXPIRY_DAYS = 60


# ---------------- access
def _side(db: Session, ctx: Ctx, unit_id: int) -> str:
    """'owner' (flat owner or owner's representative of this flat), 'tenant' (its current tenant) or ''."""
    uid = ctx.user.id
    if "FLAT_OWNER" in ctx.roles and db.scalar(select(Occupancy.id).where(Occupancy.unit_id == unit_id, Occupancy.kind == "owner", Occupancy.active, Occupancy.user_id == uid)):
        return "owner"
    if "OWNER_REP" in ctx.roles and db.scalar(select(Membership.id).where(Membership.user_id == uid, Membership.role == "OWNER_REP", Membership.unit_id == unit_id,
                                                                           Membership.org_id == ctx.property.org_id)):
        return "owner"
    if "TENANT" in ctx.roles and db.scalar(select(Occupancy.id).where(Occupancy.unit_id == unit_id, Occupancy.kind == "tenant", Occupancy.active, Occupancy.user_id == uid)):
        return "tenant"
    return ""


def _setting(db: Session, unit_id: int, create: bool = False) -> RentalSetting | None:
    s = db.scalar(select(RentalSetting).where(RentalSetting.unit_id == unit_id))
    if not s and create:
        unit = db.get(Unit, unit_id)
        s = RentalSetting(unit_id=unit_id, property_id=unit.property_id, enabled=False)
        db.add(s)
        db.flush()
    return s


def _unit(db: Session, ctx: Ctx, uid: int) -> Unit:
    ctx.feature("rental_records")
    unit = db.get(Unit, uid)
    if not unit or unit.property_id != ctx.property.id:
        raise HTTPException(404, "Not found")
    return unit


def _access(db: Session, ctx: Ctx, uid: int, owner_only: bool = False) -> tuple[Unit, str]:
    """Content access. Admin, committee and everyone else are refused. A tenant sees nothing while the switch is off."""
    unit = _unit(db, ctx, uid)
    side = _side(db, ctx, uid)
    if not side:
        raise HTTPException(403, "Rental records are private to this flat's owner and tenant")
    s = _setting(db, uid)
    if not s or not s.enabled:
        if side == "tenant":
            raise HTTPException(404, "Not found")
        raise HTTPException(403, "Rental records are switched off for this flat")
    if owner_only and side != "owner":
        raise HTTPException(403, "Only the flat owner can do this")
    return unit, side


# ---------------- pure maths (tested directly)
def _pshift(period: str, n: int) -> str:
    y, m = int(period[:4]), int(period[5:]) - 1 + n
    return f"{y + m // 12:04d}-{m % 12 + 1:02d}"


def _valid_period(p: str) -> bool:
    return len(p) == 7 and p[4] == "-" and p[:4].isdigit() and p[5:].isdigit() and 1 <= int(p[5:]) <= 12


def build_ledger(agreements: list, payments: list, today: date) -> dict:
    """Rent due vs received by month. Due = rent of the agreement covering that month (latest start wins), from the first
    agreement's month to this month. Only confirmed payments count. A month before this one with money still owed is overdue."""
    cur = today.strftime("%Y-%m")
    confirmed: dict[str, int] = {}
    for p in payments:
        if p.status == "confirmed":
            confirmed[p.period] = confirmed.get(p.period, 0) + p.amount
    due: dict[str, int] = {}
    if agreements:
        p = min(a.start_date for a in agreements).strftime("%Y-%m")
        while p <= cur:
            first = date(int(p[:4]), int(p[5:]), 1)
            last = date(first.year, first.month, calendar.monthrange(first.year, first.month)[1])
            cover = [a for a in agreements if a.start_date <= last and (a.end_date is None or a.end_date >= first)]
            if cover:
                due[p] = max(cover, key=lambda a: a.start_date).rent
            p = _pshift(p, 1)
    months, running = [], 0
    for p in sorted(set(due) | set(confirmed)):
        d, r = due.get(p, 0), confirmed.get(p, 0)
        running += d - r
        months.append({"period": p, "due": d, "received": r, "outstanding": max(0, d - r), "balance": running, "overdue": p < cur and d - r > 0})
    return {"months": months, "total_due": sum(m["due"] for m in months), "total_received": sum(m["received"] for m in months), "balance": running,
            "overdue": [m for m in months if m["overdue"]], "overdue_amount": sum(m["outstanding"] for m in months if m["overdue"])}


def agreement_flags(a: RentalAgreement, today: date) -> dict:
    left = (a.end_date - today).days if a.end_date else None
    return {"days_left": left, "expired": left is not None and left < 0, "expiring": left is not None and 0 <= left <= EXPIRY_DAYS}


# ---------------- serializers
def _agr(a: RentalAgreement, today: date) -> dict:
    return {"id": a.id, "title": a.title, "start_date": a.start_date.isoformat(), "end_date": a.end_date.isoformat() if a.end_date else None, "rent": a.rent, "advance": a.advance,
            "filename": a.filename, "size": a.size, "content_type": a.content_type, "at": a.created_at.isoformat(), **agreement_flags(a, today)}


def _pay(p: RentalPayment) -> dict:
    return {"id": p.id, "period": p.period, "amount": p.amount, "method": p.method, "paid_on": p.paid_on.isoformat(), "note": p.note, "bank_ref": p.bank_ref, "status": p.status,
            "source": p.source, "receipt_no": p.receipt_no, "at": p.created_at.isoformat()}


def _issue(i: RentalIssue) -> dict:
    return {"id": i.id, "title": i.title, "body": i.body, "status": i.status, "cost": i.cost, "cost_note": i.cost_note, "has_photo": bool(i.photo_stored), "raised_side": i.raised_side,
            "at": i.created_at.isoformat(), "updated": i.updated_at.isoformat()}


def _fu(f: RentalFollowup) -> dict:
    return {"id": f.id, "text": f.text, "due_date": f.due_date.isoformat() if f.due_date else None, "ref_kind": f.ref_kind, "ref": f.ref, "done": f.done,
            "overdue": bool(f.due_date and not f.done and f.due_date < date.today())}


def _name(db: Session, uid: int | None) -> str:
    u = db.get(User, uid) if uid else None
    return u.name if u else ""


# ---------------- who am I here, and the switch
@router.get("/flats")
def my_flats(ctx: Ctx = Depends(property_ctx), db: Session = Depends(get_db)):
    """The flats where I am the owner side or the tenant. A tenant is told nothing about a flat whose switch is off."""
    ctx.feature("rental_records")
    out = []
    for u in db.scalars(select(Unit).where(Unit.property_id == ctx.property.id, Unit.id.in_(ctx.unit_ids or {0})).order_by(Unit.number)):
        side = _side(db, ctx, u.id)
        if not side:
            continue
        s = _setting(db, u.id)
        on = bool(s and s.enabled)
        if side == "tenant" and not on:
            continue
        out.append({"unit_id": u.id, "number": u.number, "side": side, "enabled": on})
    return out


@router.get("/switches")
def switches(ctx: Ctx = Depends(property_ctx), db: Session = Depends(get_db)):
    """For the building admin: only whether the add-on is on, flat by flat. Never any content."""
    ctx.feature("rental_records")
    ctx.need(*MANAGE)
    on = {s.unit_id: s.enabled for s in db.scalars(select(RentalSetting).where(RentalSetting.property_id == ctx.property.id))}
    return [{"unit_id": u.id, "number": u.number, "enabled": bool(on.get(u.id))} for u in db.scalars(select(Unit).where(Unit.property_id == ctx.property.id).order_by(Unit.number))]


class SwitchIn(BaseModel):
    enabled: bool


@router.put("/units/{uid}/switch")
def set_switch(uid: int, body: SwitchIn, ctx: Ctx = Depends(property_ctx), db: Session = Depends(get_db)):
    """The flat owner (or representative) turns the add-on on or off. The building admin can do it on the owner's behalf."""
    _unit(db, ctx, uid)
    side = _side(db, ctx, uid)
    if side != "owner" and not ctx.has(*MANAGE):
        raise HTTPException(403, "Only the flat owner can switch this")
    s = _setting(db, uid, create=True)
    changed = s.enabled != body.enabled
    s.enabled, s.updated_by, s.updated_at = body.enabled, ctx.user.id, now()
    if changed:
        audit(db, user_id=ctx.user.id, org_id=ctx.property.org_id, property_id=ctx.property.id, action="rental.switch", entity="unit", entity_id=uid,
              meta={"enabled": body.enabled, "by": side or "admin"})
    db.commit()
    return {"unit_id": uid, "enabled": s.enabled}


# ---------------- one flat, whole picture
@router.get("/units/{uid}")
def overview(uid: int, ctx: Ctx = Depends(property_ctx), db: Session = Depends(get_db)):
    unit, side = _access(db, ctx, uid)
    today = date.today()
    ags = db.scalars(select(RentalAgreement).where(RentalAgreement.unit_id == uid).order_by(RentalAgreement.start_date.desc())).all()
    pays = db.scalars(select(RentalPayment).where(RentalPayment.unit_id == uid).order_by(RentalPayment.paid_on.desc(), RentalPayment.id.desc())).all()
    if side == "tenant":
        pays = [p for p in pays if p.status != "rejected" or p.source == "tenant"]
    led = build_ledger(ags, pays, today)
    people = db.scalars(select(Occupancy).where(Occupancy.unit_id == uid, Occupancy.active)).all()
    return {"unit": {"id": unit.id, "number": unit.number}, "side": side,
            "people": [{"kind": o.kind, "name": o.name, "name_bn": o.name_bn, "phone": o.phone} for o in people],
            "agreements": [_agr(a, today) for a in ags], "expiring": [a.id for a in ags if agreement_flags(a, today)["expiring"]],
            "ledger": led, "payments": [_pay(p) for p in pays],
            "notes": [{"id": n.id, "kind": n.kind, "period": n.period, "body": n.body, "sms_status": n.sms_status, "at": n.created_at.isoformat(), "by": _name(db, n.created_by)}
                      for n in db.scalars(select(RentalNote).where(RentalNote.unit_id == uid).order_by(RentalNote.id.desc()).limit(50))] if side == "owner" else [],
            "issues": [_issue(i) for i in db.scalars(select(RentalIssue).where(RentalIssue.unit_id == uid).order_by(RentalIssue.id.desc()))],
            "followups": [_fu(f) for f in db.scalars(select(RentalFollowup).where(RentalFollowup.unit_id == uid).order_by(RentalFollowup.done, RentalFollowup.due_date, RentalFollowup.id))]}


# ---------------- files
async def _read_upload(file: UploadFile, kinds: dict = ALLOWED) -> tuple[bytes, str]:
    spec = kinds.get(file.content_type or "")
    if not spec:
        raise HTTPException(422, "Upload a photo (JPG or PNG) or a PDF")
    data = await file.read(config.MAX_UPLOAD_BYTES + 1)
    if len(data) > config.MAX_UPLOAD_BYTES:
        raise HTTPException(413, "The file is bigger than 3 MB")
    if not data:
        raise HTTPException(422, "The file is empty")
    if not data.startswith(spec[1]):
        raise HTTPException(422, "The file does not look like its type")
    return data, spec[0]


def _save(unit_id: int, data: bytes, ext: str) -> str:
    folder = config.UPLOAD_DIR / "rental" / str(unit_id)
    folder.mkdir(parents=True, exist_ok=True)
    stored = f"{secrets.token_hex(10)}.{ext}"
    (folder / stored).write_bytes(data)
    return stored


def _send(unit_id: int, stored: str, ctype: str, name: str):
    path = config.UPLOAD_DIR / "rental" / str(unit_id) / (stored or "x")
    if not stored or not path.exists():
        raise HTTPException(404, "Not found")
    return FileResponse(path, media_type=ctype, filename=name or stored, headers={"X-Content-Type-Options": "nosniff"})


# ---------------- agreements
@router.post("/units/{uid}/agreements", status_code=201)
async def add_agreement(uid: int, title: str = Form(..., min_length=1, max_length=160), start_date: date = Form(...), end_date: date | None = Form(None),
                        rent: int = Form(0, ge=0, le=10**10), advance: int = Form(0, ge=0, le=10**10), file: UploadFile = File(...),
                        ctx: Ctx = Depends(property_ctx), db: Session = Depends(get_db)):
    _access(db, ctx, uid, owner_only=True)
    if end_date and end_date < start_date:
        raise HTTPException(422, "The end date is before the start date")
    data, ext = await _read_upload(file)
    a = RentalAgreement(unit_id=uid, title=title.strip(), start_date=start_date, end_date=end_date, rent=rent, advance=advance, filename=(file.filename or f"agreement.{ext}")[:160],
                        stored=_save(uid, data, ext), content_type=file.content_type, size=len(data), created_by=ctx.user.id)
    db.add(a)
    db.flush()
    audit(db, user_id=ctx.user.id, org_id=ctx.property.org_id, property_id=ctx.property.id, action="rental.agreement.add", entity="unit", entity_id=uid)
    db.commit()
    return _agr(a, date.today())


def _mine(db: Session, model, mid: int, ctx: Ctx, owner_only: bool = False):
    row = db.get(model, mid)
    if not row:
        raise HTTPException(404, "Not found")
    uid = row.unit_id if hasattr(row, "unit_id") else db.get(RentalIssue, row.issue_id).unit_id
    unit, side = _access(db, ctx, uid, owner_only)
    return row, unit, side


@router.get("/agreements/{aid}/file")
def agreement_file(aid: int, ctx: Ctx = Depends(property_ctx), db: Session = Depends(get_db)):
    a, _, _ = _mine(db, RentalAgreement, aid, ctx)
    return _send(a.unit_id, a.stored, a.content_type, a.filename)


@router.delete("/agreements/{aid}")
def del_agreement(aid: int, ctx: Ctx = Depends(property_ctx), db: Session = Depends(get_db)):
    a, _, _ = _mine(db, RentalAgreement, aid, ctx, owner_only=True)
    (config.UPLOAD_DIR / "rental" / str(a.unit_id) / a.stored).unlink(missing_ok=True)
    db.delete(a)
    audit(db, user_id=ctx.user.id, org_id=ctx.property.org_id, property_id=ctx.property.id, action="rental.agreement.delete", entity="unit", entity_id=a.unit_id)
    db.commit()
    return {"ok": True}


# ---------------- rent ledger
class PayIn(BaseModel):
    period: str
    amount: int = Field(gt=0, le=10**10)
    method: str
    paid_on: date
    note: str = Field(default="", max_length=300)
    bank_ref: str = Field(default="", max_length=60)


@router.post("/units/{uid}/payments", status_code=201)
def add_payment(uid: int, body: PayIn, ctx: Ctx = Depends(property_ctx), db: Session = Depends(get_db)):
    """Owner: records rent received (confirmed at once). Tenant: logs "I paid", which waits for the owner to confirm."""
    _, side = _access(db, ctx, uid)
    if not _valid_period(body.period):
        raise HTTPException(422, "Month must look like 2026-10")
    if body.method not in ("cash", "bank"):
        raise HTTPException(422, "Method is cash or bank")
    if body.paid_on > date.today() + timedelta(days=1):
        raise HTTPException(422, "The date is in the future")
    p = RentalPayment(unit_id=uid, period=body.period, amount=body.amount, method=body.method, paid_on=body.paid_on, note=body.note.strip(), bank_ref=body.bank_ref.strip(),
                      status="confirmed" if side == "owner" else "pending", source=side, created_by=ctx.user.id, decided_at=now() if side == "owner" else None)
    db.add(p)
    db.flush()
    audit(db, user_id=ctx.user.id, org_id=ctx.property.org_id, property_id=ctx.property.id, action=f"rental.payment.{'record' if side == 'owner' else 'claim'}", entity="unit", entity_id=uid)
    db.commit()
    return _pay(p)


def _decide(pid: int, status: str, ctx: Ctx, db: Session):
    p, _, _ = _mine(db, RentalPayment, pid, ctx, owner_only=True)
    if p.status != "pending":
        raise HTTPException(409, "This payment is already decided")
    p.status, p.decided_at = status, now()
    audit(db, user_id=ctx.user.id, org_id=ctx.property.org_id, property_id=ctx.property.id, action=f"rental.payment.{status}", entity="unit", entity_id=p.unit_id)
    db.commit()
    return _pay(p)


@router.post("/payments/{pid}/confirm")
def confirm_payment(pid: int, ctx: Ctx = Depends(property_ctx), db: Session = Depends(get_db)):
    return _decide(pid, "confirmed", ctx, db)


@router.post("/payments/{pid}/reject")
def reject_payment(pid: int, ctx: Ctx = Depends(property_ctx), db: Session = Depends(get_db)):
    return _decide(pid, "rejected", ctx, db)


@router.delete("/payments/{pid}")
def del_payment(pid: int, ctx: Ctx = Depends(property_ctx), db: Session = Depends(get_db)):
    """The owner removes a wrong entry. A payment that has a receipt stays: the receipt number must not disappear."""
    p, _, _ = _mine(db, RentalPayment, pid, ctx, owner_only=True)
    if p.receipt_no:
        raise HTTPException(409, "A receipt was issued for this payment")
    db.delete(p)
    audit(db, user_id=ctx.user.id, org_id=ctx.property.org_id, property_id=ctx.property.id, action="rental.payment.delete", entity="unit", entity_id=p.unit_id)
    db.commit()
    return {"ok": True}


@router.post("/payments/{pid}/receipt")
def make_receipt(pid: int, ctx: Ctx = Depends(property_ctx), db: Session = Depends(get_db)):
    """Gives a confirmed payment its money receipt number (1, 2, 3 ... per flat). Asking again returns the same one."""
    p, unit, _ = _mine(db, RentalPayment, pid, ctx, owner_only=True)
    if p.status != "confirmed":
        raise HTTPException(409, "Only a confirmed payment gets a receipt")
    if not p.receipt_no:
        s = db.scalar(select(RentalSetting).where(RentalSetting.unit_id == p.unit_id).with_for_update())
        s.receipt_seq += 1
        p.receipt_seq, p.receipt_no = s.receipt_seq, f"MR-{unit.number}-{s.receipt_seq:04d}"
        audit(db, user_id=ctx.user.id, org_id=ctx.property.org_id, property_id=ctx.property.id, action="rental.receipt", entity="unit", entity_id=p.unit_id, meta={"no": p.receipt_no})
        db.commit()
    return _pay(p)


@router.get("/payments/{pid}/receipt")
def get_receipt(pid: int, ctx: Ctx = Depends(property_ctx), db: Session = Depends(get_db)):
    p, unit, side = _mine(db, RentalPayment, pid, ctx)
    if p.status != "confirmed" or not p.receipt_no:
        raise HTTPException(404, "Not found")
    people = db.scalars(select(Occupancy).where(Occupancy.unit_id == unit.id, Occupancy.active)).all()
    ags = db.scalars(select(RentalAgreement).where(RentalAgreement.unit_id == unit.id)).all()
    pays = db.scalars(select(RentalPayment).where(RentalPayment.unit_id == unit.id)).all()
    month = next((m for m in build_ledger(ags, pays, date.today())["months"] if m["period"] == p.period), None)
    return {"receipt_no": p.receipt_no, "paid_on": p.paid_on.isoformat(), "amount": p.amount, "method": p.method, "bank_ref": p.bank_ref, "period": p.period, "note": p.note,
            "unit": unit.number, "building": ctx.property.name, "building_bn": ctx.property.name_bn, "address": ctx.property.address, "side": side,
            "month_due": month["due"] if month else 0, "month_outstanding": month["outstanding"] if month else 0,
            "people": [{"kind": o.kind, "name": o.name, "name_bn": o.name_bn} for o in people], "received_by": _name(db, p.created_by) if p.source == "owner" else ""}


# ---------------- follow-up on rent
class RemindIn(BaseModel):
    period: str


@router.post("/units/{uid}/remind")
def remind(uid: int, body: RemindIn, ctx: Ctx = Depends(property_ctx), db: Session = Depends(get_db)):
    """Owner sends an SMS reminder to the tenant (costs one SMS credit). The text never carries the amount, and the message is
    not listed in the building's Messages screen: it stays private. The reminder lands in the note history."""
    unit, _ = _access(db, ctx, uid, owner_only=True)
    if not _valid_period(body.period):
        raise HTTPException(422, "Month must look like 2026-10")
    t = db.scalar(select(Occupancy).where(Occupancy.unit_id == uid, Occupancy.kind == "tenant", Occupancy.active))
    if not t:
        raise HTTPException(409, "This flat has no tenant")
    lang = (db.get(User, t.user_id).lang if t.user_id and db.get(User, t.user_id) else "bn") or "bn"
    text = (f"FlatWise: your flat owner has sent a rent reminder for {body.period} (flat {unit.number}). Please open Rental records." if lang == "en"
            else f"FlatWise: ফ্ল্যাট {unit.number}-এর {body.period} মাসের ভাড়ার বিষয়ে বাড়িওয়ালার রিমাইন্ডার। অনুগ্রহ করে ভাড়ার রেকর্ড দেখুন।")
    msg = Message(property_id=ctx.property.id, unit_id=uid, to_name=t.name, to_phone=t.phone, template="rent_remind", lang=lang, body=text, idem_key=f"rr{uid}:{secrets.token_hex(6)}")
    deliver(db, ctx.property.org_id, msg)          # not added to the session on purpose: the building's Messages list must not show it
    n = RentalNote(unit_id=uid, kind="reminder", period=body.period, body=text, sms_status=msg.status, created_by=ctx.user.id)
    db.add(n)
    audit(db, user_id=ctx.user.id, org_id=ctx.property.org_id, property_id=ctx.property.id, action="rental.remind", entity="unit", entity_id=uid, meta={"status": msg.status})
    db.commit()
    return {"status": msg.status, "error": msg.error}


class NoteIn(BaseModel):
    body: str = Field(min_length=1, max_length=400)
    period: str = ""


@router.post("/units/{uid}/notes", status_code=201)
def add_note(uid: int, body: NoteIn, ctx: Ctx = Depends(property_ctx), db: Session = Depends(get_db)):
    _access(db, ctx, uid, owner_only=True)
    db.add(RentalNote(unit_id=uid, kind="note", period=body.period if _valid_period(body.period) else "", body=body.body.strip(), created_by=ctx.user.id))
    db.commit()
    return {"ok": True}


# ---------------- issues
@router.post("/units/{uid}/issues", status_code=201)
async def add_issue(uid: int, title: str = Form(..., min_length=1, max_length=160), body: str = Form("", max_length=4000), photo: UploadFile | None = File(None),
                    ctx: Ctx = Depends(property_ctx), db: Session = Depends(get_db)):
    _, side = _access(db, ctx, uid)
    i = RentalIssue(unit_id=uid, title=title.strip(), body=body.strip(), raised_by=ctx.user.id, raised_side=side)
    if photo is not None and photo.filename:
        data, ext = await _read_upload(photo, {k: v for k, v in ALLOWED.items() if k.startswith("image/")})
        i.photo_stored, i.photo_type, i.photo_name = _save(uid, data, ext), photo.content_type, photo.filename[:160]
    db.add(i)
    db.flush()
    audit(db, user_id=ctx.user.id, org_id=ctx.property.org_id, property_id=ctx.property.id, action="rental.issue.add", entity="unit", entity_id=uid)
    db.commit()
    return _issue(i)


def _comment(db: Session, c: RentalComment) -> dict:
    return {"id": c.id, "side": c.side, "body": c.body, "by": _name(db, c.user_id), "at": c.created_at.isoformat()}


@router.get("/issues/{iid}")
def get_issue(iid: int, ctx: Ctx = Depends(property_ctx), db: Session = Depends(get_db)):
    i, _, _ = _mine(db, RentalIssue, iid, ctx)
    return {**_issue(i), "comments": [_comment(db, c) for c in db.scalars(select(RentalComment).where(RentalComment.issue_id == iid).order_by(RentalComment.id))]}


class CommentIn(BaseModel):
    body: str = Field(min_length=1, max_length=1000)


@router.post("/issues/{iid}/comments", status_code=201)
def add_comment(iid: int, body: CommentIn, ctx: Ctx = Depends(property_ctx), db: Session = Depends(get_db)):
    i, _, side = _mine(db, RentalIssue, iid, ctx)
    c = RentalComment(issue_id=iid, user_id=ctx.user.id, side=side, body=body.body.strip())
    db.add(c)
    i.updated_at = now()
    db.commit()
    return _comment(db, c)


class IssueEdit(BaseModel):
    status: str | None = None
    cost: int | None = Field(default=None, ge=0, le=10**10)
    cost_note: str | None = Field(default=None, max_length=200)


@router.patch("/issues/{iid}")
def edit_issue(iid: int, body: IssueEdit, ctx: Ctx = Depends(property_ctx), db: Session = Depends(get_db)):
    """Either side moves the status; only the owner marks the cost."""
    i, _, side = _mine(db, RentalIssue, iid, ctx)
    if body.status is not None:
        if body.status not in ISSUE_STATUS:
            raise HTTPException(422, "Unknown status")
        i.status = body.status
    if body.cost is not None or body.cost_note is not None:
        if side != "owner":
            raise HTTPException(403, "Only the flat owner can mark the cost")
        if body.cost is not None:
            i.cost = body.cost
        if body.cost_note is not None:
            i.cost_note = body.cost_note.strip()
    i.updated_at = now()
    audit(db, user_id=ctx.user.id, org_id=ctx.property.org_id, property_id=ctx.property.id, action="rental.issue.edit", entity="unit", entity_id=i.unit_id)
    db.commit()
    return _issue(i)


@router.get("/issues/{iid}/photo")
def issue_photo(iid: int, ctx: Ctx = Depends(property_ctx), db: Session = Depends(get_db)):
    i, _, _ = _mine(db, RentalIssue, iid, ctx)
    return _send(i.unit_id, i.photo_stored, i.photo_type, i.photo_name)


# ---------------- follow-ups
class FollowIn(BaseModel):
    text: str = Field(min_length=1, max_length=300)
    due_date: date | None = None
    ref_kind: str = ""
    ref: str = Field(default="", max_length=16)


@router.post("/units/{uid}/followups", status_code=201)
def add_followup(uid: int, body: FollowIn, ctx: Ctx = Depends(property_ctx), db: Session = Depends(get_db)):
    _access(db, ctx, uid)
    if body.ref_kind not in ("", "rent", "issue"):
        raise HTTPException(422, "A follow-up is tied to rent or an issue")
    f = RentalFollowup(unit_id=uid, text=body.text.strip(), due_date=body.due_date, ref_kind=body.ref_kind, ref=body.ref if body.ref_kind else "", created_by=ctx.user.id)
    db.add(f)
    db.commit()
    return _fu(f)


class DoneIn(BaseModel):
    done: bool


@router.patch("/followups/{fid}")
def mark_followup(fid: int, body: DoneIn, ctx: Ctx = Depends(property_ctx), db: Session = Depends(get_db)):
    f, _, _ = _mine(db, RentalFollowup, fid, ctx)
    f.done, f.done_at = body.done, now() if body.done else None
    db.commit()
    return _fu(f)


@router.delete("/followups/{fid}")
def del_followup(fid: int, ctx: Ctx = Depends(property_ctx), db: Session = Depends(get_db)):
    f, _, _ = _mine(db, RentalFollowup, fid, ctx)
    db.delete(f)
    db.commit()
    return {"ok": True}
