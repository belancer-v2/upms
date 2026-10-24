"""Notices: who they are for, who has read them, and who still needs a nudge. Policies: versions and acceptance."""
import secrets
from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..audit import audit
from ..db import get_db
from ..deps import Ctx, property_ctx
from ..models.billing import Message
from ..models.core import Membership, User, now
from ..models.notice import Notice, Policy, PolicyAcceptance, PolicyVersion, Receipt
from ..models.property import Occupancy, Unit
from ..permissions import COMMITTEE, MANAGE
from ..services.messaging import deliver

router = APIRouter(prefix="/api/notices", tags=["notices"])
pol = APIRouter(prefix="/api/policies", tags=["policies"])
PUBLISH = MANAGE | {"PRESIDENT", "SECRETARY"}
REACH = MANAGE | COMMITTEE
RES = {"FLAT_OWNER", "OWNER_REP"}
AUDIENCES = ("all", "owners", "tenants", "committee")


def _in_audience(ctx: Ctx, aud: str) -> bool:
    if ctx.has(*MANAGE) or aud == "all" and ctx.has(*(RES | {"TENANT"} | COMMITTEE)):
        return True
    return (aud == "owners" and ctx.has(*(RES | COMMITTEE))) or (aud == "tenants" and ctx.has("TENANT")) or (aud == "committee" and ctx.has(*COMMITTEE))


def _recipients(db: Session, ctx: Ctx, aud: str) -> list[dict]:
    out, seen = [], set()
    units = {u.id: u.number for u in db.scalars(select(Unit).where(Unit.property_id == ctx.property.id))}
    if aud in ("all", "owners", "tenants"):
        kinds = {"all": ("owner", "tenant"), "owners": ("owner",), "tenants": ("tenant",)}[aud]
        for o in db.scalars(select(Occupancy).where(Occupancy.unit_id.in_(list(units)), Occupancy.active, Occupancy.kind.in_(kinds))):
            out.append({"name": o.name, "unit": units[o.unit_id], "phone": o.phone, "user_id": o.user_id})
            seen.add(o.user_id)
    if aud in ("all", "committee"):
        for m in db.scalars(select(Membership).where(Membership.property_id == ctx.property.id, Membership.role.in_(list(COMMITTEE)))):
            if m.user_id in seen:
                continue
            u = db.get(User, m.user_id)
            seen.add(m.user_id)
            out.append({"name": u.name, "unit": "", "phone": u.phone, "user_id": u.id})
    return out


def _n(db: Session, n: Notice, ctx: Ctx, mine: Receipt | None, users: dict) -> dict:
    d = {"id": n.id, "title": n.title, "title_bn": n.title_bn, "body": n.body, "body_bn": n.body_bn, "audience": n.audience, "priority": n.priority, "pinned": n.pinned, "status": n.status,
         "at": n.created_at.isoformat(), "by": users.get(n.created_by, ""), "read": bool(mine and mine.read_at)}
    if ctx.has(*REACH):
        rows = db.scalars(select(Receipt).where(Receipt.notice_id == n.id)).all()
        d["reach"] = {"total": len(rows), "read": sum(1 for r in rows if r.read_at), "app": sum(1 for r in rows if r.read_via == "app"), "link": sum(1 for r in rows if r.read_via == "link"), "no_phone": sum(1 for r in rows if not r.phone and not r.read_at)}
    return d


@router.get("")
def notices(ctx: Ctx = Depends(property_ctx), db: Session = Depends(get_db)):
    ctx.feature("notices")
    users = {u.id: u.name for u in db.scalars(select(User))}
    mine = {r.notice_id: r for r in db.scalars(select(Receipt).where(Receipt.user_id == ctx.user.id))}
    out = []
    for n in db.scalars(select(Notice).where(Notice.property_id == ctx.property.id, Notice.status == "live").order_by(Notice.pinned.desc(), Notice.created_at.desc()).limit(100)):
        if _in_audience(ctx, n.audience):
            out.append(_n(db, n, ctx, mine.get(n.id), users))
    return out


class NoticeIn(BaseModel):
    title: str = Field(min_length=3, max_length=160)
    title_bn: str = ""
    body: str = Field(min_length=3)
    body_bn: str = ""
    audience: str = Field(default="all", pattern="^(all|owners|tenants|committee)$")
    priority: str = Field(default="normal", pattern="^(normal|urgent)$")
    sms: bool = False


