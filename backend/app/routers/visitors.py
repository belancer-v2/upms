"""M15 Visitor log: the guard desk records arrivals, residents approve or deny, passes and frequent visitors skip the wait."""
import hashlib
import hmac
import secrets
from datetime import date, datetime, timedelta, timezone

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session

from .. import config
from ..audit import audit
from ..db import get_db
from ..services.storage import get_storage
from ..deps import Ctx, property_ctx
from ..models.core import AuditLog, Membership, now
from ..models.property import Unit
from ..models.visitors import FrequentVisitor, Visit, VisitorNotice, VisitorPass, VisitorSetting
from ..permissions import COMMITTEE, MANAGE, RESIDENT

router = APIRouter(prefix="/api/visitors", tags=["visitors"])
BD = timezone(timedelta(hours=6))                       # Bangladesh time: "today" means the Dhaka day
PURPOSES = ("guest", "delivery", "courier", "service", "cab", "official", "other")
FREQ_ROLES = ("maid", "driver", "tutor", "cook", "other")
STATUSES = ("waiting", "approved", "denied", "in", "out", "cancelled")
ACTIVE = ("waiting", "approved", "in")
GATE = MANAGE | {"GUARD", "CARETAKER"}
READ_ALL = GATE | COMMITTEE
SEE_PHONE = MANAGE | COMMITTEE
SEE_PHOTO = MANAGE | {"GUARD", "CARETAKER"}
SETTINGS_EDIT = MANAGE | {"PRESIDENT", "SECRETARY"}
MAX_PHOTO = 2 * 1024 * 1024
PHOTO_TYPES = {"image/jpeg": "jpg", "image/png": "png"}
PASS_MAX_DAYS = 7
PASS_MAX_ACTIVE = 20
FAIL_LIMIT = 8                                           # wrong pass codes per guard per 10 minutes
PURPOSE_PAT = "^(" + "|".join(PURPOSES) + ")$"
FREQ_PURPOSE = {"maid": "service", "cook": "service", "driver": "cab", "tutor": "other", "other": "other"}


def _gate(ctx: Ctx) -> None:
    ctx.feature("visitor")


def _aware(dt: datetime | None) -> datetime | None:
    return dt.replace(tzinfo=timezone.utc) if dt and dt.tzinfo is None else dt


def _iso(dt: datetime | None) -> str | None:
    dt = _aware(dt)
    return dt.isoformat() if dt else None


def _today() -> date:
    return datetime.now(BD).date()


def _day_start(d: date) -> datetime:
    return datetime(d.year, d.month, d.day, tzinfo=BD).astimezone(timezone.utc)


def _settings(db: Session, pid: int) -> VisitorSetting:
    s = db.scalar(select(VisitorSetting).where(VisitorSetting.property_id == pid))
    return s or VisitorSetting(property_id=pid, page_size=10, overstay_hours=12)


def _units(db: Session, ctx: Ctx) -> dict[int, str]:
    return {u.id: u.number for u in db.scalars(select(Unit).where(Unit.property_id == ctx.property.id))}


def _my_units(ctx: Ctx) -> set[int]:
    return set(ctx.unit_ids) if ctx.has(*RESIDENT) and not ctx.saas_staff else set()


def _is_overstay(v: Visit, hours: int) -> bool:
    return v.status == "in" and v.in_at is not None and now() - _aware(v.in_at) > timedelta(hours=hours)


def _row(v: Visit, units: dict, ctx: Ctx, hours: int) -> dict:
    return {"id": v.id, "unit_id": v.unit_id, "unit": units.get(v.unit_id, ""), "name": v.name, "phone": v.phone if ctx.has(*SEE_PHONE) else "",
            "purpose": v.purpose, "people": v.people, "vehicle": v.vehicle, "kind": v.kind, "status": v.status, "via": v.decision_via, "note": v.note if ctx.has(*GATE, *COMMITTEE) else "",
            "created_at": _iso(v.created_at), "decided_at": _iso(v.decided_at), "in_at": _iso(v.in_at), "out_at": _iso(v.out_at),
            "overstay": _is_overstay(v, hours), "photo": bool(v.photo_file) and ctx.has(*SEE_PHOTO)}


def _resident_row(v: Visit, units: dict) -> dict:
    """What a resident sees about a visitor to their own flat: no guard notes. They can see the visitor's photo (decision: residents may see photos of visitors to their own flat)."""
    return {"id": v.id, "unit_id": v.unit_id, "unit": units.get(v.unit_id, ""), "name": v.name, "phone": v.phone, "purpose": v.purpose, "people": v.people, "vehicle": v.vehicle,
            "kind": v.kind, "status": v.status, "via": v.decision_via, "created_at": _iso(v.created_at), "decided_at": _iso(v.decided_at), "in_at": _iso(v.in_at), "out_at": _iso(v.out_at),
            "can_decide": v.status == "waiting", "photo": bool(v.photo_file)}


