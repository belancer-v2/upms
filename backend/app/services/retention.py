"""Data retention: how long FlatWise keeps personal records, and the functions that purge what is past its time.

Nothing here runs by itself. The jobs agent owns scheduling: call `run_purge(db)` from a nightly job (or press "Run purge" in the SaaS
console, which calls the same function). Audit rows are never deleted (the audit log is append-only and hash-chained).

A month count of 0 means "keep forever" for that kind of record.
"""
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from .. import config
from ..audit import audit
from ..models.core import now
from ..models.credits import PlatformSetting

# key -> (stored name, default months, what it covers)
SETTINGS = {
    "visitor_months": ("ret.visitor_months", 24),
    "outbox_months": ("ret.outbox_months", 12),
    "former_months": ("ret.former_months", 36),
}
MAX_MONTHS = 120
MIN_MONTHS = 3


def get_settings(db: Session) -> dict:
    out = {}
    for k, (stored, default) in SETTINGS.items():
        row = db.get(PlatformSetting, stored)
        try:
            out[k] = int(row.value) if row else default
        except ValueError:
            out[k] = default
    out["audit"] = "never"   # fixed: the audit log is never purged
    return out


def validate_months(v: int) -> int:
    if v != 0 and not (MIN_MONTHS <= v <= MAX_MONTHS):
        raise ValueError(f"Use 0 (keep forever) or {MIN_MONTHS} to {MAX_MONTHS} months")
    return v


def save_settings(db: Session, values: dict) -> dict:
    for k, v in values.items():
        if k not in SETTINGS or v is None:
            continue
        stored = SETTINGS[k][0]
        v = validate_months(int(v))
        row = db.get(PlatformSetting, stored)
        if row:
            row.value = str(v)
        else:
            db.add(PlatformSetting(key=stored, value=str(v)))
    db.flush()
    return get_settings(db)


def _cutoff(months: int, at: datetime | None = None) -> datetime:
    return (at or now()) - timedelta(days=round(months * 30.44))


def _unlink(path) -> bool:
    try:
        path.unlink(missing_ok=True)
        return True
    except OSError:
        return False


def purge_visitors(db: Session, months: int, dry_run: bool = False, at: datetime | None = None) -> dict:
    """Visitor log older than `months`: the visits (and their photos), resident notifications, visitor-bay parking logs and finished passes."""
    from ..models.parking import ParkingVisit
    from ..models.visitors import Visit, VisitorNotice, VisitorPass
    if not months:
        return {"visits": 0, "notices": 0, "parking_visits": 0, "passes": 0, "photos": 0}
    cut = _cutoff(months, at)
    ids = [r for r in db.scalars(select(Visit.id).where(Visit.created_at < cut))]
    photos = list(db.execute(select(Visit.property_id, Visit.photo_file).where(Visit.id.in_(ids), Visit.photo_file != ""))) if ids else []
    n = {"visits": len(ids),
         "notices": db.scalar(select(func.count()).select_from(VisitorNotice).where(VisitorNotice.visit_id.in_(ids))) or 0 if ids else 0,
         "parking_visits": db.scalar(select(func.count()).select_from(ParkingVisit).where(ParkingVisit.in_at < cut)) or 0,
         "passes": db.scalar(select(func.count()).select_from(VisitorPass).where(VisitorPass.valid_to < cut, VisitorPass.status != "active")) or 0,
         "photos": len(photos)}
    if dry_run or not any(n.values()):
        return n
    for pid, name in photos:
        _unlink(config.UPLOAD_DIR / "visitors" / str(pid) / name)
    for chunk in range(0, len(ids), 500):
        part = ids[chunk:chunk + 500]
        db.execute(delete(VisitorNotice).where(VisitorNotice.visit_id.in_(part)))
        db.execute(delete(Visit).where(Visit.id.in_(part)))
    db.execute(delete(ParkingVisit).where(ParkingVisit.in_at < cut))
    db.execute(delete(VisitorPass).where(VisitorPass.valid_to < cut, VisitorPass.status != "active"))
    return n


