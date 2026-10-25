"""Vendor contracts (annual maintenance contracts) for lift, generator, CCTV, fire safety and pest control, with a service visit log. Money is integer paisa."""
from datetime import date, datetime

from sqlalchemy import BigInteger, Date, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from ..db import Base
from .core import now


class Contract(Base):
    __tablename__ = "contracts"
    id: Mapped[int] = mapped_column(primary_key=True)
    property_id: Mapped[int] = mapped_column(ForeignKey("properties.id"), index=True)
    kind: Mapped[str] = mapped_column(String(12), default="other")      # lift | generator | cctv | fire | pest | other
    title: Mapped[str] = mapped_column(String(160))
    vendor_id: Mapped[int | None] = mapped_column(ForeignKey("vendors.id"), nullable=True)
    vendor_name: Mapped[str] = mapped_column(String(100), default="")   # used when the vendor is not in the vendor list
    start_date: Mapped[date] = mapped_column(Date)
    end_date: Mapped[date] = mapped_column(Date, index=True)
    annual_cost: Mapped[int] = mapped_column(BigInteger, default=0)     # paisa per year
    interval_days: Mapped[int] = mapped_column(Integer, default=90)     # a service visit is due this many days after the last one
    status: Mapped[str] = mapped_column(String(8), default="active")    # active | ended
    note: Mapped[str] = mapped_column(Text, default="")
    created_by: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class ContractVisit(Base):
    """One service visit by the vendor. cost is optional; 'create expense' turns it into a finance Expense (expense_id)."""
    __tablename__ = "contract_visits"
    id: Mapped[int] = mapped_column(primary_key=True)
    contract_id: Mapped[int] = mapped_column(ForeignKey("contracts.id"), index=True)
    visited_on: Mapped[date] = mapped_column(Date, index=True)
    technician: Mapped[str] = mapped_column(String(100), default="")
    notes: Mapped[str] = mapped_column(Text, default="")
    cost: Mapped[int] = mapped_column(BigInteger, default=0)            # paisa, 0 = covered by the annual fee
    expense_id: Mapped[int | None] = mapped_column(ForeignKey("expenses.id"), nullable=True)
    created_by: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class ContractDoc(Base):
    """The signed contract, or a visit report. Stored under uploads/contracts/<property>/."""
    __tablename__ = "contract_docs"
    id: Mapped[int] = mapped_column(primary_key=True)
    contract_id: Mapped[int] = mapped_column(ForeignKey("contracts.id"), index=True)
    visit_id: Mapped[int | None] = mapped_column(ForeignKey("contract_visits.id"), nullable=True)
    kind: Mapped[str] = mapped_column(String(10), default="contract")   # contract | report | other
    filename: Mapped[str] = mapped_column(String(160), default="")
    stored: Mapped[str] = mapped_column(String(80), default="")
    content_type: Mapped[str] = mapped_column(String(60), default="")
    size: Mapped[int] = mapped_column(Integer, default=0)
    created_by: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
