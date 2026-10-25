"""Tamper-evident, append-only audit log.

Every audit_log row stores `prev_hash` (the previous row's hash) and `row_hash` = SHA-256(prev_hash | canonical row). Editing, inserting or
deleting a row in the middle of the log breaks the chain at that row, which `verify_chain` (or `python -m app.auditchain verify`) reports.
Rows are hashed by a mapper event, so it does not matter which code path wrote them. The application also refuses to UPDATE or DELETE an
audit row. The audit_head row (locked FOR UPDATE until the transaction ends) serialises writers on PostgreSQL and MySQL so concurrent workers cannot fork the chain.

Limits (see SECURITY.md): someone with direct write access to the database can recompute the whole chain, and removing the newest rows is only
detected if the head hash was recorded elsewhere. `verify` prints the head hash so it can be copied to a log you trust.
"""
from __future__ import annotations

import hashlib
import json
import sys
from datetime import timezone

from sqlalchemy import event, insert, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, object_session

from .models.core import AuditLog, now
from .models.security import AuditHead

_TAIL = "audit_chain_tail"


def _iso(dt) -> str:
    if dt is None:
        return ""
    if dt.tzinfo is not None:
        dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
    return dt.strftime("%Y-%m-%dT%H:%M:%S.%f")


def row_hash(prev: str, r) -> str:
    body = json.dumps([r.at and _iso(r.at), r.user_id, r.org_id, r.property_id, r.action, r.entity or "", r.entity_id or "", r.meta or {}, r.note or ""],
                      sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)
    return hashlib.sha256(f"{prev}|{body}".encode()).hexdigest()


@event.listens_for(AuditLog, "before_insert")
def _chain(mapper, connection, target: AuditLog) -> None:
    target.at = target.at or now()
    target.entity, target.entity_id, target.note = target.entity or "", target.entity_id or "", target.note or ""
    target.meta = target.meta or {}
    sess = object_session(target)
    tail = sess.info.get(_TAIL) if sess is not None else None
    if tail is None:
        tail = _lock_head(connection)
    target.prev_hash = tail
    target.row_hash = row_hash(tail, target)
    connection.execute(update(AuditHead).where(AuditHead.id == 1).values(hash=target.row_hash))
    if sess is not None:
        sess.info[_TAIL] = target.row_hash


def _lock_head(connection) -> str:
    """Reads the newest hash while holding the head row's lock until this transaction ends (FOR UPDATE; a no-op on SQLite, which has one writer)."""
    row = connection.execute(select(AuditHead.hash).where(AuditHead.id == 1).with_for_update()).first()
    if row is not None:
        return row[0]
    last = connection.execute(select(AuditLog.row_hash).where(AuditLog.row_hash != "").order_by(AuditLog.id.desc()).limit(1)).scalar() or ""
    try:
        with connection.begin_nested():
            connection.execute(insert(AuditHead).values(id=1, hash=last))
    except IntegrityError:           # another transaction created it first
        pass
    return connection.execute(select(AuditHead.hash).where(AuditHead.id == 1).with_for_update()).scalar() or ""


@event.listens_for(Session, "after_flush_postexec")
def _forget_tail(session, _ctx) -> None:
    session.info.pop(_TAIL, None)


@event.listens_for(AuditLog, "before_update")
def _no_update(mapper, connection, target) -> None:
    raise RuntimeError("The audit log is append-only: rows cannot be changed")


@event.listens_for(AuditLog, "before_delete")
def _no_delete(mapper, connection, target) -> None:
    raise RuntimeError("The audit log is append-only: rows cannot be deleted")


def verify_chain(db: Session) -> dict:
    """Walks the whole log in id order. ok is False at the first row whose hash or link does not match."""
    expected, checked, unchained, head = "", 0, 0, ""
    for r in db.scalars(select(AuditLog).order_by(AuditLog.id).execution_options(yield_per=500)):
        if not r.row_hash:
            unchained += 1          # written before the chain existed (or blanked: the next linked row will then fail)
            continue
        checked += 1
        if r.prev_hash != expected:
            return {"ok": False, "checked": checked, "unchained": unchained, "bad_id": r.id, "reason": "link broken: a row before this one was changed, inserted or removed", "head": head}
        if row_hash(r.prev_hash, r) != r.row_hash:
            return {"ok": False, "checked": checked, "unchained": unchained, "bad_id": r.id, "reason": "row content does not match its hash", "head": head}
        expected = head = r.row_hash
    stored = db.scalar(select(AuditHead.hash).where(AuditHead.id == 1))
    if stored is not None and stored != head:
        return {"ok": False, "checked": checked, "unchained": unchained, "bad_id": None, "reason": "the newest rows do not match the recorded head: rows were removed from the end", "head": head}
    return {"ok": True, "checked": checked, "unchained": unchained, "bad_id": None, "reason": "", "head": head}


def main(argv: list[str]) -> int:
    from .db import SessionLocal
    if len(argv) < 2 or argv[1] != "verify":
        print("usage: python -m app.auditchain verify")
        return 2
    with SessionLocal() as db:
        res = verify_chain(db)
    print(json.dumps(res, indent=2))
    return 0 if res["ok"] else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
