"""Optional photo and personal details for any person: a signed-in user, an occupant (owner/tenant) or a staff entry.

One small table keyed by (kind, ref_id), so no existing table needs new columns and old dev databases just get a new table.
"""
from datetime import date, datetime

from sqlalchemy import JSON, Date, DateTime, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from ..db import Base
from .core import now


class Profile(Base):
    __tablename__ = "profiles"
    __table_args__ = (UniqueConstraint("kind", "ref_id", name="one_profile_per_person"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    kind: Mapped[str] = mapped_column(String(10))                       # user | occupant | staff
    ref_id: Mapped[int] = mapped_column(Integer, index=True)
    photo_file: Mapped[str] = mapped_column(String(120), default="")
    photo_type: Mapped[str] = mapped_column(String(20), default="")
    photo_ver: Mapped[int] = mapped_column(Integer, default=0)          # bumps on every change, used to bust caches
    about: Mapped[str] = mapped_column(String(300), default="")
    dob: Mapped[date | None] = mapped_column(Date, nullable=True)
    blood_group: Mapped[str] = mapped_column(String(4), default="")
    profession: Mapped[str] = mapped_column(String(120), default="")
    emergency_name: Mapped[str] = mapped_column(String(120), default="")
    emergency_phone: Mapped[str] = mapped_column(String(32), default="")
    address: Mapped[str] = mapped_column(String(240), default="")
    languages: Mapped[list] = mapped_column(JSON, default=list)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
