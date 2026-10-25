"""M18: outsourced security and cleaning agencies, who they supply, posts, shifts, the duty roster, attendance and monthly bill checks. Money is integer paisa."""
from datetime import date, datetime

from sqlalchemy import BigInteger, Boolean, Date, DateTime, ForeignKey, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from ..db import Base
from .core import now


class Agency(Base):
    __tablename__ = "agencies"
    id: Mapped[int] = mapped_column(primary_key=True)
    property_id: Mapped[int] = mapped_column(ForeignKey("properties.id"), index=True)
    name: Mapped[str] = mapped_column(String(120))
    name_bn: Mapped[str] = mapped_column(String(120), default="")
    kind: Mapped[str] = mapped_column(String(10), default="security")        # security | cleaning | both
    trade_licence: Mapped[str] = mapped_column(String(60), default="")
    reg_no: Mapped[str] = mapped_column(String(80), default="")              # registration / TIN / BIN, free text
    psc_licence: Mapped[str] = mapped_column(String(60), default="")         # private security company licence
    address: Mapped[str] = mapped_column(String(200), default="")
    contact_name: Mapped[str] = mapped_column(String(100), default="")
    contact_phone: Mapped[str] = mapped_column(String(32), default="")
    emergency_phone: Mapped[str] = mapped_column(String(32), default="")     # 24h number
    contract_start: Mapped[date | None] = mapped_column(Date, nullable=True)
    contract_end: Mapped[date | None] = mapped_column(Date, nullable=True)
    fee_mode: Mapped[str] = mapped_column(String(10), default="flat")        # flat (monthly) | per_post (per post per month)
    monthly_fee: Mapped[int] = mapped_column(BigInteger, default=0)             # paisa
    notice_days: Mapped[int] = mapped_column(Integer, default=30)
    sla_notes: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(8), default="active")         # active | ended
    vendor_id: Mapped[int | None] = mapped_column(Integer, nullable=True)    # the Vendor row its invoices are booked under
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class AgencyDoc(Base):
    __tablename__ = "agency_docs"
    id: Mapped[int] = mapped_column(primary_key=True)
    agency_id: Mapped[int] = mapped_column(ForeignKey("agencies.id"), index=True)
    kind: Mapped[str] = mapped_column(String(24))      # licence | contract | insurance | police_verification
    filename: Mapped[str] = mapped_column(String(160))
    stored: Mapped[str] = mapped_column(String(60))
    content_type: Mapped[str] = mapped_column(String(40))
    size: Mapped[int] = mapped_column(Integer)
    uploaded_by: Mapped[int] = mapped_column(Integer)
    uploaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class StaffPosting(Base):
    """Links a Staff row to the agency that employs them. No row means a direct (building) employee. Agency staff are never on the building's salary sheets."""
    __tablename__ = "staff_postings"
    id: Mapped[int] = mapped_column(primary_key=True)
    staff_id: Mapped[int] = mapped_column(ForeignKey("staff.id"), unique=True)
    agency_id: Mapped[int] = mapped_column(ForeignKey("agencies.id"), index=True)
    emp_no: Mapped[str] = mapped_column(String(40), default="")
    deployed_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    substitute: Mapped[bool] = mapped_column(Boolean, default=False)


