"""Parking (M17): slots that travel with the flat, vehicles, guard lookup and visitor bays. Needs the 'parking' plan feature."""
import secrets
from datetime import date

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from .. import config
from ..audit import audit
from ..db import get_db
from ..deps import Ctx, property_ctx
from ..models.core import now
from ..models.parking import ParkingAllocation, ParkingEntitlement, ParkingSetting, ParkingSlot, ParkingVisit, Vehicle
from ..models.property import Occupancy, Unit
from ..permissions import COMMITTEE, MANAGE, RESIDENT
from ..services.parking import KINDS, clean_plate, entitlement, held, set_entitlement

router = APIRouter(prefix="/api/parking", tags=["parking"])
SEE = MANAGE | COMMITTEE | {"AUDITOR", "CARETAKER", "GUARD"}   # the slot map
WATCH = MANAGE | {"GUARD"}                                      # plate lookup and visitor bays
KIND_PAT = "^(" + "|".join(KINDS) + ")$"
PHOTO_TYPES = {"image/jpeg": ("jpg", b"\xff\xd8\xff"), "image/png": ("png", b"\x89PNG\r\n\x1a\n")}
MAX_PHOTO = 2 * 1024 * 1024


def _gate(ctx: Ctx) -> None:
    ctx.feature("parking")


def _log(db: Session, ctx: Ctx, action: str, entity: str, eid, meta: dict | None = None) -> None:
    audit(db, user_id=ctx.user.id, org_id=ctx.property.org_id, property_id=ctx.property.id, action=action, entity=entity, entity_id=eid, meta=meta or {})


def _size(db: Session, ctx: Ctx, size: int | None) -> int:
    if size:
        return size
    s = db.get(ParkingSetting, ctx.property.id)
    return s.page_size if s else 24


def _slot(db: Session, ctx: Ctx, sid: int) -> ParkingSlot:
    s = db.get(ParkingSlot, sid)
    if not s or s.property_id != ctx.property.id:
        raise HTTPException(404, "Slot not found")
    return s


def _unit(db: Session, ctx: Ctx, uid: int) -> Unit:
    u = db.get(Unit, uid)
    if not u or u.property_id != ctx.property.id:
        raise HTTPException(404, "Flat not found")
    return u


def _current(db: Session, slot_id: int) -> ParkingAllocation | None:
    return db.scalar(select(ParkingAllocation).where(ParkingAllocation.slot_id == slot_id, ParkingAllocation.until.is_(None)))


def _owners(db: Session, unit_ids: set[int]) -> dict[int, Occupancy]:
    out: dict[int, Occupancy] = {}
    if unit_ids:
        for o in db.scalars(select(Occupancy).where(Occupancy.unit_id.in_(unit_ids), Occupancy.kind == "owner", Occupancy.active).order_by(Occupancy.id.desc())):
            out[o.unit_id] = o
    return out


def _slot_row(s: ParkingSlot, unit: Unit | None, owner: Occupancy | None, busy: bool = False) -> dict:
    state = "blocked" if s.status == "blocked" else "visitor" if s.visitor else "occupied" if unit else "free"
    return {"id": s.id, "code": s.code, "level": s.level, "kind": s.kind, "cover": s.cover, "status": s.status, "visitor": s.visitor, "note": s.note, "state": state,
            "unit_id": unit.id if unit else None, "unit": unit.number if unit else "", "owner": owner.name if owner else "", "owner_bn": owner.name_bn if owner else "", "in_use": busy}


def _veh(v: Vehicle, unit_no: str = "") -> dict:
    return {"id": v.id, "unit_id": v.unit_id, "unit": unit_no, "reg_no": v.reg_no, "kind": v.kind, "make_model": v.make_model, "colour": v.colour, "sticker": v.sticker,
            "holder_kind": v.holder_kind, "temporary": v.temporary, "status": v.status, "has_photo": bool(v.photo), "created_at": v.created_at.isoformat()}


