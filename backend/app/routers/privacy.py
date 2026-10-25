"""Privacy: account-deletion requests (any signed-in person) and the SaaS console's data-retention page."""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..audit import audit
from ..db import get_db
from ..deps import current_user, require_saas
from ..models.core import User, now
from ..models.setup import DeletionRequest
from ..security import verify_password
from ..services import privacy, retention

router = APIRouter(prefix="/api/me/deletion", tags=["privacy"])
console = APIRouter(prefix="/api/saas", tags=["retention"])
ADMINS = ("SUPER_ADMIN", "SAAS_ADMIN")


class DeletionOut(BaseModel):
    id: int
    status: str
    reason: str = ""
    requested_at: str
    processed_at: str | None = None
    note: str = ""


class DeletionState(BaseModel):
    request: DeletionOut | None = None
    blockers: list[str] = Field(default=[], description="saas_staff | last_admin. Empty means the request can be sent.")


class DeletionIn(BaseModel):
    password: str = Field(min_length=1, max_length=100, description="Your current password, to confirm it is you.")
    reason: str = Field(default="", max_length=300)


def _out(r: DeletionRequest) -> DeletionOut:
    return DeletionOut(id=r.id, status=r.status, reason=r.reason, requested_at=r.requested_at.isoformat(), processed_at=r.processed_at.isoformat() if r.processed_at else None, note=r.note)


def _pending(db: Session, uid: int) -> DeletionRequest | None:
    return db.scalar(select(DeletionRequest).where(DeletionRequest.user_id == uid, DeletionRequest.status == "pending"))


@router.get("", response_model=DeletionState, summary="My account-deletion request, if any")
def mine(user: User = Depends(current_user), db: Session = Depends(get_db)):
    last = db.scalar(select(DeletionRequest).where(DeletionRequest.user_id == user.id).order_by(DeletionRequest.id.desc()))
    return DeletionState(request=_out(last) if last else None, blockers=privacy.blockers(db, user))


