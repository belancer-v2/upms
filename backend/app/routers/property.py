"""Units, people and the agency portfolio. Everything here is scoped to the building in X-Property-Id."""
import secrets
from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..audit import audit
from ..db import get_db
from ..deps import Ctx, current_user, property_ctx
from ..models.core import Membership, Organization, Property, User
from ..models.property import Occupancy, Unit
from ..permissions import MANAGE, SEE_CONTACTS, VIEW_ALL_UNITS
from ..security import hash_password

router = APIRouter(prefix="/api", tags=["property"])


def sync_status(db: Session, unit: Unit) -> None:
    """A unit is occupied when a tenant lives there, or an owner who lives there. Otherwise vacant (or on offer to let)."""
    occ = db.scalars(select(Occupancy).where(Occupancy.unit_id == unit.id, Occupancy.active)).all()
    lived_in = any(o.kind == "tenant" or o.resides for o in occ)
    if lived_in:
        unit.status = "occupied"
    elif unit.status not in ("to_let", "to_let_pending"):
        unit.status = "vacant"


def unit_dict(db: Session, u: Unit, contacts: bool) -> dict:
    occ = db.scalars(select(Occupancy).where(Occupancy.unit_id == u.id).order_by(Occupancy.id)).all()
    cur = [o for o in occ if o.active]
    return {"id": u.id, "block": u.block, "floor": u.floor, "number": u.number, "area_sqft": u.area_sqft, "bedrooms": u.bedrooms, "status": u.status,
            "owners": [_occ(o, contacts) for o in cur if o.kind == "owner"], "tenants": [_occ(o, contacts) for o in cur if o.kind == "tenant"],
            "history": [_occ(o, contacts) for o in occ if not o.active]}


def _occ(o: Occupancy, contacts: bool) -> dict:
    return {"id": o.id, "kind": o.kind, "name": o.name, "name_bn": o.name_bn, "phone": o.phone if contacts else "", "email": o.email if contacts else "",
            "resides": o.resides, "has_login": o.user_id is not None, "start_date": o.start_date.isoformat(), "end_date": o.end_date.isoformat() if o.end_date else None}


def _own_unit(ctx: Ctx, unit: Unit) -> bool:
    return unit.id in ctx.unit_ids


@router.get("/units")
def list_units(q: str = "", status: str = "", ctx: Ctx = Depends(property_ctx), db: Session = Depends(get_db)):
    sees_all = ctx.has(*VIEW_ALL_UNITS)
    contacts = ctx.has(*SEE_CONTACTS)
    stmt = select(Unit).where(Unit.property_id == ctx.property.id).order_by(Unit.floor, Unit.block, Unit.number)
    if not sees_all:
        if not ctx.unit_ids:
            return []
        stmt = stmt.where(Unit.id.in_(ctx.unit_ids))
    rows = db.scalars(stmt).all()
    out = [unit_dict(db, u, contacts) for u in rows]
    if status:
        out = [u for u in out if u["status"] == status]
    if q:
        ql = q.lower()
        out = [u for u in out if ql in u["number"].lower() or any(ql in p["name"].lower() for p in u["owners"] + u["tenants"])]
    return out


@router.get("/units/summary")
def summary(ctx: Ctx = Depends(property_ctx), db: Session = Depends(get_db)):
    ctx.need(*VIEW_ALL_UNITS)
    return _summary(db, ctx.property.id)


def _summary(db: Session, pid: int) -> dict:
    units = db.scalars(select(Unit).where(Unit.property_id == pid)).all()
    ids = [u.id for u in units]
    occ = db.scalars(select(Occupancy).where(Occupancy.unit_id.in_(ids), Occupancy.active)).all() if ids else []
    by = {s: sum(u.status == s for u in units) for s in ("occupied", "vacant", "to_let", "to_let_pending")}
    return {"units": len(units), **by, "floors": len({u.floor for u in units}), "owners": sum(o.kind == "owner" for o in occ), "tenants": sum(o.kind == "tenant" for o in occ),
            "area_sqft": round(sum(u.area_sqft for u in units))}