# ---------------- settings and summary
@router.get("/settings")
def get_settings(ctx: Ctx = Depends(property_ctx), db: Session = Depends(get_db)):
    _gate(ctx)
    return {"page_size": _size(db, ctx, None)}


class SettingsIn(BaseModel):
    page_size: int = Field(ge=6, le=100)


@router.put("/settings")
def put_settings(body: SettingsIn, ctx: Ctx = Depends(property_ctx), db: Session = Depends(get_db)):
    _gate(ctx)
    ctx.need(*MANAGE)
    s = db.get(ParkingSetting, ctx.property.id)
    if s:
        s.page_size = body.page_size
    else:
        db.add(ParkingSetting(property_id=ctx.property.id, page_size=body.page_size))
    _log(db, ctx, "parking.settings", "property", ctx.property.id, {"page_size": body.page_size})
    db.commit()
    return {"page_size": body.page_size}


def _unmet(db: Session, pid: int) -> list[dict]:
    units = {u.id: u for u in db.scalars(select(Unit).where(Unit.property_id == pid))}
    ents: dict[int, dict[str, int]] = {}
    for e in db.scalars(select(ParkingEntitlement).where(ParkingEntitlement.unit_id.in_(units or {-1}))):
        ents.setdefault(e.unit_id, {})[e.kind] = e.count
    got: dict[int, dict[str, int]] = {}
    for uid, k, n in db.execute(select(ParkingAllocation.unit_id, ParkingAllocation.vehicle_kind, func.count()).where(ParkingAllocation.unit_id.in_(units or {-1}), ParkingAllocation.until.is_(None))
                                .group_by(ParkingAllocation.unit_id, ParkingAllocation.vehicle_kind)):
        got.setdefault(uid, {})[k] = n
    out = []
    for uid, e in ents.items():
        miss = {k: n - got.get(uid, {}).get(k, 0) for k, n in e.items() if n > got.get(uid, {}).get(k, 0)}
        if miss:
            out.append({"unit_id": uid, "unit": units[uid].number, "floor": units[uid].floor, "missing": miss, "entitled": e, "held": got.get(uid, {})})
    return sorted(out, key=lambda r: (r["floor"], r["unit"]))


def _free_stmt(pid: int):
    taken = select(ParkingAllocation.slot_id).where(ParkingAllocation.until.is_(None))
    return select(ParkingSlot).where(ParkingSlot.property_id == pid, ParkingSlot.status == "active", ParkingSlot.visitor.is_(False), ParkingSlot.id.not_in(taken))


@router.get("/summary")
def summary(ctx: Ctx = Depends(property_ctx), db: Session = Depends(get_db)):
    _gate(ctx)
    ctx.need(*SEE)
    pid = ctx.property.id
    slots = db.scalars(select(ParkingSlot).where(ParkingSlot.property_id == pid)).all()
    taken = set(db.scalars(select(ParkingAllocation.slot_id).where(ParkingAllocation.until.is_(None))))
    vs = db.scalars(select(Vehicle).where(Vehicle.property_id == pid)).all()
    return {"slots": len(slots), "occupied": sum(s.id in taken for s in slots), "free": sum(s.status == "active" and not s.visitor and s.id not in taken for s in slots),
            "visitor": sum(s.visitor for s in slots), "blocked": sum(s.status == "blocked" for s in slots), "flats_unmet": len(_unmet(db, pid)),
            "vehicles": len(vs), "to_review": sum(v.status == "to_review" for v in vs), "page_size": _size(db, ctx, None)}