def purge_outbox(db: Session, months: int, dry_run: bool = False, at: datetime | None = None) -> dict:
    """Sent e-mail copies (subject, rendered body, address) and the SMS log (phone number, text) older than `months`. Queued rows are never touched."""
    from ..models.billing import Message
    from ..models.jobs import SmsDispatch
    from ..models.mail import MailOutbox
    if not months:
        return {"emails": 0, "sms": 0}
    cut = _cutoff(months, at)
    mail = MailOutbox.created_at < cut, MailOutbox.status != "queued"
    sms_ids = list(db.scalars(select(Message.id).where(Message.created_at < cut, Message.status != "queued")))
    n = {"emails": db.scalar(select(func.count()).select_from(MailOutbox).where(*mail)) or 0, "sms": len(sms_ids)}
    if dry_run or not any(n.values()):
        return n
    db.execute(delete(MailOutbox).where(*mail))
    for chunk in range(0, len(sms_ids), 500):
        part = sms_ids[chunk:chunk + 500]
        db.execute(delete(SmsDispatch).where(SmsDispatch.message_id.in_(part)))
        db.execute(delete(Message).where(Message.id.in_(part)))
    return n


def purge_former_residents(db: Session, months: int, dry_run: bool = False, at: datetime | None = None) -> dict:
    """People who moved out more than `months` ago: phone and email are blanked on the occupancy record (the name and dates stay for the flat's history),
    and their tenant-onboarding file (documents, National ID, family and address details) is erased."""
    from ..models.onboarding import TenantCase, TenantDoc
    from ..models.property import Occupancy
    if not months:
        return {"contacts": 0, "cases": 0, "documents": 0}
    cut = _cutoff(months, at)
    cut_day = cut.date()
    occ_stmt = select(Occupancy).where(Occupancy.active.is_(False), Occupancy.end_date.is_not(None), Occupancy.end_date < cut_day, (Occupancy.phone != "") | (Occupancy.email != ""))
    occs = list(db.scalars(occ_stmt))
    gone = {o.id for o in db.scalars(select(Occupancy).where(Occupancy.active.is_(False), Occupancy.end_date.is_not(None), Occupancy.end_date < cut_day))}
    cand = [c for c in db.scalars(select(TenantCase).where((TenantCase.occupancy_id.in_(gone)) | (TenantCase.status == "cancelled")))
            if (c.occupancy_id in gone) or (c.created_at.replace(tzinfo=timezone.utc) < cut)]
    docs = list(db.scalars(select(TenantDoc).where(TenantDoc.case_id.in_([c.id for c in cand])))) if cand else []
    with_docs = {d.case_id for d in docs}
    cases = [c for c in cand if c.details or c.nid_enc or c.phone or c.id in with_docs]
    n = {"contacts": len(occs), "cases": len(cases), "documents": len(docs)}
    if dry_run or not any(n.values()):
        return n
    for d in docs:
        _unlink(config.UPLOAD_DIR / str(d.case_id) / d.stored)
        db.delete(d)
    for c in cases:
        c.details, c.nid_enc, c.nid_last4, c.phone = {}, "", "", ""
    for o in occs:
        o.phone, o.email = "", ""
    return n


def run_purge(db: Session, dry_run: bool = False, by_user_id: int | None = None, at: datetime | None = None) -> dict:
    """Runs every purge with the saved settings and writes one audit row (not for a dry run). The caller commits."""
    s = get_settings(db)
    result = {"dry_run": dry_run, "settings": s,
              "visitors": purge_visitors(db, s["visitor_months"], dry_run, at),
              "outbox": purge_outbox(db, s["outbox_months"], dry_run, at),
              "former_residents": purge_former_residents(db, s["former_months"], dry_run, at)}
    if not dry_run:
        counts = {k: v for k, v in result.items() if k in ("visitors", "outbox", "former_residents")}
        audit(db, user_id=by_user_id, action="retention.purge", entity="retention", meta=counts, note="manual" if by_user_id else "scheduled")
    return result


def last_run(db: Session):
    from ..models.core import AuditLog
    row = db.scalar(select(AuditLog).where(AuditLog.action == "retention.purge").order_by(AuditLog.id.desc()))
    return {"at": row.at.isoformat(), "meta": row.meta, "note": row.note} if row else None