class UnitIn(BaseModel):
    block: str = ""
    floor: int = Field(ge=0, le=80)
    number: str = Field(min_length=1, max_length=16)
    area_sqft: float = Field(default=0, ge=0, le=20000)
    bedrooms: int = Field(default=3, ge=0, le=10)


def _manage(ctx: Ctx):
    ctx.need(*MANAGE)


@router.post("/units", status_code=201)
def add_unit(body: UnitIn, ctx: Ctx = Depends(property_ctx), db: Session = Depends(get_db)):
    _manage(ctx)
    if db.scalar(select(Unit.id).where(Unit.property_id == ctx.property.id, Unit.number == body.number)):
        raise HTTPException(409, "This unit number already exists")
    u = Unit(property_id=ctx.property.id, **body.model_dump())
    db.add(u)
    db.flush()
    audit(db, user_id=ctx.user.id, org_id=ctx.property.org_id, property_id=ctx.property.id, action="unit.add", entity="unit", entity_id=u.id, meta={"number": u.number})
    db.commit()
    return unit_dict(db, u, True)


class GenIn(BaseModel):
    floors: int = Field(ge=1, le=60)
    blocks: list[str] = Field(default_factory=lambda: ["A"], max_length=6)
    per_block: int = Field(ge=1, le=12)
    area_sqft: float = 1200
    bedrooms: int = 3


@router.post("/units/generate", status_code=201)
def generate(body: GenIn, ctx: Ctx = Depends(property_ctx), db: Session = Depends(get_db)):
    """Creates A-101, A-102 ... for every block and floor. Skips numbers that already exist."""
    _manage(ctx)
    have = set(db.scalars(select(Unit.number).where(Unit.property_id == ctx.property.id)))
    made = 0
    for f in range(1, body.floors + 1):
        for b in body.blocks:
            for n in range(1, body.per_block + 1):
                num = f"{b}-{f}{n:02d}"
                if num not in have:
                    db.add(Unit(property_id=ctx.property.id, block=b, floor=f, number=num, area_sqft=body.area_sqft, bedrooms=body.bedrooms))
                    made += 1
    ctx.property.floors = max(ctx.property.floors, body.floors)
    audit(db, user_id=ctx.user.id, org_id=ctx.property.org_id, property_id=ctx.property.id, action="unit.generate", meta={"created": made})
    db.commit()
    return {"created": made}


class ImportRow(BaseModel):
    number: str
    floor: int = 1
    block: str = ""
    area_sqft: float = 0
    bedrooms: int = 3
    owner_name: str = ""
    owner_phone: str = ""


@router.post("/units/import")
def import_units(rows: list[ImportRow], ctx: Ctx = Depends(property_ctx), db: Session = Depends(get_db)):
    """The frontend parses the CSV or Excel paste and sends rows. Existing numbers are updated, new ones created."""
    _manage(ctx)
    created = updated = 0
    for r in rows[:500]:
        u = db.scalar(select(Unit).where(Unit.property_id == ctx.property.id, Unit.number == r.number))
        if u:
            u.area_sqft, u.bedrooms, u.floor = r.area_sqft or u.area_sqft, r.bedrooms, r.floor
            updated += 1
        else:
            u = Unit(property_id=ctx.property.id, number=r.number, floor=r.floor, block=r.block, area_sqft=r.area_sqft, bedrooms=r.bedrooms)
            db.add(u)
            db.flush()
            created += 1
        if r.owner_name and not db.scalar(select(Occupancy.id).where(Occupancy.unit_id == u.id, Occupancy.kind == "owner", Occupancy.active)):
            db.add(Occupancy(unit_id=u.id, kind="owner", name=r.owner_name, phone=r.owner_phone, resides=False, start_date=date.today()))
    audit(db, user_id=ctx.user.id, org_id=ctx.property.org_id, property_id=ctx.property.id, action="unit.import", meta={"created": created, "updated": updated})
    db.commit()
    return {"created": created, "updated": updated}


class OccIn(BaseModel):
    kind: str = Field(pattern="^(owner|tenant)$")
    name: str = Field(min_length=2, max_length=120)
    name_bn: str = ""
    phone: str = ""
    email: str = ""
    resides: bool = True
    start_date: date | None = None
    create_login: bool = False