def _sms(db: Session, ctx: Ctx, n: Notice, r: Receipt, key: str, nudge: bool = False) -> bool:
    if not r.phone:
        return False
    link = f"flatwise.app/n/{r.token}"
    title = n.title_bn or n.title
    body = f"{ctx.property.name_bn or ctx.property.name}: {'স্মরণ: ' if nudge else ''}{title}। পড়ুন: {link}"
    m = Message(property_id=ctx.property.id, to_name=r.name, to_phone=r.phone, template="notice", lang="bn", body=body, idem_key=key)
    if db.scalar(select(Message.id).where(Message.idem_key == key)):
        return False
    db.add(m)
    deliver(db, ctx.property.org_id, m)
    if m.status == "sent":
        r.sms_at = now()
    return m.status == "sent"


@router.post("", status_code=201)
def publish(body: NoticeIn, ctx: Ctx = Depends(property_ctx), db: Session = Depends(get_db)):
    ctx.feature("notices")
    ctx.need(*PUBLISH)
    n = Notice(property_id=ctx.property.id, title=body.title, title_bn=body.title_bn, body=body.body, body_bn=body.body_bn, audience=body.audience, priority=body.priority, created_by=ctx.user.id)
    db.add(n)
    db.flush()
    sent = 0
    for p in _recipients(db, ctx, body.audience):
        r = Receipt(notice_id=n.id, name=p["name"], unit=p["unit"], phone=p["phone"], user_id=p["user_id"], token=secrets.token_urlsafe(12))
        db.add(r)
        db.flush()
        if body.sms:
            sent += _sms(db, ctx, n, r, f"notice{n.id}:{r.id}:first")
    audit(db, user_id=ctx.user.id, org_id=ctx.property.org_id, property_id=ctx.property.id, action="notice.publish", entity="notice", entity_id=n.id, meta={"audience": n.audience, "sms": sent})
    db.commit()
    return {"id": n.id, "sms_sent": sent}


def _one(db: Session, ctx: Ctx, nid: int) -> Notice:
    ctx.feature("notices")
    n = db.get(Notice, nid)
    if not n or n.property_id != ctx.property.id:
        raise HTTPException(404, "Not found")
    return n


@router.post("/{nid}/read")
def read(nid: int, ctx: Ctx = Depends(property_ctx), db: Session = Depends(get_db)):
    n = _one(db, ctx, nid)
    if not _in_audience(ctx, n.audience):
        raise HTTPException(403, "Your role cannot do this")
    if ctx.has(*MANAGE) and not db.scalar(select(Receipt.id).where(Receipt.notice_id == n.id, Receipt.user_id == ctx.user.id)):
        return {"ok": True}   # staff reading is not counted as a resident reading
    rows = db.scalars(select(Receipt).where(Receipt.notice_id == n.id, Receipt.user_id == ctx.user.id)).all()
    if not rows:
        rows = [Receipt(notice_id=n.id, name=ctx.user.name, phone=ctx.user.phone, user_id=ctx.user.id, token=secrets.token_urlsafe(12))]
        db.add(rows[0])
    for r in rows:
        if not r.read_at:
            r.read_at, r.read_via = now(), "app"
    db.commit()
    return {"ok": True}


@router.get("/{nid}/reach")
def reach(nid: int, ctx: Ctx = Depends(property_ctx), db: Session = Depends(get_db)):
    n = _one(db, ctx, nid)
    ctx.need(*REACH)
    rows = db.scalars(select(Receipt).where(Receipt.notice_id == n.id).order_by(Receipt.unit, Receipt.name)).all()
    fmt = lambda r: {"id": r.id, "name": r.name, "unit": r.unit, "phone": r.phone if ctx.has(*MANAGE, "TREASURER", "PRESIDENT", "SECRETARY") else "", "via": r.read_via, "read_at": r.read_at.isoformat() if r.read_at else None,
                     "sms_at": r.sms_at.isoformat() if r.sms_at else None, "has_login": bool(r.user_id)}
    return {"read": [fmt(r) for r in rows if r.read_at], "not_read": [fmt(r) for r in rows if not r.read_at]}


