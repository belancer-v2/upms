"""Owner rental records add-on (M14). Private between one flat's owner and its current tenant. Money is integer paisa."""
from datetime import date, datetime

from sqlalchemy import BigInteger, Boolean, Date, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from ..db import Base
from .core import now


class RentalSetting(Base):
    """The per-flat switch. Off by default (no row = off). Also holds the flat's receipt counter."""
    __tablename__ = "rental_settings"
    id: Mapped[int] = mapped_column(primary_key=True)
    unit_id: Mapped[int] = mapped_column(ForeignKey("units.id"), unique=True)
    property_id: Mapped[int] = mapped_column(ForeignKey("properties.id"), index=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    receipt_seq: Mapped[int] = mapped_column(Integer, default=0)
    updated_by: Mapped[int | None] = mapped_column(Integer, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class RentalAgreement(Base):
    __tablename__ = "rental_agreements"
    id: Mapped[int] = mapped_column(primary_key=True)
    unit_id: Mapped[int] = mapped_column(ForeignKey("units.id"), index=True)
    title: Mapped[str] = mapped_column(String(160))
    start_date: Mapped[date] = mapped_column(Date)
    end_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    rent: Mapped[int] = mapped_column(BigInteger, default=0)          # monthly, paisa
    advance: Mapped[int] = mapped_column(BigInteger, default=0)       # paisa
    filename: Mapped[str] = mapped_column(String(160), default="")
    stored: Mapped[str] = mapped_column(String(80), default="")
    content_type: Mapped[str] = mapped_column(String(60), default="")
    size: Mapped[int] = mapped_column(Integer, default=0)
    created_by: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class RentalPayment(Base):
    """Rent received for a month. The owner's entries are confirmed at once; a tenant's "I paid" waits for the owner."""
    __tablename__ = "rental_payments"
    id: Mapped[int] = mapped_column(primary_key=True)
    unit_id: Mapped[int] = mapped_column(ForeignKey("units.id"), index=True)
    period: Mapped[str] = mapped_column(String(7), index=True)     # YYYY-MM
    amount: Mapped[int] = mapped_column(BigInteger)                   # paisa
    method: Mapped[str] = mapped_column(String(8))                 # cash | bank
    paid_on: Mapped[date] = mapped_column(Date)
    note: Mapped[str] = mapped_column(String(300), default="")
    bank_ref: Mapped[str] = mapped_column(String(60), default="")
    status: Mapped[str] = mapped_column(String(10), default="confirmed", index=True)   # confirmed | pending | rejected
    source: Mapped[str] = mapped_column(String(8), default="owner")                    # owner | tenant
    receipt_no: Mapped[str] = mapped_column(String(30), default="")
    receipt_seq: Mapped[int] = mapped_column(Integer, default=0)
    created_by: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class RentalNote(Base):
    """Follow-up history on rent: reminders sent and the owner's notes."""
    __tablename__ = "rental_notes"
    id: Mapped[int] = mapped_column(primary_key=True)
    unit_id: Mapped[int] = mapped_column(ForeignKey("units.id"), index=True)
    kind: Mapped[str] = mapped_column(String(10), default="note")  # note | reminder
    period: Mapped[str] = mapped_column(String(7), default="")
    body: Mapped[str] = mapped_column(String(400), default="")
    sms_status: Mapped[str] = mapped_column(String(8), default="")  # sent | failed | ""
    created_by: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class RentalIssue(Base):
    __tablename__ = "rental_issues"
    id: Mapped[int] = mapped_column(primary_key=True)
    unit_id: Mapped[int] = mapped_column(ForeignKey("units.id"), index=True)
    title: Mapped[str] = mapped_column(String(160))
    body: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(12), default="open", index=True)   # open | in_progress | fixed | closed
    cost: Mapped[int | None] = mapped_column(BigInteger, nullable=True)              # paisa
    cost_note: Mapped[str] = mapped_column(String(200), default="")
    photo_name: Mapped[str] = mapped_column(String(160), default="")
    photo_stored: Mapped[str] = mapped_column(String(80), default="")
    photo_type: Mapped[str] = mapped_column(String(60), default="")
    raised_by: Mapped[int | None] = mapped_column(Integer, nullable=True)
    raised_side: Mapped[str] = mapped_column(String(8), default="tenant")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class RentalComment(Base):
    __tablename__ = "rental_comments"
    id: Mapped[int] = mapped_column(primary_key=True)
    issue_id: Mapped[int] = mapped_column(ForeignKey("rental_issues.id"), index=True)
    user_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    side: Mapped[str] = mapped_column(String(8), default="owner")
    body: Mapped[str] = mapped_column(String(1000))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class RentalFollowup(Base):
    __tablename__ = "rental_followups"
    id: Mapped[int] = mapped_column(primary_key=True)
    unit_id: Mapped[int] = mapped_column(ForeignKey("units.id"), index=True)
    text: Mapped[str] = mapped_column(String(300))
    due_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    ref_kind: Mapped[str] = mapped_column(String(8), default="")   # rent | issue | ""
    ref: Mapped[str] = mapped_column(String(16), default="")       # a period (rent) or an issue id
    done: Mapped[bool] = mapped_column(Boolean, default=False)
    created_by: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    done_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