# ---------------- slot map
@router.get("/slots")
def slots(q: str = "", state: str = "", kind: str = "", page: int = Query(1, ge=1), size: int | None = Query(None, ge=1, le=100), ctx: Ctx = Depends(property_ctx), db: Session = Depends(get_db)):
    _gate(ctx)
    ctx.need(*SEE)
    size = _size(db, ctx, size)
    cur = select(ParkingAllocation).where(ParkingAllocation.until.is_(None)).subquery()
    stmt = select(ParkingSlot, Unit).outerjoin(cur, cur.c.slot_id == ParkingSlot.id).outerjoin(Unit, Unit.id == cur.c.unit_id).where(ParkingSlot.property_id == ctx.property.id)
    if kind in KINDS:
        stmt = stmt.where(ParkingSlot.kind == kind)
    if state == "blocked":
        stmt = stmt.where(ParkingSlot.status == "blocked")
    elif state == "visitor":
        stmt = stmt.where(ParkingSlot.visitor.is_(True), ParkingSlot.status == "active")
    elif state == "occupied":
        stmt = stmt.where(Unit.id.is_not(None), ParkingSlot.status == "active")
    elif state == "free":
        stmt = stmt.where(Unit.id.is_(None), ParkingSlot.status == "active", ParkingSlot.visitor.is_(False))
    if q.strip():
        like = f"%{q.strip()}%"
        stmt = stmt.where(or_(ParkingSlot.code.ilike(like), Unit.number.ilike(like), ParkingSlot.level.ilike(like)))
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = db.execute(stmt.order_by(ParkingSlot.code).offset((page - 1) * size).limit(size)).all()
    owners = _owners(db, {u.id for _, u in rows if u})
    busy = set(db.scalars(select(ParkingVisit.slot_id).where(ParkingVisit.property_id == ctx.property.id, ParkingVisit.out_at.is_(None))))
    return {"items": [_slot_row(s, u, owners.get(u.id) if u else None, s.id in busy) for s, u in rows], "total": total, "page": page, "size": size}


class SlotIn(BaseModel):
    code: str = Field(min_length=1, max_length=32)
    level: str = Field(default="", max_length=32)
    kind: str = Field(default="car", pattern=KIND_PAT)
    cover: str = Field(default="open", pattern="^(covered|open)$")
    visitor: bool = False
    note: str = Field(default="", max_length=200)


@router.post("/slots", status_code=201)
def add_slot(body: SlotIn, ctx: Ctx = Depends(property_ctx), db: Session = Depends(get_db)):
    _gate(ctx)
    ctx.need(*MANAGE)
    code = body.code.strip().upper()
    if db.scalar(select(ParkingSlot.id).where(ParkingSlot.property_id == ctx.property.id, ParkingSlot.code == code)):
        raise HTTPException(409, "This slot code already exists")
    s = ParkingSlot(property_id=ctx.property.id, code=code, level=body.level.strip(), kind=body.kind, cover=body.cover, visitor=body.visitor, note=body.note.strip())
    db.add(s)
    db.flush()
    _log(db, ctx, "parking.slot.add", "parking_slot", s.id, {"code": code, "kind": s.kind, "visitor": s.visitor})
    db.commit()
    return _slot_row(s, None, None)


class SlotEdit(BaseModel):
    level: str | None = Field(default=None, max_length=32)
    cover: str | None = Field(default=None, pattern="^(covered|open)$")
    status: str | None = Field(default=None, pattern="^(active|blocked)$")
    visitor: bool | None = None
    note: str | None = Field(default=None, max_length=200)


@router.put("/slots/{sid}")
def edit_slot(sid: int, body: SlotEdit, ctx: Ctx = Depends(property_ctx), db: Session = Depends(get_db)):
    _gate(ctx)
    ctx.need(*MANAGE)
    s = _slot(db, ctx, sid)
    cur = _current(db, s.id)
    if cur and (body.status == "blocked" or body.visitor):
        raise HTTPException(422, "Take the slot back from the flat first")
    for k, v in body.model_dump(exclude_none=True).items():
        setattr(s, k, v.strip() if isinstance(v, str) else v)
    _log(db, ctx, "parking.slot.edit", "parking_slot", s.id, body.model_dump(exclude_none=True))
    db.commit()
    owner = _owners(db, {cur.unit_id}).get(cur.unit_id) if cur else None
    return _slot_row(s, db.get(Unit, cur.unit_id) if cur else None, owner)


class AllocIn(BaseModel):
    unit_id: int