@router.post("/{nid}/nudge")
def nudge(nid: int, ctx: Ctx = Depends(property_ctx), db: Session = Depends(get_db)):
    """Sends an SMS with the notice link to everyone who has not read it yet. Once a day per person."""
    n = _one(db, ctx, nid)
    ctx.need(*PUBLISH)
    sent = failed = 0
    for r in db.scalars(select(Receipt).where(Receipt.notice_id == n.id, Receipt.read_at.is_(None))):
        if not r.phone:
            continue
        ok = _sms(db, ctx, n, r, f"notice{n.id}:{r.id}:nudge:{date.today().isoformat()}", nudge=True)
        sent += ok
        failed += (not ok and not db.scalar(select(Message.id).where(Message.idem_key == f"notice{n.id}:{r.id}:nudge:{date.today().isoformat()}", Message.status == "sent")))
    audit(db, user_id=ctx.user.id, org_id=ctx.property.org_id, property_id=ctx.property.id, action="notice.nudge", entity="notice", entity_id=n.id, meta={"sent": sent})
    db.commit()
    return {"sent": sent, "failed": failed}


@router.post("/{nid}/pin")
def pin(nid: int, ctx: Ctx = Depends(property_ctx), db: Session = Depends(get_db)):
    n = _one(db, ctx, nid)
    ctx.need(*PUBLISH)
    n.pinned = not n.pinned
    db.commit()
    return {"pinned": n.pinned}


@router.post("/{nid}/archive")
def archive(nid: int, ctx: Ctx = Depends(property_ctx), db: Session = Depends(get_db)):
    n = _one(db, ctx, nid)
    ctx.need(*PUBLISH)
    n.status = "archived"
    audit(db, user_id=ctx.user.id, org_id=ctx.property.org_id, property_id=ctx.property.id, action="notice.archive", entity="notice", entity_id=n.id)
    db.commit()
    return {"ok": True}


@router.get("/link/{token}")
def by_link(token: str, db: Session = Depends(get_db)):
    """The page an SMS link opens. No sign-in. Opening it is the read proof."""
    r = db.scalar(select(Receipt).where(Receipt.token == token))
    n = db.get(Notice, r.notice_id) if r else None
    if not r or n.status != "live":
        raise HTTPException(404, "This notice is not available")
    if not r.read_at:
        r.read_at, r.read_via = now(), "link"
        db.commit()
    from ..models.core import Property
    p = db.get(Property, n.property_id)
    return {"building": p.name, "building_bn": p.name_bn, "title": n.title, "title_bn": n.title_bn, "body": n.body, "body_bn": n.body_bn, "priority": n.priority, "at": n.created_at.isoformat(), "for": r.name}


# ---------------- policies
class PolicyIn(BaseModel):
    title: str = Field(min_length=3)
    title_bn: str = ""
    body: str = Field(min_length=10)
    body_bn: str = ""


class VersionIn(BaseModel):
    body: str = Field(min_length=10)
    body_bn: str = ""
    change_note: str = Field(default="", max_length=200)


def _latest(db: Session, pid: int) -> PolicyVersion:
    return db.scalar(select(PolicyVersion).where(PolicyVersion.policy_id == pid).order_by(PolicyVersion.version.desc()))


def _accepters(db: Session, ctx: Ctx) -> list[int]:
    return sorted({m.user_id for m in db.scalars(select(Membership).where(Membership.property_id == ctx.property.id, Membership.role.in_(list(RES | {"TENANT"} | COMMITTEE))))})


def _p(db: Session, p: Policy, ctx: Ctx) -> dict:
    v = _latest(db, p.id)
    accepted = {a.user_id for a in db.scalars(select(PolicyAcceptance).where(PolicyAcceptance.version_id == v.id))}
    ever = db.scalar(select(func.count()).select_from(PolicyAcceptance).join(PolicyVersion, PolicyVersion.id == PolicyAcceptance.version_id).where(PolicyVersion.policy_id == p.id, PolicyAcceptance.user_id == ctx.user.id)) or 0
    d = {"id": p.id, "title": p.title, "title_bn": p.title_bn, "version": v.version, "body": v.body, "body_bn": v.body_bn, "change_note": v.change_note, "published_at": v.published_at.isoformat(),
         "accepted": ctx.user.id in accepted, "accepted_before": ever > 0 and ctx.user.id not in accepted}
    if ctx.has(*REACH):
        who = _accepters(db, ctx)
        d["accepted_count"], d["audience_count"] = len([u for u in who if u in accepted]), len(who)
    return d