def _log(db: Session, ctx: Ctx, action: str, entity: str, eid, meta: dict | None = None) -> None:
    audit(db, user_id=ctx.user.id, org_id=ctx.property.org_id, property_id=ctx.property.id, action=action, entity=entity, entity_id=eid, meta=meta or {})


def _unit(db: Session, ctx: Ctx, unit_id: int) -> Unit:
    u = db.get(Unit, unit_id)
    if not u or u.property_id != ctx.property.id:
        raise HTTPException(404, "Flat not found")
    return u


def _visit(db: Session, ctx: Ctx, vid: int) -> Visit:
    v = db.get(Visit, vid)
    if not v or v.property_id != ctx.property.id:
        raise HTTPException(404, "Not found")
    return v


def _notify(db: Session, ctx: Ctx, v: Visit, kind: str) -> int:
    """One entry per resident login (owner, tenant, owner's representative) of the flat. Returns how many people were notified."""
    ms = db.scalars(select(Membership).where(Membership.org_id == ctx.property.org_id, Membership.unit_id == v.unit_id, Membership.role.in_(list(RESIDENT)))).all()
    users = {m.user_id for m in ms if m.property_id in (ctx.property.id, None)}
    for uid in sorted(users):
        db.add(VisitorNotice(property_id=ctx.property.id, user_id=uid, unit_id=v.unit_id, visit_id=v.id, kind=kind))
    return len(users)


# ---------------------------------------------------------------- settings, flats

class SettingsIn(BaseModel):
    page_size: int = Field(ge=5, le=100)
    overstay_hours: int = Field(default=12, ge=1, le=72)


@router.get("/settings")
def get_settings(ctx: Ctx = Depends(property_ctx), db: Session = Depends(get_db)):
    _gate(ctx)
    s = _settings(db, ctx.property.id)
    return {"page_size": s.page_size, "overstay_hours": s.overstay_hours, "can_edit": ctx.has(*SETTINGS_EDIT)}


@router.put("/settings")
def put_settings(body: SettingsIn, ctx: Ctx = Depends(property_ctx), db: Session = Depends(get_db)):
    _gate(ctx)
    ctx.need(*SETTINGS_EDIT)
    s = db.scalar(select(VisitorSetting).where(VisitorSetting.property_id == ctx.property.id))
    old = {"page_size": s.page_size, "overstay_hours": s.overstay_hours} if s else {}
    if s:
        s.page_size, s.overstay_hours = body.page_size, body.overstay_hours
    else:
        db.add(VisitorSetting(property_id=ctx.property.id, page_size=body.page_size, overstay_hours=body.overstay_hours))
    _log(db, ctx, "visitor.settings", "visitor_setting", ctx.property.id, {"from": old, "to": body.model_dump()})
    db.commit()
    return {"page_size": body.page_size, "overstay_hours": body.overstay_hours, "can_edit": True}


@router.get("/flats")
def flats(q: str = "", ctx: Ctx = Depends(property_ctx), db: Session = Depends(get_db)):
    """Flat picker. The gate searches by number (best 30 matches); a resident gets their own flats."""
    _gate(ctx)
    stmt = select(Unit).where(Unit.property_id == ctx.property.id)
    if not ctx.has(*READ_ALL):
        mine = _my_units(ctx)
        if not mine:
            raise HTTPException(403, "Your role cannot do this")
        stmt = stmt.where(Unit.id.in_(mine))
    if q.strip():
        stmt = stmt.where(Unit.number.ilike(f"%{q.strip()}%"))
    return [{"id": u.id, "number": u.number, "block": u.block, "floor": u.floor} for u in db.scalars(stmt.order_by(Unit.number).limit(30))]


# ---------------------------------------------------------------- the gate: record arrivals

class VisitIn(BaseModel):
    unit_id: int
    name: str = Field(min_length=2, max_length=120)
    phone: str = Field(default="", max_length=32)
    purpose: str = Field(pattern=PURPOSE_PAT)
    people: int = Field(default=1, ge=1, le=50)
    vehicle: str = Field(default="", max_length=32)


@router.post("/visits", status_code=201)
def arrive(body: VisitIn, ctx: Ctx = Depends(property_ctx), db: Session = Depends(get_db)):
    _gate(ctx)
    ctx.need(*GATE)
    _unit(db, ctx, body.unit_id)
    v = Visit(property_id=ctx.property.id, unit_id=body.unit_id, name=body.name.strip(), phone=body.phone.strip(), purpose=body.purpose, people=body.people,
              vehicle=body.vehicle.strip().upper(), kind="walkin", status="waiting", created_by=ctx.user.id)
    db.add(v)
    db.flush()
    n = _notify(db, ctx, v, "ask")
    db.commit()
    return {**_row(v, _units(db, ctx), ctx, _settings(db, ctx.property.id).overstay_hours), "notified": n}


