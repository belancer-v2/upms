"""M19: SMS and email credits sold by FlatWise to buildings. Money is integer paisa. Balances are ledger sums, never edited."""
from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from ..db import Base
from .core import now


class CreditPack(Base):
    """A pack FlatWise sells. Prices are set by SaaS finance in the console."""
    __tablename__ = "credit_packs"
    id: Mapped[int] = mapped_column(primary_key=True)
    kind: Mapped[str] = mapped_column(String(6), index=True)       # sms | email
    name: Mapped[str] = mapped_column(String(80))
    name_bn: Mapped[str] = mapped_column(String(80), default="")
    credits: Mapped[int] = mapped_column(Integer)
    price: Mapped[int] = mapped_column(BigInteger)                    # paisa, before VAT
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    sort: Mapped[int] = mapped_column(Integer, default=0)


class EmailLedger(Base):
    """Prepaid email credits per organization. Append-only, parallel to SmsLedger."""
    __tablename__ = "email_ledger"
    id: Mapped[int] = mapped_column(primary_key=True)
    org_id: Mapped[int] = mapped_column(ForeignKey("organizations.id"), index=True)
    delta: Mapped[int] = mapped_column(Integer)
    reason: Mapped[str] = mapped_column(String(60), default="")
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    by_user_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    invoice_id: Mapped[int | None] = mapped_column(ForeignKey("saas_invoices.id"), nullable=True, index=True)


class CreditPurchase(Base):
    """One attempt to buy a pack, by sandbox gateway (mode gateway) or by manual transfer (mode manual)."""
    __tablename__ = "credit_purchases"
    id: Mapped[int] = mapped_column(primary_key=True)
    token: Mapped[str] = mapped_column(String(48), unique=True)    # public session id (unguessable)
    org_id: Mapped[int] = mapped_column(ForeignKey("organizations.id"), index=True)
    property_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    user_id: Mapped[int] = mapped_column(Integer)
    pack_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    kind: Mapped[str] = mapped_column(String(6))
    pack_name: Mapped[str] = mapped_column(String(80), default="")
    pack_name_bn: Mapped[str] = mapped_column(String(80), default="")
    credits: Mapped[int] = mapped_column(Integer)
    price: Mapped[int] = mapped_column(BigInteger)                    # paisa, before VAT (snapshot)
    vat_bps: Mapped[int] = mapped_column(Integer, default=0)
    vat: Mapped[int] = mapped_column(BigInteger, default=0)
    total: Mapped[int] = mapped_column(BigInteger)                    # what the buyer pays
    mode: Mapped[str] = mapped_column(String(8), default="gateway")        # gateway | manual
    method: Mapped[str] = mapped_column(String(8))                 # bkash | nagad | card | bank
    status: Mapped[str] = mapped_column(String(10), default="created", index=True)   # created | pending | paid | failed | expired | rejected
    provider_ref: Mapped[str] = mapped_column(String(40), default="")
    trx_id: Mapped[str] = mapped_column(String(40), default="")
    claimed_amount: Mapped[int | None] = mapped_column(BigInteger, nullable=True)   # manual: what the buyer says they sent
    invoice_id: Mapped[int | None] = mapped_column(ForeignKey("saas_invoices.id"), nullable=True, index=True)
    idem_key: Mapped[str] = mapped_column(String(60), unique=True)
    note: Mapped[str] = mapped_column(String(200), default="")
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    verified_by: Mapped[int | None] = mapped_column(Integer, nullable=True)


class CreditSetting(Base):
    """Per-organization low-balance thresholds."""
    __tablename__ = "credit_settings"
    id: Mapped[int] = mapped_column(primary_key=True)
    org_id: Mapped[int] = mapped_column(ForeignKey("organizations.id"), unique=True)
    sms_low: Mapped[int] = mapped_column(Integer, default=100)
    email_low: Mapped[int] = mapped_column(Integer, default=100)


class PlatformSetting(Base):
    """FlatWise-wide key/value settings (VAT, where manual payments are sent)."""
    __tablename__ = "platform_settings"
    key: Mapped[str] = mapped_column(String(30), primary_key=True)
    value: Mapped[str] = mapped_column(String(200), default="")
