"""M16: community hall and amenity booking. Residents request, the committee approves, a normal invoice is paid, the booking confirms itself.
Money is integer paisa. The invoice carries the period label HALL-<booking id>, so payment, cash, receipt and gateway flows work unchanged."""
from datetime import date, datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..audit import audit
from ..db import get_db
from ..deps import Ctx, property_ctx
from ..models.amenities import Amenity, Blackout, Booking, SlotHold
from ..models.billing import Invoice, InvoiceLine, Message, Payment
from ..models.core import User, now
from ..models.property import Occupancy, Unit
from ..permissions import MANAGE, RESIDENT, VIEW_ALL_UNITS
from ..services.messaging import deliver
from . import billing as B

router = APIRouter(prefix="/api/amenities", tags=["amenities"])
KINDS = ("hall", "rooftop", "gym", "playground", "guest_room")
PURPOSES = ("wedding_reception", "birthday", "aqeeqah", "milad", "meeting", "other")
SLOTS = {"morning": (8, 13), "evening": (15, 20), "night": (20, 24), "full": (8, 24)}
PARTS = {"morning": ("morning",), "evening": ("evening",), "night": ("night",), "full": ("morning", "evening", "night")}
SLOT_EN = {"morning": "Morning", "evening": "Evening", "night": "Night", "full": "Full day"}
SLOT_BN = {"morning": "সকাল", "evening": "সন্ধ্যা", "night": "রাত", "full": "পুরো দিন"}
LIVE = ("pending", "approved", "confirmed", "completed")
HOLDING = ("approved", "confirmed", "completed")
APPROVE = MANAGE | {"PRESIDENT", "SECRETARY"}
SETTINGS = MANAGE | {"PRESIDENT", "SECRETARY"}
HANDOVER = MANAGE | {"CARETAKER"}
REFUNDERS = MANAGE | {"TREASURER"}
SEE_ALL = VIEW_ALL_UNITS
DEFAULT_CANCEL = [{"days": 14, "pct": 100}, {"days": 7, "pct": 50}, {"days": 0, "pct": 0}]
PREFIX = "HALL-"


def _gate(ctx: Ctx) -> None:
    ctx.feature("amenities")


def _aware(dt: datetime | None) -> datetime | None:
    return dt.replace(tzinfo=timezone.utc) if dt and dt.tzinfo is None else dt


def _log(db: Session, ctx: Ctx, action: str, entity: str, eid, meta: dict | None = None) -> None:
    audit(db, user_id=ctx.user.id, org_id=ctx.property.org_id, property_id=ctx.property.id, action=action, entity=entity, entity_id=eid, meta=meta or {})


def _bdt(paisa: int) -> str:
    return f"BDT {paisa / 100:,.0f}"


# ---------------- amenity setup
class SlotIn(BaseModel):
    on: bool = False
    owner: int = Field(default=0, ge=0)
    tenant: int = Field(default=0, ge=0)


class RuleIn(BaseModel):
    days: int = Field(ge=0, le=365)
    pct: int = Field(ge=0, le=100)


class AmenityIn(BaseModel):
    kind: str = Field(default="hall", pattern="^(" + "|".join(KINDS) + ")$")
    name: str = Field(min_length=2, max_length=80)
    name_bn: str = Field(default="", max_length=80)
    capacity: int = Field(default=100, ge=1, le=5000)
    rules: str = Field(default="", max_length=4000)
    rules_bn: str = Field(default="", max_length=4000)
    photo_url: str = Field(default="", max_length=300)
    active: bool = True
    slots: dict[str, SlotIn] = {}
    ext_hour_fee: int = Field(default=0, ge=0)
    max_ext_hours: int = Field(default=2, ge=0, le=6)
    deposit: int = Field(default=0, ge=0)
    cleaning_fee: int = Field(default=0, ge=0)
    generator_fee: int = Field(default=0, ge=0)
    free_quota: int = Field(default=0, ge=0, le=50)
    min_notice_days: int = Field(default=3, ge=0, le=365)
    max_advance_days: int = Field(default=90, ge=1, le=730)
    hold_days: int = Field(default=3, ge=1, le=30)
    cancel_rules: list[RuleIn] = []


def _apply(a: Amenity, body: AmenityIn) -> None:
    d = body.model_dump()
    if any(k not in SLOTS for k in d["slots"]):
        raise HTTPException(422, "Unknown slot")
    if body.max_advance_days <= body.min_notice_days:
        raise HTTPException(422, "Max advance days must be more than min notice days")
    d["slots"] = {k: d["slots"].get(k, {"on": False, "owner": 0, "tenant": 0}) for k in SLOTS}
    d["cancel_rules"] = sorted(d["cancel_rules"], key=lambda r: -r["days"]) or DEFAULT_CANCEL
    for k, v in d.items():
        setattr(a, k, v)