class DeliveryIn(BaseModel):
    unit_id: int
    name: str = Field(default="Delivery", max_length=120)
    vehicle: str = Field(default="", max_length=32)


@router.post("/visits/delivery", status_code=201)
def delivery(body: DeliveryIn, ctx: Ctx = Depends(property_ctx), db: Session = Depends(get_db)):
    """One tap: the flat is told, nobody has to approve, and the delivery person is logged as inside."""
    _gate(ctx)
    ctx.need(*GATE)
    _unit(db, ctx, body.unit_id)
    t = now()
    v = Visit(property_id=ctx.property.id, unit_id=body.unit_id, name=body.name.strip() or "Delivery", purpose="delivery", people=1, vehicle=body.vehicle.strip().upper(), kind="delivery",
              status="in", decision_via="delivery", decided_at=t, in_at=t, created_by=ctx.user.id, created_at=t)
    db.add(v)
    db.flush()
    n = _notify(db, ctx, v, "info")
    db.commit()
    return {**_row(v, _units(db, ctx), ctx, _settings(db, ctx.property.id).overstay_hours), "notified": n}


@router.post("/visits/{vid}/in")
def mark_in(vid: int, ctx: Ctx = Depends(property_ctx), db: Session = Depends(get_db)):
    _gate(ctx)
    ctx.need(*GATE)
    v = _visit(db, ctx, vid)
    if v.status != "approved":
        raise HTTPException(409, "Only an approved visitor can go in" if v.status != "waiting" else "Still waiting for the resident to approve")
    v.status, v.in_at = "in", now()
    db.commit()
    return _row(v, _units(db, ctx), ctx, _settings(db, ctx.property.id).overstay_hours)


@router.post("/visits/{vid}/out")
def mark_out(vid: int, ctx: Ctx = Depends(property_ctx), db: Session = Depends(get_db)):
    _gate(ctx)
    ctx.need(*GATE)
    v = _visit(db, ctx, vid)
    if v.status != "in":
        raise HTTPException(409, "This visitor is not inside")
    v.status, v.out_at = "out", now()
    db.commit()
    return _row(v, _units(db, ctx), ctx, _settings(db, ctx.property.id).overstay_hours)


@router.post("/visits/{vid}/cancel")
def cancel(vid: int, ctx: Ctx = Depends(property_ctx), db: Session = Depends(get_db)):
    _gate(ctx)
    ctx.need(*GATE)
    v = _visit(db, ctx, vid)
    if v.status not in ("waiting", "approved"):
        raise HTTPException(409, "This entry can no longer be cancelled")
    old, v.status = v.status, "cancelled"
    _log(db, ctx, "visitor.cancel", "visit", v.id, {"from": old})
    db.commit()
    return _row(v, _units(db, ctx), ctx, _settings(db, ctx.property.id).overstay_hours)


class OverrideIn(BaseModel):
    note: str = Field(min_length=3, max_length=200)


@router.post("/visits/{vid}/override")
def override(vid: int, body: OverrideIn, ctx: Ctx = Depends(property_ctx), db: Session = Depends(get_db)):
    """The gate lets a visitor in without the resident's answer (resident not reachable). A visitor the resident DENIED can only be overridden by the caretaker or an admin. Always audited."""
    _gate(ctx)
    ctx.need(*GATE)
    v = _visit(db, ctx, vid)
    if v.status not in ("waiting", "denied"):
        raise HTTPException(409, "Nothing to override")
    if v.status == "denied" and not ctx.has(*MANAGE, "CARETAKER"):
        raise HTTPException(403, "Only the caretaker or an admin can override a denied visitor")
    old = v.status
    v.status, v.decision_via, v.decided_by, v.decided_at, v.note = "approved", "override", ctx.user.id, now(), body.note.strip()
    _log(db, ctx, "visitor.override", "visit", v.id, {"from": old, "note": v.note, "unit_id": v.unit_id})
    _notify(db, ctx, v, "info")
    db.commit()
    return _row(v, _units(db, ctx), ctx, _settings(db, ctx.property.id).overstay_hours)


