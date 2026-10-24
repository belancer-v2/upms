"""M15: guard-desk visitor log, pre-approved passes, frequent visitors, resident notifications."""
from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from ..db import Base
from .core import now


class Visit(Base):
    __tablename__ = "visits"
    id: Mapped[int] = mapped_column(primary_key=True)
    property_id: Mapped[int] = mapped_column(ForeignKey("properties.id"), index=True)
    unit_id: Mapped[int] = mapped_column(ForeignKey("units.id"), index=True)
    name: Mapped[str] = mapped_column(String(120), index=True)
    phone: Mapped[str] = mapped_column(String(32), default="")
    purpose: Mapped[str] = mapped_column(String(10))                        # guest | delivery | courier | service | cab | official | other
    people: Mapped[int] = mapped_column(Integer, default=1)
    vehicle: Mapped[str] = mapped_column(String(32), default="")
    kind: Mapped[str] = mapped_column(String(10), default="walkin")         # walkin | delivery | pass | frequent
    status: Mapped[str] = mapped_column(String(10), default="waiting", index=True)   # waiting | approved | denied | in | out | cancelled
    photo_file: Mapped[str] = mapped_column(String(80), default="")
    photo_type: Mapped[str] = mapped_column(String(12), default="")
    decided_by: Mapped[int | None] = mapped_column(Integer, nullable=True)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    decision_via: Mapped[str] = mapped_column(String(10), default="")       # resident | pass | frequent | delivery | override
    note: Mapped[str] = mapped_column(String(200), default="")
    pass_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    frequent_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    in_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    out_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_by: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, index=True)


class VisitorPass(Base):
    """A pre-approved visitor. The 6-digit code is stored only as a keyed hash and shown once."""
    __tablename__ = "visitor_passes"
    id: Mapped[int] = mapped_column(primary_key=True)
    property_id: Mapped[int] = mapped_column(ForeignKey("properties.id"), index=True)
    unit_id: Mapped[int] = mapped_column(ForeignKey("units.id"), index=True)
    name: Mapped[str] = mapped_column(String(120))
    purpose: Mapped[str] = mapped_column(String(10), default="guest")
    people: Mapped[int] = mapped_column(Integer, default=1)
    vehicle: Mapped[str] = mapped_column(String(32), default="")
    valid_from: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    valid_to: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    code_hash: Mapped[str] = mapped_column(String(64), index=True)
    status: Mapped[str] = mapped_column(String(10), default="active")       # active | used | cancelled
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_by: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class FrequentVisitor(Base):
    __tablename__ = "frequent_visitors"
    id: Mapped[int] = mapped_column(primary_key=True)
    property_id: Mapped[int] = mapped_column(ForeignKey("properties.id"), index=True)
    unit_id: Mapped[int] = mapped_column(ForeignKey("units.id"), index=True)
    name: Mapped[str] = mapped_column(String(120))
    phone: Mapped[str] = mapped_column(String(32), default="")
    role: Mapped[str] = mapped_column(String(10), default="maid")           # maid | driver | tutor | cook | other
    valid_from: Mapped[date] = mapped_column(Date)
    valid_to: Mapped[date] = mapped_column(Date)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_by: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class VisitorNotice(Base):
    """One notification entry per resident login of the flat."""
    __tablename__ = "visitor_notices"
    id: Mapped[int] = mapped_column(primary_key=True)
    property_id: Mapped[int] = mapped_column(ForeignKey("properties.id"), index=True)
    user_id: Mapped[int] = mapped_column(Integer, index=True)
    unit_id: Mapped[int] = mapped_column(ForeignKey("units.id"))
    visit_id: Mapped[int] = mapped_column(ForeignKey("visits.id"), index=True)
    kind: Mapped[str] = mapped_column(String(10))                           # ask | info
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, index=True)
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class VisitorSetting(Base):
    __tablename__ = "visitor_settings"
    __table_args__ = (UniqueConstraint("property_id", name="one_visitor_setting"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    property_id: Mapped[int] = mapped_column(ForeignKey("properties.id"))
    page_size: Mapped[int] = mapped_column(Integer, default=10)
    overstay_hours: Mapped[int] = mapped_column(Integer, default=12)
