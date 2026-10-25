"""M18: outsourced security and cleaning agencies, duty roster, attendance and the monthly agency bill check."""
import secrets
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import config
from ..audit import audit
from ..services.uploads import safe_filename
from ..db import get_db
from ..services.storage import get_storage
from ..deps import Ctx, property_ctx
from ..models.agency import Agency, AgencyBill, AgencyDoc, AgencySetting, Post, Replacement, RosterSlot, ShiftDef, StaffPosting
from ..models.billing import Message
from ..models.finance import Expense, Vendor
from ..models.staff import Staff
from ..permissions import COMMITTEE, MANAGE
from ..services import vault
from ..services.messaging import deliver
from .finance import DUAL_ABOVE

router = APIRouter(prefix="/api/agency", tags=["agency"])
ROSTER_VIEW = MANAGE | COMMITTEE | {"AUDITOR", "CARETAKER", "GUARD"}      # guards see the roster only
AGENCY_VIEW = MANAGE | COMMITTEE | {"AUDITOR", "CARETAKER"}              # no guards: contacts, contract, documents
MONEY_SEE = MANAGE | COMMITTEE | {"AUDITOR"}                              # contract fees
AGENCY_EDIT = MANAGE | {"PRESIDENT", "SECRETARY"}
ROSTER_EDIT = MANAGE | {"SECRETARY", "CARETAKER"}
BILL = MANAGE | {"TREASURER"}
BILL_VIEW = BILL | {"PRESIDENT", "SECRETARY", "AUDITOR"}
KINDS = "^(security|cleaning|both)$"
DOC_KINDS = "^(licence|contract|insurance|police_verification)$"
SLOT_STATES = ("planned", "present", "late", "absent", "leave")
DOC_TYPES = {"application/pdf": ("pdf", b"%PDF"), "image/jpeg": ("jpg", b"\xff\xd8\xff"), "image/png": ("png", b"\x89PNG\r\n\x1a\n")}
DHAKA = timezone(timedelta(hours=6))
EXPIRY_DAYS = 60
MAX_HOURS = 12


def _gate(ctx: Ctx) -> None:
    ctx.feature("staff")


def _today() -> date:
    return datetime.now(DHAKA).date()


def week_start(d: date) -> date:
    """Bangladesh working weeks run Saturday to Friday."""
    return d - timedelta(days=(d.weekday() - 5) % 7)


def _hhmm(s: str) -> int:
    h, m = s.split(":")
    return int(h) * 60 + int(m)


def shift_hours(sh: ShiftDef) -> float:
    return ((_hhmm(sh.end) - _hhmm(sh.start)) % 1440) / 60


def _agency_dict(a: Agency, ctx: Ctx, db: Session | None = None) -> dict:
    today = _today()
    left = (a.contract_end - today).days if a.contract_end else None
    d = {"id": a.id, "name": a.name, "name_bn": a.name_bn, "kind": a.kind, "trade_licence": a.trade_licence, "reg_no": a.reg_no, "psc_licence": a.psc_licence, "address": a.address,
         "contact_name": a.contact_name, "contact_phone": a.contact_phone, "emergency_phone": a.emergency_phone, "contract_start": a.contract_start.isoformat() if a.contract_start else None,
         "contract_end": a.contract_end.isoformat() if a.contract_end else None, "days_left": left, "notice_days": a.notice_days, "sla_notes": a.sla_notes, "status": a.status,
         "expiring": a.status == "active" and left is not None and 0 <= left <= EXPIRY_DAYS, "expired": a.status == "active" and left is not None and left < 0}
    if ctx.has(*MONEY_SEE):
        d.update(fee_mode=a.fee_mode, monthly_fee=a.monthly_fee)
    if db is not None:
        d["staff"] = db.scalar(select(func.count()).select_from(StaffPosting).join(Staff, Staff.id == StaffPosting.staff_id).where(StaffPosting.agency_id == a.id, Staff.status == "active")) or 0
        d["posts"] = db.scalar(select(func.count()).select_from(Post).where(Post.agency_id == a.id, Post.active)) or 0
    return d


def _agency(db: Session, ctx: Ctx, aid: int) -> Agency:
    a = db.get(Agency, aid)
    if not a or a.property_id != ctx.property.id:
        raise HTTPException(404, "Not found")
    return a


def _log(db: Session, ctx: Ctx, action: str, entity: str, eid, meta: dict | None = None) -> None:
    audit(db, user_id=ctx.user.id, org_id=ctx.property.org_id, property_id=ctx.property.id, action=action, entity=entity, entity_id=eid, meta=meta or {})


