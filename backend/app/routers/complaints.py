"""Service requests (complaints): residents raise them, staff triage and fix them, an SLA clock marks the late ones."""
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from ..audit import audit
from ..db import get_db
from ..deps import Ctx, property_ctx
from ..models.core import Membership, User, now
from ..models.property import Unit
from ..models.requests import RequestComment, ServiceRequest, SlaRule
from ..permissions import COMMITTEE, MANAGE, RESIDENT

router = APIRouter(prefix="/api/requests", tags=["requests"])
CATEGORIES = ("lift", "water", "electricity", "security", "cleaning", "noise", "other")
DEFAULT_SLA = {"lift": 24, "water": 12, "electricity": 12, "security": 6, "cleaning": 48, "noise": 24, "other": 72}
STATUSES = ("open", "assigned", "in_progress", "resolved", "closed")
OPEN_STATES = ("open", "assigned", "in_progress")
TRIAGE = MANAGE | COMMITTEE | {"CARETAKER"}
SEE_ALL = TRIAGE | {"AUDITOR"}
STAFF_ROLES = MANAGE | {"CARETAKER", "GUARD"}
SLA_EDIT = MANAGE | {"PRESIDENT", "SECRETARY"}
CAT_PAT = "^(" + "|".join(CATEGORIES) + ")$"


def _aware(dt: datetime | None) -> datetime | None:
    return dt.replace(tzinfo=timezone.utc) if dt and dt.tzinfo is None else dt


def _gate(ctx: Ctx) -> None:
    ctx.feature("committee")


def _sla(db: Session, pid: int) -> dict[str, int]:
    out = dict(DEFAULT_SLA)
    for r in db.scalars(select(SlaRule).where(SlaRule.property_id == pid)):
        out[r.category] = r.hours
    return out


def _overdue(r: ServiceRequest) -> bool:
    return r.status in OPEN_STATES and now() > _aware(r.due_at)


def _row(r: ServiceRequest, units: dict, users: dict) -> dict:
    u = units.get(r.unit_id)
    return {"id": r.id, "category": r.category, "title": r.title, "text": r.text, "status": r.status, "unit_id": r.unit_id, "unit": u.number if u else "",
            "raised_by": users.get(r.raised_by, ""), "assignee_id": r.assignee_id, "assignee": users.get(r.assignee_id, "") if r.assignee_id else "",
            "created_at": r.created_at.isoformat(), "due_at": r.due_at.isoformat(), "sla_hours": r.sla_hours, "overdue": _overdue(r),
            "resolved_at": r.resolved_at.isoformat() if r.resolved_at else None, "closed_at": r.closed_at.isoformat() if r.closed_at else None,
            "reopened": r.reopened, "rating": r.rating, "rating_note": r.rating_note}


def _users(db: Session) -> dict:
    return {u.id: u.name for u in db.scalars(select(User))}


def _units(db: Session, ctx: Ctx) -> dict:
    return {u.id: u for u in db.scalars(select(Unit).where(Unit.property_id == ctx.property.id))}


def _scope(ctx: Ctx, stmt):
    if ctx.has(*SEE_ALL):
        return stmt
    if not ctx.has(*RESIDENT):
        raise HTTPException(403, "Your role cannot do this")
    return stmt.where(or_(ServiceRequest.unit_id.in_(ctx.unit_ids or {-1}), ServiceRequest.raised_by == ctx.user.id))


def _mine(db: Session, ctx: Ctx, rid: int) -> ServiceRequest:
    _gate(ctx)
    r = db.get(ServiceRequest, rid)
    if not r or r.property_id != ctx.property.id:
        raise HTTPException(404, "Not found")
    if not ctx.has(*SEE_ALL) and not (r.raised_by == ctx.user.id or (r.unit_id and r.unit_id in ctx.unit_ids)):
        raise HTTPException(404, "Not found")
    return r


def _is_owner_of(ctx: Ctx, r: ServiceRequest) -> bool:
    return r.raised_by == ctx.user.id or bool(r.unit_id and r.unit_id in ctx.unit_ids and ctx.has(*RESIDENT))


def _event(db: Session, rid: int, uid: int, text: str) -> None:
    db.add(RequestComment(request_id=rid, user_id=uid, text=text, kind="event"))


def _log(db: Session, ctx: Ctx, action: str, r: ServiceRequest, meta: dict | None = None) -> None:
    audit(db, user_id=ctx.user.id, org_id=ctx.property.org_id, property_id=ctx.property.id, action=action, entity="service_request", entity_id=r.id, meta=meta or {})


