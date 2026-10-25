"""P3: background job bookkeeping. Own tables only, so existing tables are not altered.

JobLock         one row per job name; whoever holds an unexpired row is the only runner (multi-worker safe)
JobRun          history: one row per attempt (schedule or manual), with result or error
JobMark         idempotency marks for jobs ("this reminder step was already sent"); unique key
SystemAlert     things the SaaS team must look at (failed integrity check, stuck payment, unpaid dunning)
BuildingAutomation  per-building opt-ins (automatic monthly billing). Default off.
SmsDispatch     provider-side facts about one SMS Message (segments, provider id, delivery report)
"""
from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from ..db import Base
from .core import now


class JobLock(Base):
    __tablename__ = "job_locks"
    name: Mapped[str] = mapped_column(String(60), primary_key=True)
    owner: Mapped[str] = mapped_column(String(80), default="")
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class JobRun(Base):
    __tablename__ = "job_runs"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(60), index=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, index=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(10), default="running", index=True)   # running | ok | warn | failed | skipped
    trigger: Mapped[str] = mapped_column(String(10), default="schedule")             # schedule | manual
    owner: Mapped[str] = mapped_column(String(80), default="")                       # lock owner (host:pid:rand)
    lock_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    by_user_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    result: Mapped[dict] = mapped_column(JSON, default=dict)
    error: Mapped[str] = mapped_column(Text, default="")


class JobMark(Base):
    __tablename__ = "job_marks"
    key: Mapped[str] = mapped_column(String(120), primary_key=True)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, index=True)


class SystemAlert(Base):
    __tablename__ = "system_alerts"
    id: Mapped[int] = mapped_column(primary_key=True)
    dedupe_key: Mapped[str] = mapped_column(String(120), unique=True)
    kind: Mapped[str] = mapped_column(String(30), index=True)       # integrity | payment_stuck | dunning | job_failed | low_credit
    severity: Mapped[str] = mapped_column(String(8), default="warn")  # info | warn | error
    message: Mapped[str] = mapped_column(Text, default="")
    meta: Mapped[dict] = mapped_column(JSON, default=dict)
    org_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    property_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, index=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class BuildingAutomation(Base):
    __tablename__ = "building_automation"
    property_id: Mapped[int] = mapped_column(ForeignKey("properties.id"), primary_key=True)
    auto_billing: Mapped[bool] = mapped_column(Boolean, default=False)   # opt-in: create the month's invoices by itself
    bill_day: Mapped[int] = mapped_column(Integer, default=1)            # day of month (1-28) the run happens on
    due_day: Mapped[int] = mapped_column(Integer, default=10)            # due day written on those invoices
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, onupdate=now)


class SmsDispatch(Base):
    __tablename__ = "sms_dispatch"
    message_id: Mapped[int] = mapped_column(ForeignKey("messages.id"), primary_key=True)
    provider: Mapped[str] = mapped_column(String(20), default="")
    provider_ref: Mapped[str] = mapped_column(String(80), default="", index=True)
    segments: Mapped[int] = mapped_column(Integer, default=1)
    encoding: Mapped[str] = mapped_column(String(8), default="gsm")      # gsm | unicode
    credits: Mapped[int] = mapped_column(Integer, default=1)             # credits spent for this message
    dlr_status: Mapped[str] = mapped_column(String(16), default="")      # delivered | undelivered | "" (no report yet)
    dlr_detail: Mapped[str] = mapped_column(String(120), default="")
    dlr_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    refunded: Mapped[bool] = mapped_column(Boolean, default=False)