@router.post("/visits/{vid}/photo")
async def upload_photo(vid: int, file: UploadFile = File(...), ctx: Ctx = Depends(property_ctx), db: Session = Depends(get_db)):
    _gate(ctx)
    ctx.need(*GATE)
    v = _visit(db, ctx, vid)
    if file.content_type not in PHOTO_TYPES:
        raise HTTPException(422, "Please upload a JPG or PNG photo")
    data = await file.read(MAX_PHOTO + 1)
    if len(data) > MAX_PHOTO:
        raise HTTPException(413, "The photo is larger than 2 MB")
    real = "image/png" if data.startswith(b"\x89PNG\r\n\x1a\n") else "image/jpeg" if data.startswith(b"\xff\xd8\xff") else None
    if real != file.content_type:
        raise HTTPException(422, "The file is not a valid JPG or PNG photo")
    folder = f"visitors/{ctx.property.id}"
    name = f"v{v.id}_{secrets.token_hex(6)}.{PHOTO_TYPES[real]}"
    get_storage().put(f"{folder}/{name}", data, real)
    if v.photo_file:
        get_storage().delete(f"{folder}/{v.photo_file}")
    v.photo_file, v.photo_type = name, real
    db.commit()
    return _row(v, _units(db, ctx), ctx, _settings(db, ctx.property.id).overstay_hours)


@router.get("/visits/{vid}/photo")
def photo(vid: int, ctx: Ctx = Depends(property_ctx), db: Session = Depends(get_db)):
    _gate(ctx)
    v = _visit(db, ctx, vid)
    if not ctx.has(*SEE_PHOTO) and v.unit_id not in _my_units(ctx):
        raise HTTPException(403, "Your role cannot do this")   # residents see photos of visitors to their own flat only
    key = f"visitors/{ctx.property.id}/{v.photo_file}" if v.photo_file else None
    if not key or not get_storage().exists(key):
        raise HTTPException(404, "No photo")
    return get_storage().serve(key, v.photo_type, headers={"Cache-Control": "private, max-age=3600"})


# ---------------------------------------------------------------- the gate board, the log and the reports

def _counts(db: Session, ctx: Ctx) -> dict:
    hours = _settings(db, ctx.property.id).overstay_hours
    base = select(Visit).where(Visit.property_id == ctx.property.id)
    inside = db.scalars(base.where(Visit.status == "in")).all()
    over = [v for v in inside if _is_overstay(v, hours)]
    return {"today": db.scalar(select(func.count()).select_from(base.where(Visit.created_at >= _day_start(_today())).subquery())) or 0,
            "inside": len(inside), "waiting": db.scalar(select(func.count()).select_from(base.where(Visit.status == "waiting").subquery())) or 0,
            "overstay": len(over), "overstay_vehicles": sum(1 for v in over if v.vehicle), "vehicles_inside": sum(1 for v in inside if v.vehicle), "overstay_hours": hours}


@router.get("/summary")
def summary(ctx: Ctx = Depends(property_ctx), db: Session = Depends(get_db)):
    _gate(ctx)
    ctx.need(*READ_ALL)
    return _counts(db, ctx)


@router.get("/board")
def board(ctx: Ctx = Depends(property_ctx), db: Session = Depends(get_db)):
    """What the guard watches (the screen polls it every 10 seconds): waiting, approved and still inside."""
    _gate(ctx)
    ctx.need(*GATE)
    hours = _settings(db, ctx.property.id).overstay_hours
    # a visitor the resident denied stays on the board for an hour, so the guard sees the answer
    recent_no = and_(Visit.status == "denied", Visit.decided_at >= now() - timedelta(hours=1))
    rows = db.scalars(select(Visit).where(Visit.property_id == ctx.property.id, or_(Visit.status.in_(ACTIVE), recent_no)).order_by(Visit.created_at.desc(), Visit.id.desc()).limit(200)).all()
    units = _units(db, ctx)
    out = [_row(v, units, ctx, hours) for v in rows]
    return {"waiting": [r for r in out if r["status"] == "waiting"], "approved": [r for r in out if r["status"] == "approved"], "inside": [r for r in out if r["status"] == "in"],
            "denied": [r for r in out if r["status"] == "denied"], "counts": _counts(db, ctx)}


