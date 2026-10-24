"""Service charge: rules, invoices, payments, and the message queue used for reminders."""
from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from ..db import Base
from .core import now


class ChargeRule(Base):
    __tablename__ = "charge_rules"
    id: Mapped[int] = mapped_column(primary_key=True)
    property_id: Mapped[int] = mapped_column(ForeignKey("properties.id"), index=True)
    name: Mapped[str] = mapped_column(String(80))
    name_bn: Mapped[str] = mapped_column(String(80), default="")
    kind: Mapped[str] = mapped_column(String(10), default="flat")   # flat | per_sqft
    amount: Mapped[int] = mapped_column(Integer)                    # paisa. For per_sqft: paisa per square foot
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class Invoice(Base):
    __tablename__ = "invoices"
    __table_args__ = (UniqueConstraint("unit_id", "period", name="one_invoice_per_unit_period"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    property_id: Mapped[int] = mapped_column(ForeignKey("properties.id"), index=True)
    unit_id: Mapped[int] = mapped_column(ForeignKey("units.id"), index=True)
    period: Mapped[str] = mapped_column(String(16), index=True)     # 2026-10, or HALL-12 for an amenity booking
    number: Mapped[str] = mapped_column(String(32))
    issue_date: Mapped[date] = mapped_column(Date)
    due_date: Mapped[date] = mapped_column(Date)
    total: Mapped[int] = mapped_column(Integer)                     # paisa
    paid: Mapped[int] = mapped_column(Integer, default=0)           # paisa, verified payments only
    status: Mapped[str] = mapped_column(String(8), default="open")  # open | partial | paid | void


class InvoiceLine(Base):
    __tablename__ = "invoice_lines"
    id: Mapped[int] = mapped_column(primary_key=True)
    invoice_id: Mapped[int] = mapped_column(ForeignKey("invoices.id"), index=True)
    description: Mapped[str] = mapped_column(String(120))
    description_bn: Mapped[str] = mapped_column(String(120), default="")
    amount: Mapped[int] = mapped_column(Integer)


class Payment(Base):
    __tablename__ = "payments"
    id: Mapped[int] = mapped_column(primary_key=True)
    property_id: Mapped[int] = mapped_column(ForeignKey("properties.id"), index=True)
    invoice_id: Mapped[int] = mapped_column(ForeignKey("invoices.id"), index=True)
    unit_id: Mapped[int] = mapped_column(Integer, index=True)
    amount: Mapped[int] = mapped_column(Integer)
    method: Mapped[str] = mapped_column(String(8))                  # bkash | nagad | bank | cash
    trx_id: Mapped[str] = mapped_column(String(40), default="")
    paid_on: Mapped[date] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(10), default="pending", index=True)  # pending | verified | rejected
    submitted_by: Mapped[int | None] = mapped_column(Integer, nullable=True)
    verified_by: Mapped[int | None] = mapped_column(Integer, nullable=True)
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    receipt_no: Mapped[str] = mapped_column(String(24), default="")
    note: Mapped[str] = mapped_column(String(200), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class Message(Base):
    """Every SMS or email the system sends, and why. The idempotency key stops duplicates."""
    __tablename__ = "messages"
    id: Mapped[int] = mapped_column(primary_key=True)
    property_id: Mapped[int] = mapped_column(ForeignKey("properties.id"), index=True)
    unit_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    to_name: Mapped[str] = mapped_column(String(120), default="")
    to_phone: Mapped[str] = mapped_column(String(32), default="")
    channel: Mapped[str] = mapped_column(String(8), default="sms")
    template: Mapped[str] = mapped_column(String(30))
    lang: Mapped[str] = mapped_column(String(2), default="bn")
    body: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(8), default="queued", index=True)   # queued | sent | failed
    error: Mapped[str] = mapped_column(String(120), default="")
    idem_key: Mapped[str] = mapped_column(String(80), unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
