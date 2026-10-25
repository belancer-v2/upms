"""Runner: DB lock per job name, run history, schedule maths and the asyncio loop.

Locking: job_locks has one row per job. A worker may run a job only after it inserted the row, or took over a row whose
expiry has passed (single conditional UPDATE, so exactly one worker wins). After winning, the worker re-checks that the
job is still due, so two workers waking at the same moment never run it twice in a row.
"""
from __future__ import annotations

import asyncio
import logging
import os
import secrets
import socket
import traceback
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Callable

from sqlalchemy import delete, func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..db import SessionLocal
from ..models.core import now
from ..models.jobs import JobLock, JobMark, JobRun, SystemAlert

log = logging.getLogger("flatwise.jobs")
DHAKA = timezone(timedelta(hours=6))   # Bangladesh has no daylight saving; daily jobs are scheduled on Dhaka time
OWNER = f"{socket.gethostname()}:{os.getpid()}:{secrets.token_hex(3)}"
RETRY_MINUTES = 30
MAX_ATTEMPTS = 3


def aware(dt: datetime | None) -> datetime | None:
    return dt.replace(tzinfo=timezone.utc) if dt is not None and dt.tzinfo is None else dt


def local_date(at: datetime):
    return aware(at).astimezone(DHAKA).date()


@dataclass(frozen=True)
class Schedule:
    every_minutes: int = 0     # interval job
    hour: int = 0              # daily job, Dhaka time (used when every_minutes == 0)
    minute: int = 0

    def label(self) -> str:
        if self.every_minutes:
            return f"every {self.every_minutes} min" if self.every_minutes < 60 else f"every {self.every_minutes // 60} h"
        return f"daily {self.hour:02d}:{self.minute:02d} Dhaka"


@dataclass(frozen=True)
class JobDef:
    name: str
    title: str
    fn: Callable[[Session, datetime], dict]
    schedule: Schedule
    lock_minutes: int = 20


JOBS: dict[str, JobDef] = {}


def register(name: str, title: str, schedule: Schedule, lock_minutes: int = 20):
    def deco(fn):
        JOBS[name] = JobDef(name, title, fn, schedule, lock_minutes)
        return fn
    return deco


# ------------------------------------------------------------------ marks (idempotency inside a job)
def claim(db: Session, key: str, at: datetime | None = None) -> bool:
    """True the first time a key is seen, False every time after. Safe under concurrency (unique key)."""
    if db.get(JobMark, key):
        return False
    try:
        with db.begin_nested():
            db.add(JobMark(key=key[:120], at=at or now()))
            db.flush()
        return True
    except IntegrityError:
        return False


def alert(db: Session, dedupe_key: str, kind: str, message: str, severity: str = "warn", meta: dict | None = None, org_id: int | None = None, property_id: int | None = None,
          at: datetime | None = None) -> bool:
    """Writes one SystemAlert per dedupe key. Returns False when the alert already existed."""
    if db.scalar(select(SystemAlert.id).where(SystemAlert.dedupe_key == dedupe_key[:120])):
        return False
    try:
        with db.begin_nested():
            db.add(SystemAlert(dedupe_key=dedupe_key[:120], kind=kind, severity=severity, message=message[:2000], meta=meta or {}, org_id=org_id, property_id=property_id, created_at=at or now()))
            db.flush()
        return True
    except IntegrityError:
        return False


# ------------------------------------------------------------------ lock
def acquire(db: Session, name: str, owner: str, ttl: timedelta, at: datetime) -> bool:
    exp = at + ttl
    try:
        with db.begin_nested():
            db.add(JobLock(name=name, owner=owner, expires_at=exp))
            db.flush()
        db.commit()
        return True
    except IntegrityError:
        pass
    got = db.execute(update(JobLock).where(JobLock.name == name, JobLock.expires_at < at).values(owner=owner, expires_at=exp)).rowcount == 1
    db.commit()
    return got


def release(db: Session, name: str, owner: str) -> None:
    db.execute(delete(JobLock).where(JobLock.name == name, JobLock.owner == owner))
    db.commit()