@router.get("/visits")
def visits(q: str = "", flat: str = "", date_from: date | None = None, date_to: date | None = None, status: str = "", purpose: str = "", inside: bool = False, overstay: bool = False,
           page: int = Query(1, ge=1), size: int | None = Query(None, ge=1, le=100), ctx: Ctx = Depends(property_ctx), db: Session = Depends(get_db)):
    """The log. The guard sees today's log plus anyone still active; admin and committee search every day."""
    _gate(ctx)
    ctx.need(*READ_ALL)
    s = _settings(db, ctx.property.id)
    size = size or s.page_size
    stmt = select(Visit).where(Visit.property_id == ctx.property.id)
    if not ctx.has(*MANAGE, *COMMITTEE, "CARETAKER"):
        stmt = stmt.where(or_(Visit.created_at >= _day_start(_today()), Visit.status.in_(ACTIVE)))
    else:
        if date_from:
            stmt = stmt.where(Visit.created_at >= _day_start(date_from))
        if date_to:
            stmt = stmt.where(Visit.created_at < _day_start(date_to + timedelta(days=1)))
    if q.strip():
        stmt = stmt.where(or_(Visit.name.ilike(f"%{q.strip()}%"), Visit.vehicle.ilike(f"%{q.strip()}%")))
    if flat.strip():
        stmt = stmt.where(Visit.unit_id.in_(select(Unit.id).where(Unit.property_id == ctx.property.id, Unit.number.ilike(f"%{flat.strip()}%"))))
    if status in STATUSES:
        stmt = stmt.where(Visit.status == status)
    if purpose in PURPOSES:
        stmt = stmt.where(Visit.purpose == purpose)
    if inside or overstay:
        stmt = stmt.where(Visit.status == "in")
    if overstay:
        stmt = stmt.where(Visit.in_at < now() - timedelta(hours=s.overstay_hours))
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = db.scalars(stmt.order_by(Visit.created_at.desc(), Visit.id.desc()).offset((page - 1) * size).limit(size)).all()
    units = _units(db, ctx)
    return {"items": [_row(v, units, ctx, s.overstay_hours) for v in rows], "total": total, "page": page, "size": size}


# ---------------------------------------------------------------- residents

def _resident(ctx: Ctx) -> set[int]:
    mine = _my_units(ctx)
    if not mine:
        raise HTTPException(403, "Your role cannot do this")
    return mine


@router.get("/mine")
def mine(q: str = "", status: str = "", page: int = Query(1, ge=1), size: int | None = Query(None, ge=1, le=100), ctx: Ctx = Depends(property_ctx), db: Session = Depends(get_db)):
    _gate(ctx)
    units_ids = _resident(ctx)
    size = size or _settings(db, ctx.property.id).page_size
    stmt = select(Visit).where(Visit.property_id == ctx.property.id, Visit.unit_id.in_(units_ids))
    if q.strip():
        stmt = stmt.where(Visit.name.ilike(f"%{q.strip()}%"))
    if status in STATUSES:
        stmt = stmt.where(Visit.status == status)
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = db.scalars(stmt.order_by(Visit.created_at.desc(), Visit.id.desc()).offset((page - 1) * size).limit(size)).all()
    units = _units(db, ctx)
    return {"items": [_resident_row(v, units) for v in rows], "total": total, "page": page, "size": size}


@router.get("/mine/pending")
def pending(ctx: Ctx = Depends(property_ctx), db: Session = Depends(get_db)):
    """Visitors at the gate for my flat who wait for an answer, and my unread count. The page polls it."""
    _gate(ctx)
    units_ids = _resident(ctx)
    rows = db.scalars(select(Visit).where(Visit.property_id == ctx.property.id, Visit.unit_id.in_(units_ids), Visit.status == "waiting").order_by(Visit.created_at, Visit.id).limit(50)).all()
    unread = db.scalar(select(func.count()).select_from(VisitorNotice).where(VisitorNotice.user_id == ctx.user.id, VisitorNotice.property_id == ctx.property.id, VisitorNotice.read_at.is_(None))) or 0
    units = _units(db, ctx)
    return {"waiting": [_resident_row(v, units) for v in rows], "unread": unread}


@router.get("/mine/notifications")
def notifications(page: int = Query(1, ge=1), size: int | None = Query(None, ge=1, le=100), ctx: Ctx = Depends(property_ctx), db: Session = Depends(get_db)):
    _gate(ctx)
    _resident(ctx)
    size = size or _settings(db, ctx.property.id).page_size
    stmt = select(VisitorNotice).where(VisitorNotice.user_id == ctx.user.id, VisitorNotice.property_id == ctx.property.id)
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    ns = db.scalars(stmt.order_by(VisitorNotice.created_at.desc(), VisitorNotice.id.desc()).offset((page - 1) * size).limit(size)).all()
    vs = {v.id: v for v in db.scalars(select(Visit).where(Visit.id.in_([n.visit_id for n in ns] or [-1])))}
    units = _units(db, ctx)
    return {"items": [{"id": n.id, "kind": n.kind, "at": _iso(n.created_at), "read": n.read_at is not None, "visit": _resident_row(vs[n.visit_id], units)} for n in ns if n.visit_id in vs],
            "total": total, "page": page, "size": size}


@router.post("/mine/notifications/read")
def read_all(ctx: Ctx = Depends(property_ctx), db: Session = Depends(get_db)):
    _gate(ctx)
    _resident(ctx)
    for n in db.scalars(select(VisitorNotice).where(VisitorNotice.user_id == ctx.user.id, VisitorNotice.property_id == ctx.property.id, VisitorNotice.read_at.is_(None))):
        n.read_at = now()
    db.commit()
    return {"ok": True}


