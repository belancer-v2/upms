"""The committee: members with tenure, meetings with minutes, and simple majority votes on proposals."""
from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..audit import audit
from ..db import get_db
from ..deps import Ctx, property_ctx
from ..models.core import Membership, User, now
from ..models.requests import CommitteeMember, Meeting, Proposal, ProposalVote
from ..permissions import COMMITTEE, MANAGE

router = APIRouter(prefix="/api/committee", tags=["committee"])
ROLES = ("president", "secretary", "treasurer", "member")
EDIT = MANAGE | {"PRESIDENT", "SECRETARY"}
SEE = MANAGE | COMMITTEE | {"AUDITOR"}
EXPIRING_DAYS = 90


def _gate(ctx: Ctx) -> None:
    ctx.feature("committee")
    ctx.need(*SEE)


def _log(db: Session, ctx: Ctx, action: str, entity: str, eid, meta: dict | None = None) -> None:
    audit(db, user_id=ctx.user.id, org_id=ctx.property.org_id, property_id=ctx.property.id, action=action, entity=entity, entity_id=eid, meta=meta or {})


def _page(stmt, db: Session, page: int, size: int, order):
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    return total, db.scalars(stmt.order_by(*order).offset((page - 1) * size).limit(size)).all()


# ---------------- members and tenure
def _m(m: CommitteeMember) -> dict:
    today = date.today()
    left = (m.end_date - today).days
    return {"id": m.id, "name": m.name, "name_bn": m.name_bn, "role": m.role, "user_id": m.user_id, "start_date": m.start_date.isoformat(), "end_date": m.end_date.isoformat(), "note": m.note,
            "current": m.start_date <= today <= m.end_date, "expired": m.end_date < today, "upcoming": m.start_date > today,
            "expiring_soon": 0 <= left <= EXPIRING_DAYS, "days_left": left}


@router.get("/members")
def members(scope: str = Query("current", pattern="^(current|history)$"), q: str = "", page: int = Query(1, ge=1), size: int = Query(10, ge=1, le=100),
            ctx: Ctx = Depends(property_ctx), db: Session = Depends(get_db)):
    """current = serving today. history = everyone who ever served, newest tenure first."""
    _gate(ctx)
    stmt = select(CommitteeMember).where(CommitteeMember.property_id == ctx.property.id)
    if scope == "current":
        stmt = stmt.where(CommitteeMember.start_date <= date.today(), CommitteeMember.end_date >= date.today())
    if q.strip():
        stmt = stmt.where(CommitteeMember.name.ilike(f"%{q.strip()}%"))
    total, rows = _page(stmt, db, page, size, (CommitteeMember.end_date.desc(), CommitteeMember.id))
    return {"items": [_m(m) for m in rows], "total": total, "page": page, "size": size,
            "expiring": db.scalar(select(func.count()).select_from(CommitteeMember).where(CommitteeMember.property_id == ctx.property.id, CommitteeMember.end_date >= date.today(),
                                                                                           CommitteeMember.end_date <= date.today() + timedelta(days=EXPIRING_DAYS))) or 0}


