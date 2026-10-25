"""Optional online payments: per-building gateway settings and one row per checkout attempt."""
from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Integer, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from ..db import Base
from .core import now


class GatewayConfig(Base):
    __tablename__ = "gateway_configs"
    id: Mapped[int] = mapped_column(primary_key=True)
    property_id: Mapped[int] = mapped_column(ForeignKey("properties.id"), unique=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    providers: Mapped[list] = mapped_column(JSON, default=list)               # subset of bkash | nagad | card
    fee_mode: Mapped[str] = mapped_column(String(16), default="building_absorbs")   # building_absorbs | payer_pays
    fee_bps: Mapped[int] = mapped_column(Integer, default=0)                   # basis points: 150 = 1.5%
    credentials_enc: Mapped[str] = mapped_column(Text, default="")             # vault-sealed, write-only through the API
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, onupdate=now)


class GatewaySession(Base):
    __tablename__ = "gateway_sessions"
    id: Mapped[int] = mapped_column(primary_key=True)
    token: Mapped[str] = mapped_column(String(48), unique=True)                # the public session id (unguessable)
    property_id: Mapped[int] = mapped_column(ForeignKey("properties.id"), index=True)
    invoice_id: Mapped[int] = mapped_column(ForeignKey("invoices.id"), index=True)
    unit_id: Mapped[int] = mapped_column(Integer, index=True)
    user_id: Mapped[int] = mapped_column(Integer)
    provider: Mapped[str] = mapped_column(String(8))
    amount: Mapped[int] = mapped_column(BigInteger)                               # paisa credited to the invoice
    fee: Mapped[int] = mapped_column(BigInteger, default=0)                       # paisa, from fee_bps at checkout time
    fee_mode: Mapped[str] = mapped_column(String(16), default="building_absorbs")
    charged: Mapped[int] = mapped_column(BigInteger)                              # paisa the payer is asked to pay (amount, or amount + fee)
    status: Mapped[str] = mapped_column(String(8), default="created", index=True)   # created | paid | failed | expired
    provider_ref: Mapped[str] = mapped_column(String(40), default="")
    trx_id: Mapped[str] = mapped_column(String(40), default="")
    payment_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    idem_key: Mapped[str] = mapped_column(String(60), unique=True)             # one payment per session, whatever the provider replays
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