class DecisionIn(BaseModel):
    approve: bool


@router.post("/visits/{vid}/decision")
def decide(vid: int, body: DecisionIn, ctx: Ctx = Depends(property_ctx), db: Session = Depends(get_db)):
    _gate(ctx)
    mine_ids = _resident(ctx)
    v = _visit(db, ctx, vid)
    if v.unit_id not in mine_ids:
        raise HTTPException(404, "Not found")                       # another flat's visitor does not exist for you
    if v.status != "waiting":
        raise HTTPException(409, "This visitor has already been answered")
    v.status, v.decided_by, v.decided_at, v.decision_via = ("approved" if body.approve else "denied"), ctx.user.id, now(), "resident"
    if not body.approve:
        _log(db, ctx, "visitor.deny", "visit", v.id, {"unit_id": v.unit_id, "name": v.name})
    for n in db.scalars(select(VisitorNotice).where(VisitorNotice.visit_id == v.id, VisitorNotice.user_id == ctx.user.id, VisitorNotice.read_at.is_(None))):
        n.read_at = now()
    db.commit()
    return _resident_row(v, _units(db, ctx))


# ---------------------------------------------------------------- pre-approved passes

def _hash(pid: int, code: str) -> str:
    return hmac.new(config.SECRET_KEY.encode(), f"visitor-pass:{pid}:{code}".encode(), hashlib.sha256).hexdigest()


def _pass_status(p: VisitorPass) -> str:
    if p.status == "active" and now() > _aware(p.valid_to):
        return "expired"
    return p.status


def _pass_row(p: VisitorPass, units: dict) -> dict:
    return {"id": p.id, "unit_id": p.unit_id, "unit": units.get(p.unit_id, ""), "name": p.name, "purpose": p.purpose, "people": p.people, "vehicle": p.vehicle,
            "valid_from": _iso(p.valid_from), "valid_to": _iso(p.valid_to), "status": _pass_status(p), "used_at": _iso(p.used_at), "created_at": _iso(p.created_at)}


def _dt(d: datetime) -> datetime:
    return d.replace(tzinfo=BD).astimezone(timezone.utc) if d.tzinfo is None else d.astimezone(timezone.utc)


class PassIn(BaseModel):
    unit_id: int | None = None
    name: str = Field(min_length=2, max_length=120)
    purpose: str = Field(default="guest", pattern=PURPOSE_PAT)
    people: int = Field(default=1, ge=1, le=50)
    vehicle: str = Field(default="", max_length=32)
    valid_from: datetime
    valid_to: datetime


def _unit_for_resident(db: Session, ctx: Ctx, unit_id: int | None) -> Unit:
    """A resident acts for their own flat; an admin names the flat."""
    mine_ids = _my_units(ctx)
    if unit_id is None:
        if not mine_ids:
            raise HTTPException(422, "Choose a flat")
        unit_id = sorted(mine_ids)[0]
    if not ctx.has(*MANAGE) and unit_id not in mine_ids:
        raise HTTPException(403, "You can only do this for your own flat")
    return _unit(db, ctx, unit_id)


@router.post("/passes", status_code=201)
def create_pass(body: PassIn, ctx: Ctx = Depends(property_ctx), db: Session = Depends(get_db)):
    """The code is returned here and nowhere else. Only a keyed hash is stored."""
    _gate(ctx)
    if not ctx.has(*RESIDENT, *MANAGE):
        raise HTTPException(403, "Your role cannot do this")
    unit = _unit_for_resident(db, ctx, body.unit_id)
    vf, vt = _dt(body.valid_from), _dt(body.valid_to)
    if vt <= vf or vt <= now():
        raise HTTPException(422, "The end time must be after the start time and in the future")
    if vt - vf > timedelta(days=PASS_MAX_DAYS):
        raise HTTPException(422, f"A pass can be valid for at most {PASS_MAX_DAYS} days")
    active = db.scalars(select(VisitorPass).where(VisitorPass.unit_id == unit.id, VisitorPass.status == "active", VisitorPass.valid_to > now())).all()
    if len(active) >= PASS_MAX_ACTIVE:
        raise HTTPException(409, "Too many open passes for this flat")
    taken = {p.code_hash for p in db.scalars(select(VisitorPass).where(VisitorPass.property_id == ctx.property.id, VisitorPass.status == "active", VisitorPass.valid_to > now()))}
    for _ in range(50):
        code = f"{secrets.randbelow(10**6):06d}"
        if _hash(ctx.property.id, code) not in taken:
            break
    else:
        raise HTTPException(503, "Could not make a code, try again")
    p = VisitorPass(property_id=ctx.property.id, unit_id=unit.id, name=body.name.strip(), purpose=body.purpose, people=body.people, vehicle=body.vehicle.strip().upper(),
                    valid_from=vf, valid_to=vt, code_hash=_hash(ctx.property.id, code), created_by=ctx.user.id)
    db.add(p)
    db.flush()
    _log(db, ctx, "visitor.pass.create", "visitor_pass", p.id, {"unit_id": unit.id})
    db.commit()
    return {**_pass_row(p, _units(db, ctx)), "code": code}


