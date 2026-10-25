"""M16: amenities (community hall first), their prices and rules, blackout dates, bookings and the slot holds that make double booking impossible."""
from datetime import date, datetime

from sqlalchemy import BigInteger, Boolean, Date, DateTime, ForeignKey, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from ..db import Base
from .core import now


class Amenity(Base):
    __tablename__ = "amenities"
    id: Mapped[int] = mapped_column(primary_key=True)
    property_id: Mapped[int] = mapped_column(ForeignKey("properties.id"), index=True)
    kind: Mapped[str] = mapped_column(String(12), default="hall")           # hall | rooftop | gym | playground | guest_room
    name: Mapped[str] = mapped_column(String(80))
    name_bn: Mapped[str] = mapped_column(String(80), default="")
    capacity: Mapped[int] = mapped_column(Integer, default=100)
    rules: Mapped[str] = mapped_column(Text, default="")
    rules_bn: Mapped[str] = mapped_column(Text, default="")
    photo_url: Mapped[str] = mapped_column(String(300), default="")
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    # {"morning": {"on": true, "owner": paisa, "tenant": paisa}, "evening": ..., "night": ..., "full": ...}
    slots: Mapped[dict] = mapped_column(JSON, default=dict)
    ext_hour_fee: Mapped[int] = mapped_column(BigInteger, default=0)           # paisa per extra hour, 0 = no extension offered
    max_ext_hours: Mapped[int] = mapped_column(Integer, default=2)
    deposit: Mapped[int] = mapped_column(BigInteger, default=0)                # refundable security deposit
    cleaning_fee: Mapped[int] = mapped_column(BigInteger, default=0)
    generator_fee: Mapped[int] = mapped_column(BigInteger, default=0)          # optional, chosen by the resident
    free_quota: Mapped[int] = mapped_column(Integer, default=0)             # free bookings per flat per year
    min_notice_days: Mapped[int] = mapped_column(Integer, default=3)
    max_advance_days: Mapped[int] = mapped_column(Integer, default=90)
    hold_days: Mapped[int] = mapped_column(Integer, default=3)              # days to pay after approval before the slot is freed
    cancel_rules: Mapped[list] = mapped_column(JSON, default=list)          # [{"days": 7, "pct": 100}, ...] refund % of the fees by days before the event


class Blackout(Base):
    __tablename__ = "amenity_blackouts"
    id: Mapped[int] = mapped_column(primary_key=True)
    property_id: Mapped[int] = mapped_column(ForeignKey("properties.id"), index=True)
    amenity_id: Mapped[int | None] = mapped_column(ForeignKey("amenities.id"), nullable=True)   # null = every amenity
    on_date: Mapped[date] = mapped_column(Date, index=True)
    reason: Mapped[str] = mapped_column(String(120), default="")
    reason_bn: Mapped[str] = mapped_column(String(120), default="")
    created_by: Mapped[int | None] = mapped_column(Integer, nullable=True)


class Booking(Base):
    __tablename__ = "amenity_bookings"
    id: Mapped[int] = mapped_column(primary_key=True)
    property_id: Mapped[int] = mapped_column(ForeignKey("properties.id"), index=True)
    amenity_id: Mapped[int] = mapped_column(ForeignKey("amenities.id"), index=True)
    unit_id: Mapped[int] = mapped_column(ForeignKey("units.id"), index=True)
    user_id: Mapped[int] = mapped_column(Integer, index=True)
    party: Mapped[str] = mapped_column(String(8), default="owner")          # owner | tenant: decides which fee applies
    on_date: Mapped[date] = mapped_column(Date, index=True)
    slot: Mapped[str] = mapped_column(String(8))                            # morning | evening | night | full
    purpose: Mapped[str] = mapped_column(String(24), default="other")
    guests: Mapped[int] = mapped_column(Integer, default=0)
    catering: Mapped[bool] = mapped_column(Boolean, default=False)
    contact: Mapped[str] = mapped_column(String(32), default="")
    note: Mapped[str] = mapped_column(String(300), default="")
    ext_hours: Mapped[int] = mapped_column(Integer, default=0)
    use_generator: Mapped[bool] = mapped_column(Boolean, default=False)
    # pending -> approved (awaiting payment) -> confirmed (paid) -> completed (handover done); or rejected | cancelled | expired
    status: Mapped[str] = mapped_column(String(10), default="pending", index=True)
    reason: Mapped[str] = mapped_column(String(300), default="")            # rejection or cancellation reason
    decided_by: Mapped[int | None] = mapped_column(Integer, nullable=True)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    invoice_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    fee: Mapped[int] = mapped_column(BigInteger, default=0)                    # all in paisa, fixed when approved
    ext_fee: Mapped[int] = mapped_column(BigInteger, default=0)
    cleaning: Mapped[int] = mapped_column(BigInteger, default=0)
    generator: Mapped[int] = mapped_column(BigInteger, default=0)
    deposit: Mapped[int] = mapped_column(BigInteger, default=0)
    total: Mapped[int] = mapped_column(BigInteger, default=0)
    free_used: Mapped[bool] = mapped_column(Boolean, default=False)         # the yearly free quota paid the slot fee
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # handover after the event
    damage_amount: Mapped[int] = mapped_column(BigInteger, default=0)
    damage_note: Mapped[str] = mapped_column(String(300), default="")
    handover_by: Mapped[int | None] = mapped_column(Integer, nullable=True)
    handover_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # money going back to the resident (deposit release or cancellation refund); recorded, not posted to the ledger
    refund_amount: Mapped[int] = mapped_column(BigInteger, default=0)
    refund_method: Mapped[str] = mapped_column(String(8), default="")
    refunded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class SlotHold(Base):
    """One row per part of the day a live booking occupies. The unique key is what makes a double booking impossible."""
    __tablename__ = "amenity_slot_holds"
    __table_args__ = (UniqueConstraint("amenity_id", "on_date", "part", name="one_booking_per_slot"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    amenity_id: Mapped[int] = mapped_column(ForeignKey("amenities.id"), index=True)
    on_date: Mapped[date] = mapped_column(Date)
    part: Mapped[str] = mapped_column(String(8))                            # morning | evening | night ("full" takes all three)
    booking_id: Mapped[int] = mapped_column(ForeignKey("amenity_bookings.id"), index=True)