def _amenity(a: Amenity) -> dict:
    return {"id": a.id, "kind": a.kind, "name": a.name, "name_bn": a.name_bn, "capacity": a.capacity, "rules": a.rules, "rules_bn": a.rules_bn, "photo_url": a.photo_url, "active": a.active,
            "slots": a.slots or {}, "slot_hours": {k: list(v) for k, v in SLOTS.items()}, "ext_hour_fee": a.ext_hour_fee, "max_ext_hours": a.max_ext_hours, "deposit": a.deposit,
            "cleaning_fee": a.cleaning_fee, "generator_fee": a.generator_fee, "free_quota": a.free_quota, "min_notice_days": a.min_notice_days, "max_advance_days": a.max_advance_days,
            "hold_days": a.hold_days, "cancel_rules": a.cancel_rules or DEFAULT_CANCEL}


def _get_amenity(db: Session, ctx: Ctx, aid: int) -> Amenity:
    a = db.get(Amenity, aid)
    if not a or a.property_id != ctx.property.id:
        raise HTTPException(404, "Not found")
    return a


@router.get("")
def amenities(ctx: Ctx = Depends(property_ctx), db: Session = Depends(get_db)):
    _gate(ctx)
    stmt = select(Amenity).where(Amenity.property_id == ctx.property.id).order_by(Amenity.id)
    if not ctx.has(*SETTINGS):
        stmt = stmt.where(Amenity.active)
    return [_amenity(a) for a in db.scalars(stmt)]


@router.post("", status_code=201)
def add_amenity(body: AmenityIn, ctx: Ctx = Depends(property_ctx), db: Session = Depends(get_db)):
    _gate(ctx)
    ctx.need(*SETTINGS)
    a = Amenity(property_id=ctx.property.id)
    _apply(a, body)
    db.add(a)
    db.flush()
    _log(db, ctx, "amenity.add", "amenity", a.id, {"name": a.name})
    db.commit()
    return _amenity(a)


@router.put("/{aid}")
def edit_amenity(aid: int, body: AmenityIn, ctx: Ctx = Depends(property_ctx), db: Session = Depends(get_db)):
    _gate(ctx)
    ctx.need(*SETTINGS)
    a = _get_amenity(db, ctx, aid)
    _apply(a, body)
    _log(db, ctx, "amenity.edit", "amenity", a.id, {"name": a.name, "deposit": a.deposit})
    db.commit()
    return _amenity(a)


# ---------------- blackout dates
class BlackoutIn(BaseModel):
    on_date: date
    amenity_id: int | None = None
    reason: str = Field(default="", max_length=120)
    reason_bn: str = Field(default="", max_length=120)


def _blk(b: Blackout) -> dict:
    return {"id": b.id, "on_date": b.on_date.isoformat(), "amenity_id": b.amenity_id, "reason": b.reason, "reason_bn": b.reason_bn}


@router.get("/blackouts")
def blackouts(amenity_id: int = 0, past: bool = False, page: int = Query(1, ge=1), size: int = Query(10, ge=1, le=100), ctx: Ctx = Depends(property_ctx), db: Session = Depends(get_db)):
    _gate(ctx)
    stmt = select(Blackout).where(Blackout.property_id == ctx.property.id)
    if amenity_id:
        stmt = stmt.where(or_(Blackout.amenity_id == amenity_id, Blackout.amenity_id.is_(None)))
    if not past:
        stmt = stmt.where(Blackout.on_date >= date.today())
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = db.scalars(stmt.order_by(Blackout.on_date, Blackout.id).offset((page - 1) * size).limit(size)).all()
    return {"items": [_blk(b) for b in rows], "total": total, "page": page, "size": size}


@router.post("/blackouts", status_code=201)
def add_blackout(body: BlackoutIn, ctx: Ctx = Depends(property_ctx), db: Session = Depends(get_db)):
    _gate(ctx)
    ctx.need(*SETTINGS)
    if body.amenity_id:
        _get_amenity(db, ctx, body.amenity_id)
    if db.scalar(select(Blackout.id).where(Blackout.property_id == ctx.property.id, Blackout.on_date == body.on_date, Blackout.amenity_id == body.amenity_id)):
        raise HTTPException(409, "This date is already blocked")
    b = Blackout(property_id=ctx.property.id, created_by=ctx.user.id, **body.model_dump())
    db.add(b)
    db.flush()
    stmt = select(func.count()).select_from(Booking).where(Booking.property_id == ctx.property.id, Booking.on_date == body.on_date, Booking.status.in_(LIVE))
    if body.amenity_id:
        stmt = stmt.where(Booking.amenity_id == body.amenity_id)
    affected = db.scalar(stmt) or 0
    _log(db, ctx, "amenity.blackout.add", "blackout", b.id, {"date": body.on_date.isoformat(), "affected": affected})
    db.commit()
    return {**_blk(b), "affected": affected}


@router.delete("/blackouts/{bid}", status_code=204)
def del_blackout(bid: int, ctx: Ctx = Depends(property_ctx), db: Session = Depends(get_db)):
    _gate(ctx)
    ctx.need(*SETTINGS)
    b = db.get(Blackout, bid)
    if not b or b.property_id != ctx.property.id:
        raise HTTPException(404, "Not found")
    _log(db, ctx, "amenity.blackout.remove", "blackout", b.id, {"date": b.on_date.isoformat()})
    db.delete(b)
    db.commit()