@router.get("/passes")
def passes(status: str = "", page: int = Query(1, ge=1), size: int | None = Query(None, ge=1, le=100), ctx: Ctx = Depends(property_ctx), db: Session = Depends(get_db)):
    _gate(ctx)
    stmt = select(VisitorPass).where(VisitorPass.property_id == ctx.property.id)
    if not ctx.has(*MANAGE):
        stmt = stmt.where(VisitorPass.unit_id.in_(_resident(ctx)))
    if status == "active":
        stmt = stmt.where(VisitorPass.status == "active", VisitorPass.valid_to > now())
    elif status == "expired":
        stmt = stmt.where(VisitorPass.status == "active", VisitorPass.valid_to <= now())
    elif status in ("used", "cancelled"):
        stmt = stmt.where(VisitorPass.status == status)
    size = size or _settings(db, ctx.property.id).page_size
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = db.scalars(stmt.order_by(VisitorPass.created_at.desc(), VisitorPass.id.desc()).offset((page - 1) * size).limit(size)).all()
    units = _units(db, ctx)
    return {"items": [_pass_row(p, units) for p in rows], "total": total, "page": page, "size": size}


@router.post("/passes/{pid}/cancel")
def cancel_pass(pid: int, ctx: Ctx = Depends(property_ctx), db: Session = Depends(get_db)):
    _gate(ctx)
    p = db.get(VisitorPass, pid)
    if not p or p.property_id != ctx.property.id or (not ctx.has(*MANAGE) and p.unit_id not in _my_units(ctx)):
        raise HTTPException(404, "Not found")
    if p.status != "active":
        raise HTTPException(409, "This pass is no longer open")
    p.status = "cancelled"
    _log(db, ctx, "visitor.pass.cancel", "visitor_pass", p.id)
    db.commit()
    return _pass_row(p, _units(db, ctx))


class RedeemIn(BaseModel):
    code: str = Field(pattern=r"^\d{6}$")


@router.post("/passes/redeem", status_code=201)
def redeem(body: RedeemIn, ctx: Ctx = Depends(property_ctx), db: Session = Depends(get_db)):
    """The guard types the code at the gate. A valid code approves the visitor at once and can never be used again."""
    _gate(ctx)
    ctx.need(*GATE)
    since = now() - timedelta(minutes=10)
    fails = db.scalar(select(func.count()).select_from(AuditLog).where(AuditLog.user_id == ctx.user.id, AuditLog.property_id == ctx.property.id, AuditLog.action == "visitor.pass.fail", AuditLog.at >= since)) or 0
    if fails >= FAIL_LIMIT:
        raise HTTPException(429, "Too many wrong codes. Wait a few minutes.")
    t = now()
    p = db.scalar(select(VisitorPass).where(VisitorPass.property_id == ctx.property.id, VisitorPass.code_hash == _hash(ctx.property.id, body.code), VisitorPass.status == "active",
                                            VisitorPass.valid_from <= t, VisitorPass.valid_to >= t))
    if not p:
        _log(db, ctx, "visitor.pass.fail", "visitor_pass", "")
        db.commit()
        raise HTTPException(404, "This code is not valid. It may be wrong, used or expired.")
    p.status, p.used_at = "used", t
    v = Visit(property_id=ctx.property.id, unit_id=p.unit_id, name=p.name, purpose=p.purpose, people=p.people, vehicle=p.vehicle, kind="pass", status="approved", decision_via="pass",
              decided_at=t, pass_id=p.id, created_by=ctx.user.id, created_at=t)
    db.add(v)
    db.flush()
    n = _notify(db, ctx, v, "info")
    _log(db, ctx, "visitor.pass.use", "visitor_pass", p.id, {"visit_id": v.id})
    db.commit()
    return {**_row(v, _units(db, ctx), ctx, _settings(db, ctx.property.id).overstay_hours), "notified": n}


# ---------------------------------------------------------------- frequent visitors

def _freq_row(f: FrequentVisitor, units: dict, ctx: Ctx) -> dict:
    today = _today()
    return {"id": f.id, "unit_id": f.unit_id, "unit": units.get(f.unit_id, ""), "name": f.name, "phone": f.phone if ctx.has(*SEE_PHONE) or f.unit_id in _my_units(ctx) else "", "role": f.role,
            "valid_from": f.valid_from.isoformat(), "valid_to": f.valid_to.isoformat(), "active": f.active, "valid_today": f.active and f.valid_from <= today <= f.valid_to}


