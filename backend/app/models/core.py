"""Core tenancy and identity model.

Tenancy: Organization -> Property (building) -> Unit. A Membership ties a user to a role
inside an organization/property (and optionally a unit). One person can hold many
memberships, which is how "flat owner + committee member" works.
"""
from datetime import datetime, timezone

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy import false as sa_false, true as sa_true
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..db import Base


def now() -> datetime:
    return datetime.now(timezone.utc)


SAAS_ROLES = ["SUPER_ADMIN", "SAAS_ADMIN", "SAAS_FINANCE", "SAAS_SALES", "SAAS_USER"]
CUSTOMER_ROLES = [
    "AGENCY_MANAGER", "PROPERTY_ADMIN", "FLAT_OWNER", "TENANT", "CARETAKER",
    "PRESIDENT", "SECRETARY", "TREASURER", "MEMBER", "AUDITOR", "GUARD", "OWNER_REP",
]
COMMITTEE_ROLES = ["PRESIDENT", "SECRETARY", "TREASURER", "MEMBER"]


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(160), unique=True, index=True)
    phone: Mapped[str] = mapped_column(String(32), default="")
    name: Mapped[str] = mapped_column(String(120))
    name_bn: Mapped[str] = mapped_column(String(120), default="")
    password_hash: Mapped[str] = mapped_column(String(100))
    lang: Mapped[str] = mapped_column(String(4), default="en")
    saas_role: Mapped[str | None] = mapped_column(String(24), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    # Security (P2). token_version is bumped to invalidate every signed token at once (password change, role removal).
    token_version: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    must_change_password: Mapped[bool] = mapped_column(Boolean, default=False, server_default=sa_false())
    password_changed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    email_verified: Mapped[bool] = mapped_column(Boolean, default=True, server_default=sa_true())
    memberships: Mapped[list["Membership"]] = relationship(back_populates="user", cascade="all, delete-orphan")


class Organization(Base):
    __tablename__ = "organizations"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(160))
    name_bn: Mapped[str] = mapped_column(String(160), default="")
    kind: Mapped[str] = mapped_column(String(12), default="committee")  # committee | agency
    status: Mapped[str] = mapped_column(String(12), default="trial")  # trial | active | suspended
    city: Mapped[str] = mapped_column(String(80), default="Dhaka")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    properties: Mapped[list["Property"]] = relationship(back_populates="org", cascade="all, delete-orphan")


class Property(Base):
    """A building. This is the unit SaaS plans are priced on."""
    __tablename__ = "properties"
    id: Mapped[int] = mapped_column(primary_key=True)
    org_id: Mapped[int] = mapped_column(ForeignKey("organizations.id"), index=True)
    name: Mapped[str] = mapped_column(String(160))
    name_bn: Mapped[str] = mapped_column(String(160), default="")
    address: Mapped[str] = mapped_column(String(240), default="")
    city: Mapped[str] = mapped_column(String(80), default="Dhaka")
    kind: Mapped[str] = mapped_column(String(16), default="residential")
    floors: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    org: Mapped[Organization] = relationship(back_populates="properties")


class Membership(Base):
    __tablename__ = "memberships"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    org_id: Mapped[int] = mapped_column(ForeignKey("organizations.id"), index=True)
    property_id: Mapped[int | None] = mapped_column(ForeignKey("properties.id"), nullable=True, index=True)
    unit_id: Mapped[int | None] = mapped_column(Integer, nullable=True)  # FK added with the units table (M3)
    role: Mapped[str] = mapped_column(String(24), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    user: Mapped[User] = relationship(back_populates="memberships")


class AuditLog(Base):
    """Append-only. Never updated or deleted by the application."""
    __tablename__ = "audit_log"
    id: Mapped[int] = mapped_column(primary_key=True)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, index=True)
    user_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    org_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    property_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    action: Mapped[str] = mapped_column(String(60), index=True)
    entity: Mapped[str] = mapped_column(String(60), default="")
    entity_id: Mapped[str] = mapped_column(String(40), default="")
    meta: Mapped[dict] = mapped_column(JSON, default=dict)
    note: Mapped[str] = mapped_column(Text, default="")
    # Tamper evidence (P2): row_hash = SHA-256 over this row and prev_hash, so editing or removing a row breaks the chain. See app/auditchain.py.
    prev_hash: Mapped[str] = mapped_column(String(64), default="", server_default="")
    row_hash: Mapped[str] = mapped_column(String(64), default="", server_default="")