@router.post("/slots/{sid}/allocate")
def allocate(sid: int, body: AllocIn, ctx: Ctx = Depends(property_ctx), db: Session = Depends(get_db)):
    """Gives a free slot to a flat, or moves a held slot to another flat (reassign)."""
    _gate(ctx)
    ctx.need(*MANAGE)
    s, u = _slot(db, ctx, sid), _unit(db, ctx, body.unit_id)
    if s.status != "active" or s.visitor:
        raise HTTPException(422, "A blocked or visitor slot cannot be given to a flat")
    cur = _current(db, s.id)
    if cur and cur.unit_id == u.id:
        raise HTTPException(409, "The flat already holds this slot")
    if cur:
        cur.until = date.today()
    db.add(ParkingAllocation(slot_id=s.id, unit_id=u.id, vehicle_kind=s.kind, since=date.today()))
    _log(db, ctx, "parking.reassign" if cur else "parking.allocate", "parking_slot", s.id, {"code": s.code, "to": u.number, "from": db.get(Unit, cur.unit_id).number if cur else None})
    db.commit()
    return _slot_row(s, u, _owners(db, {u.id}).get(u.id))


@router.post("/slots/{sid}/unallocate")
def unallocate(sid: int, ctx: Ctx = Depends(property_ctx), db: Session = Depends(get_db)):
    _gate(ctx)
    ctx.need(*MANAGE)
    s = _slot(db, ctx, sid)
    cur = _current(db, s.id)
    if not cur:
        raise HTTPException(409, "The slot is already free")
    cur.until = date.today()
    _log(db, ctx, "parking.unallocate", "parking_slot", s.id, {"code": s.code, "from": db.get(Unit, cur.unit_id).number})
    db.commit()
    return _slot_row(s, None, None)


class SwapIn(BaseModel):
    slot_a: int
    slot_b: int


@router.post("/swap")
def swap(body: SwapIn, ctx: Ctx = Depends(property_ctx), db: Session = Depends(get_db)):
    """Two flats exchange their slots. The slots must be the same kind, so every vehicle still fits."""
    _gate(ctx)
    ctx.need(*MANAGE)
    a, b = _slot(db, ctx, body.slot_a), _slot(db, ctx, body.slot_b)
    ca, cb = _current(db, a.id), _current(db, b.id)
    if a.id == b.id or not ca or not cb:
        raise HTTPException(422, "Choose two different slots that both belong to a flat")
    if ca.unit_id == cb.unit_id:
        raise HTTPException(422, "Both slots belong to the same flat")
    if a.kind != b.kind:
        raise HTTPException(422, "Only slots of the same vehicle kind can be swapped")
    ua, ub = ca.unit_id, cb.unit_id
    ca.until = cb.until = date.today()
    db.add_all([ParkingAllocation(slot_id=a.id, unit_id=ub, vehicle_kind=a.kind, since=date.today()), ParkingAllocation(slot_id=b.id, unit_id=ua, vehicle_kind=b.kind, since=date.today())])
    _log(db, ctx, "parking.swap", "parking_slot", a.id, {"a": a.code, "b": b.code, "unit_a": db.get(Unit, ua).number, "unit_b": db.get(Unit, ub).number})
    db.commit()
    return {"ok": True}


@router.get("/handover")
def handover(which: str = Query("free", pattern="^(free|unmet)$"), q: str = "", page: int = Query(1, ge=1), size: int | None = Query(None, ge=1, le=100),
             ctx: Ctx = Depends(property_ctx), db: Session = Depends(get_db)):
    """Free slots to hand out, or flats that are promised more slots than they hold."""
    _gate(ctx)
    ctx.need(*SEE)
    size = _size(db, ctx, size)
    if which == "free":
        stmt = _free_stmt(ctx.property.id)
        if q.strip():
            stmt = stmt.where(ParkingSlot.code.ilike(f"%{q.strip()}%"))
        total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
        rows = db.scalars(stmt.order_by(ParkingSlot.code).offset((page - 1) * size).limit(size)).all()
        return {"items": [_slot_row(s, None, None) for s in rows], "total": total, "page": page, "size": size}
    rows = [r for r in _unmet(db, ctx.property.id) if not q.strip() or q.strip().lower() in r["unit"].lower()]
    return {"items": rows[(page - 1) * size: page * size], "total": len(rows), "page": page, "size": size}