@router.post("", response_model=DeletionOut, status_code=201, summary="Ask FlatWise to erase my personal details")
def request_deletion(body: DeletionIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Needs your password. FlatWise staff process the request: your name, email, phone, photo and profile are erased and your sign-in closed.
    Invoices, payments and the ledger stay, because they belong to the building's books, but they carry no name of yours."""
    if not verify_password(body.password, user.password_hash):
        raise HTTPException(403, "Wrong password")
    if _pending(db, user.id):
        raise HTTPException(409, "You already asked. We are working on it.")
    b = privacy.blockers(db, user)
    if b:
        raise HTTPException(409, "saas_staff" if "saas_staff" in b else "last_admin")
    r = DeletionRequest(user_id=user.id, reason=body.reason.strip())
    db.add(r)
    db.flush()
    audit(db, user_id=user.id, action="privacy.deletion_request", entity="deletion_request", entity_id=r.id)
    db.commit()
    return _out(r)


@router.delete("", status_code=204, summary="Withdraw my deletion request")
def cancel(user: User = Depends(current_user), db: Session = Depends(get_db)):
    r = _pending(db, user.id)
    if not r:
        raise HTTPException(404, "Nothing to withdraw")
    r.status, r.processed_at = "cancelled", now()
    audit(db, user_id=user.id, action="privacy.deletion_cancel", entity="deletion_request", entity_id=r.id)
    db.commit()


# ---------------- SaaS console: deletion requests
class AdminRow(DeletionOut):
    user_id: int
    name: str
    email: str
    blockers: list[str] = []


class RejectIn(BaseModel):
    note: str = Field(min_length=3, max_length=300)


@console.get("/deletions", response_model=list[AdminRow], summary="Account-deletion requests")
def deletions(status: str = "pending", user: User = Depends(require_saas(*ADMINS)), db: Session = Depends(get_db)):
    stmt = select(DeletionRequest).order_by(DeletionRequest.id.desc()).limit(200)
    if status != "all":
        stmt = stmt.where(DeletionRequest.status == status)
    out = []
    for r in db.scalars(stmt):
        u = db.get(User, r.user_id)
        out.append(AdminRow(**_out(r).model_dump(), user_id=r.user_id, name=u.name if u else "", email=u.email if u else "", blockers=privacy.blockers(db, u) if u and r.status == "pending" else []))
    return out


@console.post("/deletions/{rid}/process", response_model=DeletionOut, summary="Erase the person's details now")
def process(rid: int, user: User = Depends(require_saas(*ADMINS)), db: Session = Depends(get_db)):
    r = db.get(DeletionRequest, rid)
    if not r or r.status != "pending":
        raise HTTPException(404, "No pending request")
    target = db.get(User, r.user_id)
    if not target:
        raise HTTPException(404, "User not found")
    b = privacy.blockers(db, target)
    if b:
        raise HTTPException(409, "This account cannot be erased yet: " + ", ".join(b))
    done = privacy.anonymise_user(db, target, by_user_id=user.id)
    r.status, r.processed_at, r.processed_by, r.note = "completed", now(), user.id, "Erased: " + ", ".join(f"{k} {v}" for k, v in done.items())
    db.commit()
    return _out(r)


@console.post("/deletions/{rid}/reject", response_model=DeletionOut, summary="Refuse a deletion request with a reason")
def reject(rid: int, body: RejectIn, user: User = Depends(require_saas(*ADMINS)), db: Session = Depends(get_db)):
    r = db.get(DeletionRequest, rid)
    if not r or r.status != "pending":
        raise HTTPException(404, "No pending request")
    r.status, r.processed_at, r.processed_by, r.note = "rejected", now(), user.id, body.note
    audit(db, user_id=user.id, action="privacy.deletion_reject", entity="deletion_request", entity_id=r.id, note=body.note)
    db.commit()
    return _out(r)


# ---------------- SaaS console: data retention
class RetentionIn(BaseModel):
    visitor_months: int | None = Field(default=None, ge=0, le=120, description="Visitor log, photos, passes, visitor-bay logs. 0 keeps them forever.")
    outbox_months: int | None = Field(default=None, ge=0, le=120, description="Sent e-mail copies and the SMS log. 0 keeps them forever.")
    former_months: int | None = Field(default=None, ge=0, le=120, description="Phone, email and onboarding documents of people who moved out. 0 keeps them forever.")


class RetentionOut(BaseModel):
    settings: dict
    preview: dict
    last_run: dict | None = None
    min_months: int = retention.MIN_MONTHS
    max_months: int = retention.MAX_MONTHS


class RunIn(BaseModel):
    dry_run: bool = False


def _state(db: Session) -> RetentionOut:
    prev = retention.run_purge(db, dry_run=True)
    return RetentionOut(settings=prev["settings"], preview={k: prev[k] for k in ("visitors", "outbox", "former_residents")}, last_run=retention.last_run(db))


@console.get("/retention", response_model=RetentionOut, summary="Retention settings, what is due for purging, and the last run")
def get_retention(user: User = Depends(require_saas(*ADMINS)), db: Session = Depends(get_db)):
    return _state(db)


@console.put("/retention", response_model=RetentionOut, summary="Change retention periods")
def put_retention(body: RetentionIn, user: User = Depends(require_saas(*ADMINS)), db: Session = Depends(get_db)):
    before = retention.get_settings(db)
    try:
        after = retention.save_settings(db, body.model_dump())
    except ValueError as e:
        raise HTTPException(422, str(e))
    audit(db, user_id=user.id, action="retention.settings", entity="retention", meta={"from": before, "to": after})
    db.commit()
    return _state(db)


@console.post("/retention/run", summary="Run the purge now (not scheduled)")
def run_retention(body: RunIn, user: User = Depends(require_saas(*ADMINS)), db: Session = Depends(get_db)):
    """Deletes what is past its retention period. `dry_run: true` only counts. The audit log is never touched. Scheduling is the jobs agent's job:
    it should call `app.services.retention.run_purge(db)` on a schedule."""
    result = retention.run_purge(db, dry_run=body.dry_run, by_user_id=user.id)
    db.commit()
    return result
