"""SaaS console: background jobs (last runs, run now, failures, alerts) and the per-building billing automation opt-in."""
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..audit import audit
from ..db import get_db
from ..deps import Ctx, property_ctx, require_saas
from ..jobs import runner
from ..jobs import tasks  # noqa: F401  (registers the jobs)
from ..models.core import User, now
from ..models.jobs import BuildingAutomation, JobRun, SystemAlert
from ..permissions import MANAGE

ADMINS = ("SUPER_ADMIN", "SAAS_ADMIN")
router = APIRouter(prefix="/api/saas/jobs", tags=["jobs"], dependencies=[Depends(require_saas(*ADMINS))])
auto_router = APIRouter(prefix="/api/billing/automation", tags=["billing"])
MONEY_ROLES = MANAGE | {"TREASURER"}


def _run(r: JobRun) -> dict:
    return {"id": r.id, "name": r.name, "status": r.status, "trigger": r.trigger, "started_at": r.started_at.isoformat(), "finished_at": r.finished_at.isoformat() if r.finished_at else None,
            "result": r.result or {}, "error": r.error, "owner": r.owner}


@router.get("")
def jobs(db: Session = Depends(get_db)):
    out = []
    for j in runner.JOBS.values():
        last = db.scalar(select(JobRun).where(JobRun.name == j.name).order_by(JobRun.id.desc()).limit(1))
        ok = db.scalar(select(JobRun).where(JobRun.name == j.name, JobRun.status.in_(("ok", "warn"))).order_by(JobRun.id.desc()).limit(1))
        fails = db.scalar(select(func.count()).select_from(JobRun).where(JobRun.name == j.name, JobRun.status == "failed", JobRun.started_at >= now().replace(hour=0, minute=0, second=0, microsecond=0))) or 0
        out.append({"name": j.name, "title": j.title, "schedule": j.schedule.label(), "last": _run(last) if last else None, "last_ok_at": ok.started_at.isoformat() if ok else None, "failed_today": fails})
    open_alerts = db.scalar(select(func.count()).select_from(SystemAlert).where(SystemAlert.resolved_at.is_(None))) or 0
    return {"jobs": out, "open_alerts": open_alerts}


@router.get("/runs")
def runs(name: str = "", status: str = "", page: int = Query(1, ge=1), size: int = Query(10, ge=1, le=100), db: Session = Depends(get_db)):
    stmt = select(JobRun)
    if name:
        stmt = stmt.where(JobRun.name == name)
    if status:
        stmt = stmt.where(JobRun.status == status)
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = db.scalars(stmt.order_by(JobRun.id.desc()).offset((page - 1) * size).limit(size)).all()
    return {"total": total, "page": page, "size": size, "rows": [_run(r) for r in rows]}


@router.post("/{name}/run")
def run_now(name: str, user: User = Depends(require_saas(*ADMINS)), db: Session = Depends(get_db)):
    if name not in runner.JOBS:
        raise HTTPException(404, "Unknown job")
    r = runner.run_job(name, trigger="manual", user_id=user.id)
    audit(db, user_id=user.id, action="saas.job.run", entity="job", entity_id=name, meta={"status": (r or {}).get("status")})
    db.commit()
    if r and r.get("status") == "locked":
        raise HTTPException(409, "This job is already running")
    return r


@router.get("/alerts")
def alerts(open_only: bool = True, page: int = Query(1, ge=1), size: int = Query(10, ge=1, le=100), db: Session = Depends(get_db)):
    stmt = select(SystemAlert)
    if open_only:
        stmt = stmt.where(SystemAlert.resolved_at.is_(None))
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = db.scalars(stmt.order_by(SystemAlert.id.desc()).offset((page - 1) * size).limit(size)).all()
    return {"total": total, "page": page, "size": size, "rows": [{"id": a.id, "kind": a.kind, "severity": a.severity, "message": a.message, "meta": a.meta, "created_at": a.created_at.isoformat(),
                                                                  "resolved_at": a.resolved_at.isoformat() if a.resolved_at else None} for a in rows]}


@router.post("/alerts/{aid}/resolve")
def resolve(aid: int, user: User = Depends(require_saas(*ADMINS)), db: Session = Depends(get_db)):
    a = db.get(SystemAlert, aid)
    if not a:
        raise HTTPException(404, "Not found")
    a.resolved_at = a.resolved_at or now()
    db.commit()
    return {"ok": True}


# ---------------- per-building opt-in
class AutoIn(BaseModel):
    auto_billing: bool
    bill_day: int = Field(default=1, ge=1, le=28)
    due_day: int = Field(default=10, ge=1, le=28)


def _auto_out(a: BuildingAutomation | None) -> dict:
    return {"auto_billing": bool(a and a.auto_billing), "bill_day": a.bill_day if a else 1, "due_day": a.due_day if a else 10}


@auto_router.get("")
def get_auto(ctx: Ctx = Depends(property_ctx), db: Session = Depends(get_db)):
    ctx.feature("billing")
    ctx.need(*MONEY_ROLES)
    return _auto_out(db.get(BuildingAutomation, ctx.property.id))


@auto_router.put("")
def put_auto(body: AutoIn, ctx: Ctx = Depends(property_ctx), db: Session = Depends(get_db)):
    """Opt in to automatic monthly invoices. Off by default."""
    ctx.feature("billing")
    ctx.need(*MONEY_ROLES)
    a = db.get(BuildingAutomation, ctx.property.id)
    if not a:
        a = BuildingAutomation(property_id=ctx.property.id)
        db.add(a)
    a.auto_billing, a.bill_day, a.due_day = body.auto_billing, body.bill_day, body.due_day
    audit(db, user_id=ctx.user.id, org_id=ctx.property.org_id, property_id=ctx.property.id, action="billing.automation", entity="property", entity_id=ctx.property.id, meta=body.model_dump())
    db.commit()
    return _auto_out(a)
