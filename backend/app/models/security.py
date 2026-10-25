"""Security tables (P2): sign-in sessions with rotating refresh tokens, one-time e-mail / reset tokens, and a shared rate-limit store.

Nothing secret is stored in clear text: refresh tokens and one-time tokens are kept as SHA-256 hashes of 256-bit random values.
"""
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from ..db import Base
from .core import now


class AuthSession(Base):
    """One signed-in device. The refresh token rotates on every use; the access token carries this row's id and dies with it."""
    __tablename__ = "auth_sessions"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)          # SHA-256 of the current refresh token
    prev_hash: Mapped[str] = mapped_column(String(64), default="", index=True)  # the token it replaced (reuse = theft signal)
    rotated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    device: Mapped[str] = mapped_column(String(120), default="")
    ip: Mapped[str] = mapped_column(String(45), default="")
    user_agent: Mapped[str] = mapped_column(String(200), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    last_used_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_reason: Mapped[str] = mapped_column(String(30), default="")


class AuthToken(Base):
    """Single-use token sent by e-mail or SMS: password reset (kind=reset) or e-mail verification (kind=verify)."""
    __tablename__ = "auth_tokens"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(8), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    ip: Mapped[str] = mapped_column(String(45), default="")


class RateLimit(Base):
    """Fixed-window counter shared by every worker. `key` never holds raw e-mail addresses (they are hashed)."""
    __tablename__ = "rate_limits"
    key: Mapped[str] = mapped_column(String(190), primary_key=True)
    count: Mapped[int] = mapped_column(Integer, default=0)
    window_start: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    strikes: Mapped[int] = mapped_column(Integer, default=0)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, index=True)


class AuditHead(Base):
    """One row holding the newest audit hash. Its row lock serialises audit writers on PostgreSQL and MySQL, so the hash chain cannot fork."""
    __tablename__ = "audit_head"
    id: Mapped[int] = mapped_column(primary_key=True)
    hash: Mapped[str] = mapped_column(String(64), default="")