class EntIn(BaseModel):
    car: int = Field(default=0, ge=0, le=10)
    motorbike: int = Field(default=0, ge=0, le=10)
    bicycle: int = Field(default=0, ge=0, le=10)


@router.put("/units/{uid}/entitlement")
def put_entitlement(uid: int, body: EntIn, ctx: Ctx = Depends(property_ctx), db: Session = Depends(get_db)):
    _gate(ctx)
    ctx.need(*MANAGE)
    u = _unit(db, ctx, uid)
    for k, n in body.model_dump().items():
        set_entitlement(db, u.id, k, n)
    _log(db, ctx, "parking.entitlement", "unit", u.id, body.model_dump())
    db.commit()
    return entitlement(db, u.id)


# ---------------- one flat: slots, vehicles, limits
def _unit_view(db: Session, u: Unit) -> dict:
    allocs = db.scalars(select(ParkingAllocation).where(ParkingAllocation.unit_id == u.id, ParkingAllocation.until.is_(None))).all()
    sl = {s.id: s for s in db.scalars(select(ParkingSlot).where(ParkingSlot.id.in_([a.slot_id for a in allocs] or [-1])))}
    vs = db.scalars(select(Vehicle).where(Vehicle.unit_id == u.id).order_by(Vehicle.id)).all()
    return {"unit": {"id": u.id, "number": u.number}, "entitlement": entitlement(db, u.id), "held": held(db, u.id),
            "slots": [_slot_row(sl[a.slot_id], u, None) | {"since": a.since.isoformat()} for a in sorted(allocs, key=lambda a: sl[a.slot_id].code)],
            "vehicles": [_veh(v, u.number) for v in vs], "allowed": len(allocs), "used": sum(not v.temporary for v in vs), "temp_used": sum(v.temporary for v in vs)}


@router.get("/mine")
def mine(ctx: Ctx = Depends(property_ctx), db: Session = Depends(get_db)):
    _gate(ctx)
    ctx.need(*RESIDENT)
    units = db.scalars(select(Unit).where(Unit.property_id == ctx.property.id, Unit.id.in_(ctx.unit_ids or {-1})).order_by(Unit.number)).all()
    return [_unit_view(db, u) for u in units]


@router.get("/units/{uid}")
def unit_parking(uid: int, ctx: Ctx = Depends(property_ctx), db: Session = Depends(get_db)):
    _gate(ctx)
    u = _unit(db, ctx, uid)
    if not (ctx.has(*(MANAGE | COMMITTEE | {"AUDITOR", "CARETAKER"})) or uid in ctx.unit_ids):
        raise HTTPException(404, "Flat not found")
    return _unit_view(db, u)


# ---------------- vehicles
def _can_touch(ctx: Ctx, v: Vehicle) -> bool:
    if ctx.has(*MANAGE):
        return True
    if v.unit_id not in ctx.unit_ids or not ctx.has(*RESIDENT):
        return False
    return ctx.has("FLAT_OWNER", "OWNER_REP") or v.registered_by == ctx.user.id   # a tenant manages only their own vehicles


def _vehicle(db: Session, ctx: Ctx, vid: int, write: bool = True) -> Vehicle:
    v = db.get(Vehicle, vid)
    if not v or v.property_id != ctx.property.id:
        raise HTTPException(404, "Vehicle not found")
    if write and not _can_touch(ctx, v):
        raise HTTPException(404, "Vehicle not found")
    return v


class VehicleIn(BaseModel):
    unit_id: int
    reg_no: str = Field(min_length=3, max_length=64)
    kind: str = Field(pattern=KIND_PAT)
    make_model: str = Field(default="", max_length=80)
    colour: str = Field(default="", max_length=32)
    sticker: str = Field(default="", max_length=32)
    temporary: bool = False


