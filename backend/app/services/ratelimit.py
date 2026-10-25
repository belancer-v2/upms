"""Rate limits and progressive lockouts that work across workers.

State lives in the rate_limits table and is written in its own short transaction, so a counter survives the request failing (a wrong
password raises 401 and the request transaction is rolled back, but the failed attempt must still count). If the database cannot be
reached the limiter falls back to per-process memory instead of letting traffic through unlimited or failing the request.
Call the limiter before the request has written anything (SQLite allows one writer at a time).
"""
from __future__ import annotations

import hashlib
import logging
import random
import threading
from datetime import timedelta, timezone

from fastapi import HTTPException, Request
from sqlalchemy.exc import IntegrityError

from .. import config
from ..db import SessionLocal
from ..models.core import now
from ..models.security import RateLimit
from ..netutil import client_ip

log = logging.getLogger("flatwise.security")
_mem: dict[str, "_Mem"] = {}
_mem_lock = threading.Lock()


class _Mem:
    def __init__(self):
        self.count, self.window_start, self.locked_until, self.strikes, self.updated_at = 0, None, None, 0, None


def aware(d):
    return d.replace(tzinfo=timezone.utc) if d is not None and d.tzinfo is None else d


def hkey(*parts: str) -> str:
    """Stable short hash for keys, so e-mail addresses never sit in the table in clear text."""
    return hashlib.sha256("|".join(p.strip().lower() for p in parts).encode()).hexdigest()[:32]


def _secs(until, t) -> int:
    return max(1, int((aware(until) - t).total_seconds()) + 1) if until and aware(until) > t else 0


def _consume(row, t, limit: int, window: int) -> int:
    if row.window_start is None or (t - aware(row.window_start)).total_seconds() >= window:
        row.window_start, row.count = t, 0
    row.count += 1
    row.updated_at = t
    if row.count > limit:
        return max(1, int(window - (t - aware(row.window_start)).total_seconds()))
    return 0


def _fail(row, t, threshold: int, window: int, base: int, cap: int) -> int:
    """Count a failure. From `threshold` failures inside the window the key locks for base * 2^n seconds (capped), doubling on every further failure."""
    if row.window_start is None or ((t - aware(row.window_start)).total_seconds() >= window and not _secs(row.locked_until, t)):
        row.window_start, row.count, row.strikes = t, 0, 0
    row.count += 1
    row.updated_at = t
    if row.count >= threshold:
        row.strikes += 1
        row.locked_until = t + timedelta(seconds=min(cap, base * 2 ** (row.strikes - 1)))
        return _secs(row.locked_until, t)
    return 0


def _run(key: str, fn):
    """fn(row, now) -> int, applied to the database row for key (created if missing), falling back to memory if the database fails."""
    t = now()
    try:
        with SessionLocal() as s:
            row = s.get(RateLimit, key, with_for_update=True)
            if row is None:
                row = RateLimit(key=key, count=0, strikes=0, window_start=None, updated_at=t)
                s.add(row)
                try:
                    s.flush()
                except IntegrityError:           # another worker created it first
                    s.rollback()
                    row = s.get(RateLimit, key, with_for_update=True)
            out = fn(row, t)
            s.commit()
            if random.random() < 0.005:
                purge()
            return out
    except Exception:  # noqa: BLE001  (never take the site down because the limiter cannot reach the database)
        log.warning("rate limiter fell back to memory", exc_info=True)
        with _mem_lock:
            return fn(_mem.setdefault(key, _Mem()), t)


def consume(key: str, limit: int, window: int) -> int:
    """Count one hit. Returns 0 if allowed, else the seconds to wait."""
    if not config.RATE_LIMITS:
        return 0
    return _run(key, lambda r, t: _consume(r, t, limit, window))


def fail(key: str, threshold: int, window: int = 900, base: int = 30, cap: int = 1800) -> int:
    """Register a failed attempt. Returns the lock length in seconds if the key is now locked, else 0."""
    if not config.RATE_LIMITS:
        return 0
    return _run(key, lambda r, t: _fail(r, t, threshold, window, base, cap))


def locked_for(key: str) -> int:
    """Seconds left on a lock, without counting anything."""
    if not config.RATE_LIMITS:
        return 0
    t = now()
    try:
        with SessionLocal() as s:
            row = s.get(RateLimit, key)
            return _secs(row.locked_until, t) if row else 0
    except Exception:  # noqa: BLE001
        with _mem_lock:
            m = _mem.get(key)
            return _secs(m.locked_until, t) if m else 0


def clear(key: str) -> None:
    try:
        with SessionLocal() as s:
            row = s.get(RateLimit, key)
            if row:
                s.delete(row)
                s.commit()
    except Exception:  # noqa: BLE001
        pass
    with _mem_lock:
        _mem.pop(key, None)


def reset_all() -> None:
    """Tests only."""
    try:
        with SessionLocal() as s:
            s.query(RateLimit).delete()
            s.commit()
    except Exception:  # noqa: BLE001
        pass
    with _mem_lock:
        _mem.clear()


def purge(days: int = 2) -> None:
    try:
        with SessionLocal() as s:
            s.query(RateLimit).filter(RateLimit.updated_at < now() - timedelta(days=days)).delete()
            s.commit()
    except Exception:  # noqa: BLE001
        pass


def too_many(wait: int, msg: str = "Too many requests. Please wait a little and try again.") -> HTTPException:
    return HTTPException(429, msg, headers={"Retry-After": str(wait)})


def limit(name: str, count: int, window: int):
    """Route dependency: at most `count` hits per client address per `window` seconds."""
    def dep(request: Request) -> None:
        wait = consume(f"{name}:ip:{client_ip(request)}", count, window)
        if wait:
            raise too_many(wait)
    dep.__name__ = f"rate_limit_{name}"
    return dep
