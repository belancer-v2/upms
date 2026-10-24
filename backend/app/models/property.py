"""Units, owners and tenants of a building."""
from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, Float, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from ..db import Base
from .core import now


class Unit(Base):
    __tablename__ = "units"
    id: Mapped[int] = mapped_column(primary_key=True)
    property_id: Mapped[int] = mapped_column(ForeignKey("properties.id"), index=True)
    block: Mapped[str] = mapped_column(String(8), default="")
    floor: Mapped[int] = mapped_column(Integer, default=1)
    number: Mapped[str] = mapped_column(String(16))                   # A-501
    area_sqft: Mapped[float] = mapped_column(Float, default=0)
    bedrooms: Mapped[int] = mapped_column(Integer, default=3)
    # occupied | vacant | to_let_pending | to_let   (to_let needs the owner's approval)
    status: Mapped[str] = mapped_column(String(16), default="vacant", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class Occupancy(Base):
    """An owner or tenant of a unit. Kept even after move-out, so the history stays."""
    __tablename__ = "occupancies"
    id: Mapped[int] = mapped_column(primary_key=True)
    unit_id: Mapped[int] = mapped_column(ForeignKey("units.id"), index=True)
    kind: Mapped[str] = mapped_column(String(8))                      # owner | tenant
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    name: Mapped[str] = mapped_column(String(120))
    name_bn: Mapped[str] = mapped_column(String(120), default="")
    phone: Mapped[str] = mapped_column(String(32), default="")
    email: Mapped[str] = mapped_column(String(160), default="")
    resides: Mapped[bool] = mapped_column(Boolean, default=True)      # owner living in the flat
    start_date: Mapped[date] = mapped_column(Date)
    end_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