@router.post("/vehicles", status_code=201)
def add_vehicle(body: VehicleIn, ctx: Ctx = Depends(property_ctx), db: Session = Depends(get_db)):
    _gate(ctx)
    u = _unit(db, ctx, body.unit_id)
    admin = ctx.has(*MANAGE)
    if not admin and not (ctx.has(*RESIDENT) and u.id in ctx.unit_ids):
        raise HTTPException(403, "Your role cannot do this")
    if body.temporary and not admin:
        raise HTTPException(403, "Only the building admin can issue a temporary permit")
    shown, norm = clean_plate(body.reg_no)
    if len(norm) < 4:
        raise HTTPException(422, "Enter the full registration number")
    if db.scalar(select(Vehicle.id).where(Vehicle.property_id == ctx.property.id, Vehicle.reg_norm == norm)):
        raise HTTPException(409, "This registration number is already registered in the building")
    mine = db.scalars(select(Vehicle).where(Vehicle.unit_id == u.id)).all()
    if body.temporary:
        if any(v.temporary for v in mine):
            raise HTTPException(409, "This flat already has a temporary permit")
    else:
        slots_k = held(db, u.id)[body.kind]
        if slots_k == 0:
            raise HTTPException(422, f"This flat has no {body.kind} slot, so a {body.kind} cannot be registered")
        if sum(1 for v in mine if v.kind == body.kind and not v.temporary) >= slots_k:
            raise HTTPException(422, f"All of this flat's {body.kind} slots already have a vehicle")
    tenant_only = ctx.has("TENANT") and not ctx.has("FLAT_OWNER", "OWNER_REP") and not admin
    v = Vehicle(property_id=ctx.property.id, unit_id=u.id, reg_no=shown, reg_norm=norm, kind=body.kind, make_model=body.make_model.strip(), colour=body.colour.strip(), sticker=body.sticker.strip(),
                holder_kind="tenant" if tenant_only else "owner", temporary=body.temporary, registered_by=ctx.user.id)
    db.add(v)
    db.flush()
    _log(db, ctx, "parking.vehicle.add", "vehicle", v.id, {"reg": shown, "unit": u.number, "temporary": v.temporary})
    db.commit()
    return _veh(v, u.number)


class VehicleEdit(BaseModel):
    make_model: str | None = Field(default=None, max_length=80)
    colour: str | None = Field(default=None, max_length=32)
    sticker: str | None = Field(default=None, max_length=32)


@router.put("/vehicles/{vid}")
def edit_vehicle(vid: int, body: VehicleEdit, ctx: Ctx = Depends(property_ctx), db: Session = Depends(get_db)):
    _gate(ctx)
    v = _vehicle(db, ctx, vid)
    for k, val in body.model_dump(exclude_none=True).items():
        setattr(v, k, val.strip())
    _log(db, ctx, "parking.vehicle.edit", "vehicle", v.id)
    db.commit()
    return _veh(v, db.get(Unit, v.unit_id).number)


@router.post("/vehicles/{vid}/keep")
def keep_vehicle(vid: int, ctx: Ctx = Depends(property_ctx), db: Session = Depends(get_db)):
    """Confirms a vehicle that was marked 'to review' after a move-out."""
    _gate(ctx)
    v = _vehicle(db, ctx, vid)
    v.status = "active"
    _log(db, ctx, "parking.vehicle.keep", "vehicle", v.id)
    db.commit()
    return _veh(v, db.get(Unit, v.unit_id).number)


@router.delete("/vehicles/{vid}", status_code=204)
def remove_vehicle(vid: int, ctx: Ctx = Depends(property_ctx), db: Session = Depends(get_db)):
    _gate(ctx)
    v = _vehicle(db, ctx, vid)
    if v.photo:
        (config.UPLOAD_DIR / "vehicles" / v.photo).unlink(missing_ok=True)
    _log(db, ctx, "parking.vehicle.remove", "vehicle", v.id, {"reg": v.reg_no})
    db.delete(v)
    db.commit()