@router.post("/units/{unit_id}/occupants", status_code=201)
def add_occupant(unit_id: int, body: OccIn, ctx: Ctx = Depends(property_ctx), db: Session = Depends(get_db)):
    u = db.get(Unit, unit_id)
    if not u or u.property_id != ctx.property.id:
        raise HTTPException(404, "Unit not found")
    # Admins add anyone. An owner can add a tenant to their own flat (owner-led tenant onboarding).
    if not (ctx.has(*MANAGE) or (body.kind == "tenant" and ctx.has("FLAT_OWNER", "OWNER_REP") and _own_unit(ctx, u))):
        raise HTTPException(403, "Your role cannot do this")
    if body.kind == "tenant" and db.scalar(select(Occupancy.id).where(Occupancy.unit_id == u.id, Occupancy.kind == "tenant", Occupancy.active)):
        raise HTTPException(409, "This flat already has a tenant. Move them out first.")
    occ = Occupancy(unit_id=u.id, kind=body.kind, name=body.name, name_bn=body.name_bn, phone=body.phone, email=body.email.strip().lower(),
                    resides=body.resides if body.kind == "owner" else True, start_date=body.start_date or date.today())
    temp = None
    if body.create_login and occ.email:
        if db.scalar(select(User.id).where(User.email == occ.email)):
            raise HTTPException(409, "That email already has an account")
        temp = secrets.token_urlsafe(7)
        usr = User(email=occ.email, name=body.name, name_bn=body.name_bn, phone=body.phone, password_hash=hash_password(temp))
        db.add(usr)
        db.flush()
        occ.user_id = usr.id
        db.add(Membership(user_id=usr.id, org_id=ctx.property.org_id, property_id=ctx.property.id, unit_id=u.id, role="FLAT_OWNER" if body.kind == "owner" else "TENANT"))
    db.add(occ)
    db.flush()
    sync_status(db, u)
    audit(db, user_id=ctx.user.id, org_id=ctx.property.org_id, property_id=ctx.property.id, action=f"occupant.add.{body.kind}", entity="unit", entity_id=u.id, meta={"name": body.name})
    db.commit()
    return {"unit": unit_dict(db, u, True), "temp_password": temp}


@router.post("/occupants/{occ_id}/move-out")
def move_out(occ_id: int, ctx: Ctx = Depends(property_ctx), db: Session = Depends(get_db)):
    o = db.get(Occupancy, occ_id)
    u = db.get(Unit, o.unit_id) if o else None
    if not o or not u or u.property_id != ctx.property.id or not o.active:
        raise HTTPException(404, "Not found")
    if not (ctx.has(*MANAGE) or (o.kind == "tenant" and ctx.has("FLAT_OWNER", "OWNER_REP") and _own_unit(ctx, u))):
        raise HTTPException(403, "Your role cannot do this")
    o.active, o.end_date = False, date.today()
    if o.user_id:  # the login stops working for this building
        for m in db.scalars(select(Membership).where(Membership.user_id == o.user_id, Membership.unit_id == u.id)):
            db.delete(m)
    sync_status(db, u)
    audit(db, user_id=ctx.user.id, org_id=ctx.property.org_id, property_id=ctx.property.id, action="occupant.move_out", entity="unit", entity_id=u.id, meta={"name": o.name, "kind": o.kind})
    db.commit()
    return unit_dict(db, u, True)


@router.post("/units/{unit_id}/to-let/{step}")
def to_let(unit_id: int, step: str, ctx: Ctx = Depends(property_ctx), db: Session = Depends(get_db)):
    """request (admin) -> approve (the owner) -> to_let. The owner can also withdraw."""
    u = db.get(Unit, unit_id)
    if not u or u.property_id != ctx.property.id or step not in ("request", "approve", "withdraw"):
        raise HTTPException(404, "Not found")
    if step == "request":
        _manage(ctx)
        if u.status != "vacant":
            raise HTTPException(422, "Only a vacant flat can be offered")
        u.status = "to_let_pending"
    elif step == "approve":
        if not (ctx.has("FLAT_OWNER", "OWNER_REP") and _own_unit(ctx, u)):
            raise HTTPException(403, "Only the owner can approve")
        if u.status != "to_let_pending":
            raise HTTPException(422, "Nothing to approve")
        u.status = "to_let"
    else:
        if not (ctx.has(*MANAGE) or (ctx.has("FLAT_OWNER", "OWNER_REP") and _own_unit(ctx, u))):
            raise HTTPException(403, "Your role cannot do this")
        u.status = "vacant"
    audit(db, user_id=ctx.user.id, org_id=ctx.property.org_id, property_id=ctx.property.id, action=f"unit.to_let.{step}", entity="unit", entity_id=u.id)
    db.commit()
    return unit_dict(db, u, ctx.has(*SEE_CONTACTS))