def _blackout(db: Session, pid: int, aid: int, on: date) -> Blackout | None:
    return db.scalar(select(Blackout).where(Blackout.property_id == pid, Blackout.on_date == on, or_(Blackout.amenity_id == aid, Blackout.amenity_id.is_(None))))


# ---------------- pricing
def _party(db: Session, ctx: Ctx, unit_id: int) -> str:
    occ = db.scalar(select(Occupancy).where(Occupancy.unit_id == unit_id, Occupancy.user_id == ctx.user.id, Occupancy.active))
    if occ:
        return occ.kind
    return "tenant" if "TENANT" in ctx.roles and not (ctx.roles & {"FLAT_OWNER", "OWNER_REP"}) else "owner"


def _free_left(db: Session, a: Amenity, unit_id: int, year: int) -> int:
    if a.free_quota <= 0:
        return 0
    used = db.scalar(select(func.count()).select_from(Booking).where(Booking.amenity_id == a.id, Booking.unit_id == unit_id, Booking.free_used, Booking.status.in_(HOLDING),
                                                                     Booking.on_date >= date(year, 1, 1), Booking.on_date <= date(year, 12, 31))) or 0
    return max(0, a.free_quota - used)


def price(db: Session, a: Amenity, slot: str, party: str, unit_id: int, on: date, ext_hours: int = 0, generator: bool = False) -> dict:
    cfg = (a.slots or {}).get(slot) or {}
    if not cfg.get("on"):
        raise HTTPException(422, "This slot is not offered")
    if ext_hours and (a.ext_hour_fee <= 0 or ext_hours > a.max_ext_hours):
        raise HTTPException(422, "Extra hours are not available or too many")
    if generator and a.generator_fee <= 0:
        raise HTTPException(422, "Generator is not offered")
    free = _free_left(db, a, unit_id, on.year) > 0
    rent = int(cfg.get(party, 0))
    fee = 0 if free else rent
    ext = a.ext_hour_fee * ext_hours
    gen = a.generator_fee if generator else 0
    return {"party": party, "rent": rent, "fee": fee, "free": free, "ext_fee": ext, "cleaning": a.cleaning_fee, "generator": gen, "deposit": a.deposit,
            "total": fee + ext + a.cleaning_fee + gen + a.deposit}


def _window(a: Amenity, on: date) -> None:
    today = date.today()
    if on < today + timedelta(days=a.min_notice_days):
        raise HTTPException(422, f"Please book at least {a.min_notice_days} days ahead")
    if on > today + timedelta(days=a.max_advance_days):
        raise HTTPException(422, f"You can book at most {a.max_advance_days} days ahead")


def _my_unit(db: Session, ctx: Ctx, unit_id: int | None) -> int:
    if not ctx.has(*RESIDENT) or not ctx.unit_ids:
        raise HTTPException(403, "Only an owner or tenant with a flat can book")
    if unit_id and unit_id not in ctx.unit_ids:
        raise HTTPException(403, "You can only book for your own flat")
    return unit_id or sorted(ctx.unit_ids)[0]


@router.get("/quote")
def quote(amenity_id: int, on_date: date, slot: str, ext_hours: int = 0, generator: bool = False, unit_id: int = 0, ctx: Ctx = Depends(property_ctx), db: Session = Depends(get_db)):
    _gate(ctx)
    a = _get_amenity(db, ctx, amenity_id)
    if slot not in SLOTS:
        raise HTTPException(422, "Unknown slot")
    uid = _my_unit(db, ctx, unit_id or None)
    return price(db, a, slot, _party(db, ctx, uid), uid, on_date, ext_hours, generator)


# ---------------- expiry
def expire_stale(db: Session, pid: int, at=None) -> int:
    """Unpaid approvals older than the hold period, and requests whose day has passed, free their slot. `at` lets the scheduled job and tests inject the time."""
    n, t = 0, at or now()
    today = at.date() if at else date.today()
    for b in db.scalars(select(Booking).where(Booking.property_id == pid, Booking.status.in_(("pending", "approved")))):
        inv = db.get(Invoice, b.invoice_id) if b.invoice_id else None
        if b.status == "approved" and b.expires_at and _aware(b.expires_at) < t and not (inv and inv.paid > 0):
            pass
        elif b.status == "pending" and b.on_date < today:
            pass
        else:
            continue
        _release(db, b)
        b.status, b.reason = "expired", b.reason or "Not paid in time" if b.status == "approved" else "Date passed"
        if inv and inv.status != "void" and inv.paid == 0:
            inv.status = "void"
        audit(db, action="amenity.booking.expire", property_id=pid, entity="booking", entity_id=b.id)
        n += 1
    if n:
        db.commit()
    return n


def _release(db: Session, b: Booking) -> None:
    for h in db.scalars(select(SlotHold).where(SlotHold.booking_id == b.id)):
        db.delete(h)
    db.flush()