@router.get("/vehicles")
def vehicles(q: str = "", status: str = "", page: int = Query(1, ge=1), size: int | None = Query(None, ge=1, le=100), ctx: Ctx = Depends(property_ctx), db: Session = Depends(get_db)):
    _gate(ctx)
    ctx.need(*(MANAGE | COMMITTEE | {"AUDITOR", "CARETAKER"}))
    size = _size(db, ctx, size)
    stmt = select(Vehicle, Unit).join(Unit, Unit.id == Vehicle.unit_id).where(Vehicle.property_id == ctx.property.id)
    if status in ("active", "to_review"):
        stmt = stmt.where(Vehicle.status == status)
    if q.strip():
        _, norm = clean_plate(q)
        like = f"%{q.strip()}%"
        stmt = stmt.where(or_(Vehicle.reg_norm.like(f"%{norm}%") if norm else False, Unit.number.ilike(like), Vehicle.sticker.ilike(like), Vehicle.make_model.ilike(like)))
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = db.execute(stmt.order_by(Vehicle.status.desc(), Vehicle.id).offset((page - 1) * size).limit(size)).all()
    return {"items": [_veh(v, u.number) for v, u in rows], "total": total, "page": page, "size": size}


@router.get("/lookup")
def lookup(reg: str = Query(min_length=2, max_length=64), ctx: Ctx = Depends(property_ctx), db: Session = Depends(get_db)):
    """Gate check: plate in, flat, owner name and slot out. No phone numbers."""
    _gate(ctx)
    ctx.need(*WATCH)
    _, norm = clean_plate(reg)
    if len(norm) < 2:
        raise HTTPException(422, "Type at least two letters or digits")
    rows = db.execute(select(Vehicle, Unit).join(Unit, Unit.id == Vehicle.unit_id).where(Vehicle.property_id == ctx.property.id, Vehicle.reg_norm.like(f"%{norm}%")).order_by(Vehicle.reg_norm).limit(10)).all()
    owners = _owners(db, {u.id for _, u in rows})
    out = []
    for v, u in rows:
        codes = [s.code for s in db.scalars(select(ParkingSlot).join(ParkingAllocation, ParkingAllocation.slot_id == ParkingSlot.id).where(ParkingAllocation.unit_id == u.id, ParkingAllocation.until.is_(None),
                                                                                                                       ParkingSlot.kind == v.kind).order_by(ParkingSlot.code))]
        o = owners.get(u.id)
        out.append({"reg_no": v.reg_no, "kind": v.kind, "make_model": v.make_model, "colour": v.colour, "sticker": v.sticker, "status": v.status, "temporary": v.temporary,
                    "unit": u.number, "owner": o.name if o else "", "owner_bn": o.name_bn if o else "", "slots": codes})
    return {"items": out}


# ---------------- vehicle photo
@router.post("/vehicles/{vid}/photo")
async def upload_photo(vid: int, file: UploadFile = File(...), ctx: Ctx = Depends(property_ctx), db: Session = Depends(get_db)):
    _gate(ctx)
    v = _vehicle(db, ctx, vid)
    spec = PHOTO_TYPES.get(file.content_type or "")
    if not spec:
        raise HTTPException(422, "Upload a JPG or PNG photo")
    data = await file.read(MAX_PHOTO + 1)
    if len(data) > MAX_PHOTO:
        raise HTTPException(413, "The photo is bigger than 2 MB")
    if not data or not data.startswith(spec[1]):
        raise HTTPException(422, "The file does not look like its type")
    folder = config.UPLOAD_DIR / "vehicles"
    folder.mkdir(parents=True, exist_ok=True)
    if v.photo:
        (folder / v.photo).unlink(missing_ok=True)
    v.photo, v.photo_type = f"{v.id}_{secrets.token_hex(8)}.{spec[0]}", file.content_type
    (folder / v.photo).write_bytes(data)
    _log(db, ctx, "parking.vehicle.photo", "vehicle", v.id)
    db.commit()
    return _veh(v, db.get(Unit, v.unit_id).number)


