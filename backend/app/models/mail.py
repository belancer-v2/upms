"""M20: FlatWise's own email promotion. Templates, audiences, campaigns, outbox, suppression."""
from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from ..db import Base
from .core import now


class MailTemplate(Base):
    __tablename__ = "mail_templates"
    id: Mapped[int] = mapped_column(primary_key=True)
    key: Mapped[str] = mapped_column(String(40), unique=True)
    name: Mapped[str] = mapped_column(String(120))
    name_bn: Mapped[str] = mapped_column(String(120), default="")
    kind: Mapped[str] = mapped_column(String(14), default="promotional")  # transactional | promotional
    subject_en: Mapped[str] = mapped_column(String(200), default="")
    subject_bn: Mapped[str] = mapped_column(String(200), default="")
    blocks_en: Mapped[list] = mapped_column(JSON, default=list)
    blocks_bn: Mapped[list] = mapped_column(JSON, default=list)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    updated_by: Mapped[int | None] = mapped_column(Integer, nullable=True)


class MailAudience(Base):
    __tablename__ = "mail_audiences"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    kind: Mapped[str] = mapped_column(String(12))  # stage | trial | active | churned | plan | city | band | csv
    params: Mapped[dict] = mapped_column(JSON, default=dict)
    created_by: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class MailProspect(Base):
    """A row from an uploaded CSV. Belongs to one csv audience."""
    __tablename__ = "mail_prospects"
    id: Mapped[int] = mapped_column(primary_key=True)
    audience_id: Mapped[int] = mapped_column(ForeignKey("mail_audiences.id", ondelete="CASCADE"), index=True)
    email: Mapped[str] = mapped_column(String(160), index=True)
    name: Mapped[str] = mapped_column(String(120), default="")
    company: Mapped[str] = mapped_column(String(160), default="")
    city: Mapped[str] = mapped_column(String(80), default="")
    lang: Mapped[str] = mapped_column(String(2), default="")
    consent_source: Mapped[str] = mapped_column(String(60), default="csv_upload")


class MailConsent(Base):
    """Where a lead's permission to email came from, and their preferred language."""
    __tablename__ = "mail_consents"
    lead_id: Mapped[int] = mapped_column(ForeignKey("leads.id"), primary_key=True)
    source: Mapped[str] = mapped_column(String(60), default="website_form")
    lang: Mapped[str] = mapped_column(String(2), default="")
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class MailCampaign(Base):
    __tablename__ = "mail_campaigns"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(160))
    audience_id: Mapped[int] = mapped_column(ForeignKey("mail_audiences.id"))
    template_id: Mapped[int] = mapped_column(ForeignKey("mail_templates.id"))
    lang_rule: Mapped[str] = mapped_column(String(10), default="recipient")  # recipient | bn | en
    status: Mapped[str] = mapped_column(String(10), default="draft", index=True)  # draft | scheduled | sending | sent | cancelled
    scheduled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    throttle_per_hour: Mapped[int] = mapped_column(Integer, default=0)  # 0 = use the global setting
    simulate: Mapped[bool] = mapped_column(Boolean, default=True)
    created_by: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class MailOutbox(Base):
    """One rendered email to one person. This is also the per-recipient result row."""
    __tablename__ = "mail_outbox"
    id: Mapped[int] = mapped_column(primary_key=True)
    campaign_id: Mapped[int | None] = mapped_column(ForeignKey("mail_campaigns.id"), nullable=True, index=True)
    template_key: Mapped[str] = mapped_column(String(40), default="")
    kind: Mapped[str] = mapped_column(String(14), default="promotional")
    to_email: Mapped[str] = mapped_column(String(160), index=True)
    to_name: Mapped[str] = mapped_column(String(120), default="")
    lang: Mapped[str] = mapped_column(String(2), default="bn")
    lead_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    org_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    subject: Mapped[str] = mapped_column(String(240), default="")
    html: Mapped[str] = mapped_column(Text, default="")
    text: Mapped[str] = mapped_column(Text, default="")
    vars: Mapped[dict] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String(12), default="queued", index=True)  # queued | sent | bounced | suppressed | skipped | failed
    reason: Mapped[str] = mapped_column(String(60), default="")
    is_test: Mapped[bool] = mapped_column(Boolean, default=False)
    provider: Mapped[str] = mapped_column(String(12), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    opened_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    clicked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    bounced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    unsubscribed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    clicks: Mapped[list] = mapped_column(JSON, default=list)  # URLs clicked


class MailSuppression(Base):
    """Global do-not-email list. unsubscribe blocks promotional mail; bounce, complaint and manual block everything."""
    __tablename__ = "mail_suppressions"
    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(160), unique=True)
    reason: Mapped[str] = mapped_column(String(12), default="unsubscribe")  # unsubscribe | bounce | complaint | manual
    source: Mapped[str] = mapped_column(String(80), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    by_user_id: Mapped[int | None] = mapped_column(Integer, nullable=True)


class MailSetting(Base):
    __tablename__ = "mail_settings"
    key: Mapped[str] = mapped_column(String(40), primary_key=True)
    value: Mapped[str] = mapped_column(String(200), default="")