class MemberIn(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    name_bn: str = ""
    role: str = Field(pattern="^(" + "|".join(ROLES) + ")$")
    start_date: date
    end_date: date
    user_id: int | None = None
    note: str = Field(default="", max_length=200)

    @model_validator(mode="after")
    def _order(self):
        if self.end_date <= self.start_date:
            raise ValueError("The end date must be after the start date")
        return self


@router.post("/members", status_code=201)
def add_member(body: MemberIn, ctx: Ctx = Depends(property_ctx), db: Session = Depends(get_db)):
    _gate(ctx)
    ctx.need(*EDIT)
    m = CommitteeMember(property_id=ctx.property.id, **body.model_dump())
    db.add(m)
    db.flush()
    _log(db, ctx, "committee.member_add", "committee_member", m.id, {"role": m.role, "name": m.name})
    db.commit()
    return _m(m)


class TenureIn(BaseModel):
    end_date: date
    note: str = Field(default="", max_length=200)


@router.put("/members/{mid}")
def change_tenure(mid: int, body: TenureIn, ctx: Ctx = Depends(property_ctx), db: Session = Depends(get_db)):
    """Extend or end a tenure. The row stays in the history."""
    _gate(ctx)
    ctx.need(*EDIT)
    m = db.get(CommitteeMember, mid)
    if not m or m.property_id != ctx.property.id:
        raise HTTPException(404, "Not found")
    if body.end_date <= m.start_date:
        raise HTTPException(422, "The end date must be after the start date")
    old, m.end_date, m.note = m.end_date.isoformat(), body.end_date, body.note or m.note
    _log(db, ctx, "committee.tenure", "committee_member", m.id, {"from": old, "to": body.end_date.isoformat()})
    db.commit()
    return _m(m)


# ---------------- meetings
def _mt(m: Meeting, full: bool = False) -> dict:
    d = {"id": m.id, "title": m.title, "held_on": m.held_on.isoformat(), "place": m.place, "status": m.status, "present": sum(1 for a in m.attendance if a.get("present")), "invited": len(m.attendance), "decisions_n": len(m.decisions)}
    if full:
        d.update({"agenda": m.agenda, "attendance": m.attendance, "minutes": m.minutes, "decisions": m.decisions})
    return d


def _meeting(db: Session, ctx: Ctx, mid: int) -> Meeting:
    _gate(ctx)
    m = db.get(Meeting, mid)
    if not m or m.property_id != ctx.property.id:
        raise HTTPException(404, "Not found")
    return m


@router.get("/meetings")
def meetings(status: str = "", q: str = "", page: int = Query(1, ge=1), size: int = Query(10, ge=1, le=100), ctx: Ctx = Depends(property_ctx), db: Session = Depends(get_db)):
    _gate(ctx)
    stmt = select(Meeting).where(Meeting.property_id == ctx.property.id)
    if status in ("scheduled", "held", "cancelled"):
        stmt = stmt.where(Meeting.status == status)
    if q.strip():
        stmt = stmt.where(Meeting.title.ilike(f"%{q.strip()}%"))
    total, rows = _page(stmt, db, page, size, (Meeting.held_on.desc(), Meeting.id.desc()))
    return {"items": [_mt(m) for m in rows], "total": total, "page": page, "size": size}


class MeetingIn(BaseModel):
    title: str = Field(min_length=3, max_length=160)
    held_on: date
    place: str = Field(default="", max_length=160)
    agenda: str = Field(default="", max_length=4000)


@router.post("/meetings", status_code=201)
def schedule(body: MeetingIn, ctx: Ctx = Depends(property_ctx), db: Session = Depends(get_db)):
    _gate(ctx)
    ctx.need(*EDIT)
    today = date.today()
    serving = db.scalars(select(CommitteeMember).where(CommitteeMember.property_id == ctx.property.id, CommitteeMember.start_date <= today, CommitteeMember.end_date >= today).order_by(CommitteeMember.id)).all()
    m = Meeting(property_id=ctx.property.id, title=body.title.strip(), held_on=body.held_on, place=body.place.strip(), agenda=body.agenda.strip(), created_by=ctx.user.id,
                attendance=[{"member_id": s.id, "name": s.name, "name_bn": s.name_bn, "role": s.role, "present": False} for s in serving])
    db.add(m)
    db.flush()
    _log(db, ctx, "meeting.schedule", "meeting", m.id, {"held_on": body.held_on.isoformat()})
    db.commit()
    return _mt(m, True)


@router.get("/meetings/{mid}")
def meeting(mid: int, ctx: Ctx = Depends(property_ctx), db: Session = Depends(get_db)):
    return _mt(_meeting(db, ctx, mid), True)


class MinutesIn(BaseModel):
    present: list[int] = []
    minutes: str = Field(default="", max_length=20000)
    decisions: list[str] = Field(default=[], max_length=50)


@router.post("/meetings/{mid}/minutes")
def minutes(mid: int, body: MinutesIn, ctx: Ctx = Depends(property_ctx), db: Session = Depends(get_db)):
    """Records attendance, the minutes and the decisions, and marks the meeting as held."""
    m = _meeting(db, ctx, mid)
    ctx.need(*EDIT)
    if m.status == "cancelled":
        raise HTTPException(409, "This meeting was cancelled")
    if m.held_on > date.today():
        raise HTTPException(409, "The meeting has not happened yet")
    pres = set(body.present)
    m.attendance = [{**a, "present": a["member_id"] in pres} for a in m.attendance]
    m.minutes, m.decisions, m.status = body.minutes.strip(), [d.strip() for d in body.decisions if d.strip()], "held"
    _log(db, ctx, "meeting.minutes", "meeting", m.id, {"present": len(pres), "decisions": len(m.decisions)})
    db.commit()
    return _mt(m, True)


@router.post("/meetings/{mid}/cancel")
def cancel(mid: int, ctx: Ctx = Depends(property_ctx), db: Session = Depends(get_db)):
    m = _meeting(db, ctx, mid)
    ctx.need(*EDIT)
    if m.status != "scheduled":
        raise HTTPException(409, "Only a scheduled meeting can be cancelled")
    m.status = "cancelled"
    _log(db, ctx, "meeting.cancel", "meeting", m.id)
    db.commit()
    return _mt(m, True)


# ---------------- votes
def _voters(db: Session, ctx: Ctx) -> set[int]:
    return {m.user_id for m in db.scalars(select(Membership).where(Membership.org_id == ctx.property.org_id, Membership.role.in_(list(COMMITTEE)))) if m.property_id in (ctx.property.id, None)}


def _result(approve: int, reject: int) -> str:
    return "approved" if approve > reject else "rejected" if reject > approve else "tied"


def _p(db: Session, p: Proposal, ctx: Ctx, users: dict | None = None) -> dict:
    users = users or dict(db.execute(select(User.id, User.name)).all())
    votes = db.scalars(select(ProposalVote).where(ProposalVote.proposal_id == p.id)).all()
    mine = next((v.choice for v in votes if v.user_id == ctx.user.id), None)
    eligible = len(_voters(db, ctx))
    tally = p.tally if p.status == "closed" else {"approve": sum(1 for v in votes if v.choice == "approve"), "reject": sum(1 for v in votes if v.choice == "reject"), "eligible": eligible}
    d = {"id": p.id, "title": p.title, "text": p.text, "status": p.status, "result": p.result, "tally": tally, "voted": len(votes), "my_vote": mine, "can_vote": p.status == "open" and ctx.has(*COMMITTEE) and mine is None,
         "created_by": users.get(p.created_by, ""), "created_at": p.created_at.isoformat(), "closed_at": p.closed_at.isoformat() if p.closed_at else None}
    d["votes"] = [{"name": users.get(v.user_id, ""), "choice": v.choice, "at": v.at.isoformat()} for v in votes] if p.status == "closed" else []
    return d


def _proposal(db: Session, ctx: Ctx, pid: int) -> Proposal:
    _gate(ctx)
    p = db.get(Proposal, pid)
    if not p or p.property_id != ctx.property.id:
        raise HTTPException(404, "Not found")
    return p


@router.get("/proposals")
def proposals(status: str = "", q: str = "", page: int = Query(1, ge=1), size: int = Query(10, ge=1, le=100), ctx: Ctx = Depends(property_ctx), db: Session = Depends(get_db)):
    _gate(ctx)
    stmt = select(Proposal).where(Proposal.property_id == ctx.property.id)
    if status in ("open", "closed"):
        stmt = stmt.where(Proposal.status == status)
    if q.strip():
        stmt = stmt.where(Proposal.title.ilike(f"%{q.strip()}%"))
    total, rows = _page(stmt, db, page, size, (Proposal.status.desc(), Proposal.created_at.desc(), Proposal.id.desc()))   # "open" sorts before "closed" when descending
    users = dict(db.execute(select(User.id, User.name)).all())
    return {"items": [_p(db, p, ctx, users) for p in rows], "total": total, "page": page, "size": size}


class ProposalIn(BaseModel):
    title: str = Field(min_length=3, max_length=160)
    text: str = Field(default="", max_length=4000)


@router.post("/proposals", status_code=201)
def propose(body: ProposalIn, ctx: Ctx = Depends(property_ctx), db: Session = Depends(get_db)):
    _gate(ctx)
    ctx.need(*(EDIT | COMMITTEE))
    p = Proposal(property_id=ctx.property.id, title=body.title.strip(), text=body.text.strip(), created_by=ctx.user.id)
    db.add(p)
    db.flush()
    _log(db, ctx, "proposal.create", "proposal", p.id)
    db.commit()
    return _p(db, p, ctx)


class VoteIn(BaseModel):
    choice: str = Field(pattern="^(approve|reject)$")


@router.post("/proposals/{pid}/vote")
def vote(pid: int, body: VoteIn, ctx: Ctx = Depends(property_ctx), db: Session = Depends(get_db)):
    p = _proposal(db, ctx, pid)
    if ctx.user.id not in _voters(db, ctx):   # only committee members vote, never SaaS staff or managers
        raise HTTPException(403, "Your role cannot do this")
    if p.status != "open":
        raise HTTPException(409, "Voting is closed")
    if db.scalar(select(ProposalVote.id).where(ProposalVote.proposal_id == p.id, ProposalVote.user_id == ctx.user.id)):
        raise HTTPException(409, "You have already voted")
    db.add(ProposalVote(proposal_id=p.id, user_id=ctx.user.id, choice=body.choice))
    _log(db, ctx, "proposal.vote", "proposal", p.id, {"choice": body.choice})
    db.commit()
    return _p(db, p, ctx)


@router.post("/proposals/{pid}/close")
def close(pid: int, ctx: Ctx = Depends(property_ctx), db: Session = Depends(get_db)):
    """Counts the votes, applies the majority rule and locks the result."""
    p = _proposal(db, ctx, pid)
    ctx.need(*EDIT)
    if p.status != "open":
        raise HTTPException(409, "Voting is already closed")
    votes = db.scalars(select(ProposalVote).where(ProposalVote.proposal_id == p.id)).all()
    a, r = sum(1 for v in votes if v.choice == "approve"), sum(1 for v in votes if v.choice == "reject")
    p.tally, p.result, p.status, p.closed_at = {"approve": a, "reject": r, "eligible": len(_voters(db, ctx))}, _result(a, r), "closed", now()
    _log(db, ctx, "proposal.close", "proposal", p.id, {"result": p.result, "approve": a, "reject": r})
    db.commit()
    return _p(db, p, ctx)
