"""P5: new-customer setup wizard progress, and account-deletion requests."""
from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from ..db import Base
from .core import now


class SetupProgress(Base):
    """One row per building that is (or was) in the setup wizard. Saved on the server so a person can stop and continue on another phone."""
    __tablename__ = "setup_progress"
    id: Mapped[int] = mapped_column(primary_key=True)
    property_id: Mapped[int] = mapped_column(ForeignKey("properties.id", ondelete="CASCADE"), unique=True, index=True)
    steps: Mapped[dict] = mapped_column(JSON, default=dict)        # {"building": "done" | "skipped"}; a missing step is still to do
    data: Mapped[dict] = mapped_column(JSON, default=dict)         # small answers: {"due_day": 10, "reminders": {"enabled": true, "steps": [...]}}
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    dismissed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)   # the dashboard card was hidden
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    updated_by: Mapped[int | None] = mapped_column(Integer, nullable=True)


class DeletionRequest(Base):
    """A person asking FlatWise to erase their personal details. Processing anonymises the account; ledger rows stay balanced."""
    __tablename__ = "deletion_requests"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, index=True)       # no FK on purpose: the row outlives the user's details
    status: Mapped[str] = mapped_column(String(10), default="pending", index=True)   # pending | completed | rejected | cancelled
    reason: Mapped[str] = mapped_column(String(300), default="")
    requested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    processed_by: Mapped[int | None] = mapped_column(Integer, nullable=True)
    note: Mapped[str] = mapped_column(Text, default="")            # why it was rejected, or what was done
