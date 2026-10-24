"""Building staff (caretaker, guards, cleaners), the NID vault, and monthly salary sheets."""
from datetime import date, datetime

from sqlalchemy import Date, DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from ..db import Base
from .core import now


class Staff(Base):
    __tablename__ = "staff"
    id: Mapped[int] = mapped_column(primary_key=True)
    property_id: Mapped[int] = mapped_column(ForeignKey("properties.id"), index=True)
    name: Mapped[str] = mapped_column(String(100))
    name_bn: Mapped[str] = mapped_column(String(100), default="")
    role: Mapped[str] = mapped_column(String(12), default="other")   # caretaker | guard | cleaner | driver | other
    phone: Mapped[str] = mapped_column(String(32), default="")
    joined: Mapped[date] = mapped_column(Date)
    salary: Mapped[int] = mapped_column(Integer)                      # monthly, paisa
    status: Mapped[str] = mapped_column(String(8), default="active")  # active | left
    nid_enc: Mapped[str] = mapped_column(String(300), default="")     # encrypted NID number
    nid_last4: Mapped[str] = mapped_column(String(4), default="")


class NidView(Base):
    """Every time someone reveals a full NID, it is written here. Rows are never edited."""
    __tablename__ = "nid_views"
    id: Mapped[int] = mapped_column(primary_key=True)
    property_id: Mapped[int] = mapped_column(Integer, index=True)
    staff_id: Mapped[int] = mapped_column(Integer, index=True)
    viewer_id: Mapped[int] = mapped_column(Integer)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class SalarySheet(Base):
    __tablename__ = "salary_sheets"
    __table_args__ = (UniqueConstraint("property_id", "period", name="one_sheet_per_month"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    property_id: Mapped[int] = mapped_column(ForeignKey("properties.id"), index=True)
    period: Mapped[str] = mapped_column(String(7))
    status: Mapped[str] = mapped_column(String(10), default="draft")   # draft | approved | paid
    created_by: Mapped[int] = mapped_column(Integer)
    approved_by: Mapped[int | None] = mapped_column(Integer, nullable=True)
    paid_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    method: Mapped[str] = mapped_column(String(8), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class SalaryLine(Base):
    __tablename__ = "salary_lines"
    id: Mapped[int] = mapped_column(primary_key=True)
    sheet_id: Mapped[int] = mapped_column(ForeignKey("salary_sheets.id"), index=True)
    staff_id: Mapped[int] = mapped_column(Integer, index=True)
    base: Mapped[int] = mapped_column(Integer)
    bonus: Mapped[int] = mapped_column(Integer, default=0)
    deduction: Mapped[int] = mapped_column(Integer, default=0)
    bonus_kind: Mapped[str] = mapped_column(String(8), default="")    # eid | other
    note: Mapped[str] = mapped_column(String(120), default="")
