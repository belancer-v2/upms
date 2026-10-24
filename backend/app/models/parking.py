"""Parking (M17): slots, who holds them, vehicles and visitor bays. A slot belongs to a flat like the flat belongs to an owner."""
from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from ..db import Base
from .core import now


class ParkingSetting(Base):
    __tablename__ = "parking_settings"
    property_id: Mapped[int] = mapped_column(ForeignKey("properties.id"), primary_key=True)
    page_size: Mapped[int] = mapped_column(Integer, default=24)


class ParkingSlot(Base):
    __tablename__ = "parking_slots"
    __table_args__ = (UniqueConstraint("property_id", "code"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    property_id: Mapped[int] = mapped_column(ForeignKey("properties.id"), index=True)
    code: Mapped[str] = mapped_column(String(32))                       # P-A-01, A-501-C1
    level: Mapped[str] = mapped_column(String(32), default="")          # level or zone
    kind: Mapped[str] = mapped_column(String(12), default="car")        # car | motorbike | bicycle
    cover: Mapped[str] = mapped_column(String(8), default="open")       # covered | open
    status: Mapped[str] = mapped_column(String(8), default="active")    # active | blocked
    visitor: Mapped[bool] = mapped_column(Boolean, default=False)       # reserved for visitors, never given to a flat
    note: Mapped[str] = mapped_column(String(200), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class ParkingAllocation(Base):
    """A slot held by a flat. until is null while it is current; ended rows stay as history."""
    __tablename__ = "parking_allocations"
    id: Mapped[int] = mapped_column(primary_key=True)
    slot_id: Mapped[int] = mapped_column(ForeignKey("parking_slots.id"), index=True)
    unit_id: Mapped[int] = mapped_column(ForeignKey("units.id"), index=True)
    vehicle_kind: Mapped[str] = mapped_column(String(12), default="car")
    since: Mapped[date] = mapped_column(Date)
    until: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)


class ParkingEntitlement(Base):
    """How many slots of each vehicle kind a flat is promised."""
    __tablename__ = "parking_entitlements"
    __table_args__ = (UniqueConstraint("unit_id", "kind"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    unit_id: Mapped[int] = mapped_column(ForeignKey("units.id"), index=True)
    kind: Mapped[str] = mapped_column(String(12))
    count: Mapped[int] = mapped_column(Integer, default=0)


class Vehicle(Base):
    __tablename__ = "vehicles"
    id: Mapped[int] = mapped_column(primary_key=True)
    property_id: Mapped[int] = mapped_column(ForeignKey("properties.id"), index=True)
    unit_id: Mapped[int] = mapped_column(ForeignKey("units.id"), index=True)
    reg_no: Mapped[str] = mapped_column(String(64))                     # as shown, normalised
    reg_norm: Mapped[str] = mapped_column(String(64), index=True)       # letters and digits only, for duplicate checks and search
    kind: Mapped[str] = mapped_column(String(12))
    make_model: Mapped[str] = mapped_column(String(80), default="")
    colour: Mapped[str] = mapped_column(String(32), default="")
    sticker: Mapped[str] = mapped_column(String(32), default="")
    holder_kind: Mapped[str] = mapped_column(String(8), default="owner")  # owner | tenant
    temporary: Mapped[bool] = mapped_column(Boolean, default=False)       # admin-issued extra permit
    status: Mapped[str] = mapped_column(String(10), default="active")     # active | to_review
    photo: Mapped[str] = mapped_column(String(80), default="")
    photo_type: Mapped[str] = mapped_column(String(24), default="")
    registered_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class ParkingVisit(Base):
    """A visitor car on a visitor bay. Plate, bay and times only; separate from the visitor-pass module."""
    __tablename__ = "parking_visits"
    id: Mapped[int] = mapped_column(primary_key=True)
    property_id: Mapped[int] = mapped_column(ForeignKey("properties.id"), index=True)
    slot_id: Mapped[int] = mapped_column(ForeignKey("parking_slots.id"), index=True)
    plate: Mapped[str] = mapped_column(String(64))
    in_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    out_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    logged_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
