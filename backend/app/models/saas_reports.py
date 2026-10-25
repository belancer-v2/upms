"""M21: SaaS reports and FlatWise tax invoices. Own tables only; the M2 tables are not changed.

SubscriptionEvent  one row per plan change / activate / suspend / cancel / trial start (MRR history)
LeadStageEvent     one row per lead status change (days per stage)
SaasSettings       FlatWise company details printed on every tax invoice (one row, id 1)
SaasNumberSeq      gap-free counters per series (INV, CN) and fiscal year
SaasInvoiceDoc     tax-invoice facts for a SaasInvoice (number, VAT split, items, language); append-only
SaasCreditNote     CN-2026-0001, references an invoice; created when an invoice is voided or refunded
"""
from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from ..db import Base
from .core import now


class SubscriptionEvent(Base):
    __tablename__ = "subscription_events"
    id: Mapped[int] = mapped_column(primary_key=True)
    org_id: Mapped[int] = mapped_column(ForeignKey("organizations.id"), index=True)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, index=True)
    kind: Mapped[str] = mapped_column(String(14))  # trial_start | activate | plan_change | suspend | cancel
    plan_key: Mapped[str] = mapped_column(String(20), default="")
    band: Mapped[str] = mapped_column(String(3), default="")
    cycle: Mapped[str] = mapped_column(String(8), default="monthly")
    status: Mapped[str] = mapped_column(String(12), default="")   # subscription status after the event
    mrr: Mapped[int] = mapped_column(BigInteger, default=0)           # paisa per month after the event, 0 when not paying
    by_user_id: Mapped[int | None] = mapped_column(Integer, nullable=True)


class LeadStageEvent(Base):
    __tablename__ = "lead_stage_events"
    id: Mapped[int] = mapped_column(primary_key=True)
    lead_id: Mapped[int] = mapped_column(ForeignKey("leads.id"), index=True)
    status: Mapped[str] = mapped_column(String(12))
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class SaasSettings(Base):
    __tablename__ = "saas_settings"
    id: Mapped[int] = mapped_column(primary_key=True)
    legal_name: Mapped[str] = mapped_column(String(160), default="FlatWise Technologies Ltd.")
    legal_name_bn: Mapped[str] = mapped_column(String(160), default="ফ্ল্যাটওয়াইজ টেকনোলজিস লিমিটেড")
    address: Mapped[str] = mapped_column(String(300), default="House 12, Road 5, Dhanmondi, Dhaka 1205")
    address_bn: Mapped[str] = mapped_column(String(300), default="বাড়ি ১২, রোড ৫, ধানমন্ডি, ঢাকা ১২০৫")
    phone: Mapped[str] = mapped_column(String(40), default="")
    email: Mapped[str] = mapped_column(String(120), default="")
    bin_no: Mapped[str] = mapped_column(String(40), default="")     # VAT registration (BIN)
    tin: Mapped[str] = mapped_column(String(40), default="")
    bank_details: Mapped[str] = mapped_column(Text, default="")
    bkash_merchant: Mapped[str] = mapped_column(String(40), default="")
    nagad_merchant: Mapped[str] = mapped_column(String(40), default="")
    logo_url: Mapped[str] = mapped_column(Text, default="")
    footer_text: Mapped[str] = mapped_column(Text, default="")
    footer_text_bn: Mapped[str] = mapped_column(Text, default="")
    invoice_prefix: Mapped[str] = mapped_column(String(8), default="INV")
    credit_prefix: Mapped[str] = mapped_column(String(8), default="CN")
    default_vat_pct: Mapped[float] = mapped_column(default=15.0)
    fy_start_month: Mapped[int] = mapped_column(Integer, default=1)  # 1 = calendar year, 7 = July to June
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class SaasNumberSeq(Base):
    __tablename__ = "saas_number_seq"
    series: Mapped[str] = mapped_column(String(8), primary_key=True)
    fy: Mapped[int] = mapped_column(Integer, primary_key=True)
    last: Mapped[int] = mapped_column(Integer, default=0)


class SaasInvoiceDoc(Base):
    __tablename__ = "saas_invoice_docs"
    id: Mapped[int] = mapped_column(primary_key=True)
    invoice_id: Mapped[int] = mapped_column(ForeignKey("saas_invoices.id"), unique=True)
    doc_no: Mapped[str] = mapped_column(String(32), unique=True)
    fy: Mapped[int] = mapped_column(Integer)
    seq: Mapped[int] = mapped_column(Integer)
    issued_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    vat_pct: Mapped[float] = mapped_column(default=15.0)
    net: Mapped[int] = mapped_column(BigInteger)            # paisa, before VAT
    vat: Mapped[int] = mapped_column(BigInteger)            # paisa
    total: Mapped[int] = mapped_column(BigInteger)          # paisa, equals SaasInvoice.amount
    items: Mapped[list] = mapped_column(JSON, default=list)  # [{desc, desc_bn, qty, net}]
    lang: Mapped[str] = mapped_column(String(2), default="en")
    quote_ref: Mapped[str] = mapped_column(String(40), default="")
    emailed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    issued_by: Mapped[int | None] = mapped_column(Integer, nullable=True)


class SaasCreditNote(Base):
    __tablename__ = "saas_credit_notes"
    id: Mapped[int] = mapped_column(primary_key=True)
    doc_no: Mapped[str] = mapped_column(String(32), unique=True)
    fy: Mapped[int] = mapped_column(Integer)
    seq: Mapped[int] = mapped_column(Integer)
    invoice_id: Mapped[int] = mapped_column(ForeignKey("saas_invoices.id"), index=True)
    org_id: Mapped[int] = mapped_column(ForeignKey("organizations.id"), index=True)
    kind: Mapped[str] = mapped_column(String(8), default="void")  # void | refund
    amount: Mapped[int] = mapped_column(BigInteger)                  # paisa, VAT included
    vat: Mapped[int] = mapped_column(BigInteger, default=0)
    reason: Mapped[str] = mapped_column(String(200), default="")
    issued_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    issued_by: Mapped[int | None] = mapped_column(Integer, nullable=True)
    __table_args__ = (UniqueConstraint("invoice_id", "kind", "amount", "issued_at"),)