# ---------------- agencies
class AgencyIn(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    name_bn: str = Field(default="", max_length=120)
    kind: str = Field(default="security", pattern=KINDS)
    trade_licence: str = Field(default="", max_length=60)
    reg_no: str = Field(default="", max_length=80)
    psc_licence: str = Field(default="", max_length=60)
    address: str = Field(default="", max_length=200)
    contact_name: str = Field(default="", max_length=100)
    contact_phone: str = Field(default="", max_length=32)
    emergency_phone: str = Field(default="", max_length=32)
    contract_start: date | None = None
    contract_end: date | None = None
    fee_mode: str = Field(default="flat", pattern="^(flat|per_post)$")
    monthly_fee: int = Field(default=0, ge=0, le=10**10)
    notice_days: int = Field(default=30, ge=0, le=365)
    sla_notes: str = Field(default="", max_length=2000)
    status: str = Field(default="active", pattern="^(active|ended)$")


def _check_agency(body: AgencyIn) -> None:
    if body.contract_start and body.contract_end and body.contract_end < body.contract_start:
        raise HTTPException(422, "The contract ends before it starts")
    if body.kind in ("security", "both") and not body.psc_licence.strip():
        raise HTTPException(422, "A security agency needs its PSC licence number")


@router.get("/agencies")
def agencies(ctx: Ctx = Depends(property_ctx), db: Session = Depends(get_db)):
    _gate(ctx)
    ctx.need(*AGENCY_VIEW)
    return [_agency_dict(a, ctx, db) for a in db.scalars(select(Agency).where(Agency.property_id == ctx.property.id).order_by(Agency.status, Agency.name))]


@router.post("/agencies", status_code=201)
def add_agency(body: AgencyIn, ctx: Ctx = Depends(property_ctx), db: Session = Depends(get_db)):
    _gate(ctx)
    ctx.need(*AGENCY_EDIT)
    _check_agency(body)
    a = Agency(property_id=ctx.property.id, **body.model_dump())
    db.add(a)
    db.flush()
    v = Vendor(property_id=ctx.property.id, name=a.name, name_bn=a.name_bn, phone=a.contact_phone, category="services")   # its invoices are booked under this vendor
    db.add(v)
    db.flush()
    a.vendor_id = v.id
    _log(db, ctx, "agency.add", "agency", a.id, {"kind": a.kind})
    db.commit()
    return _agency_dict(a, ctx, db)


@router.get("/agencies/{aid}")
def agency_detail(aid: int, ctx: Ctx = Depends(property_ctx), db: Session = Depends(get_db)):
    _gate(ctx)
    ctx.need(*AGENCY_VIEW)
    a = _agency(db, ctx, aid)
    docs = db.scalars(select(AgencyDoc).where(AgencyDoc.agency_id == a.id).order_by(AgencyDoc.id.desc())).all() if ctx.has(*MONEY_SEE) else []
    return {**_agency_dict(a, ctx, db), "docs": [_doc(d) for d in docs]}


@router.put("/agencies/{aid}")
def edit_agency(aid: int, body: AgencyIn, ctx: Ctx = Depends(property_ctx), db: Session = Depends(get_db)):
    _gate(ctx)
    ctx.need(*AGENCY_EDIT)
    a = _agency(db, ctx, aid)
    _check_agency(body)
    for k, v in body.model_dump().items():
        setattr(a, k, v)
    if a.vendor_id and (v_ := db.get(Vendor, a.vendor_id)):
        v_.name, v_.name_bn, v_.phone = a.name, a.name_bn, a.contact_phone
    _log(db, ctx, "agency.edit", "agency", a.id, {"status": a.status})
    db.commit()
    return _agency_dict(a, ctx, db)


# ---------------- documents
def _doc(d: AgencyDoc) -> dict:
    return {"id": d.id, "kind": d.kind, "filename": d.filename, "size": d.size, "content_type": d.content_type, "at": d.uploaded_at.isoformat()}


@router.post("/agencies/{aid}/docs", status_code=201)
async def upload_doc(aid: int, kind: str = Form(..., pattern=DOC_KINDS), file: UploadFile = File(...), ctx: Ctx = Depends(property_ctx), db: Session = Depends(get_db)):
    _gate(ctx)
    ctx.need(*AGENCY_EDIT)
    a = _agency(db, ctx, aid)
    spec = DOC_TYPES.get(file.content_type or "")
    if not spec:
        raise HTTPException(422, "Upload a PDF, JPG or PNG file")
    data = await file.read(config.MAX_UPLOAD_BYTES + 1)
    if len(data) > config.MAX_UPLOAD_BYTES:
        raise HTTPException(413, "The file is bigger than 3 MB")
    if not data:
        raise HTTPException(422, "The file is empty")
    if not data.startswith(spec[1]):
        raise HTTPException(422, "The file does not look like its type")
    stored = f"{secrets.token_hex(10)}.{spec[0]}"
    get_storage().put(f"agencies/{a.id}/{stored}", data, file.content_type or "")
    d = AgencyDoc(agency_id=a.id, kind=kind, filename=safe_filename(file.filename, f"{kind}.{spec[0]}"), stored=stored, content_type=file.content_type, size=len(data), uploaded_by=ctx.user.id)
    db.add(d)
    db.flush()
    _log(db, ctx, "agency.doc.add", "agency", a.id, {"kind": kind})
    db.commit()
    return _doc(d)


def _own_doc(db: Session, ctx: Ctx, aid: int, did: int) -> tuple[Agency, AgencyDoc]:
    a = _agency(db, ctx, aid)
    d = db.get(AgencyDoc, did)
    if not d or d.agency_id != a.id:
        raise HTTPException(404, "Not found")
    return a, d


@router.get("/agencies/{aid}/docs/{did}")
def get_doc(aid: int, did: int, ctx: Ctx = Depends(property_ctx), db: Session = Depends(get_db)):
    _gate(ctx)
    ctx.need(*MONEY_SEE)
    a, d = _own_doc(db, ctx, aid, did)
    key = f"agencies/{a.id}/{d.stored}"
    if not get_storage().exists(key):
        raise HTTPException(404, "Not found")
    return get_storage().serve(key, d.content_type, d.filename, headers={"X-Content-Type-Options": "nosniff"})


@router.delete("/agencies/{aid}/docs/{did}", status_code=204)
def delete_doc(aid: int, did: int, ctx: Ctx = Depends(property_ctx), db: Session = Depends(get_db)):
    _gate(ctx)
    ctx.need(*AGENCY_EDIT)
    a, d = _own_doc(db, ctx, aid, did)
    get_storage().delete(f"agencies/{a.id}/{d.stored}")
    db.delete(d)
    _log(db, ctx, "agency.doc.delete", "agency", a.id, {"kind": d.kind})
    db.commit()


# ---------------- agency staff (same staff register, same encrypted NID vault)
class AgencyStaffIn(BaseModel):
    name: str = Field(min_length=2, max_length=100)
    name_bn: str = Field(default="", max_length=100)
    role: str = Field(default="guard", pattern="^(guard|cleaner|caretaker|other)$")
    phone: str = Field(default="", max_length=32)
    nid: str = Field(default="", max_length=20)
    emp_no: str = Field(default="", max_length=40)
    deployed_on: date | None = None
    substitute: bool = False


def _make_staff(db: Session, ctx: Ctx, a: Agency, body: AgencyStaffIn) -> Staff:
    nid = "".join(ch for ch in body.nid if ch.isdigit())
    if body.nid and len(nid) not in (10, 13, 17):
        raise HTTPException(422, "A National ID has 10, 13 or 17 digits")
    s = Staff(property_id=ctx.property.id, name=body.name, name_bn=body.name_bn, role=body.role, phone=body.phone, joined=body.deployed_on or _today(), salary=0,
              nid_enc=vault.seal(nid) if nid else "", nid_last4=nid[-4:] if nid else "")   # salary 0: the agency pays them, never the building payroll
    db.add(s)
    db.flush()
    db.add(StaffPosting(staff_id=s.id, agency_id=a.id, emp_no=body.emp_no, deployed_on=body.deployed_on or _today(), substitute=body.substitute))
    db.flush()
    return s


@router.post("/agencies/{aid}/staff", status_code=201)
def add_agency_staff(aid: int, body: AgencyStaffIn, ctx: Ctx = Depends(property_ctx), db: Session = Depends(get_db)):
    _gate(ctx)
    ctx.need(*AGENCY_EDIT)
    a = _agency(db, ctx, aid)
    s = _make_staff(db, ctx, a, body)
    _log(db, ctx, "agency.staff.add", "staff", s.id, {"agency": a.id, "role": s.role})
    db.commit()
    return {"id": s.id, "name": s.name, "agency_id": a.id, "nid": vault.mask(s.nid_last4)}


class PostingIn(BaseModel):
    agency_id: int | None = None
    emp_no: str = Field(default="", max_length=40)
    deployed_on: date | None = None


@router.put("/staff/{sid}/posting")
def set_posting(sid: int, body: PostingIn, ctx: Ctx = Depends(property_ctx), db: Session = Depends(get_db)):
    """Moves a staff member between direct and an agency. Agency staff leave the building's salary sheets."""
    _gate(ctx)
    ctx.need(*AGENCY_EDIT)
    s = db.get(Staff, sid)
    if not s or s.property_id != ctx.property.id:
        raise HTTPException(404, "Not found")
    link = db.scalar(select(StaffPosting).where(StaffPosting.staff_id == sid))
    if body.agency_id is None:
        if link:
            db.delete(link)
    else:
        _agency(db, ctx, body.agency_id)
        if link:
            link.agency_id, link.emp_no, link.deployed_on = body.agency_id, body.emp_no, body.deployed_on
        else:
            db.add(StaffPosting(staff_id=sid, agency_id=body.agency_id, emp_no=body.emp_no, deployed_on=body.deployed_on))
    _log(db, ctx, "agency.staff.link", "staff", sid, {"agency": body.agency_id})
    db.commit()
    return {"id": sid, "agency_id": body.agency_id}


# ---------------- posts and shifts
class PostIn(BaseModel):
    name: str = Field(min_length=2, max_length=80)
    name_bn: str = Field(default="", max_length=80)
    kind: str = Field(default="security", pattern="^(security|cleaning)$")
    headcount: int = Field(default=1, ge=1, le=20)
    shift_ids: list[int] = []
    agency_id: int | None = None
    active: bool = True


class ShiftIn(BaseModel):
    name: str = Field(min_length=2, max_length=40)
    name_bn: str = Field(default="", max_length=40)
    start: str = Field(pattern=r"^([01]\d|2[0-3]):[0-5]\d$")
    end: str = Field(pattern=r"^([01]\d|2[0-3]):[0-5]\d$")
    active: bool = True


def _post(p: Post) -> dict:
    return {"id": p.id, "name": p.name, "name_bn": p.name_bn, "kind": p.kind, "headcount": p.headcount, "shift_ids": p.shift_ids or [], "agency_id": p.agency_id, "active": p.active}


def _shift(s: ShiftDef) -> dict:
    return {"id": s.id, "name": s.name, "name_bn": s.name_bn, "start": s.start, "end": s.end, "hours": shift_hours(s), "active": s.active}


def _posts(db: Session, ctx: Ctx, only_active: bool = False) -> list[Post]:
    stmt = select(Post).where(Post.property_id == ctx.property.id).order_by(Post.id)
    return list(db.scalars(stmt.where(Post.active) if only_active else stmt))


def _shifts(db: Session, ctx: Ctx, only_active: bool = False) -> list[ShiftDef]:
    stmt = select(ShiftDef).where(ShiftDef.property_id == ctx.property.id).order_by(ShiftDef.start, ShiftDef.id)
    return list(db.scalars(stmt.where(ShiftDef.active) if only_active else stmt))


@router.get("/posts")
def posts(ctx: Ctx = Depends(property_ctx), db: Session = Depends(get_db)):
    _gate(ctx)
    ctx.need(*ROSTER_VIEW)
    return {"posts": [_post(p) for p in _posts(db, ctx)], "shifts": [_shift(s) for s in _shifts(db, ctx)]}


def _check_post(db: Session, ctx: Ctx, body: PostIn) -> None:
    if body.agency_id is not None:
        _agency(db, ctx, body.agency_id)
    have = {s.id for s in _shifts(db, ctx)}
    if any(i not in have for i in body.shift_ids):
        raise HTTPException(422, "Unknown shift")


@router.post("/posts", status_code=201)
def add_post(body: PostIn, ctx: Ctx = Depends(property_ctx), db: Session = Depends(get_db)):
    _gate(ctx)
    ctx.need(*ROSTER_EDIT)
    _check_post(db, ctx, body)
    p = Post(property_id=ctx.property.id, **body.model_dump())
    db.add(p)
    db.flush()
    _log(db, ctx, "roster.post.add", "post", p.id)
    db.commit()
    return _post(p)


@router.put("/posts/{pid}")
def edit_post(pid: int, body: PostIn, ctx: Ctx = Depends(property_ctx), db: Session = Depends(get_db)):
    _gate(ctx)
    ctx.need(*ROSTER_EDIT)
    p = db.get(Post, pid)
    if not p or p.property_id != ctx.property.id:
        raise HTTPException(404, "Not found")
    _check_post(db, ctx, body)
    for k, v in body.model_dump().items():
        setattr(p, k, v)
    _log(db, ctx, "roster.post.edit", "post", p.id)
    db.commit()
    return _post(p)


@router.post("/shifts", status_code=201)
def add_shift(body: ShiftIn, ctx: Ctx = Depends(property_ctx), db: Session = Depends(get_db)):
    _gate(ctx)
    ctx.need(*ROSTER_EDIT)
    if body.start == body.end:
        raise HTTPException(422, "A shift cannot start and end at the same time")
    s = ShiftDef(property_id=ctx.property.id, **body.model_dump())
    db.add(s)
    db.flush()
    _log(db, ctx, "roster.shift.add", "shift", s.id)
    db.commit()
    return _shift(s)


@router.put("/shifts/{sid}")
def edit_shift(sid: int, body: ShiftIn, ctx: Ctx = Depends(property_ctx), db: Session = Depends(get_db)):
    _gate(ctx)
    ctx.need(*ROSTER_EDIT)
    s = db.get(ShiftDef, sid)
    if not s or s.property_id != ctx.property.id:
        raise HTTPException(404, "Not found")
    if body.start == body.end:
        raise HTTPException(422, "A shift cannot start and end at the same time")
    for k, v in body.model_dump().items():
        setattr(s, k, v)
    _log(db, ctx, "roster.shift.edit", "shift", s.id)
    db.commit()
    return _shift(s)


# ---------------- roster
def conflicts(slots: list[RosterSlot], hours: dict[int, float], lo: date, hi: date) -> list[dict]:
    """Rules, as warnings (never blocks): two shifts the same day, more than 12 h in a day, seven days in a row. Absent and leave slots do not count as working."""
    by: dict[int, dict[date, list[RosterSlot]]] = defaultdict(lambda: defaultdict(list))
    for s in slots:
        if s.status not in ("absent", "leave"):
            by[s.staff_id][s.day].append(s)
    out = []
    for sid, days in by.items():
        for d, items in sorted(days.items()):
            if not (lo <= d <= hi):
                continue
            if len(items) > 1:
                out.append({"staff_id": sid, "date": d.isoformat(), "type": "two_shifts"})
            if sum(hours.get(i.shift_id, 0) for i in items) > MAX_HOURS:
                out.append({"staff_id": sid, "date": d.isoformat(), "type": "over_12h"})
            if all((d - timedelta(days=k)) in days for k in range(7)):
                out.append({"staff_id": sid, "date": d.isoformat(), "type": "seven_days"})
    return out


def _week_slots(db: Session, ctx: Ctx, start: date, end: date) -> list[RosterSlot]:
    return list(db.scalars(select(RosterSlot).where(RosterSlot.property_id == ctx.property.id, RosterSlot.day >= start, RosterSlot.day <= end).order_by(RosterSlot.day, RosterSlot.id)))


def _staff_map(db: Session, ctx: Ctx) -> dict[int, dict]:
    ag = {a.id: a for a in db.scalars(select(Agency).where(Agency.property_id == ctx.property.id))}
    link = {l.staff_id: l for l in db.scalars(select(StaffPosting).join(Agency, Agency.id == StaffPosting.agency_id).where(Agency.property_id == ctx.property.id))}
    out = {}
    for s in db.scalars(select(Staff).where(Staff.property_id == ctx.property.id)):
        l = link.get(s.id)
        a = ag.get(l.agency_id) if l else None
        out[s.id] = {"name": s.name, "name_bn": s.name_bn, "role": s.role, "agency_id": a.id if a else None, "agency": a.name if a else "", "agency_bn": a.name_bn if a else "",
                     "emp_no": l.emp_no if l else "", "substitute": bool(l and l.substitute), "active": s.status == "active"}
    return out


def _slot(s: RosterSlot, st: dict, phones: bool = False) -> dict:
    p = st.get(s.staff_id, {})
    return {"id": s.id, "date": s.day.isoformat(), "post_id": s.post_id, "shift_id": s.shift_id, "staff_id": s.staff_id, "name": p.get("name", ""), "name_bn": p.get("name_bn", ""),
            "role": p.get("role", ""), "agency_id": p.get("agency_id"), "agency": p.get("agency", ""), "agency_bn": p.get("agency_bn", ""), "status": s.status,
            "substitute": s.substitute or p.get("substitute", False), "note": s.note}


def _parse_week(start: date | None) -> date:
    return week_start(start or _today())


@router.get("/roster")
def roster(start: date | None = None, ctx: Ctx = Depends(property_ctx), db: Session = Depends(get_db)):
    _gate(ctx)
    ctx.need(*ROSTER_VIEW)
    ws = _parse_week(start)
    we = ws + timedelta(days=6)
    sh = _shifts(db, ctx)
    hours = {s.id: shift_hours(s) for s in sh}
    st = _staff_map(db, ctx)
    slots = _week_slots(db, ctx, ws - timedelta(days=6), we + timedelta(days=6))
    mine = [s for s in slots if ws <= s.day <= we]
    warns = conflicts(slots, hours, ws, we)
    for w in warns:
        w["name"], w["name_bn"] = st.get(w["staff_id"], {}).get("name", ""), st.get(w["staff_id"], {}).get("name_bn", "")
    can = ctx.has(*ROSTER_EDIT)
    return {"start": ws.isoformat(), "end": we.isoformat(), "days": [(ws + timedelta(days=i)).isoformat() for i in range(7)], "posts": [_post(p) for p in _posts(db, ctx) if p.active],
            "shifts": [_shift(s) for s in sh if s.active], "slots": [_slot(s, st) for s in mine], "warnings": warns, "can_edit": can, "building": ctx.property.name, "building_bn": ctx.property.name_bn,
            "staff": [{"id": i, "name": v["name"], "name_bn": v["name_bn"], "role": v["role"], "agency_id": v["agency_id"], "agency": v["agency"]} for i, v in st.items() if v["active"]] if can else []}


class SlotIn(BaseModel):
    date: date
    post_id: int
    shift_id: int
    staff_id: int
    substitute: bool = False
    note: str = Field(default="", max_length=160)


def _slot_check(db: Session, ctx: Ctx, body: SlotIn) -> None:
    p, sh, s = db.get(Post, body.post_id), db.get(ShiftDef, body.shift_id), db.get(Staff, body.staff_id)
    if not p or p.property_id != ctx.property.id or not p.active:
        raise HTTPException(422, "Unknown post")
    if not sh or sh.property_id != ctx.property.id or not sh.active:
        raise HTTPException(422, "Unknown shift")
    if not s or s.property_id != ctx.property.id or s.status != "active":
        raise HTTPException(422, "Unknown or inactive staff")
    if p.shift_ids and sh.id not in p.shift_ids:
        raise HTTPException(422, "This post is not staffed on that shift")


def _add_slot(db: Session, ctx: Ctx, body: SlotIn, status: str = "planned") -> RosterSlot:
    _slot_check(db, ctx, body)
    if db.scalar(select(RosterSlot.id).where(RosterSlot.post_id == body.post_id, RosterSlot.shift_id == body.shift_id, RosterSlot.day == body.date, RosterSlot.staff_id == body.staff_id)):
        raise HTTPException(409, "This person is already on that slot")
    s = RosterSlot(property_id=ctx.property.id, day=body.date, post_id=body.post_id, shift_id=body.shift_id, staff_id=body.staff_id, status=status, substitute=body.substitute, note=body.note)
    db.add(s)
    db.flush()
    return s


def _warn_for(db: Session, ctx: Ctx, staff_id: int, d: date) -> list[dict]:
    hours = {s.id: shift_hours(s) for s in _shifts(db, ctx)}
    slots = [s for s in _week_slots(db, ctx, d - timedelta(days=6), d + timedelta(days=6)) if s.staff_id == staff_id]
    return [w for w in conflicts(slots, hours, d - timedelta(days=6), d + timedelta(days=6)) if w["date"] == d.isoformat()]


@router.post("/roster/slots", status_code=201)
def add_slot(body: SlotIn, ctx: Ctx = Depends(property_ctx), db: Session = Depends(get_db)):
    _gate(ctx)
    ctx.need(*ROSTER_EDIT)
    s = _add_slot(db, ctx, body)
    _log(db, ctx, "roster.assign", "roster", s.id, {"date": body.date.isoformat(), "staff": body.staff_id})
    db.commit()
    return {**_slot(s, _staff_map(db, ctx)), "warnings": _warn_for(db, ctx, s.staff_id, s.day)}


@router.delete("/roster/slots/{slid}", status_code=204)
def delete_slot(slid: int, ctx: Ctx = Depends(property_ctx), db: Session = Depends(get_db)):
    _gate(ctx)
    ctx.need(*ROSTER_EDIT)
    s = db.get(RosterSlot, slid)
    if not s or s.property_id != ctx.property.id:
        raise HTTPException(404, "Not found")
    db.delete(s)
    _log(db, ctx, "roster.unassign", "roster", slid)
    db.commit()


class WeekIn(BaseModel):
    start: date
    apply: bool = True


def _prev_template(db: Session, ctx: Ctx, ws: date) -> list[RosterSlot]:
    return [s for s in _week_slots(db, ctx, ws - timedelta(days=7), ws - timedelta(days=1)) if not s.substitute]


def _fill(db: Session, ctx: Ctx, ws: date, apply: bool, gaps_only: bool) -> dict:
    """Takes last week's people and puts them on the same post, shift and weekday. Auto-fill only fills what is still short and skips anyone who would break a rule."""
    ws = week_start(ws)
    hours = {s.id: shift_hours(s) for s in _shifts(db, ctx)}
    posts = {p.id: p for p in _posts(db, ctx, True)}
    st = _staff_map(db, ctx)
    existing = _week_slots(db, ctx, ws - timedelta(days=6), ws + timedelta(days=12))
    pool = list(existing)
    have = defaultdict(int)
    for s in existing:
        if ws <= s.day <= ws + timedelta(days=6):
            have[(s.day, s.post_id, s.shift_id)] += 1
    made, skipped = [], 0
    for t in _prev_template(db, ctx, ws):
        if t.post_id not in posts or not st.get(t.staff_id, {}).get("active"):
            skipped += 1
            continue
        d = t.day + timedelta(days=7)
        key = (d, t.post_id, t.shift_id)
        if gaps_only and have[key] >= posts[t.post_id].headcount:
            continue
        if any(x.post_id == t.post_id and x.shift_id == t.shift_id and x.day == d and x.staff_id == t.staff_id for x in pool):
            continue
        trial = RosterSlot(property_id=ctx.property.id, day=d, post_id=t.post_id, shift_id=t.shift_id, staff_id=t.staff_id, status="planned")
        if gaps_only and any(w["staff_id"] == t.staff_id and w["date"] == d.isoformat() for w in conflicts([x for x in pool if x.staff_id == t.staff_id] + [trial], hours, d, d)):
            skipped += 1
            continue
        pool.append(trial)
        have[key] += 1
        made.append(trial)
    if apply:
        for m in made:
            db.add(m)
        _log(db, ctx, "roster.copy" if not gaps_only else "roster.autofill", "roster", ws.isoformat(), {"added": len(made)})
        db.commit()
    return {"start": ws.isoformat(), "applied": apply, "added": len(made), "skipped": skipped, "suggestions": [_slot(m, st) for m in made]}


@router.post("/roster/copy")
def copy_week(body: WeekIn, ctx: Ctx = Depends(property_ctx), db: Session = Depends(get_db)):
    """Copy last week: same people, same posts, same shifts. Anything already planned is kept."""
    _gate(ctx)
    ctx.need(*ROSTER_EDIT)
    return _fill(db, ctx, body.start, body.apply, gaps_only=False)


@router.post("/roster/autofill")
def autofill(body: WeekIn, ctx: Ctx = Depends(property_ctx), db: Session = Depends(get_db)):
    _gate(ctx)
    ctx.need(*ROSTER_EDIT)
    return _fill(db, ctx, body.start, body.apply, gaps_only=True)


# ---------------- attendance
class MarkIn(BaseModel):
    status: str = Field(pattern="^(planned|present|late|absent|leave)$")
    note: str = Field(default="", max_length=160)


@router.post("/roster/slots/{slid}/mark")
def mark(slid: int, body: MarkIn, ctx: Ctx = Depends(property_ctx), db: Session = Depends(get_db)):
    _gate(ctx)
    ctx.need(*ROSTER_EDIT)
    s = db.get(RosterSlot, slid)
    if not s or s.property_id != ctx.property.id:
        raise HTTPException(404, "Not found")
    if s.day > _today() + timedelta(days=1):
        raise HTTPException(422, "You cannot mark attendance for a day that has not come")
    s.status, s.note = body.status, body.note or s.note
    s.marked_by, s.marked_at = (ctx.user.id, datetime.now(timezone.utc)) if body.status != "planned" else (None, None)
    _log(db, ctx, "attendance.mark", "roster", s.id, {"status": body.status})
    db.commit()
    return _slot(s, _staff_map(db, ctx))


def _on_duty(db: Session, ctx: Ctx) -> tuple[list[ShiftDef], dict]:
    """Which shift is running now (Dhaka time) and on which date it started, so a night shift after midnight still counts."""
    now_ = datetime.now(DHAKA)
    minutes = now_.hour * 60 + now_.minute
    cur = {}
    for sh in _shifts(db, ctx, True):
        a, b = _hhmm(sh.start), _hhmm(sh.end)
        if a < b and a <= minutes < b:
            cur[sh.id] = now_.date()
        elif a >= b and (minutes >= a):
            cur[sh.id] = now_.date()
        elif a >= b and minutes < b:
            cur[sh.id] = now_.date() - timedelta(days=1)
    return _shifts(db, ctx, True), cur


@router.get("/today")
def today(ctx: Ctx = Depends(property_ctx), db: Session = Depends(get_db)):
    """Today's one-tap attendance list, and who is on duty right now."""
    _gate(ctx)
    ctx.need(*ROSTER_VIEW)
    td = _today()
    shifts, cur = _on_duty(db, ctx)
    st = _staff_map(db, ctx)
    days = {td, *cur.values()}
    slots = [s for s in _week_slots(db, ctx, min(days), td)]
    posts = {p.id: p for p in _posts(db, ctx)}
    items = []
    for s in slots:
        if s.day == td or cur.get(s.shift_id) == s.day:
            d = _slot(s, st)
            d["post"], d["post_bn"] = posts[s.post_id].name, posts[s.post_id].name_bn
            d["now"] = cur.get(s.shift_id) == s.day and s.status not in ("absent", "leave")
            items.append(d)
    return {"date": td.isoformat(), "shifts": [_shift(x) for x in shifts], "items": items, "can_edit": ctx.has(*ROSTER_EDIT)}


@router.get("/duty")
def duty(ctx: Ctx = Depends(property_ctx), db: Session = Depends(get_db)):
    """Read-only strip for every resident: names, posts and the agency name. No phone numbers, no IDs."""
    _gate(ctx)
    td = _today()
    shifts, cur = _on_duty(db, ctx)
    st = _staff_map(db, ctx)
    posts = {p.id: p for p in _posts(db, ctx)}
    sh = {s.id: s for s in shifts}
    out = []
    for s in _week_slots(db, ctx, min({td, *cur.values()}), td):
        if cur.get(s.shift_id) == s.day and s.status not in ("absent", "leave") and s.post_id in posts:
            p, w = posts[s.post_id], st.get(s.staff_id, {})
            out.append({"post": p.name, "post_bn": p.name_bn, "shift": sh[s.shift_id].name, "shift_bn": sh[s.shift_id].name_bn, "start": sh[s.shift_id].start, "end": sh[s.shift_id].end,
                        "name": w.get("name", ""), "name_bn": w.get("name_bn", ""), "agency": w.get("agency", ""), "agency_bn": w.get("agency_bn", "")})
    return {"date": td.isoformat(), "items": out}


# ---------------- replacements
class ReplaceIn(BaseModel):
    slot_id: int
    note: str = Field(default="", max_length=160)


def _repl(r: Replacement, st: dict, posts: dict, shifts: dict, ags: dict) -> dict:
    a = ags.get(r.agency_id)
    return {"id": r.id, "slot_id": r.slot_id, "date": r.day.isoformat(), "post": posts[r.post_id].name if r.post_id in posts else "", "post_bn": posts[r.post_id].name_bn if r.post_id in posts else "",
            "shift": shifts[r.shift_id].name if r.shift_id in shifts else "", "shift_bn": shifts[r.shift_id].name_bn if r.shift_id in shifts else "", "agency": a.name if a else "", "agency_bn": a.name_bn if a else "",
            "absent": st.get(r.absent_staff_id, {}).get("name", ""), "absent_bn": st.get(r.absent_staff_id, {}).get("name_bn", ""), "status": r.status, "substitute": st.get(r.sub_staff_id, {}).get("name", "") if r.sub_staff_id else "",
            "sms_status": r.sms_status, "note": r.note, "at": r.created_at.isoformat()}


def _maps(db: Session, ctx: Ctx):
    return ({p.id: p for p in _posts(db, ctx)}, {s.id: s for s in _shifts(db, ctx)}, {a.id: a for a in db.scalars(select(Agency).where(Agency.property_id == ctx.property.id))})


@router.get("/replacements")
def replacements(page: int = Query(1, ge=1), size: int = Query(10, ge=1, le=100), ctx: Ctx = Depends(property_ctx), db: Session = Depends(get_db)):
    _gate(ctx)
    ctx.need(*AGENCY_VIEW)
    stmt = select(Replacement).where(Replacement.property_id == ctx.property.id)
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = db.scalars(stmt.order_by(Replacement.id.desc()).offset((page - 1) * size).limit(size)).all()
    st, (posts_, shifts_, ags) = _staff_map(db, ctx), _maps(db, ctx)
    return {"items": [_repl(r, st, posts_, shifts_, ags) for r in rows], "total": total, "page": page, "size": size}


@router.post("/replacements", status_code=201)
def ask_replacement(body: ReplaceIn, ctx: Ctx = Depends(property_ctx), db: Session = Depends(get_db)):
    """Records the request and sends an SMS to the agency's contact person."""
    _gate(ctx)
    ctx.need(*ROSTER_EDIT)
    s = db.get(RosterSlot, body.slot_id)
    if not s or s.property_id != ctx.property.id:
        raise HTTPException(404, "Not found")
    if s.status not in ("absent", "leave"):
        raise HTTPException(422, "Mark the person absent or on leave first")
    posts_, shifts_, ags = _maps(db, ctx)
    st = _staff_map(db, ctx)
    aid = st.get(s.staff_id, {}).get("agency_id") or (posts_[s.post_id].agency_id if s.post_id in posts_ else None)
    a = ags.get(aid) if aid else None
    if not a:
        raise HTTPException(422, "This slot does not belong to an agency")
    if db.scalar(select(Replacement.id).where(Replacement.slot_id == s.id, Replacement.status == "requested")):
        raise HTTPException(409, "A replacement is already requested for this slot")
    r = Replacement(property_id=ctx.property.id, slot_id=s.id, agency_id=a.id, day=s.day, post_id=s.post_id, shift_id=s.shift_id, absent_staff_id=s.staff_id, note=body.note, requested_by=ctx.user.id)
    db.add(r)
    db.flush()
    sh, p = shifts_[s.shift_id], posts_[s.post_id]
    m = Message(property_id=ctx.property.id, to_name=a.contact_name or a.name_bn or a.name, to_phone=a.contact_phone, template="roster_replacement", lang="bn", idem_key=f"rosterrepl{r.id}",
                body=f"{ctx.property.name_bn or ctx.property.name}: {s.day.isoformat()} {sh.name_bn or sh.name} ({sh.start}-{sh.end}), {p.name_bn or p.name} পোস্টে বদলি কর্মী পাঠান। অনুপস্থিত: {st[s.staff_id]['name_bn'] or st[s.staff_id]['name']}।")
    db.add(m)
    deliver(db, ctx.property.org_id, m)
    r.sms_status = m.status
    _log(db, ctx, "roster.replacement", "agency", a.id, {"slot": s.id})
    db.commit()
    return _repl(r, st, posts_, shifts_, ags)


class FulfilIn(BaseModel):
    staff_id: int | None = None
    new: AgencyStaffIn | None = None


@router.post("/replacements/{rid}/fulfil")
def fulfil(rid: int, body: FulfilIn, ctx: Ctx = Depends(property_ctx), db: Session = Depends(get_db)):
    """The agency sent someone: pick an existing person or add a new substitute. The substitute is put on the same slot, marked as such."""
    _gate(ctx)
    ctx.need(*ROSTER_EDIT)
    r = db.get(Replacement, rid)
    if not r or r.property_id != ctx.property.id:
        raise HTTPException(404, "Not found")
    if r.status != "requested":
        raise HTTPException(422, "Already fulfilled")
    a = db.get(Agency, r.agency_id)
    if body.new:
        sid = _make_staff(db, ctx, a, body.new.model_copy(update={"substitute": True})).id
    elif body.staff_id:
        sid = body.staff_id
    else:
        raise HTTPException(422, "Choose a person or add a new substitute")
    slot = _add_slot(db, ctx, SlotIn(date=r.day, post_id=r.post_id, shift_id=r.shift_id, staff_id=sid, substitute=True, note="substitute"), status="planned")
    r.status, r.sub_staff_id = "fulfilled", sid
    _log(db, ctx, "roster.substitute", "roster", slot.id, {"replacement": r.id})
    db.commit()
    st = _staff_map(db, ctx)
    return {**_repl(r, st, *_maps(db, ctx)), "slot": _slot(slot, st)}


# ---------------- summary and bill check
def _period(period: str) -> tuple[date, date]:
    try:
        y, m = int(period[:4]), int(period[5:7])
        assert len(period) == 7 and period[4] == "-" and 1 <= m <= 12
    except Exception:
        raise HTTPException(422, "Period must look like 2026-10")
    first = date(y, m, 1)
    return first, (date(y + (m == 12), m % 12 + 1, 1) - timedelta(days=1))


def shortfall(db: Session, ctx: Ctx, agency: Agency, period: str) -> dict:
    """Missing person-shifts for an agency's posts. Only days where attendance was taken count, so an unmarked day never costs the agency money."""
    lo, hi = _period(period)
    hi = min(hi, _today())
    if hi < lo:
        return {"units": 0, "days": []}
    slots = _week_slots(db, ctx, lo, hi)
    closed = {s.day for s in slots if s.status != "planned"}
    present = defaultdict(int)
    for s in slots:
        if s.status in ("present", "late"):
            present[(s.day, s.post_id, s.shift_id)] += 1
    shifts_ = [s.id for s in _shifts(db, ctx, True)]
    rows, units = [], 0
    for p in _posts(db, ctx, True):
        if p.agency_id != agency.id:
            continue
        for d in sorted(closed):
            for shid in (p.shift_ids or shifts_):
                short = max(0, p.headcount - present[(d, p.id, shid)])
                if short:
                    units += short
                    rows.append({"date": d.isoformat(), "post_id": p.id, "shift_id": shid, "required": p.headcount, "present": present[(d, p.id, shid)], "short": short})
    return {"units": units, "days": rows}


def _rate(db: Session, ctx: Ctx) -> int:
    row = db.scalar(select(AgencySetting).where(AgencySetting.property_id == ctx.property.id))
    return row.shortfall_rate if row else 40000


def expected_bill(db: Session, ctx: Ctx, a: Agency, period: str) -> dict:
    sf = shortfall(db, ctx, a, period)
    n_posts = db.scalar(select(func.count()).select_from(Post).where(Post.agency_id == a.id, Post.active)) or 0
    contract = a.monthly_fee if a.fee_mode == "flat" else a.monthly_fee * n_posts
    rate = _rate(db, ctx)
    deduction = min(contract, sf["units"] * rate)
    return {"agency_id": a.id, "period": period, "fee_mode": a.fee_mode, "monthly_fee": a.monthly_fee, "posts": n_posts, "contract": contract, "rate": rate, "shortfall_units": sf["units"],
            "deduction": deduction, "expected": contract - deduction, "days": sf["days"]}


@router.get("/attendance/summary")
def attendance_summary(period: str, ctx: Ctx = Depends(property_ctx), db: Session = Depends(get_db)):
    _gate(ctx)
    ctx.need(*AGENCY_VIEW)
    lo, hi = _period(period)
    slots = _week_slots(db, ctx, lo, hi)
    st = _staff_map(db, ctx)
    per = defaultdict(lambda: {"scheduled": 0, "present": 0, "late": 0, "absent": 0, "leave": 0})
    for s in slots:
        if st.get(s.staff_id, {}).get("agency_id") is None:
            continue
        r = per[s.staff_id]
        r["scheduled"] += 1
        if s.status in r:
            r[s.status] += 1
    staff_rows = [{"staff_id": i, "name": st[i]["name"], "name_bn": st[i]["name_bn"], "agency_id": st[i]["agency_id"], "agency": st[i]["agency"], "emp_no": st[i]["emp_no"], "substitute": st[i]["substitute"], **v}
                  for i, v in per.items()]
    agencies_ = []
    for a in db.scalars(select(Agency).where(Agency.property_id == ctx.property.id).order_by(Agency.name)):
        mine = [r for r in staff_rows if r["agency_id"] == a.id]
        sf = shortfall(db, ctx, a, period)
        agencies_.append({"agency_id": a.id, "name": a.name, "name_bn": a.name_bn, "scheduled": sum(r["scheduled"] for r in mine), "present": sum(r["present"] for r in mine), "late": sum(r["late"] for r in mine),
                          "absent": sum(r["absent"] for r in mine), "leave": sum(r["leave"] for r in mine), "shortfall_units": sf["units"], "shortfall_days": len({d["date"] for d in sf["days"]})})
    return {"period": period, "staff": sorted(staff_rows, key=lambda r: (r["agency"], r["name"])), "agencies": agencies_}


@router.get("/bills/check")
def bill_check(agency_id: int, period: str, ctx: Ctx = Depends(property_ctx), db: Session = Depends(get_db)):
    _gate(ctx)
    ctx.need(*BILL_VIEW)
    return expected_bill(db, ctx, _agency(db, ctx, agency_id), period)


class SettingIn(BaseModel):
    shortfall_rate: int = Field(ge=0, le=10**9)


@router.get("/settings")
def get_settings(ctx: Ctx = Depends(property_ctx), db: Session = Depends(get_db)):
    _gate(ctx)
    ctx.need(*BILL_VIEW)
    return {"shortfall_rate": _rate(db, ctx)}


@router.put("/settings")
def put_settings(body: SettingIn, ctx: Ctx = Depends(property_ctx), db: Session = Depends(get_db)):
    _gate(ctx)
    ctx.need(*(AGENCY_EDIT | {"TREASURER"}))
    row = db.scalar(select(AgencySetting).where(AgencySetting.property_id == ctx.property.id))
    if row:
        row.shortfall_rate = body.shortfall_rate
    else:
        db.add(AgencySetting(property_id=ctx.property.id, shortfall_rate=body.shortfall_rate))
    _log(db, ctx, "agency.settings", "agency", ctx.property.id, {"rate": body.shortfall_rate})
    db.commit()
    return {"shortfall_rate": body.shortfall_rate}


def _bill(b: AgencyBill, ags: dict, exps: dict) -> dict:
    a, e = ags.get(b.agency_id), exps.get(b.expense_id)
    return {"id": b.id, "agency_id": b.agency_id, "agency": a.name if a else "", "agency_bn": a.name_bn if a else "", "period": b.period, "number": b.number, "amount": b.amount, "expected": b.expected,
            "shortfall_units": b.shortfall_units, "deduction": b.deduction, "variance": b.amount - b.expected, "note": b.note, "expense_id": b.expense_id,
            "status": e.status if e else "", "approvals": len(e.approvals) if e else 0, "approvals_needed": (2 if e.needs_two else 1) if e else 1, "at": b.created_at.isoformat()}


@router.get("/bills")
def bills(page: int = Query(1, ge=1), size: int = Query(10, ge=1, le=100), ctx: Ctx = Depends(property_ctx), db: Session = Depends(get_db)):
    _gate(ctx)
    ctx.need(*BILL_VIEW)
    stmt = select(AgencyBill).where(AgencyBill.property_id == ctx.property.id)
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = db.scalars(stmt.order_by(AgencyBill.period.desc(), AgencyBill.id.desc()).offset((page - 1) * size).limit(size)).all()
    ags = {a.id: a for a in db.scalars(select(Agency).where(Agency.property_id == ctx.property.id))}
    exps = {e.id: e for e in db.scalars(select(Expense).where(Expense.id.in_([b.expense_id for b in rows if b.expense_id])))}
    return {"items": [_bill(b, ags, exps) for b in rows], "total": total, "page": page, "size": size}


class BillIn(BaseModel):
    agency_id: int
    period: str
    number: str = Field(min_length=1, max_length=60)
    amount: int = Field(gt=0, le=10**11)
    note: str = Field(default="", max_length=200)


@router.post("/bills", status_code=201)
def add_bill(body: BillIn, ctx: Ctx = Depends(property_ctx), db: Session = Depends(get_db)):
    """Records the agency's invoice next to what the system expects, and raises a normal expense so approval (two people above BDT 50,000) and the ledger work as usual."""
    _gate(ctx)
    ctx.need(*BILL)
    a = _agency(db, ctx, body.agency_id)
    chk = expected_bill(db, ctx, a, body.period)
    old = db.scalar(select(AgencyBill).where(AgencyBill.agency_id == a.id, AgencyBill.period == body.period))
    if old:
        e0 = db.get(Expense, old.expense_id) if old.expense_id else None
        if e0 and e0.status != "rejected":
            raise HTTPException(409, "A bill for this agency and month is already recorded")
        db.delete(old)
        db.flush()
    e = Expense(property_id=ctx.property.id, category="services", vendor_id=a.vendor_id, title=f"{a.name} invoice {body.number} ({body.period})"[:160], amount=body.amount, spent_on=_today(),
                needs_two=body.amount > DUAL_ABOVE, requested_by=ctx.user.id)
    db.add(e)
    db.flush()
    b = AgencyBill(property_id=ctx.property.id, agency_id=a.id, period=body.period, number=body.number, amount=body.amount, expected=chk["expected"], shortfall_units=chk["shortfall_units"],
                   deduction=chk["deduction"], note=body.note, expense_id=e.id, created_by=ctx.user.id)
    db.add(b)
    db.flush()
    _log(db, ctx, "agency.bill", "agency", a.id, {"period": body.period, "amount": body.amount, "expense": e.id})
    audit(db, user_id=ctx.user.id, org_id=ctx.property.org_id, property_id=ctx.property.id, action="expense.request", entity="expense", entity_id=e.id, meta={"amount": e.amount, "category": e.category})
    db.commit()
    return _bill(b, {a.id: a}, {e.id: e})