# ---------------- messages
def _notify(db: Session, org_id: int, pid: int, b: Booking, a: Amenity, tpl: str, en: str, bn: str) -> None:
    key = f"booking:{b.id}:{tpl}"
    if db.scalar(select(Message.id).where(Message.idem_key == key)):
        return
    user = db.get(User, b.user_id)
    occ = db.scalar(select(Occupancy).where(Occupancy.unit_id == b.unit_id, Occupancy.user_id == b.user_id, Occupancy.active))
    lang = user.lang if user and user.lang in ("en", "bn") else "bn"
    msg = Message(property_id=pid, unit_id=b.unit_id, to_name=user.name if user else "", to_phone=(user.phone if user and user.phone else occ.phone if occ else ""), template=tpl, lang=lang,
                  body=bn if lang == "bn" else en, idem_key=key)
    db.add(msg)
    deliver(db, org_id, msg)


# ---------------- bookings
def _rows_for(db: Session, bs: list[Booking], ctx: Ctx) -> list[dict]:
    amen = {a.id: a for a in db.scalars(select(Amenity).where(Amenity.id.in_({b.amenity_id for b in bs} or {-1})))}
    units = {u.id: u for u in db.scalars(select(Unit).where(Unit.id.in_({b.unit_id for b in bs} or {-1})))}
    users = {u.id: u for u in db.scalars(select(User).where(User.id.in_({b.user_id for b in bs} or {-1})))}
    invs = {i.id: i for i in db.scalars(select(Invoice).where(Invoice.id.in_({b.invoice_id for b in bs if b.invoice_id} or {-1})))}
    staff = ctx.has(*SEE_ALL)
    out = []
    for b in bs:
        a, u, usr, inv = amen.get(b.amenity_id), units.get(b.unit_id), users.get(b.user_id), invs.get(b.invoice_id)
        mine = b.user_id == ctx.user.id or b.unit_id in ctx.unit_ids
        conflict = False
        if b.status == "pending":
            conflict = bool(db.scalar(select(func.count()).select_from(SlotHold).where(SlotHold.amenity_id == b.amenity_id, SlotHold.on_date == b.on_date, SlotHold.part.in_(PARTS[b.slot]))))
        paid = inv.paid if inv else 0
        out.append({"id": b.id, "amenity_id": b.amenity_id, "amenity": a.name if a else "", "amenity_bn": a.name_bn if a else "", "kind": a.kind if a else "", "unit_id": b.unit_id,
                    "unit": u.number if u else "", "by": usr.name if usr else "", "by_bn": usr.name_bn if usr else "", "party": b.party, "on_date": b.on_date.isoformat(), "slot": b.slot,
                    "hours": list(SLOTS[b.slot]), "purpose": b.purpose, "guests": b.guests, "catering": b.catering, "contact": b.contact if (staff or mine) else "", "note": b.note,
                    "ext_hours": b.ext_hours, "use_generator": b.use_generator, "status": b.status, "reason": b.reason, "expires_at": b.expires_at.isoformat() if b.expires_at else None,
                    "invoice_id": b.invoice_id, "invoice_status": inv.status if inv else "", "paid": paid, "balance": max(0, b.total - paid) if inv else 0,
                    "fee": b.fee, "ext_fee": b.ext_fee, "cleaning": b.cleaning, "generator": b.generator, "deposit": b.deposit, "total": b.total, "free_used": b.free_used,
                    "damage_amount": b.damage_amount, "damage_note": b.damage_note, "refund_amount": b.refund_amount, "refund_method": b.refund_method,
                    "refunded_at": b.refunded_at.isoformat() if b.refunded_at else None, "handover_at": b.handover_at.isoformat() if b.handover_at else None,
                    "created_at": b.created_at.isoformat(), "mine": mine, "conflict": conflict,
                    "can_approve": b.status == "pending" and ctx.has(*APPROVE) and not conflict,
                    "can_cancel": b.status in ("pending", "approved", "confirmed") and (ctx.has(*APPROVE) or (mine and b.on_date >= date.today())),
                    "can_handover": b.status == "confirmed" and ctx.has(*HANDOVER) and b.on_date <= date.today(),
                    "can_refund": b.refund_amount > 0 and not b.refunded_at and ctx.has(*REFUNDERS),
                    "can_permit": b.status in ("confirmed", "completed") and (staff or mine)})
    return out


def _booking(db: Session, ctx: Ctx, bid: int) -> Booking:
    b = db.get(Booking, bid)
    if not b or b.property_id != ctx.property.id or (not ctx.has(*SEE_ALL) and not (b.user_id == ctx.user.id or b.unit_id in ctx.unit_ids)):
        raise HTTPException(404, "Not found")
    return b


class BookingIn(BaseModel):
    amenity_id: int
    on_date: date
    slot: str = Field(pattern="^(morning|evening|night|full)$")
    purpose: str = Field(default="other", pattern="^(" + "|".join(PURPOSES) + ")$")
    guests: int = Field(ge=1)
    catering: bool = False
    contact: str = Field(min_length=6, max_length=32)
    note: str = Field(default="", max_length=300)
    ext_hours: int = Field(default=0, ge=0, le=6)
    use_generator: bool = False
    unit_id: int | None = None


