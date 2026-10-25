"""Chart of accounts, append-only journal, expenses, vendors, fixed assets and budgets. Money is integer paisa."""
from datetime import date, datetime

from sqlalchemy import BigInteger, Boolean, Date, DateTime, ForeignKey, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from ..db import Base
from .core import now


class Account(Base):
    __tablename__ = "accounts"
    __table_args__ = (UniqueConstraint("property_id", "code", name="one_code_per_building"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    property_id: Mapped[int] = mapped_column(ForeignKey("properties.id"), index=True)
    code: Mapped[str] = mapped_column(String(8))
    name: Mapped[str] = mapped_column(String(80))
    name_bn: Mapped[str] = mapped_column(String(80), default="")
    type: Mapped[str] = mapped_column(String(10))   # asset | liability | equity | income | expense


class Journal(Base):
    """One balanced entry. Rows are never edited or deleted: a mistake is fixed by a reversing entry."""
    __tablename__ = "journals"
    __table_args__ = (UniqueConstraint("property_id", "source", "source_id", name="one_entry_per_source"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    property_id: Mapped[int] = mapped_column(ForeignKey("properties.id"), index=True)
    date: Mapped[date] = mapped_column(Date, index=True)
    memo: Mapped[str] = mapped_column(String(200))
    source: Mapped[str] = mapped_column(String(20))   # payment | expense | asset | opening | reversal
    source_id: Mapped[str] = mapped_column(String(30))
    created_by: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class JournalLine(Base):
    __tablename__ = "journal_lines"
    id: Mapped[int] = mapped_column(primary_key=True)
    journal_id: Mapped[int] = mapped_column(ForeignKey("journals.id"), index=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id"), index=True)
    debit: Mapped[int] = mapped_column(BigInteger, default=0)
    credit: Mapped[int] = mapped_column(BigInteger, default=0)


class Vendor(Base):
    __tablename__ = "vendors"
    id: Mapped[int] = mapped_column(primary_key=True)
    property_id: Mapped[int] = mapped_column(ForeignKey("properties.id"), index=True)
    name: Mapped[str] = mapped_column(String(100))
    name_bn: Mapped[str] = mapped_column(String(100), default="")
    phone: Mapped[str] = mapped_column(String(32), default="")
    category: Mapped[str] = mapped_column(String(12), default="other")


class Expense(Base):
    __tablename__ = "expenses"
    id: Mapped[int] = mapped_column(primary_key=True)
    property_id: Mapped[int] = mapped_column(ForeignKey("properties.id"), index=True)
    category: Mapped[str] = mapped_column(String(12))        # utilities | repairs | salary | fuel | services | other
    vendor_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    title: Mapped[str] = mapped_column(String(160))
    amount: Mapped[int] = mapped_column(BigInteger)
    spent_on: Mapped[date] = mapped_column(Date, index=True)
    status: Mapped[str] = mapped_column(String(10), default="pending", index=True)   # pending | approved | rejected | paid
    needs_two: Mapped[bool] = mapped_column(Boolean, default=False)
    approvals: Mapped[list] = mapped_column(JSON, default=list)   # [{user_id, name, at}]
    requested_by: Mapped[int] = mapped_column(Integer)
    method: Mapped[str] = mapped_column(String(8), default="")
    paid_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    reason: Mapped[str] = mapped_column(String(200), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class Asset(Base):
    __tablename__ = "assets"
    id: Mapped[int] = mapped_column(primary_key=True)
    property_id: Mapped[int] = mapped_column(ForeignKey("properties.id"), index=True)
    name: Mapped[str] = mapped_column(String(120))
    name_bn: Mapped[str] = mapped_column(String(120), default="")
    category: Mapped[str] = mapped_column(String(20), default="equipment")
    cost: Mapped[int] = mapped_column(BigInteger)
    bought_on: Mapped[date] = mapped_column(Date)
    life_years: Mapped[int] = mapped_column(Integer, default=10)
    capitalised: Mapped[bool] = mapped_column(Boolean, default=True)
    status: Mapped[str] = mapped_column(String(10), default="in_use")   # in_use | disposed
    note: Mapped[str] = mapped_column(Text, default="")


class Budget(Base):
    __tablename__ = "budgets"
    __table_args__ = (UniqueConstraint("property_id", "year", "category", name="one_budget_line"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    property_id: Mapped[int] = mapped_column(ForeignKey("properties.id"), index=True)
    year: Mapped[int] = mapped_column(Integer)
    category: Mapped[str] = mapped_column(String(12))
    amount: Mapped[int] = mapped_column(BigInteger)      # whole year, paisa