# ------------------------------------------------------------------ schedule
def is_due(db: Session, job: JobDef, at: datetime) -> bool:
    at = aware(at)
    s = job.schedule
    last = db.scalar(select(JobRun).where(JobRun.name == job.name, JobRun.trigger == "schedule", JobRun.status != "skipped").order_by(JobRun.id.desc()).limit(1))
    if s.every_minutes:
        return last is None or aware(last.started_at) <= at - timedelta(minutes=s.every_minutes)
    local = at.astimezone(DHAKA)
    slot = local.replace(hour=s.hour, minute=s.minute, second=0, microsecond=0).astimezone(timezone.utc)
    if slot > at:
        return False
    runs = db.execute(select(JobRun.status, JobRun.started_at).where(JobRun.name == job.name, JobRun.trigger == "schedule", JobRun.started_at >= slot).order_by(JobRun.id)).all()
    if not runs:
        return True
    if any(st in ("ok", "warn", "running") for st, _ in runs):
        return False
    # only failures so far in this slot: retry after a pause, a few times
    return len(runs) < MAX_ATTEMPTS and aware(runs[-1][1]) <= at - timedelta(minutes=RETRY_MINUTES)


# ------------------------------------------------------------------ run
def _scrub(text: str) -> str:
    return text[-3500:]


def run_job(name: str, *, at: datetime | None = None, trigger: str = "schedule", user_id: int | None = None, only_if_due: bool = False,
            session_factory=None) -> dict | None:
    """Runs one job under its lock. Returns the run summary, or None when another worker holds the lock (scheduled) / {status: locked} (manual)."""
    from . import tasks  # noqa: F401  (registers the jobs)
    job = JOBS.get(name)
    if not job:
        raise KeyError(name)
    at = aware(at or now())
    factory = session_factory or SessionLocal
    with factory() as db:
        if not acquire(db, name, OWNER, timedelta(minutes=job.lock_minutes), at):
            return {"name": name, "status": "locked"} if trigger == "manual" else None
        try:
            if only_if_due and not is_due(db, job, at):
                return None
            run = JobRun(name=name, started_at=at, status="running", trigger=trigger, owner=OWNER, lock_expires_at=at + timedelta(minutes=job.lock_minutes), by_user_id=user_id)
            db.add(run)
            db.commit()
            status, result, error = "ok", {}, ""
            try:
                result = job.fn(db, at) or {}
                if result.pop("warn", False):
                    status = "warn"
                db.commit()
            except Exception as e:  # a job must never take the worker down
                db.rollback()
                status, error = "failed", _scrub(f"{type(e).__name__}: {e}\n{traceback.format_exc()}")
                log.error("job %s failed: %s", name, type(e).__name__)
                alert(db, f"jobfail:{name}:{local_date(at)}", "job_failed", f"Job {name} failed: {type(e).__name__}: {str(e)[:300]}", "error", at=at)
            run = db.get(JobRun, run.id)
            run.status, run.result, run.error, run.finished_at = status, result, error, max(aware(now()), at)
            db.commit()
            return {"id": run.id, "name": name, "status": status, "result": result, "error": error}
        finally:
            release(db, name, OWNER)


def run_due_jobs(at: datetime | None = None) -> list[dict]:
    """One scheduler tick: runs every job that is due, one after another."""
    from . import tasks  # noqa: F401
    at = at or now()
    out = []
    for name, job in JOBS.items():
        with SessionLocal() as db:
            due = is_due(db, job, at)
        if due:
            r = run_job(name, at=at, only_if_due=True)
            if r:
                out.append(r)
    return out


async def _loop(stop: asyncio.Event) -> None:
    tick = max(5, int(os.getenv("JOBS_TICK_SECONDS", "30")))
    log.info("job scheduler started (%s, %d jobs)", OWNER, len(JOBS))
    while not stop.is_set():
        try:
            await asyncio.to_thread(run_due_jobs)
        except Exception as e:
            log.error("scheduler tick failed: %s", type(e).__name__)
        try:
            await asyncio.wait_for(stop.wait(), timeout=tick)
        except asyncio.TimeoutError:
            pass


@asynccontextmanager
async def scheduler_running():
    """Use in the app lifespan. Starts the loop only when JOBS_ENABLED=1."""
    if os.getenv("JOBS_ENABLED", "0") != "1":
        yield None
        return
    from . import tasks  # noqa: F401  (registers the jobs)
    stop = asyncio.Event()
    task = asyncio.create_task(_loop(stop))
    try:
        yield task
    finally:
        stop.set()
        await task


def cleanup_stats(db: Session) -> int:
    return db.scalar(select(func.count()).select_from(JobRun)) or 0
