"""New-customer setup wizard. Progress is saved per building on the server.

The wizard itself reuses the normal endpoints (PUT /api/property, POST /api/units/generate, POST /api/billing/rules).
This router only remembers what is done, keeps the small answers (due day, reminders) and creates committee sign-ins.
"""
import secrets
from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..audit import audit
from ..db import get_db
from ..deps import Ctx, property_ctx
from ..models.billing import ChargeRule
from ..models.core import Membership, User, now
from ..models.jobs import BuildingAutomation
from ..models.property import Unit
from ..models.requests import CommitteeMember
from ..models.setup import SetupProgress
from ..permissions import MANAGE
from ..security import hash_password

router = APIRouter(prefix="/api/setup", tags=["setup"])

STEPS = ["building", "flats", "charges", "reminders", "committee", "review"]
REMINDER_STEPS = ["before", "due", "o7", "o15", "o30"]
COMMITTEE_ROLES = ["PRESIDENT", "SECRETARY", "TREASURER", "MEMBER"]


class StepState(BaseModel):
    step: str
    state: str = Field(description="done | skipped | known | todo. 'known' means FlatWise already has the answer, so the wizard does not ask.")


class SetupOut(BaseModel):
    applicable: bool = Field(description="False for a building that was set up before the wizard existed, or for a role that does not set buildings up.")
    completed: bool = False
    dismissed: bool = False
    steps: list[StepState] = []
    percent: int = 0
    next_step: str | None = None
    data: dict = {}
    known: dict = {}
    features: list[str] = []


class StepIn(BaseModel):
    state: str = Field(pattern="^(done|skipped|todo)$")


class DataIn(BaseModel):
    due_day: int | None = Field(default=None, ge=1, le=28)
    reminders_enabled: bool | None = None
    reminder_steps: list[str] | None = None


