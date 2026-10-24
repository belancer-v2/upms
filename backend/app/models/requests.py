"""M10: service requests (complaints) with SLA, the committee with tenure, meetings, and committee votes."""
from datetime import date, datetime

from sqlalchemy import JSON, Date, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from ..db import Base
from .core import now


class ServiceRequest(Base):
    __tablename__ = "service_requests"
    id: Mapped[int] = mapped_column(primary_key=True)
    property_id: Mapped[int] = mapped_column(ForeignKey("properties.id"), index=True)
    unit_id: Mapped[int | None] = mapped_column(ForeignKey("units.id"), nullable=True, index=True)
    raised_by: Mapped[int] = mapped_column(Integer, index=True)
    category: Mapped[str] = mapped_column(String(12))                       # lift | water | electricity | security | cleaning | noise | other
    title: Mapped[str] = mapped_column(String(160))
    text: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(12), default="open", index=True)   # open | assigned | in_progress | resolved | closed
    assignee_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, index=True)
    due_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))       # created (or reopened) time plus the category SLA
    sla_hours: Mapped[int] = mapped_column(Integer, default=72)
    assigned_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    reopened: Mapped[int] = mapped_column(Integer, default=0)               # a resident may reopen once
    rating: Mapped[int | None] = mapped_column(Integer, nullable=True)      # 1 to 5, given once
    rating_note: Mapped[str] = mapped_column(String(300), default="")


class RequestComment(Base):
    __tablename__ = "request_comments"
    id: Mapped[int] = mapped_column(primary_key=True)
    request_id: Mapped[int] = mapped_column(ForeignKey("service_requests.id"), index=True)
    user_id: Mapped[int] = mapped_column(Integer)
    text: Mapped[str] = mapped_column(Text)
    kind: Mapped[str] = mapped_column(String(8), default="comment")         # comment | event
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class SlaRule(Base):
    """Admin-edited hours per category. A category with no row uses the default."""
    __tablename__ = "sla_rules"
    __table_args__ = (UniqueConstraint("property_id", "category", name="one_sla_per_category"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    property_id: Mapped[int] = mapped_column(ForeignKey("properties.id"), index=True)
    category: Mapped[str] = mapped_column(String(12))
    hours: Mapped[int] = mapped_column(Integer)


class CommitteeMember(Base):
    __tablename__ = "committee_members"
    id: Mapped[int] = mapped_column(primary_key=True)
    property_id: Mapped[int] = mapped_column(ForeignKey("properties.id"), index=True)
    user_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    name: Mapped[str] = mapped_column(String(120))
    name_bn: Mapped[str] = mapped_column(String(120), default="")
    role: Mapped[str] = mapped_column(String(16))                           # president | secretary | treasurer | member
    start_date: Mapped[date] = mapped_column(Date)
    end_date: Mapped[date] = mapped_column(Date)
    note: Mapped[str] = mapped_column(String(200), default="")


class Meeting(Base):
    __tablename__ = "meetings"
    id: Mapped[int] = mapped_column(primary_key=True)
    property_id: Mapped[int] = mapped_column(ForeignKey("properties.id"), index=True)
    title: Mapped[str] = mapped_column(String(160))
    held_on: Mapped[date] = mapped_column(Date, index=True)
    place: Mapped[str] = mapped_column(String(160), default="")
    agenda: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(10), default="scheduled")    # scheduled | held | cancelled
    attendance: Mapped[list] = mapped_column(JSON, default=list)            # [{member_id, name, present}]
    minutes: Mapped[str] = mapped_column(Text, default="")
    decisions: Mapped[list] = mapped_column(JSON, default=list)             # [str]
    created_by: Mapped[int] = mapped_column(Integer)


class Proposal(Base):
    __tablename__ = "proposals"
    id: Mapped[int] = mapped_column(primary_key=True)
    property_id: Mapped[int] = mapped_column(ForeignKey("properties.id"), index=True)
    title: Mapped[str] = mapped_column(String(160))
    text: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(8), default="open")          # open | closed
    result: Mapped[str] = mapped_column(String(10), default="")             # approved | rejected | tied (locked at close)
    tally: Mapped[dict] = mapped_column(JSON, default=dict)                 # locked at close: {approve, reject, eligible}
    created_by: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ProposalVote(Base):
    __tablename__ = "proposal_votes"
    __table_args__ = (UniqueConstraint("proposal_id", "user_id", name="one_vote_per_person"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    proposal_id: Mapped[int] = mapped_column(ForeignKey("proposals.id"), index=True)
    user_id: Mapped[int] = mapped_column(Integer)
    choice: Mapped[str] = mapped_column(String(8))                          # approve | reject
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