@router.get("/vehicles/{vid}/photo")
def get_photo(vid: int, ctx: Ctx = Depends(property_ctx), db: Session = Depends(get_db)):
    _gate(ctx)
    v = _vehicle(db, ctx, vid, write=False)
    if not (ctx.has(*(SEE)) or v.unit_id in ctx.unit_ids):
        raise HTTPException(404, "Vehicle not found")
    path = config.UPLOAD_DIR / "vehicles" / (v.photo or "x")
    if not v.photo or not path.exists():
        raise HTTPException(404, "No photo")
    return FileResponse(path, media_type=v.photo_type, headers={"X-Content-Type-Options": "nosniff"})


# ---------------- visitor bays
@router.get("/visits")
def visits(open_only: bool = False, page: int = Query(1, ge=1), size: int | None = Query(None, ge=1, le=100), ctx: Ctx = Depends(property_ctx), db: Session = Depends(get_db)):
    _gate(ctx)
    ctx.need(*(WATCH | {"CARETAKER"}))
    size = _size(db, ctx, size)
    stmt = select(ParkingVisit, ParkingSlot).join(ParkingSlot, ParkingSlot.id == ParkingVisit.slot_id).where(ParkingVisit.property_id == ctx.property.id)
    if open_only:
        stmt = stmt.where(ParkingVisit.out_at.is_(None))
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = db.execute(stmt.order_by(ParkingVisit.out_at.is_not(None), ParkingVisit.in_at.desc()).offset((page - 1) * size).limit(size)).all()
    bays = db.scalars(select(ParkingSlot).where(ParkingSlot.property_id == ctx.property.id, ParkingSlot.visitor, ParkingSlot.status == "active").order_by(ParkingSlot.code)).all()
    busy = set(db.scalars(select(ParkingVisit.slot_id).where(ParkingVisit.property_id == ctx.property.id, ParkingVisit.out_at.is_(None))))
    return {"items": [{"id": x.id, "plate": x.plate, "slot_id": s.id, "slot": s.code, "in_at": x.in_at.isoformat(), "out_at": x.out_at.isoformat() if x.out_at else None} for x, s in rows],
            "total": total, "page": page, "size": size, "bays": [{"id": b.id, "code": b.code, "kind": b.kind, "busy": b.id in busy} for b in bays]}


class VisitIn(BaseModel):
    plate: str = Field(min_length=2, max_length=64)
    slot_id: int


@router.post("/visits", status_code=201)
def visit_in(body: VisitIn, ctx: Ctx = Depends(property_ctx), db: Session = Depends(get_db)):
    _gate(ctx)
    ctx.need(*WATCH)
    s = _slot(db, ctx, body.slot_id)
    if not s.visitor or s.status != "active":
        raise HTTPException(422, "Choose a visitor bay")
    if db.scalar(select(ParkingVisit.id).where(ParkingVisit.slot_id == s.id, ParkingVisit.out_at.is_(None))):
        raise HTTPException(409, "A car is already parked in this bay")
    shown, norm = clean_plate(body.plate)
    if len(norm) < 2:
        raise HTTPException(422, "Enter the plate")
    x = ParkingVisit(property_id=ctx.property.id, slot_id=s.id, plate=shown, logged_by=ctx.user.id)
    db.add(x)
    db.flush()
    _log(db, ctx, "parking.visit.in", "parking_visit", x.id, {"plate": shown, "slot": s.code})
    db.commit()
    return {"id": x.id, "plate": shown, "slot": s.code, "in_at": x.in_at.isoformat(), "out_at": None}


@router.post("/visits/{xid}/out")
def visit_out(xid: int, ctx: Ctx = Depends(property_ctx), db: Session = Depends(get_db)):
    _gate(ctx)
    ctx.need(*WATCH)
    x = db.get(ParkingVisit, xid)
    if not x or x.property_id != ctx.property.id:
        raise HTTPException(404, "Not found")
    if x.out_at:
        raise HTTPException(409, "Already logged out")
    x.out_at = now()
    _log(db, ctx, "parking.visit.out", "parking_visit", x.id, {"plate": x.plate})
    db.commit()
    return {"id": x.id, "out_at": x.out_at.isoformat()}