@pol.get("")
def policies(ctx: Ctx = Depends(property_ctx), db: Session = Depends(get_db)):
    ctx.feature("policies")
    return [_p(db, p, ctx) for p in db.scalars(select(Policy).where(Policy.property_id == ctx.property.id).order_by(Policy.id))]


@pol.post("", status_code=201)
def new_policy(body: PolicyIn, ctx: Ctx = Depends(property_ctx), db: Session = Depends(get_db)):
    ctx.feature("policies")
    ctx.need(*PUBLISH)
    p = Policy(property_id=ctx.property.id, title=body.title, title_bn=body.title_bn)
    db.add(p)
    db.flush()
    db.add(PolicyVersion(policy_id=p.id, version=1, body=body.body, body_bn=body.body_bn, change_note="First version", published_by=ctx.user.id))
    audit(db, user_id=ctx.user.id, org_id=ctx.property.org_id, property_id=ctx.property.id, action="policy.create", entity="policy", entity_id=p.id)
    db.commit()
    return _p(db, p, ctx)


def _pol(db: Session, ctx: Ctx, pid: int) -> Policy:
    ctx.feature("policies")
    p = db.get(Policy, pid)
    if not p or p.property_id != ctx.property.id:
        raise HTTPException(404, "Not found")
    return p


@pol.post("/{pid}/versions", status_code=201)
def new_version(pid: int, body: VersionIn, ctx: Ctx = Depends(property_ctx), db: Session = Depends(get_db)):
    """A new version never overwrites the old one. Everyone must accept it again."""
    p = _pol(db, ctx, pid)
    ctx.need(*PUBLISH)
    v = _latest(db, p.id)
    db.add(PolicyVersion(policy_id=p.id, version=v.version + 1, body=body.body, body_bn=body.body_bn, change_note=body.change_note, published_by=ctx.user.id))
    audit(db, user_id=ctx.user.id, org_id=ctx.property.org_id, property_id=ctx.property.id, action="policy.version", entity="policy", entity_id=p.id, meta={"version": v.version + 1})
    db.commit()
    return _p(db, p, ctx)


@pol.post("/{pid}/accept")
def accept(pid: int, ctx: Ctx = Depends(property_ctx), db: Session = Depends(get_db)):
    p = _pol(db, ctx, pid)
    if ctx.user.id not in _accepters(db, ctx):
        raise HTTPException(403, "Your role cannot do this")
    v = _latest(db, p.id)
    if not db.scalar(select(PolicyAcceptance.id).where(PolicyAcceptance.version_id == v.id, PolicyAcceptance.user_id == ctx.user.id)):
        db.add(PolicyAcceptance(version_id=v.id, user_id=ctx.user.id))
        audit(db, user_id=ctx.user.id, org_id=ctx.property.org_id, property_id=ctx.property.id, action="policy.accept", entity="policy", entity_id=p.id, meta={"version": v.version})
        db.commit()
    return _p(db, p, ctx)


@pol.get("/{pid}/history")
def history(pid: int, ctx: Ctx = Depends(property_ctx), db: Session = Depends(get_db)):
    p = _pol(db, ctx, pid)
    users = {u.id: u.name for u in db.scalars(select(User))}
    out = []
    for v in db.scalars(select(PolicyVersion).where(PolicyVersion.policy_id == p.id).order_by(PolicyVersion.version.desc())):
        acc = db.scalars(select(PolicyAcceptance).where(PolicyAcceptance.version_id == v.id).order_by(PolicyAcceptance.at)).all()
        row = {"version": v.version, "change_note": v.change_note, "published_at": v.published_at.isoformat(), "by": users.get(v.published_by, ""), "accepted_count": len(acc)}
        if ctx.has(*REACH):
            row["accepted"] = [{"name": users.get(a.user_id, ""), "at": a.at.isoformat()} for a in acc]
        out.append(row)
    pending = []
    if ctx.has(*REACH):
        done = {a.user_id for a in db.scalars(select(PolicyAcceptance).where(PolicyAcceptance.version_id == _latest(db, p.id).id))}
        pending = [users.get(u, "") for u in _accepters(db, ctx) if u not in done]
    return {"versions": out, "pending": pending}