@router.post("/bookings", status_code=201)
def request_booking(body: BookingIn, ctx: Ctx = Depends(property_ctx), db: Session = Depends(get_db)):
    _gate(ctx)
    uid = _my_unit(db, ctx, body.unit_id)
    a = _get_amenity(db, ctx, body.amenity_id)
    if not a.active:
        raise HTTPException(404, "Not found")
    expire_stale(db, ctx.property.id)
    _window(a, body.on_date)
    bo = _blackout(db, ctx.property.id, a.id, body.on_date)
    if bo:
        raise HTTPException(422, f"This date is closed for booking{': ' + bo.reason if bo.reason else ''}")
    if body.guests > a.capacity:
        raise HTTPException(422, f"At most {a.capacity} guests are allowed")
    party = _party(db, ctx, uid)
    p = price(db, a, body.slot, party, uid, body.on_date, body.ext_hours, body.use_generator)
    if db.scalar(select(SlotHold.id).where(SlotHold.amenity_id == a.id, SlotHold.on_date == body.on_date, SlotHold.part.in_(PARTS[body.slot]))):
        raise HTTPException(409, "This slot is already booked")
    if db.scalar(select(Booking.id).where(Booking.unit_id == uid, Booking.on_date == body.on_date, Booking.status.in_(("pending", "approved")))):
        raise HTTPException(409, "Your flat already has a request for this date")
    b = Booking(property_id=ctx.property.id, amenity_id=a.id, unit_id=uid, user_id=ctx.user.id, party=party, on_date=body.on_date, slot=body.slot, purpose=body.purpose, guests=body.guests,
                catering=body.catering, contact=body.contact.strip(), note=body.note.strip(), ext_hours=body.ext_hours, use_generator=body.use_generator)
    db.add(b)
    db.flush()
    _log(db, ctx, "amenity.booking.request", "booking", b.id, {"amenity": a.name, "date": body.on_date.isoformat(), "slot": body.slot})
    db.commit()
    return _rows_for(db, [b], ctx)[0]


@router.get("/bookings")
def bookings(scope: str = "mine", status: str = "", amenity_id: int = 0, q: str = "", page: int = Query(1, ge=1), size: int = Query(10, ge=1, le=100),
             ctx: Ctx = Depends(property_ctx), db: Session = Depends(get_db)):
    _gate(ctx)
    expire_stale(db, ctx.property.id)
    stmt = select(Booking).where(Booking.property_id == ctx.property.id)
    if scope != "all" or not ctx.has(*SEE_ALL):
        if not ctx.unit_ids and not ctx.has(*RESIDENT):
            if not ctx.has(*SEE_ALL):
                raise HTTPException(403, "Your role cannot do this")
        stmt = stmt.where(or_(Booking.unit_id.in_(ctx.unit_ids or {-1}), Booking.user_id == ctx.user.id))
    if status:
        stmt = stmt.where(Booking.status == status) if status != "open" else stmt.where(Booking.status.in_(("pending", "approved")))
    if amenity_id:
        stmt = stmt.where(Booking.amenity_id == amenity_id)
    if q.strip():
        stmt = stmt.join(Unit, Unit.id == Booking.unit_id).where(Unit.number.ilike(f"%{q.strip()}%"))
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = db.scalars(stmt.order_by(Booking.on_date.desc(), Booking.id.desc()).offset((page - 1) * size).limit(size)).all()
    return {"items": _rows_for(db, list(rows), ctx), "total": total, "page": page, "size": size}


@router.get("/summary")
def summary(ctx: Ctx = Depends(property_ctx), db: Session = Depends(get_db)):
    _gate(ctx)
    expire_stale(db, ctx.property.id)
    stmt = select(Booking.status, func.count()).where(Booking.property_id == ctx.property.id).group_by(Booking.status)
    if not ctx.has(*SEE_ALL):
        stmt = stmt.where(or_(Booking.unit_id.in_(ctx.unit_ids or {-1}), Booking.user_id == ctx.user.id))
    counts = {s: n for s, n in db.execute(stmt)}
    return {"counts": counts, "pending": counts.get("pending", 0), "awaiting_payment": counts.get("approved", 0)}


@router.get("/bookings/{bid}")
def booking(bid: int, ctx: Ctx = Depends(property_ctx), db: Session = Depends(get_db)):
    _gate(ctx)
    return _rows_for(db, [_booking(db, ctx, bid)], ctx)[0]


class ReasonIn(BaseModel):
    reason: str = Field(default="", max_length=300)