class MemberIn(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    email: str = Field(min_length=5, max_length=160)
    phone: str = Field(default="", max_length=32)
    role: str = Field(pattern="^(PRESIDENT|SECRETARY|TREASURER|MEMBER)$")


class CommitteeIn(BaseModel):
    members: list[MemberIn] = Field(min_length=1, max_length=8)


class MemberOut(BaseModel):
    email: str
    role: str
    ok: bool
    temp_password: str | None = None
    error: str = ""


class CommitteeOut(BaseModel):
    results: list[MemberOut]


def _row(db: Session, ctx: Ctx, create: bool = False) -> SetupProgress | None:
    row = db.scalar(select(SetupProgress).where(SetupProgress.property_id == ctx.property.id))
    if row or not create:
        return row
    row = SetupProgress(property_id=ctx.property.id, steps={}, data={})
    db.add(row)
    db.flush()
    return row


def _due_day(db: Session, pid: int, row: SetupProgress) -> int | None:
    """The saved due day: the building's automation setting wins, then the wizard's own answer."""
    auto = db.get(BuildingAutomation, pid)
    if auto and (row.data or {}).get("due_day") is not None:
        return auto.due_day
    return (row.data or {}).get("due_day")


def _known(db: Session, ctx: Ctx, row: SetupProgress) -> dict:
    p = ctx.property
    units = db.scalar(select(func.count()).select_from(Unit).where(Unit.property_id == p.id)) or 0
    rules = db.scalar(select(func.count()).select_from(ChargeRule).where(ChargeRule.property_id == p.id)) or 0
    members = db.scalar(select(func.count()).select_from(CommitteeMember).where(CommitteeMember.property_id == p.id)) or 0
    return {"building": {"name": p.name, "name_bn": p.name_bn, "address": p.address, "city": p.city, "floors": p.floors},
            "units": units, "rules": rules, "committee": members,
            "due_day": _due_day(db, p.id, row)}


def _state(step: str, row: SetupProgress, known: dict) -> str:
    saved = (row.steps or {}).get(step)
    if saved in ("done", "skipped"):
        return saved
    b = known["building"]
    have = {"building": bool(b["address"]) and b["floors"] > 0, "flats": known["units"] > 0, "charges": known["rules"] > 0,
            "reminders": known["due_day"] is not None, "committee": known["committee"] > 0, "review": False}[step]
    return "known" if have else "todo"


def _out(db: Session, ctx: Ctx, row: SetupProgress) -> SetupOut:
    known = _known(db, ctx, row)
    steps = [StepState(step=s, state=_state(s, row, known)) for s in STEPS]
    left = [s.step for s in steps if s.state == "todo"]
    finished = sum(s.state != "todo" for s in steps)
    return SetupOut(applicable=True, completed=row.completed_at is not None, dismissed=row.dismissed_at is not None, steps=steps,
                    percent=round(100 * finished / len(STEPS)), next_step=left[0] if left else None, data=row.data or {}, known=known,
                    features=sorted(ctx.features & {"billing", "reminders", "parking", "committee"}))


@router.get("", response_model=SetupOut, summary="Setup wizard progress for the current building")
def get_setup(ctx: Ctx = Depends(property_ctx), db: Session = Depends(get_db)):
    """A building with no flats and no charge rules is treated as new and gets a progress row on first call.
    A building that already has flats or charges, and no row, was set up by hand: `applicable` is false and the wizard never shows."""
    if not ctx.has(*MANAGE) or (ctx.saas_staff and not ctx.roles & MANAGE):
        return SetupOut(applicable=False)
    row = _row(db, ctx)
    if not row:
        fresh = not db.scalar(select(func.count()).select_from(Unit).where(Unit.property_id == ctx.property.id)) \
            and not db.scalar(select(func.count()).select_from(ChargeRule).where(ChargeRule.property_id == ctx.property.id))
        if not fresh:
            return SetupOut(applicable=False)
        row = _row(db, ctx, create=True)
        db.commit()
    return _out(db, ctx, row)


def _need_row(db: Session, ctx: Ctx) -> SetupProgress:
    ctx.need(*MANAGE)
    return _row(db, ctx, create=True)  # type: ignore[return-value]


@router.put("/steps/{step}", response_model=SetupOut, summary="Mark one setup step done, skipped or to do")
def put_step(step: str, body: StepIn, ctx: Ctx = Depends(property_ctx), db: Session = Depends(get_db)):
    if step not in STEPS:
        raise HTTPException(404, "Unknown step")
    row = _need_row(db, ctx)
    steps = dict(row.steps or {})
    if body.state == "todo":
        steps.pop(step, None)
        row.completed_at = None
    else:
        steps[step] = body.state
    row.steps, row.updated_at, row.updated_by = steps, now(), ctx.user.id
    audit(db, user_id=ctx.user.id, org_id=ctx.property.org_id, property_id=ctx.property.id, action="setup.step", entity="setup", entity_id=step, meta={"state": body.state})
    db.commit()
    return _out(db, ctx, row)


@router.put("/data", response_model=SetupOut, summary="Save the due day and reminder choices")
def put_data(body: DataIn, ctx: Ctx = Depends(property_ctx), db: Session = Depends(get_db)):
    """The due day is also saved as the building's automation due day, which the scheduled billing job uses; automatic billing itself stays off. The reminder choice is stored with the setup progress."""
    row = _need_row(db, ctx)
    data = dict(row.data or {})
    if body.due_day is not None:
        data["due_day"] = body.due_day
        auto = db.get(BuildingAutomation, ctx.property.id)   # the same due day is used by the scheduled billing job; auto_billing stays off
        if auto:
            auto.due_day = body.due_day
        else:
            db.add(BuildingAutomation(property_id=ctx.property.id, due_day=body.due_day))
    if body.reminders_enabled is not None or body.reminder_steps is not None:
        cur = dict(data.get("reminders") or {"enabled": True, "steps": REMINDER_STEPS})
        if body.reminders_enabled is not None:
            cur["enabled"] = body.reminders_enabled
        if body.reminder_steps is not None:
            if any(s not in REMINDER_STEPS for s in body.reminder_steps):
                raise HTTPException(422, "Unknown reminder step")
            cur["steps"] = [s for s in REMINDER_STEPS if s in body.reminder_steps]
        data["reminders"] = cur
    row.data, row.updated_at, row.updated_by = data, now(), ctx.user.id
    audit(db, user_id=ctx.user.id, org_id=ctx.property.org_id, property_id=ctx.property.id, action="setup.data", entity="setup", meta=data)
    db.commit()
    return _out(db, ctx, row)


@router.post("/committee", response_model=CommitteeOut, status_code=201, summary="Create committee sign-ins with temporary passwords")
def invite_committee(body: CommitteeIn, ctx: Ctx = Depends(property_ctx), db: Session = Depends(get_db)):
    """For each person: a sign-in with a one-time temporary password (shown once), the committee role in this building, and a two-year committee tenure.
    A row that fails (for example the email already has an account) is reported and the others still go through."""
    ctx.need(*MANAGE)
    out, today = [], date.today()
    for m in body.members:
        email = m.email.strip().lower()
        if "@" not in email:
            out.append(MemberOut(email=email, role=m.role, ok=False, error="Enter a valid email"))
            continue
        if db.scalar(select(User.id).where(User.email == email)):
            out.append(MemberOut(email=email, role=m.role, ok=False, error="That email already has an account"))
            continue
        temp = secrets.token_urlsafe(7)
        usr = User(email=email, name=m.name, phone=m.phone, password_hash=hash_password(temp), must_change_password=True)
        db.add(usr)
        db.flush()
        db.add(Membership(user_id=usr.id, org_id=ctx.property.org_id, property_id=ctx.property.id, role=m.role))
        db.add(CommitteeMember(property_id=ctx.property.id, user_id=usr.id, name=m.name, role=m.role.lower(), start_date=today, end_date=today + timedelta(days=730)))
        audit(db, user_id=ctx.user.id, org_id=ctx.property.org_id, property_id=ctx.property.id, action="setup.committee", entity="user", entity_id=usr.id, meta={"role": m.role})
        out.append(MemberOut(email=email, role=m.role, ok=True, temp_password=temp))
    db.commit()
    return CommitteeOut(results=out)


@router.post("/complete", response_model=SetupOut, summary="Finish the setup wizard")
def complete(ctx: Ctx = Depends(property_ctx), db: Session = Depends(get_db)):
    row = _need_row(db, ctx)
    steps = dict(row.steps or {})
    steps["review"] = "done"
    row.steps, row.completed_at, row.updated_at, row.updated_by = steps, now(), now(), ctx.user.id
    audit(db, user_id=ctx.user.id, org_id=ctx.property.org_id, property_id=ctx.property.id, action="setup.complete", entity="setup")
    db.commit()
    return _out(db, ctx, row)


@router.post("/dismiss", response_model=SetupOut, summary="Hide the dashboard setup card")
def dismiss(ctx: Ctx = Depends(property_ctx), db: Session = Depends(get_db)):
    row = _need_row(db, ctx)
    row.dismissed_at, row.updated_at = now(), now()
    db.commit()
    return _out(db, ctx, row)
