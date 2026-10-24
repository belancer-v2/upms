"""Notices with read proof, and versioned policies with acceptance."""
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from ..db import Base
from .core import now


class Notice(Base):
    __tablename__ = "notices"
    id: Mapped[int] = mapped_column(primary_key=True)
    property_id: Mapped[int] = mapped_column(ForeignKey("properties.id"), index=True)
    title: Mapped[str] = mapped_column(String(160))
    title_bn: Mapped[str] = mapped_column(String(160), default="")
    body: Mapped[str] = mapped_column(Text)
    body_bn: Mapped[str] = mapped_column(Text, default="")
    audience: Mapped[str] = mapped_column(String(10), default="all")      # all | owners | tenants | committee
    priority: Mapped[str] = mapped_column(String(8), default="normal")    # normal | urgent
    pinned: Mapped[bool] = mapped_column(Boolean, default=False)
    status: Mapped[str] = mapped_column(String(8), default="live")        # live | archived
    created_by: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, index=True)


class Receipt(Base):
    """One row per person a notice is meant for. read_at is the proof."""
    __tablename__ = "notice_receipts"
    id: Mapped[int] = mapped_column(primary_key=True)
    notice_id: Mapped[int] = mapped_column(ForeignKey("notices.id"), index=True)
    name: Mapped[str] = mapped_column(String(120), default="")
    unit: Mapped[str] = mapped_column(String(20), default="")
    phone: Mapped[str] = mapped_column(String(32), default="")
    user_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    token: Mapped[str] = mapped_column(String(24), unique=True)
    sms_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    read_via: Mapped[str] = mapped_column(String(5), default="")          # app | link


class Policy(Base):
    __tablename__ = "policies"
    id: Mapped[int] = mapped_column(primary_key=True)
    property_id: Mapped[int] = mapped_column(ForeignKey("properties.id"), index=True)
    title: Mapped[str] = mapped_column(String(160))
    title_bn: Mapped[str] = mapped_column(String(160), default="")


class PolicyVersion(Base):
    __tablename__ = "policy_versions"
    __table_args__ = (UniqueConstraint("policy_id", "version", name="one_version_number"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    policy_id: Mapped[int] = mapped_column(ForeignKey("policies.id"), index=True)
    version: Mapped[int] = mapped_column(Integer)
    body: Mapped[str] = mapped_column(Text)
    body_bn: Mapped[str] = mapped_column(Text, default="")
    change_note: Mapped[str] = mapped_column(String(200), default="")
    published_by: Mapped[int] = mapped_column(Integer)
    published_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class PolicyAcceptance(Base):
    __tablename__ = "policy_acceptances"
    __table_args__ = (UniqueConstraint("version_id", "user_id", name="one_acceptance"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    version_id: Mapped[int] = mapped_column(ForeignKey("policy_versions.id"), index=True)
    user_id: Mapped[int] = mapped_column(Integer, index=True)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
