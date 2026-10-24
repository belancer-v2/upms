"""Tenant onboarding: a case per new tenant, their documents, and the DMP (police) pack."""
from datetime import date, datetime

from sqlalchemy import JSON, Date, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from ..db import Base
from .core import now


class TenantCase(Base):
    __tablename__ = "tenant_cases"
    id: Mapped[int] = mapped_column(primary_key=True)
    property_id: Mapped[int] = mapped_column(ForeignKey("properties.id"), index=True)
    unit_id: Mapped[int] = mapped_column(Integer, index=True)
    occupancy_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    token: Mapped[str] = mapped_column(String(24), unique=True)
    # invited | review | verified | police | done | cancelled
    status: Mapped[str] = mapped_column(String(10), default="invited", index=True)
    name: Mapped[str] = mapped_column(String(120))
    phone: Mapped[str] = mapped_column(String(32))
    rent: Mapped[int] = mapped_column(Integer, default=0)          # monthly, paisa
    advance: Mapped[int] = mapped_column(Integer, default=0)       # paisa
    start_date: Mapped[date] = mapped_column(Date)
    lease_months: Mapped[int] = mapped_column(Integer, default=12)
    details: Mapped[dict] = mapped_column(JSON, default=dict)
    nid_enc: Mapped[str] = mapped_column(String(300), default="")
    nid_last4: Mapped[str] = mapped_column(String(4), default="")
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    police_ref: Mapped[str] = mapped_column(String(60), default="")
    police_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    receipt_no: Mapped[str] = mapped_column(String(60), default="")
    events: Mapped[list] = mapped_column(JSON, default=list)       # [{at, by, key, note}]
    created_by: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class TenantDoc(Base):
    __tablename__ = "tenant_docs"
    id: Mapped[int] = mapped_column(primary_key=True)
    case_id: Mapped[int] = mapped_column(ForeignKey("tenant_cases.id"), index=True)
    kind: Mapped[str] = mapped_column(String(16))       # nid_front | nid_back | photo | agreement | noc | employer
    filename: Mapped[str] = mapped_column(String(160))
    stored: Mapped[str] = mapped_column(String(80))
    content_type: Mapped[str] = mapped_column(String(60))
    size: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(10), default="pending")   # pending | accepted | rejected
    note: Mapped[str] = mapped_column(String(160), default="")
    uploaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