class Post(Base):
    __tablename__ = "duty_posts"
    id: Mapped[int] = mapped_column(primary_key=True)
    property_id: Mapped[int] = mapped_column(ForeignKey("properties.id"), index=True)
    name: Mapped[str] = mapped_column(String(80))
    name_bn: Mapped[str] = mapped_column(String(80), default="")
    kind: Mapped[str] = mapped_column(String(10), default="security")        # security | cleaning
    headcount: Mapped[int] = mapped_column(Integer, default=1)               # people required on each shift
    shift_ids: Mapped[list] = mapped_column(JSON, default=list)              # shifts this post is staffed on; empty means every shift
    agency_id: Mapped[int | None] = mapped_column(Integer, nullable=True)    # who supplies it; none means building staff
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class ShiftDef(Base):
    __tablename__ = "duty_shifts"
    id: Mapped[int] = mapped_column(primary_key=True)
    property_id: Mapped[int] = mapped_column(ForeignKey("properties.id"), index=True)
    name: Mapped[str] = mapped_column(String(40))
    name_bn: Mapped[str] = mapped_column(String(40), default="")
    start: Mapped[str] = mapped_column(String(5))      # HH:MM
    end: Mapped[str] = mapped_column(String(5))
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class RosterSlot(Base):
    __tablename__ = "roster_slots"
    __table_args__ = (UniqueConstraint("post_id", "shift_id", "day", "staff_id", name="one_person_per_slot"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    property_id: Mapped[int] = mapped_column(ForeignKey("properties.id"), index=True)
    day: Mapped[date] = mapped_column(Date, index=True)
    post_id: Mapped[int] = mapped_column(ForeignKey("duty_posts.id"), index=True)
    shift_id: Mapped[int] = mapped_column(ForeignKey("duty_shifts.id"))
    staff_id: Mapped[int] = mapped_column(ForeignKey("staff.id"), index=True)
    status: Mapped[str] = mapped_column(String(8), default="planned")       # planned | present | late | absent | leave
    substitute: Mapped[bool] = mapped_column(Boolean, default=False)
    note: Mapped[str] = mapped_column(String(160), default="")
    marked_by: Mapped[int | None] = mapped_column(Integer, nullable=True)
    marked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Replacement(Base):
    """A request to the agency to send someone for an empty slot."""
    __tablename__ = "roster_replacements"
    id: Mapped[int] = mapped_column(primary_key=True)
    property_id: Mapped[int] = mapped_column(ForeignKey("properties.id"), index=True)
    slot_id: Mapped[int] = mapped_column(Integer, index=True)
    agency_id: Mapped[int] = mapped_column(ForeignKey("agencies.id"))
    day: Mapped[date] = mapped_column(Date)
    post_id: Mapped[int] = mapped_column(Integer)
    shift_id: Mapped[int] = mapped_column(Integer)
    absent_staff_id: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(10), default="requested")    # requested | fulfilled
    sub_staff_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    sms_status: Mapped[str] = mapped_column(String(8), default="")
    note: Mapped[str] = mapped_column(String(160), default="")
    requested_by: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class AgencySetting(Base):
    __tablename__ = "agency_settings"
    id: Mapped[int] = mapped_column(primary_key=True)
    property_id: Mapped[int] = mapped_column(ForeignKey("properties.id"), unique=True)
    shortfall_rate: Mapped[int] = mapped_column(BigInteger, default=40000)     # paisa deducted for each missing person-shift


class AgencyBill(Base):
    __tablename__ = "agency_bills"
    __table_args__ = (UniqueConstraint("agency_id", "period", name="one_bill_per_month"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    property_id: Mapped[int] = mapped_column(ForeignKey("properties.id"), index=True)
    agency_id: Mapped[int] = mapped_column(ForeignKey("agencies.id"), index=True)
    period: Mapped[str] = mapped_column(String(7))
    number: Mapped[str] = mapped_column(String(60))
    amount: Mapped[int] = mapped_column(BigInteger)           # invoiced, paisa
    expected: Mapped[int] = mapped_column(Integer)         # computed when recorded
    shortfall_units: Mapped[int] = mapped_column(Integer, default=0)
    deduction: Mapped[int] = mapped_column(BigInteger, default=0)
    note: Mapped[str] = mapped_column(String(200), default="")
    expense_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_by: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


def posting_map(db, property_id: int) -> dict[int, dict]:
    """staff id -> employer info, for staff who work for an agency. Direct staff are absent from the map."""
    from sqlalchemy import select
    ags = {a.id: a for a in db.scalars(select(Agency).where(Agency.property_id == property_id))}
    out = {}
    for l in db.scalars(select(StaffPosting).where(StaffPosting.agency_id.in_(list(ags) or [-1]))):
        a = ags[l.agency_id]
        out[l.staff_id] = {"agency_id": a.id, "name": a.name, "name_bn": a.name_bn, "emp_no": l.emp_no, "deployed_on": l.deployed_on.isoformat() if l.deployed_on else None, "substitute": l.substitute}
    return out