@router.get("")
def requests(q: str = "", status: str = "", category: str = "", overdue: bool = False, page: int = Query(1, ge=1), size: int = Query(10, ge=1, le=100),
             ctx: Ctx = Depends(property_ctx), db: Session = Depends(get_db)):
    _gate(ctx)
    stmt = _scope(ctx, select(ServiceRequest).where(ServiceRequest.property_id == ctx.property.id))
    if status in STATUSES:
        stmt = stmt.where(ServiceRequest.status == status)
    if category in CATEGORIES:
        stmt = stmt.where(ServiceRequest.category == category)
    if q.strip():
        stmt = stmt.where(ServiceRequest.title.ilike(f"%{q.strip()}%"))
    if overdue:
        stmt = stmt.where(ServiceRequest.status.in_(OPEN_STATES), ServiceRequest.due_at < now())
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = db.scalars(stmt.order_by(ServiceRequest.created_at.desc(), ServiceRequest.id.desc()).offset((page - 1) * size).limit(size)).all()
    units, users = _units(db, ctx), _users(db)
    return {"items": [_row(r, units, users) for r in rows], "total": total, "page": page, "size": size}


@router.get("/summary")
def summary(ctx: Ctx = Depends(property_ctx), db: Session = Depends(get_db)):
    _gate(ctx)
    rows = db.scalars(_scope(ctx, select(ServiceRequest).where(ServiceRequest.property_id == ctx.property.id))).all()
    counts = {s: sum(1 for r in rows if r.status == s) for s in STATUSES}
    rated = [r.rating for r in rows if r.rating]
    return {"counts": counts, "overdue": sum(1 for r in rows if _overdue(r)), "total": len(rows), "avg_rating": round(sum(rated) / len(rated), 1) if rated else None}


@router.get("/sla")
def sla(ctx: Ctx = Depends(property_ctx), db: Session = Depends(get_db)):
    _gate(ctx)
    hours = _sla(db, ctx.property.id)
    return [{"category": c, "hours": hours[c], "default": DEFAULT_SLA[c]} for c in CATEGORIES]


class SlaIn(BaseModel):
    hours: int = Field(ge=1, le=720)


@router.put("/sla/{category}")
def set_sla(category: str, body: SlaIn, ctx: Ctx = Depends(property_ctx), db: Session = Depends(get_db)):
    _gate(ctx)
    ctx.need(*SLA_EDIT)
    if category not in CATEGORIES:
        raise HTTPException(404, "Not found")
    row = db.scalar(select(SlaRule).where(SlaRule.property_id == ctx.property.id, SlaRule.category == category))
    old = row.hours if row else DEFAULT_SLA[category]
    if row:
        row.hours = body.hours
    else:
        db.add(SlaRule(property_id=ctx.property.id, category=category, hours=body.hours))
    audit(db, user_id=ctx.user.id, org_id=ctx.property.org_id, property_id=ctx.property.id, action="request.sla", entity="sla_rule", entity_id=category, meta={"from": old, "to": body.hours})
    db.commit()
    return {"category": category, "hours": body.hours}


@router.get("/assignees")
def assignees(ctx: Ctx = Depends(property_ctx), db: Session = Depends(get_db)):
    _gate(ctx)
    ctx.need(*TRIAGE)
    ids = {m.user_id: m.role for m in db.scalars(select(Membership).where(Membership.org_id == ctx.property.org_id, Membership.role.in_(list(STAFF_ROLES)))) if m.property_id in (ctx.property.id, None)}
    users = {u.id: u for u in db.scalars(select(User).where(User.id.in_(list(ids) or [-1])))}
    return sorted([{"id": i, "name": users[i].name, "name_bn": users[i].name_bn, "role": ids[i]} for i in ids if i in users], key=lambda x: x["name"])


class RequestIn(BaseModel):
    category: str = Field(pattern=CAT_PAT)
    title: str = Field(min_length=3, max_length=160)
    text: str = Field(default="", max_length=4000)
    unit_id: int | None = None


@router.post("", status_code=201)
def raise_request(body: RequestIn, ctx: Ctx = Depends(property_ctx), db: Session = Depends(get_db)):
    _gate(ctx)
    if not ctx.has(*RESIDENT, *TRIAGE):
        raise HTTPException(403, "Your role cannot do this")
    unit_id = body.unit_id
    if unit_id:
        u = db.get(Unit, unit_id)
        if not u or u.property_id != ctx.property.id:
            raise HTTPException(404, "Flat not found")
        if not ctx.has(*TRIAGE) and unit_id not in ctx.unit_ids:
            raise HTTPException(403, "You can only raise a request for your own flat")
    elif ctx.unit_ids and not ctx.has(*TRIAGE):
        unit_id = sorted(ctx.unit_ids)[0]
    hours = _sla(db, ctx.property.id)[body.category]
    r = ServiceRequest(property_id=ctx.property.id, unit_id=unit_id, raised_by=ctx.user.id, category=body.category, title=body.title.strip(), text=body.text.strip(),
                       sla_hours=hours, due_at=now() + timedelta(hours=hours))
    db.add(r)
    db.flush()
    _event(db, r.id, ctx.user.id, "raised")
    _log(db, ctx, "request.raise", r, {"category": r.category})
    db.commit()
    return _row(r, _units(db, ctx), _users(db))