class FrequentIn(BaseModel):
    unit_id: int | None = None
    name: str = Field(min_length=2, max_length=120)
    phone: str = Field(default="", max_length=32)
    role: str = Field(default="maid", pattern="^(" + "|".join(FREQ_ROLES) + ")$")
    valid_from: date
    valid_to: date


@router.post("/frequent", status_code=201)
def add_frequent(body: FrequentIn, ctx: Ctx = Depends(property_ctx), db: Session = Depends(get_db)):
    _gate(ctx)
    if not ctx.has(*RESIDENT, *MANAGE):
        raise HTTPException(403, "Your role cannot do this")
    unit = _unit_for_resident(db, ctx, body.unit_id)
    if body.valid_to < body.valid_from or (body.valid_to - body.valid_from).days > 366:
        raise HTTPException(422, "Choose valid dates, at most one year")
    f = FrequentVisitor(property_id=ctx.property.id, unit_id=unit.id, name=body.name.strip(), phone=body.phone.strip(), role=body.role, valid_from=body.valid_from, valid_to=body.valid_to, created_by=ctx.user.id)
    db.add(f)
    db.flush()
    _log(db, ctx, "visitor.frequent.add", "frequent_visitor", f.id, {"unit_id": unit.id})
    db.commit()
    return _freq_row(f, _units(db, ctx), ctx)


@router.get("/frequent")
def frequent(q: str = "", page: int = Query(1, ge=1), size: int | None = Query(None, ge=1, le=100), ctx: Ctx = Depends(property_ctx), db: Session = Depends(get_db)):
    """Residents: their flat's list. Admin and committee: all. The gate: only people valid today."""
    _gate(ctx)
    stmt = select(FrequentVisitor).where(FrequentVisitor.property_id == ctx.property.id, FrequentVisitor.active.is_(True))
    if ctx.has(*MANAGE, *COMMITTEE):
        pass
    elif ctx.has(*GATE):
        today = _today()
        stmt = stmt.where(FrequentVisitor.valid_from <= today, FrequentVisitor.valid_to >= today)
    else:
        stmt = stmt.where(FrequentVisitor.unit_id.in_(_resident(ctx)))
    if q.strip():
        stmt = stmt.where(or_(FrequentVisitor.name.ilike(f"%{q.strip()}%"), FrequentVisitor.unit_id.in_(select(Unit.id).where(Unit.property_id == ctx.property.id, Unit.number.ilike(f"%{q.strip()}%")))))
    size = size or _settings(db, ctx.property.id).page_size
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = db.scalars(stmt.order_by(FrequentVisitor.name, FrequentVisitor.id).offset((page - 1) * size).limit(size)).all()
    units = _units(db, ctx)
    return {"items": [_freq_row(f, units, ctx) for f in rows], "total": total, "page": page, "size": size}


@router.delete("/frequent/{fid}")
def remove_frequent(fid: int, ctx: Ctx = Depends(property_ctx), db: Session = Depends(get_db)):
    _gate(ctx)
    f = db.get(FrequentVisitor, fid)
    if not f or f.property_id != ctx.property.id or (not ctx.has(*MANAGE) and f.unit_id not in _my_units(ctx)):
        raise HTTPException(404, "Not found")
    f.active = False
    _log(db, ctx, "visitor.frequent.remove", "frequent_visitor", f.id)
    db.commit()
    return {"ok": True}


@router.post("/frequent/{fid}/enter", status_code=201)
def enter_frequent(fid: int, ctx: Ctx = Depends(property_ctx), db: Session = Depends(get_db)):
    """The guard waves a known person through. The flat is told, nobody has to approve."""
    _gate(ctx)
    ctx.need(*GATE)
    f = db.get(FrequentVisitor, fid)
    if not f or f.property_id != ctx.property.id or not f.active:
        raise HTTPException(404, "Not found")
    if not f.valid_from <= _today() <= f.valid_to:
        raise HTTPException(409, "This person's permission is not valid today")
    if db.scalar(select(Visit.id).where(Visit.frequent_id == f.id, Visit.status.in_(("approved", "in")))):
        raise HTTPException(409, "Already logged in")
    t = now()
    v = Visit(property_id=ctx.property.id, unit_id=f.unit_id, name=f.name, phone=f.phone, purpose=FREQ_PURPOSE.get(f.role, "other"), people=1, kind="frequent", status="approved",
              decision_via="frequent", decided_at=t, frequent_id=f.id, created_by=ctx.user.id, created_at=t)
    db.add(v)
    db.flush()
    n = _notify(db, ctx, v, "info")
    db.commit()
    return {**_row(v, _units(db, ctx), ctx, _settings(db, ctx.property.id).overstay_hours), "notified": n}