@router.post("/bookings/{bid}/approve")
def approve(bid: int, ctx: Ctx = Depends(property_ctx), db: Session = Depends(get_db)):
    _gate(ctx)
    ctx.need(*APPROVE)
    expire_stale(db, ctx.property.id)
    b = _booking(db, ctx, bid)
    a = db.get(Amenity, b.amenity_id)
    if b.status != "pending":
        raise HTTPException(409, "This request was already decided")
    if b.on_date < date.today():
        raise HTTPException(422, "The date has passed")
    if _blackout(db, b.property_id, a.id, b.on_date):
        raise HTTPException(422, "This date is closed for booking")
    # take the slot first: the unique key decides, so two approvals can never both win
    try:
        for part in PARTS[b.slot]:
            db.add(SlotHold(amenity_id=a.id, on_date=b.on_date, part=part, booking_id=b.id))
        db.flush()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "This slot is already booked by another confirmed request")
    p = price(db, a, b.slot, b.party, b.unit_id, b.on_date, b.ext_hours, b.use_generator)
    b.fee, b.ext_fee, b.cleaning, b.generator, b.deposit, b.total, b.free_used = p["fee"], p["ext_fee"], p["cleaning"], p["generator"], p["deposit"], p["total"], p["free"]
    b.decided_by, b.decided_at, b.reason = ctx.user.id, now(), ""
    sname, sbn = SLOT_EN[b.slot], SLOT_BN[b.slot]
    org, bname = ctx.property.org_id, ctx.property.name
    if b.total <= 0:
        b.status, b.confirmed_at = "confirmed", now()
        _notify(db, org, ctx.property.id, b, a, "booking_confirmed", f"{bname}: your {a.name} booking on {b.on_date:%d %b} ({sname}) is confirmed.", f"{ctx.property.name_bn or bname}: {b.on_date:%d %b} তারিখে ({sbn}) {a.name_bn or a.name} বুকিং নিশ্চিত হয়েছে।")
    else:
        due = date.today() + timedelta(days=a.hold_days)
        inv = Invoice(property_id=b.property_id, unit_id=b.unit_id, period=f"{PREFIX}{b.id}", number=f"INV-{b.property_id}-{PREFIX}{b.id}", issue_date=date.today(), due_date=due, total=b.total)
        db.add(inv)
        db.flush()
        label, label_bn = a.name, a.name_bn or a.name
        lines = [(f"{label}: {sname} ({'free quota' if b.free_used else b.party + ' rate'})", f"{label_bn}: {sbn} ({'বিনামূল্যে কোটা' if b.free_used else 'হার'})", b.fee),
                 (f"{label}: extra {b.ext_hours} hour(s)", f"{label_bn}: অতিরিক্ত {b.ext_hours} ঘণ্টা", b.ext_fee), (f"{label}: cleaning fee", f"{label_bn}: পরিচ্ছন্নতা ফি", b.cleaning),
                 (f"{label}: generator", f"{label_bn}: জেনারেটর", b.generator), (f"{label}: refundable deposit", f"{label_bn}: ফেরতযোগ্য জামানত", b.deposit)]
        for en, bn, amt in lines:
            if amt > 0 or (b.free_used and en.endswith("(free quota)")):
                db.add(InvoiceLine(invoice_id=inv.id, description=en[:120], description_bn=bn[:120], amount=amt))
        b.invoice_id, b.status = inv.id, "approved"
        b.expires_at = datetime.combine(due, datetime.max.time().replace(microsecond=0), tzinfo=timezone.utc)
        _notify(db, org, ctx.property.id, b, a, "booking_approved",
                f"{bname}: your {a.name} booking on {b.on_date:%d %b} ({sname}) is approved. Pay {_bdt(b.total)} by {due:%d %b} to confirm.",
                f"{ctx.property.name_bn or bname}: {b.on_date:%d %b} তারিখে ({sbn}) {a.name_bn or a.name} বুকিং অনুমোদিত। নিশ্চিত করতে {due:%d %b} এর মধ্যে {_bdt(b.total)} পরিশোধ করুন।")
    _log(db, ctx, "amenity.booking.approve", "booking", b.id, {"total": b.total, "invoice": b.invoice_id})
    db.commit()
    return _rows_for(db, [b], ctx)[0]


@router.post("/bookings/{bid}/reject")
def reject(bid: int, body: ReasonIn, ctx: Ctx = Depends(property_ctx), db: Session = Depends(get_db)):
    _gate(ctx)
    ctx.need(*APPROVE)
    b = _booking(db, ctx, bid)
    if b.status != "pending":
        raise HTTPException(409, "This request was already decided")
    if len(body.reason.strip()) < 3:
        raise HTTPException(422, "Please give a reason")
    a = db.get(Amenity, b.amenity_id)
    b.status, b.reason, b.decided_by, b.decided_at = "rejected", body.reason.strip(), ctx.user.id, now()
    bname = ctx.property.name
    _notify(db, ctx.property.org_id, ctx.property.id, b, a, "booking_rejected", f"{bname}: your {a.name} request for {b.on_date:%d %b} was not approved. Reason: {b.reason}",
            f"{ctx.property.name_bn or bname}: {b.on_date:%d %b} তারিখের {a.name_bn or a.name} অনুরোধ অনুমোদিত হয়নি। কারণ: {b.reason}")
    _log(db, ctx, "amenity.booking.reject", "booking", b.id, {"reason": b.reason})
    db.commit()
    return _rows_for(db, [b], ctx)[0]


def refund_for(a: Amenity, b: Booking, paid: int, today: date) -> tuple[int, int]:
    """Deposit back in full, plus a share of the other money by days left before the event. Returns (refund, percent)."""
    left = (b.on_date - today).days
    pct = 0
    for r in sorted(a.cancel_rules or DEFAULT_CANCEL, key=lambda r: -r["days"]):
        if left >= r["days"]:
            pct = r["pct"]
            break
    dep = min(paid, b.deposit)
    return dep + (paid - dep) * pct // 100, pct