@router.get("/people")
def people(kind: str = "", ctx: Ctx = Depends(property_ctx), db: Session = Depends(get_db)):
    ctx.need(*(SEE_CONTACTS | {"AUDITOR"}))
    contacts = ctx.has(*SEE_CONTACTS)
    stmt = select(Occupancy, Unit).join(Unit, Unit.id == Occupancy.unit_id).where(Unit.property_id == ctx.property.id, Occupancy.active).order_by(Unit.floor, Unit.number)
    rows = db.execute(stmt).all()
    return [{"id": o.id, "kind": o.kind, "name": o.name, "name_bn": o.name_bn, "phone": o.phone if contacts else "", "email": o.email if contacts else "", "unit": u.number,
             "unit_id": u.id, "resides": o.resides, "has_login": o.user_id is not None, "since": o.start_date.isoformat()} for o, u in rows if not kind or o.kind == kind]


class PropIn(BaseModel):
    name: str = Field(min_length=2)
    name_bn: str = ""
    address: str = ""
    city: str = ""
    floors: int = Field(default=0, ge=0, le=80)


@router.put("/property")
def edit_property(body: PropIn, ctx: Ctx = Depends(property_ctx), db: Session = Depends(get_db)):
    _manage(ctx)
    p = ctx.property
    p.name, p.name_bn, p.address, p.city, p.floors = body.name, body.name_bn, body.address, body.city or p.city, body.floors
    audit(db, user_id=ctx.user.id, org_id=p.org_id, property_id=p.id, action="property.edit", entity="property", entity_id=p.id)
    db.commit()
    return {"ok": True}


@router.get("/portfolio")
def portfolio(user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Every building the caller manages as an agency manager (or all buildings for FlatWise admins)."""
    org_ids = {m.org_id for m in db.scalars(select(Membership).where(Membership.user_id == user.id, Membership.role == "AGENCY_MANAGER", Membership.property_id.is_(None)))}
    admin = user.saas_role in ("SUPER_ADMIN", "SAAS_ADMIN")
    if not org_ids and not admin:
        raise HTTPException(403, "Not allowed")
    stmt = select(Property).order_by(Property.id)
    if not admin:
        stmt = stmt.where(Property.org_id.in_(org_ids))
    out = []
    for p in db.scalars(stmt):
        s = _summary(db, p.id)
        out.append({"id": p.id, "name": p.name, "name_bn": p.name_bn, "city": p.city, "address": p.address, "org": db.get(Organization, p.org_id).name, **s,
                    "occupancy_pct": round(100 * s["occupied"] / s["units"]) if s["units"] else 0})
    return out


class NewBuilding(BaseModel):
    name: str = Field(min_length=2)
    name_bn: str = ""
    address: str = ""
    city: str = "Dhaka"
    floors: int = Field(default=0, ge=0, le=80)


@router.post("/portfolio/buildings", status_code=201)
def add_building(body: NewBuilding, user: User = Depends(current_user), db: Session = Depends(get_db)):
    ms = db.scalars(select(Membership).where(Membership.user_id == user.id, Membership.role == "AGENCY_MANAGER", Membership.property_id.is_(None))).all()
    if not ms:
        raise HTTPException(403, "Only an agency manager can add buildings")
    p = Property(org_id=ms[0].org_id, **body.model_dump())
    db.add(p)
    db.flush()
    audit(db, user_id=user.id, org_id=p.org_id, property_id=p.id, action="property.add", entity="property", entity_id=p.id)
    db.commit()
    return {"id": p.id}
