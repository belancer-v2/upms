"""SaaS side: plans, subscriptions, leads. Prices are stored per building size band, in paisa."""
from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from ..db import Base
from .core import now

BANDS = [  # key, label, max flats (None = custom quote)
    ("S", "up to 30 flats", 30),
    ("M", "31 to 80 flats", 80),
    ("L", "81 to 200 flats", 200),
    ("XL", "200+ flats", None),
]


def band_for(units: int) -> str:
    for key, _, mx in BANDS:
        if mx is None or units <= mx:
            return key
    return "XL"


class Plan(Base):
    __tablename__ = "plans"
    key: Mapped[str] = mapped_column(String(20), primary_key=True)  # basic | standard | pro
    name: Mapped[str] = mapped_column(String(60))
    name_bn: Mapped[str] = mapped_column(String(60), default="")
    sort: Mapped[int] = mapped_column(Integer, default=0)
    monthly: Mapped[dict] = mapped_column(JSON, default=dict)      # {"S": paisa, "M": paisa, "L": paisa}
    setup: Mapped[dict] = mapped_column(JSON, default=dict)        # one-time setup fee per band
    sms_included: Mapped[dict] = mapped_column(JSON, default=dict) # SMS per month per band
    features: Mapped[list] = mapped_column(JSON, default=list)    # feature flags switched on by this plan


class Subscription(Base):
    __tablename__ = "subscriptions"
    id: Mapped[int] = mapped_column(primary_key=True)
    org_id: Mapped[int] = mapped_column(ForeignKey("organizations.id"), index=True)
    plan_key: Mapped[str] = mapped_column(ForeignKey("plans.key"))
    band: Mapped[str] = mapped_column(String(3), default="S")
    cycle: Mapped[str] = mapped_column(String(8), default="monthly")  # monthly | yearly
    status: Mapped[str] = mapped_column(String(12), default="trial")  # trial | active | past_due | suspended | cancelled
    flats: Mapped[int] = mapped_column(Integer, default=0)
    trial_ends: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    discount_pct: Mapped[int] = mapped_column(Integer, default=0)


class Lead(Base):
    __tablename__ = "leads"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    phone: Mapped[str] = mapped_column(String(32), default="")
    email: Mapped[str] = mapped_column(String(160), default="")
    building: Mapped[str] = mapped_column(String(160), default="")
    flats: Mapped[int] = mapped_column(Integer, default=0)
    city: Mapped[str] = mapped_column(String(80), default="")
    message: Mapped[str] = mapped_column(Text, default="")
    source: Mapped[str] = mapped_column(String(24), default="website")
    status: Mapped[str] = mapped_column(String(12), default="new", index=True)  # new | contacted | demo | trial | won | lost
    owner_id: Mapped[int | None] = mapped_column(Integer, nullable=True)       # SaaS sales user working this lead
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