@router.post("/bookings/{bid}/cancel")
def cancel(bid: int, body: ReasonIn, ctx: Ctx = Depends(property_ctx), db: Session = Depends(get_db)):
    _gate(ctx)
    b = _booking(db, ctx, bid)
    staff = ctx.has(*APPROVE)
    if b.status not in ("pending", "approved", "confirmed"):
        raise HTTPException(409, "This booking cannot be cancelled now")
    if not staff and (b.on_date < date.today() or not (b.user_id == ctx.user.id or b.unit_id in ctx.unit_ids)):
        raise HTTPException(403, "Your role cannot do this")
    a = db.get(Amenity, b.amenity_id)
    inv = db.get(Invoice, b.invoice_id) if b.invoice_id else None
    paid = inv.paid if inv else 0
    refund, pct = refund_for(a, b, paid, date.today()) if paid else (0, 0)
    _release(db, b)
    b.status, b.reason = "cancelled", body.reason.strip()
    b.refund_amount = refund
    if inv and paid == 0 and inv.status != "void":
        inv.status = "void"
    _log(db, ctx, "amenity.booking.cancel", "booking", b.id, {"paid": paid, "refund": refund, "pct": pct, "by_staff": staff})
    db.commit()
    return _rows_for(db, [b], ctx)[0]


class HandoverIn(BaseModel):
    damage_amount: int = Field(default=0, ge=0)
    damage_note: str = Field(default="", max_length=300)
    refund_method: str = Field(default="cash", pattern="^(cash|bank|bkash|nagad)$")


@router.post("/bookings/{bid}/handover")
def handover(bid: int, body: HandoverIn, ctx: Ctx = Depends(property_ctx), db: Session = Depends(get_db)):
    """After the event: note any damage and release the rest of the deposit. Recorded and audit-logged; the deposit is not a ledger event."""
    _gate(ctx)
    ctx.need(*HANDOVER)
    b = _booking(db, ctx, bid)
    if b.status != "confirmed":
        raise HTTPException(409, "Only a confirmed booking can be handed over")
    if b.on_date > date.today():
        raise HTTPException(409, "The event has not happened yet")
    if body.damage_amount > b.deposit:
        raise HTTPException(422, "Damage cannot be more than the deposit")
    if body.damage_amount and len(body.damage_note.strip()) < 3:
        raise HTTPException(422, "Describe the damage")
    b.damage_amount, b.damage_note = body.damage_amount, body.damage_note.strip()
    b.refund_amount, b.refund_method, b.refunded_at = b.deposit - body.damage_amount, body.refund_method, now()
    if b.refund_amount == 0:
        b.refund_method, b.refunded_at = "", None
    b.status, b.handover_by, b.handover_at = "completed", ctx.user.id, now()
    _log(db, ctx, "amenity.booking.handover", "booking", b.id, {"damage": b.damage_amount, "refund": b.refund_amount, "method": b.refund_method})
    db.commit()
    return _rows_for(db, [b], ctx)[0]


class RefundIn(BaseModel):
    method: str = Field(pattern="^(cash|bank|bkash|nagad)$")


@router.post("/bookings/{bid}/refund")
def refund(bid: int, body: RefundIn, ctx: Ctx = Depends(property_ctx), db: Session = Depends(get_db)):
    """Records that a cancellation refund was paid back."""
    _gate(ctx)
    ctx.need(*REFUNDERS)
    b = _booking(db, ctx, bid)
    if b.refund_amount <= 0 or b.refunded_at:
        raise HTTPException(409, "No refund is waiting")
    b.refund_method, b.refunded_at = body.method, now()
    _log(db, ctx, "amenity.booking.refund", "booking", b.id, {"amount": b.refund_amount, "method": body.method})
    db.commit()
    return _rows_for(db, [b], ctx)[0]


@router.post("/expire")
def expire(ctx: Ctx = Depends(property_ctx), db: Session = Depends(get_db)):
    _gate(ctx)
    ctx.need(*APPROVE)
    return {"expired": expire_stale(db, ctx.property.id)}


@router.get("/bookings/{bid}/permit")
def permit(bid: int, ctx: Ctx = Depends(property_ctx), db: Session = Depends(get_db)):
    """What the guard checks at the door."""
    _gate(ctx)
    b = _booking(db, ctx, bid)
    if b.status not in ("confirmed", "completed"):
        raise HTTPException(409, "Only a confirmed booking has a permit")
    a, u, usr = db.get(Amenity, b.amenity_id), db.get(Unit, b.unit_id), db.get(User, b.user_id)
    return {"permit_no": f"PM-{b.property_id}-{b.id:05d}", "building": ctx.property.name, "building_bn": ctx.property.name_bn, "address": ctx.property.address,
            "amenity": a.name, "amenity_bn": a.name_bn, "kind": a.kind, "on_date": b.on_date.isoformat(), "slot": b.slot, "hours": list(SLOTS[b.slot]), "ext_hours": b.ext_hours,
            "unit": u.number, "holder": usr.name if usr else "", "holder_bn": usr.name_bn if usr else "", "party": b.party, "contact": b.contact, "purpose": b.purpose, "guests": b.guests,
            "capacity": a.capacity, "catering": b.catering, "rules": a.rules, "rules_bn": a.rules_bn, "status": b.status, "confirmed_at": b.confirmed_at.isoformat() if b.confirmed_at else None}