@router.get("/{rid}")
def detail(rid: int, ctx: Ctx = Depends(property_ctx), db: Session = Depends(get_db)):
    r = _mine(db, ctx, rid)
    users = _users(db)
    d = _row(r, _units(db, ctx), users)
    d["thread"] = [{"id": c.id, "by": users.get(c.user_id, ""), "text": c.text, "kind": c.kind, "at": c.at.isoformat()} for c in db.scalars(select(RequestComment).where(RequestComment.request_id == r.id).order_by(RequestComment.id))]
    d["can_triage"] = ctx.has(*TRIAGE)
    d["can_reopen"] = r.status in ("resolved", "closed") and r.reopened == 0 and _is_owner_of(ctx, r)
    d["can_rate"] = r.status in ("resolved", "closed") and r.rating is None and _is_owner_of(ctx, r)
    return d


class AssignIn(BaseModel):
    assignee_id: int


@router.post("/{rid}/assign")
def assign(rid: int, body: AssignIn, ctx: Ctx = Depends(property_ctx), db: Session = Depends(get_db)):
    r = _mine(db, ctx, rid)
    ctx.need(*TRIAGE)
    if r.status in ("resolved", "closed"):
        raise HTTPException(409, "This request is already resolved")
    if not any(a["id"] == body.assignee_id for a in assignees(ctx, db)):
        raise HTTPException(404, "Staff member not found")
    r.assignee_id, r.assigned_at = body.assignee_id, now()
    if r.status == "open":
        r.status = "assigned"
    _event(db, r.id, ctx.user.id, f"assigned:{_users(db).get(body.assignee_id, '')}")
    _log(db, ctx, "request.assign", r, {"assignee_id": body.assignee_id})
    db.commit()
    return _row(r, _units(db, ctx), _users(db))


class StatusIn(BaseModel):
    status: str = Field(pattern="^(in_progress|resolved|closed)$")


@router.post("/{rid}/status")
def set_status(rid: int, body: StatusIn, ctx: Ctx = Depends(property_ctx), db: Session = Depends(get_db)):
    r = _mine(db, ctx, rid)
    resident_close = body.status == "closed" and r.status == "resolved" and _is_owner_of(ctx, r) and not ctx.has(*TRIAGE)
    if not resident_close:
        ctx.need(*TRIAGE)
    if STATUSES.index(body.status) <= STATUSES.index(r.status):
        raise HTTPException(409, "A request only moves forward")
    if body.status == "in_progress" and not r.assignee_id:
        raise HTTPException(409, "Assign someone first")
    old, r.status = r.status, body.status
    if body.status == "resolved":
        r.resolved_at = now()
    if body.status == "closed":
        r.closed_at = now()
        r.resolved_at = r.resolved_at or r.closed_at
    _event(db, r.id, ctx.user.id, f"status:{r.status}")
    _log(db, ctx, "request.status", r, {"from": old, "to": r.status})
    db.commit()
    return _row(r, _units(db, ctx), _users(db))


@router.post("/{rid}/reopen")
def reopen(rid: int, ctx: Ctx = Depends(property_ctx), db: Session = Depends(get_db)):
    r = _mine(db, ctx, rid)
    if not _is_owner_of(ctx, r):
        raise HTTPException(403, "Only the resident who raised it can reopen")
    if r.status not in ("resolved", "closed"):
        raise HTTPException(409, "Only a resolved request can be reopened")
    if r.reopened >= 1:
        raise HTTPException(409, "A request can be reopened only once")
    r.reopened, r.status, r.resolved_at, r.closed_at, r.rating, r.rating_note = 1, "assigned" if r.assignee_id else "open", None, None, None, ""
    r.due_at = now() + timedelta(hours=r.sla_hours)
    _event(db, r.id, ctx.user.id, "reopened")
    _log(db, ctx, "request.reopen", r)
    db.commit()
    return _row(r, _units(db, ctx), _users(db))


class RateIn(BaseModel):
    rating: int = Field(ge=1, le=5)
    note: str = Field(default="", max_length=300)


@router.post("/{rid}/rate")
def rate(rid: int, body: RateIn, ctx: Ctx = Depends(property_ctx), db: Session = Depends(get_db)):
    r = _mine(db, ctx, rid)
    if not _is_owner_of(ctx, r):
        raise HTTPException(403, "Only the resident who raised it can rate")
    if r.status not in ("resolved", "closed"):
        raise HTTPException(409, "Rate the fix after it is resolved")
    if r.rating is not None:
        raise HTTPException(409, "Already rated")
    r.rating, r.rating_note = body.rating, body.note.strip()
    _event(db, r.id, ctx.user.id, f"rated:{body.rating}")
    _log(db, ctx, "request.rate", r, {"rating": body.rating})
    db.commit()
    return _row(r, _units(db, ctx), _users(db))


class CommentIn(BaseModel):
    text: str = Field(min_length=1, max_length=2000)


@router.post("/{rid}/comments", status_code=201)
def comment(rid: int, body: CommentIn, ctx: Ctx = Depends(property_ctx), db: Session = Depends(get_db)):
    r = _mine(db, ctx, rid)
    db.add(RequestComment(request_id=r.id, user_id=ctx.user.id, text=body.text.strip()))
    _log(db, ctx, "request.comment", r)
    db.commit()
    return {"ok": True}
