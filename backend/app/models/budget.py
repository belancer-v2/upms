"""Month-by-month budget lines and month locks. Money is integer paisa."""
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from ..db import Base
from .core import now


class BudgetMonth(Base):
    __tablename__ = "budget_months"
    __table_args__ = (UniqueConstraint("property_id", "year", "month", "category", name="one_budget_month_line"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    property_id: Mapped[int] = mapped_column(ForeignKey("properties.id"), index=True)
    year: Mapped[int] = mapped_column(Integer)
    month: Mapped[int] = mapped_column(Integer)       # 1..12
    category: Mapped[str] = mapped_column(String(12))
    amount: Mapped[int] = mapped_column(Integer)      # that month, paisa


class BudgetLock(Base):
    """A closed month. Editing it again needs an explicit override and is audit-logged."""
    __tablename__ = "budget_locks"
    __table_args__ = (UniqueConstraint("property_id", "year", "month", name="one_budget_lock"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    property_id: Mapped[int] = mapped_column(ForeignKey("properties.id"), index=True)
    year: Mapped[int] = mapped_column(Integer)
    month: Mapped[int] = mapped_column(Integer)
    locked_by: Mapped[int | None] = mapped_column(Integer, nullable=True)
    locked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