# ---------------- calendar
@router.get("/{aid}/calendar")
def calendar(aid: int, month: str = "", ctx: Ctx = Depends(property_ctx), db: Session = Depends(get_db)):
    """A month grid for one amenity. Each slot is free, pending, held (approved, waiting for payment), booked or blackout. Names are shown to staff only."""
    _gate(ctx)
    a = _get_amenity(db, ctx, aid)
    expire_stale(db, ctx.property.id)
    try:
        y, m = (int(month[:4]), int(month[5:7])) if month else (date.today().year, date.today().month)
        first = date(y, m, 1)
    except ValueError:
        raise HTTPException(422, "Month must look like 2026-11")
    last = (date(y + (m == 12), m % 12 + 1, 1)) - timedelta(days=1)
    bs = db.scalars(select(Booking).where(Booking.amenity_id == a.id, Booking.on_date >= first, Booking.on_date <= last, Booking.status.in_(LIVE))).all()
    blk = {b.on_date: b for b in db.scalars(select(Blackout).where(Blackout.property_id == ctx.property.id, Blackout.on_date >= first, Blackout.on_date <= last, or_(Blackout.amenity_id == a.id, Blackout.amenity_id.is_(None))))}
    staff = ctx.has(*SEE_ALL)
    today = date.today()
    days = []
    for i in range((last - first).days + 1):
        d = first + timedelta(days=i)
        slots = {}
        for s in SLOTS:
            if not ((a.slots or {}).get(s) or {}).get("on"):
                continue
            cell = {"state": "free", "booking_id": None, "mine": False}
            for b in bs:
                if b.on_date != d or not set(PARTS[b.slot]) & set(PARTS[s]):
                    continue
                state = "booked" if b.status in ("confirmed", "completed") else "held" if b.status == "approved" else "pending"
                rank = {"free": 0, "pending": 1, "held": 2, "booked": 3}
                if rank[state] > rank[cell["state"]]:
                    cell["state"] = state
                mine = b.user_id == ctx.user.id or b.unit_id in ctx.unit_ids
                if mine or (staff and rank[state] >= rank[cell["state"]]):
                    cell["booking_id"], cell["mine"] = b.id, cell["mine"] or mine
            slots[s] = cell
        bo = blk.get(d)
        bookable = today + timedelta(days=a.min_notice_days) <= d <= today + timedelta(days=a.max_advance_days) and not bo
        days.append({"date": d.isoformat(), "blackout": {"reason": bo.reason, "reason_bn": bo.reason_bn} if bo else None, "bookable": bookable, "past": d < today, "slots": slots})
    return {"amenity": _amenity(a), "month": f"{y}-{m:02d}", "days": days}


# ---------------- ledger and payment hooks
def ledger_credits(db: Session, p: Payment) -> list[tuple[str, int, int]] | None:
    """For a payment on a hall invoice: the fee part is income (4020), the deposit part is a liability (2010). None for any other invoice."""
    inv = db.get(Invoice, p.invoice_id)
    if not inv or not inv.period.startswith(PREFIX):
        return None
    b = db.scalar(select(Booking).where(Booking.invoice_id == inv.id))
    dep = 0
    if b and b.total and b.deposit:   # cumulative, so the parts add up to the exact deposit when the invoice is fully paid
        dep = b.deposit * min(inv.paid, b.total) // b.total - b.deposit * max(0, min(inv.paid - p.amount, b.total)) // b.total
    return [("4020", 0, p.amount - dep), ("2010", 0, dep)]


def _on_payment(db: Session, ctx: Ctx, p: Payment) -> None:
    inv = db.get(Invoice, p.invoice_id)
    if not inv or not inv.period.startswith(PREFIX) or inv.paid < inv.total:
        return
    b = db.scalar(select(Booking).where(Booking.invoice_id == inv.id))
    if not b or b.status != "approved":
        return
    b.status, b.confirmed_at = "confirmed", now()
    a = db.get(Amenity, b.amenity_id)
    prop = ctx.property
    _notify(db, prop.org_id, prop.id, b, a, "booking_confirmed", f"{prop.name}: your {a.name} booking on {b.on_date:%d %b} ({SLOT_EN[b.slot]}) is confirmed. Show the permit at the gate.",
            f"{prop.name_bn or prop.name}: {b.on_date:%d %b} তারিখে ({SLOT_BN[b.slot]}) {a.name_bn or a.name} বুকিং নিশ্চিত। গেটে পারমিট দেখান।")
    audit(db, user_id=ctx.user.id, org_id=prop.org_id, property_id=prop.id, action="amenity.booking.confirm", entity="booking", entity_id=b.id, meta={"payment": p.id})


B.POST_VERIFY.append(_on_payment)   # a fully paid hall invoice confirms its booking
