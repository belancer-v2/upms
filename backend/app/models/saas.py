"""SaaS side: plans, subscriptions, leads. Prices are stored per building size band, in paisa."""
from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, Integer, JSON, String, Text
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
    email_included: Mapped[dict] = mapped_column(JSON, default=dict)  # email credits per month per band (M19)


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


class SaasInvoice(Base):
    """What FlatWise bills its customers (subscription, setup, SMS packs)."""
    __tablename__ = "saas_invoices"
    id: Mapped[int] = mapped_column(primary_key=True)
    number: Mapped[str] = mapped_column(String(24), unique=True)
    org_id: Mapped[int] = mapped_column(ForeignKey("organizations.id"), index=True)
    kind: Mapped[str] = mapped_column(String(12), default="subscription")  # subscription | setup | sms | credits
    period: Mapped[str] = mapped_column(String(8), default="")             # 2026-10, or 2026 for yearly
    description: Mapped[str] = mapped_column(String(200), default="")
    amount: Mapped[int] = mapped_column(BigInteger)                           # paisa
    status: Mapped[str] = mapped_column(String(10), default="issued", index=True)  # issued | paid | void
    issued_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    due_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    method: Mapped[str] = mapped_column(String(16), default="")
    trx_id: Mapped[str] = mapped_column(String(40), default="")
    items: Mapped[list] = mapped_column(JSON, default=list)               # M19 credit purchases: [{kind, name, name_bn, credits, amount}]
    vat_bps: Mapped[int] = mapped_column(Integer, default=0)               # M19: VAT rate in basis points at the time of sale
    vat_amount: Mapped[int] = mapped_column(BigInteger, default=0)            # M19: paisa, included in amount


class SmsLedger(Base):
    """Prepaid SMS credits per organization. Append-only: balance is the sum of deltas."""
    __tablename__ = "sms_ledger"
    id: Mapped[int] = mapped_column(primary_key=True)
    org_id: Mapped[int] = mapped_column(ForeignKey("organizations.id"), index=True)
    delta: Mapped[int] = mapped_column(Integer)
    reason: Mapped[str] = mapped_column(String(60), default="")
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    by_user_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    invoice_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)   # M19: the invoice a purchased grant belongs to


class LeadNote(Base):
    __tablename__ = "lead_notes"
    id: Mapped[int] = mapped_column(primary_key=True)
    lead_id: Mapped[int] = mapped_column(ForeignKey("leads.id"), index=True)
    user_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    text: Mapped[str] = mapped_column(Text)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class FeatureOverride(Base):
    """Per-organization switch that beats the plan (for example a goodwill extra during a trial)."""
    __tablename__ = "feature_overrides"
    id: Mapped[int] = mapped_column(primary_key=True)
    org_id: Mapped[int] = mapped_column(ForeignKey("organizations.id"), index=True)
    key: Mapped[str] = mapped_column(String(30))
    enabled: Mapped[bool] = mapped_column(default=True)


class CancellationRequest(Base):
    """A building's request to end its subscription (raised from the Plan page), approved or rejected by FlatWise.
    A SaaS admin can also end a subscription directly; that is recorded here as an approved row with no requester."""
    __tablename__ = "cancellation_requests"
    id: Mapped[int] = mapped_column(primary_key=True)
    org_id: Mapped[int] = mapped_column(ForeignKey("organizations.id"), index=True)
    requested_by: Mapped[int | None] = mapped_column(Integer, nullable=True)
    reason: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(10), default="pending", index=True)  # pending | approved | rejected | withdrawn
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    decided_by: Mapped[int | None] = mapped_column(Integer, nullable=True)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    decision_note: Mapped[str] = mapped_column(Text, default="")
