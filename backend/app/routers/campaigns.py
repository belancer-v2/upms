"""M20: email promotion console (/api/saas/mail) and the public unsubscribe, open and click links (/api/public)."""
import re
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import RedirectResponse, Response
from pydantic import BaseModel, Field
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from ..audit import audit
from ..services.ratelimit import limit as rate_limit
from ..db import get_db
from ..deps import require_saas
from ..models.core import User, now
from ..models.mail import (MailAudience, MailCampaign, MailConsent, MailOutbox, MailProspect, MailSuppression, MailTemplate)
from ..models.saas import BANDS, Lead, Plan
from ..services import mailer as M

EDIT = ("SUPER_ADMIN", "SAAS_ADMIN", "SAAS_SALES")   # create, edit and send
READ = EDIT + ("SAAS_FINANCE",)                       # finance reads campaigns and stats only
ADMINISH = ("SUPER_ADMIN", "SAAS_ADMIN")
router = APIRouter(prefix="/api/saas/mail", tags=["mail"], dependencies=[Depends(require_saas(*READ))])
public_router = APIRouter(prefix="/api/public", tags=["public"])
editor = require_saas(*EDIT)

SAMPLE = {"en": {"name": "Rahim Uddin", "building": "Sunrise Tower", "plan": "Standard", "trial_days_left": "7", "link": f"{M.APP_URL}/pricing"},
          "bn": {"name": "রহিম উদ্দিন", "building": "সানরাইজ টাওয়ার", "plan": "স্ট্যান্ডার্ড", "trial_days_left": "৭", "link": f"{M.APP_URL}/pricing"}}


def _aware(dt):
    return dt.replace(tzinfo=timezone.utc) if dt and dt.tzinfo is None else dt


def _iso(dt):
    return _aware(dt).isoformat() if dt else None


def _page(q, page: int, size: int):
    return q.limit(size).offset((max(page, 1) - 1) * size)


def _count(db: Session, stmt) -> int:
    return db.scalar(select(func.count()).select_from(stmt.order_by(None).subquery())) or 0


# ------------------------------------------------------------------ settings
class SettingsIn(BaseModel):
    weekly_cap: int | None = Field(default=None, ge=1, le=14)
    throttle_per_hour: int | None = Field(default=None, ge=1, le=20000)
    sim_seed: int | None = Field(default=None, ge=0, le=2**31)


@router.get("/settings")
def get_settings(db: Session = Depends(get_db)):
    return {"weekly_cap": M.get_int(db, "weekly_cap"), "throttle_per_hour": M.get_int(db, "throttle_per_hour"), "sim_seed": M.get_int(db, "sim_seed"),
            "provider": M.get_provider().name, "company": M.COMPANY, "address": M.ADDRESS, "csv_cap": M.CSV_CAP, "stages": M.STAGES, "bands": [b[0] for b in BANDS]}


@router.put("/settings")
def put_settings(body: SettingsIn, user: User = Depends(require_saas(*ADMINISH)), db: Session = Depends(get_db)):
    changed = body.model_dump(exclude_none=True)
    for k, v in changed.items():
        M.set_setting(db, k, v)
    audit(db, user_id=user.id, action="saas.mail.settings", entity="mail_settings", meta=changed)
    db.commit()
    return get_settings(db)


# ------------------------------------------------------------------ templates
def _tpl(t: MailTemplate, full: bool = False) -> dict:
    d = {"id": t.id, "key": t.key, "name": t.name, "name_bn": t.name_bn, "kind": t.kind, "subject_en": t.subject_en, "subject_bn": t.subject_bn, "updated_at": _iso(t.updated_at)}
    if full:
        d.update(blocks_en=t.blocks_en, blocks_bn=t.blocks_bn)
    return d


class TemplateIn(BaseModel):
    key: str = Field(pattern=r"^[a-z0-9_]{2,40}$")
    name: str = Field(min_length=2, max_length=120)
    name_bn: str = Field(default="", max_length=120)
    kind: str = Field(pattern="^(transactional|promotional)$")
    subject_en: str = Field(min_length=1, max_length=200)
    subject_bn: str = Field(min_length=1, max_length=200)
    blocks_en: list[dict]
    blocks_bn: list[dict]


def _apply_tpl(t: MailTemplate, body: TemplateIn, user: User) -> None:
    try:
        en, bn = M.clean_blocks(body.blocks_en), M.clean_blocks(body.blocks_bn)
    except ValueError as e:
        raise HTTPException(422, str(e))
    if not en or not bn:
        raise HTTPException(422, "Both the English and the Bangla version need at least one block")
    t.name, t.name_bn, t.kind = body.name, body.name_bn, body.kind
    t.subject_en, t.subject_bn, t.blocks_en, t.blocks_bn = body.subject_en, body.subject_bn, en, bn
    t.updated_at, t.updated_by = now(), user.id


@router.get("/templates")
def templates(user: User = Depends(editor), db: Session = Depends(get_db)):
    return [_tpl(t) for t in db.scalars(select(MailTemplate).order_by(MailTemplate.kind.desc(), MailTemplate.id))]


@router.get("/templates/{tid}")
def template(tid: int, user: User = Depends(editor), db: Session = Depends(get_db)):
    t = db.get(MailTemplate, tid)
    if not t:
        raise HTTPException(404, "Not found")
    return _tpl(t, True)


@router.post("/templates", status_code=201)
def create_template(body: TemplateIn, user: User = Depends(editor), db: Session = Depends(get_db)):
    if db.scalar(select(MailTemplate.id).where(MailTemplate.key == body.key)):
        raise HTTPException(409, "A template with this key already exists")
    t = MailTemplate(key=body.key)
    _apply_tpl(t, body, user)
    db.add(t)
    db.flush()
    audit(db, user_id=user.id, action="saas.mail.template.create", entity="mail_template", entity_id=t.id, meta={"key": t.key})
    db.commit()
    return _tpl(t, True)


@router.put("/templates/{tid}")
def update_template(tid: int, body: TemplateIn, user: User = Depends(editor), db: Session = Depends(get_db)):
    t = db.get(MailTemplate, tid)
    if not t:
        raise HTTPException(404, "Not found")
    if body.key != t.key:
        raise HTTPException(422, "The key cannot change")
    _apply_tpl(t, body, user)
    audit(db, user_id=user.id, action="saas.mail.template.edit", entity="mail_template", entity_id=t.id, meta={"key": t.key})
    db.commit()
    return _tpl(t, True)


@router.delete("/templates/{tid}")
def delete_template(tid: int, user: User = Depends(require_saas(*ADMINISH)), db: Session = Depends(get_db)):
    t = db.get(MailTemplate, tid)
    if not t:
        raise HTTPException(404, "Not found")
    if db.scalar(select(MailCampaign.id).where(MailCampaign.template_id == tid)):
        raise HTTPException(409, "A campaign uses this template")
    audit(db, user_id=user.id, action="saas.mail.template.delete", entity="mail_template", entity_id=tid, meta={"key": t.key})
    db.delete(t)
    db.commit()
    return {"ok": True}


class PreviewIn(BaseModel):
    lang: str = "en"
    theme: str = "light"
    subject: str | None = None
    blocks: list[dict] | None = None
    kind: str | None = None


@router.post("/templates/{tid}/preview")
def preview(tid: int, body: PreviewIn, user: User = Depends(editor), db: Session = Depends(get_db)):
    """Renders the stored template, or the unsaved blocks the editor sends, with sample data. Nothing is sent."""
    t = db.get(MailTemplate, tid) if tid else None
    if tid and not t:
        raise HTTPException(404, "Not found")
    lang = "en" if body.lang == "en" else "bn"
    try:
        blocks = M.clean_blocks(body.blocks) if body.blocks is not None else None
    except ValueError as e:
        raise HTTPException(422, str(e))
    if t:
        subject, stored, _ = M.template_side(t, lang)
        blocks = stored if blocks is None else blocks
        subject = body.subject if body.subject is not None else subject
        kind = body.kind or t.kind
    else:
        subject, blocks, kind = body.subject or "", blocks or [], body.kind or "promotional"
    r = M.render_email(subject, blocks, SAMPLE[lang], lang, kind, "preview@example.com", 0, theme="dark" if body.theme == "dark" else "light")
    return {"subject": r.subject, "html": r.html, "text": r.text, "lang": lang}


@router.post("/templates/{tid}/test")
def test_template(tid: int, body: PreviewIn, user: User = Depends(editor), db: Session = Depends(get_db)):
    t = db.get(MailTemplate, tid)
    if not t:
        raise HTTPException(404, "Not found")
    lang = "en" if body.lang == "en" else "bn"
    row = M.send_template(db, t.key, user.email, user.name, lang, SAMPLE[lang], force=True)
    row.is_test, row.subject = True, "[TEST] " + row.subject
    audit(db, user_id=user.id, action="saas.mail.test", entity="mail_template", entity_id=t.id, meta={"to": user.email})
    db.commit()
    return {"ok": True, "outbox_id": row.id, "status": row.status}


# ------------------------------------------------------------------ audiences
def _aud(db: Session, a: MailAudience) -> dict:
    return {"id": a.id, "name": a.name, "kind": a.kind, "params": a.params, "count": len(M.resolve_audience(db, a)), "created_at": _iso(a.created_at)}


class AudienceIn(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    kind: str
    params: dict = {}


@router.get("/audiences")
def audiences(user: User = Depends(editor), db: Session = Depends(get_db)):
    return [_aud(db, a) for a in db.scalars(select(MailAudience).order_by(MailAudience.id.desc()))]


@router.post("/audiences", status_code=201)
def create_audience(body: AudienceIn, user: User = Depends(editor), db: Session = Depends(get_db)):
    k, p = body.kind, body.params or {}
    if k not in M.AUDIENCE_KINDS or k == "csv":
        raise HTTPException(422, "Unknown audience type")
    if k == "stage":
        stages = [s for s in p.get("stages", []) if s in M.STAGES]
        if not stages:
            raise HTTPException(422, "Choose at least one pipeline stage")
        p = {"stages": stages}
    elif k == "plan":
        if not db.get(Plan, p.get("plan", "")):
            raise HTTPException(422, "Unknown plan")
        p = {"plan": p["plan"]}
    elif k == "city":
        if not str(p.get("city", "")).strip():
            raise HTTPException(422, "Enter a city")
        p = {"city": str(p["city"]).strip()[:80]}
    elif k == "band":
        if p.get("band") not in [b[0] for b in BANDS]:
            raise HTTPException(422, "Unknown size band")
        p = {"band": p["band"]}
    else:
        p = {}
    a = MailAudience(name=body.name, kind=k, params=p, created_by=user.id)
    db.add(a)
    db.flush()
    audit(db, user_id=user.id, action="saas.mail.audience.create", entity="mail_audience", entity_id=a.id, meta={"kind": k})
    db.commit()
    return _aud(db, a)


class CsvIn(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    csv: str = Field(min_length=1, max_length=2_000_000)
    consent_source: str = Field(default="csv_upload", min_length=2, max_length=60)


@router.post("/audiences/csv", status_code=201)
def upload_csv(body: CsvIn, user: User = Depends(editor), db: Session = Depends(get_db)):
    try:
        res = M.parse_prospects_csv(body.csv)
    except ValueError as e:
        raise HTTPException(422, str(e))
    if not res["rows"]:
        raise HTTPException(422, "No valid email addresses found")
    a = MailAudience(name=body.name, kind="csv", params={"consent_source": body.consent_source}, created_by=user.id)
    db.add(a)
    db.flush()
    db.add_all([MailProspect(audience_id=a.id, consent_source=body.consent_source, **r) for r in res["rows"]])
    audit(db, user_id=user.id, action="saas.mail.audience.csv", entity="mail_audience", entity_id=a.id,
          meta={"accepted": len(res["rows"]), "invalid": len(res["invalid"]), "duplicates": res["duplicates"], "source": body.consent_source})
    db.commit()
    return {"audience": _aud(db, a), "accepted": len(res["rows"]), "duplicates": res["duplicates"], "invalid": res["invalid"][:50], "invalid_count": len(res["invalid"]), "total": res["total"]}


@router.delete("/audiences/{aid}")
def delete_audience(aid: int, user: User = Depends(editor), db: Session = Depends(get_db)):
    a = db.get(MailAudience, aid)
    if not a:
        raise HTTPException(404, "Not found")
    if db.scalar(select(MailCampaign.id).where(MailCampaign.audience_id == aid)):
        raise HTTPException(409, "A campaign uses this audience")
    for r in db.scalars(select(MailProspect).where(MailProspect.audience_id == aid)):
        db.delete(r)
    audit(db, user_id=user.id, action="saas.mail.audience.delete", entity="mail_audience", entity_id=aid)
    db.delete(a)
    db.commit()
    return {"ok": True}


@router.get("/audiences/{aid}/recipients")
def audience_recipients(aid: int, q: str = "", page: int = 1, size: int = 20, user: User = Depends(editor), db: Session = Depends(get_db)):
    a = db.get(MailAudience, aid)
    if not a:
        raise HTTPException(404, "Not found")
    size = min(max(size, 1), 100)
    sup = {s.email: s.reason for s in db.scalars(select(MailSuppression))}
    rows = [r for r in M.resolve_audience(db, a) if not q or q.lower() in (r["email"] + r["name"] + r["building"]).lower()]
    page_rows = rows[(max(page, 1) - 1) * size: max(page, 1) * size]
    return {"total": len(rows), "page": page, "size": size,
            "items": [{"email": r["email"], "name": r["name"], "building": r["building"], "city": r["city"], "lang": r["lang"], "source": r["source"],
                       "suppressed": sup.get(r["email"], "")} for r in page_rows]}


# ------------------------------------------------------------------ campaigns
def _camp(db: Session, c: MailCampaign, stats: bool = True) -> dict:
    a, t = db.get(MailAudience, c.audience_id), db.get(MailTemplate, c.template_id)
    d = {"id": c.id, "name": c.name, "status": c.status, "audience_id": c.audience_id, "audience": a.name if a else "", "template_id": c.template_id,
         "template": t.name if t else "", "template_bn": t.name_bn if t else "", "kind": t.kind if t else "", "lang_rule": c.lang_rule,
         "scheduled_at": _iso(c.scheduled_at), "throttle_per_hour": c.throttle_per_hour, "simulate": c.simulate, "created_at": _iso(c.created_at),
         "started_at": _iso(c.started_at), "finished_at": _iso(c.finished_at)}
    if stats:
        d["stats"] = M.campaign_stats(db, c)
    return d


class CampaignIn(BaseModel):
    name: str = Field(min_length=2, max_length=160)
    audience_id: int
    template_id: int
    lang_rule: str = Field(default="recipient", pattern="^(recipient|bn|en)$")
    scheduled_at: datetime | None = None
    throttle_per_hour: int = Field(default=0, ge=0, le=20000)
    simulate: bool = True


@router.get("/campaigns")
def campaigns(db: Session = Depends(get_db)):
    return [_camp(db, c) for c in db.scalars(select(MailCampaign).order_by(MailCampaign.id.desc()))]


@router.post("/campaigns", status_code=201)
def create_campaign(body: CampaignIn, user: User = Depends(editor), db: Session = Depends(get_db)):
    if not db.get(MailAudience, body.audience_id) or not db.get(MailTemplate, body.template_id):
        raise HTTPException(422, "Choose an audience and a template")
    c = MailCampaign(name=body.name, audience_id=body.audience_id, template_id=body.template_id, lang_rule=body.lang_rule, throttle_per_hour=body.throttle_per_hour,
                     simulate=body.simulate, created_by=user.id, scheduled_at=_aware(body.scheduled_at) if body.scheduled_at else None,
                     status="scheduled" if body.scheduled_at else "draft")
    db.add(c)
    db.flush()
    audit(db, user_id=user.id, action="saas.mail.campaign.create", entity="mail_campaign", entity_id=c.id, meta={"scheduled": bool(c.scheduled_at)})
    db.commit()
    return _camp(db, c)


def _get_campaign(db: Session, cid: int) -> MailCampaign:
    c = db.get(MailCampaign, cid)
    if not c:
        raise HTTPException(404, "Not found")
    return c


@router.get("/campaigns/{cid}")
def campaign(cid: int, db: Session = Depends(get_db)):
    return _camp(db, _get_campaign(db, cid))


@router.post("/campaigns/{cid}/test")
def campaign_test(cid: int, user: User = Depends(editor), db: Session = Depends(get_db)):
    c = _get_campaign(db, cid)
    row = M.send_test(db, c, user.email, user.name, user.lang)
    audit(db, user_id=user.id, action="saas.mail.campaign.test", entity="mail_campaign", entity_id=c.id, meta={"to": user.email})
    db.commit()
    return {"ok": True, "outbox_id": row.id, "to": row.to_email, "status": row.status}


@router.post("/campaigns/{cid}/send")
def campaign_send(cid: int, user: User = Depends(editor), db: Session = Depends(get_db)):
    c = _get_campaign(db, cid)
    if c.status not in ("draft", "scheduled"):
        raise HTTPException(409, f"This campaign is {c.status}")
    n = M.queue_campaign(db, c)
    res = M.dispatch(db, c)
    audit(db, user_id=user.id, action="saas.mail.campaign.send", entity="mail_campaign", entity_id=c.id, meta={"recipients": n, **res})
    db.commit()
    return {**_camp(db, c), "run": res}


@router.post("/campaigns/{cid}/cancel")
def campaign_cancel(cid: int, user: User = Depends(editor), db: Session = Depends(get_db)):
    c = _get_campaign(db, cid)
    if c.status not in ("draft", "scheduled", "sending"):
        raise HTTPException(409, f"This campaign is {c.status}")
    left = db.scalars(select(MailOutbox).where(MailOutbox.campaign_id == c.id, MailOutbox.status == "queued", MailOutbox.is_test == False)).all()  # noqa: E712
    for r in left:
        r.status, r.reason = "skipped", "cancelled"
    c.status, c.finished_at = "cancelled", now()
    audit(db, user_id=user.id, action="saas.mail.campaign.cancel", entity="mail_campaign", entity_id=c.id, meta={"cancelled_rows": len(left)})
    db.commit()
    return _camp(db, c)


@router.post("/run-due")
def run_due(user: User = Depends(editor), db: Session = Depends(get_db)):
    """Starts scheduled campaigns that are due and continues throttled ones. Call it from a cron job every few minutes."""
    done = M.run_due(db)
    if done:
        audit(db, user_id=user.id, action="saas.mail.run_due", entity="mail_campaign", meta={"campaigns": done})
    db.commit()
    return {"ran": done}


def _row(r: MailOutbox) -> dict:
    return {"id": r.id, "campaign_id": r.campaign_id, "template": r.template_key, "kind": r.kind, "to_email": r.to_email, "to_name": r.to_name, "lang": r.lang,
            "lead_id": r.lead_id, "subject": r.subject, "status": r.status, "reason": r.reason, "is_test": r.is_test, "provider": r.provider,
            "sent_at": _iso(r.sent_at), "delivered_at": _iso(r.delivered_at), "opened_at": _iso(r.opened_at), "clicked_at": _iso(r.clicked_at),
            "bounced_at": _iso(r.bounced_at), "unsubscribed_at": _iso(r.unsubscribed_at), "clicks": r.clicks or [], "created_at": _iso(r.created_at)}


def _outbox_query(q: str, status: str, campaign_id: int | None):
    s = select(MailOutbox)
    if campaign_id:
        s = s.where(MailOutbox.campaign_id == campaign_id)
    if status:
        s = s.where(MailOutbox.status == status)
    if q:
        like = f"%{q.lower()}%"
        s = s.where(or_(func.lower(MailOutbox.to_email).like(like), func.lower(MailOutbox.subject).like(like), func.lower(MailOutbox.to_name).like(like)))
    return s.order_by(MailOutbox.id.desc())


@router.get("/campaigns/{cid}/results")
def campaign_results(cid: int, q: str = "", status: str = "", page: int = 1, size: int = 20, db: Session = Depends(get_db)):
    _get_campaign(db, cid)
    size = min(max(size, 1), 100)
    s = _outbox_query(q, status, cid)
    return {"total": _count(db, s), "page": page, "size": size, "items": [_row(r) for r in db.scalars(_page(s, page, size))]}


@router.get("/campaigns/{cid}/stats")
def campaign_stats(cid: int, db: Session = Depends(get_db)):
    return M.campaign_stats(db, _get_campaign(db, cid))


@router.get("/stats/compare")
def compare(db: Session = Depends(get_db)):
    cs = db.scalars(select(MailCampaign).where(MailCampaign.status != "draft").order_by(MailCampaign.id)).all()
    out = []
    for c in cs:
        s = M.campaign_stats(db, c)
        if s["recipients"]:
            out.append(s)
    return out


# ------------------------------------------------------------------ outbox
@router.get("/outbox")
def outbox(q: str = "", status: str = "", campaign_id: int | None = None, page: int = 1, size: int = 20, user: User = Depends(editor), db: Session = Depends(get_db)):
    size = min(max(size, 1), 100)
    s = _outbox_query(q, status, campaign_id)
    return {"total": _count(db, s), "page": page, "size": size, "items": [_row(r) for r in db.scalars(_page(s, page, size))]}


@router.get("/outbox/{oid}")
def outbox_one(oid: int, user: User = Depends(editor), db: Session = Depends(get_db)):
    r = db.get(MailOutbox, oid)
    if not r:
        raise HTTPException(404, "Not found")
    return {**_row(r), "html": r.html, "text": r.text}


# ------------------------------------------------------------------ suppression
class SuppressIn(BaseModel):
    email: str = Field(min_length=5, max_length=160)
    reason: str = Field(default="manual", pattern="^(manual|unsubscribe|bounce|complaint)$")


def _sup(s: MailSuppression) -> dict:
    return {"id": s.id, "email": s.email, "reason": s.reason, "source": s.source, "created_at": _iso(s.created_at)}


@router.get("/suppression")
def suppression(q: str = "", reason: str = "", page: int = 1, size: int = 20, user: User = Depends(editor), db: Session = Depends(get_db)):
    size = min(max(size, 1), 100)
    s = select(MailSuppression)
    if q:
        s = s.where(func.lower(MailSuppression.email).like(f"%{q.lower()}%"))
    if reason:
        s = s.where(MailSuppression.reason == reason)
    s = s.order_by(MailSuppression.id.desc())
    return {"total": _count(db, s), "page": page, "size": size, "items": [_sup(x) for x in db.scalars(_page(s, page, size))]}


@router.post("/suppression", status_code=201)
def add_suppression(body: SuppressIn, user: User = Depends(editor), db: Session = Depends(get_db)):
    email = body.email.strip().lower()
    if not M.valid_email(email):
        raise HTTPException(422, "Enter a valid email")
    s = M.add_suppression(db, email, body.reason, f"added by {user.name}", user.id)
    audit(db, user_id=user.id, action="saas.mail.suppress", entity="mail_suppression", entity_id=s.id, meta={"email": email, "reason": s.reason})
    db.commit()
    return _sup(s)


@router.delete("/suppression/{sid}")
def remove_suppression(sid: int, user: User = Depends(require_saas(*ADMINISH)), db: Session = Depends(get_db)):
    s = db.get(MailSuppression, sid)
    if not s:
        raise HTTPException(404, "Not found")
    audit(db, user_id=user.id, action="saas.mail.unsuppress", entity="mail_suppression", entity_id=sid, meta={"email": s.email, "reason": s.reason})
    db.delete(s)
    db.commit()
    return {"ok": True}


# ------------------------------------------------------------------ lead links
class ConsentIn(BaseModel):
    source: str = Field(min_length=2, max_length=60)
    lang: str = Field(default="", pattern="^(|bn|en)$")


@router.get("/leads/{lead_id}/timeline")
def lead_timeline(lead_id: int, user: User = Depends(editor), db: Session = Depends(get_db)):
    l = db.get(Lead, lead_id)
    if not l:
        raise HTTPException(404, "Not found")
    c = db.get(MailConsent, lead_id)
    sup = M.suppression_for(db, l.email) if l.email else None
    return {"consent": {"source": c.source, "lang": c.lang, "at": _iso(c.at)} if c else None, "suppressed": sup.reason if sup else "", "events": M.lead_timeline(db, lead_id)}


@router.put("/leads/{lead_id}/consent")
def lead_consent(lead_id: int, body: ConsentIn, user: User = Depends(editor), db: Session = Depends(get_db)):
    if not db.get(Lead, lead_id):
        raise HTTPException(404, "Not found")
    c = db.get(MailConsent, lead_id)
    if c:
        c.source, c.lang, c.at = body.source, body.lang, now()
    else:
        db.add(MailConsent(lead_id=lead_id, source=body.source, lang=body.lang))
    audit(db, user_id=user.id, action="saas.mail.consent", entity="lead", entity_id=lead_id, meta={"source": body.source})
    db.commit()
    return {"ok": True}


# ------------------------------------------------------------------ public: no sign-in
@public_router.get("/unsubscribe/{token}", dependencies=[Depends(rate_limit("unsub", 40, 600))])
def unsubscribe_info(token: str, db: Session = Depends(get_db)):
    """Shows who the link is for without changing anything (mail scanners open links). POST confirms."""
    data = M.unsign(token, "unsub")
    if not data or not M.valid_email(str(data.get("e", ""))):
        raise HTTPException(400, "This link is not valid")
    return {"email": M.mask(data["e"]), "already": M.suppression_for(db, data["e"]) is not None}


@public_router.post("/unsubscribe/{token}", dependencies=[Depends(rate_limit("unsub", 40, 600))])
def unsubscribe_do(token: str, db: Session = Depends(get_db)):
    res = M.unsubscribe(db, token)
    if not res:
        raise HTTPException(400, "This link is not valid")
    if not res["already"]:
        audit(db, action="saas.mail.unsubscribe", entity="mail_suppression", meta={"email": res["email"], "outbox_id": res["outbox_id"]})
    db.commit()
    return {"ok": True, "email": M.mask(res["email"]), "already": res["already"]}


PIXEL = bytes.fromhex("47494638396101000100800000000000ffffff21f90401000000002c00000000010001000002024401003b")


@public_router.get("/mail/open/{token}.gif", dependencies=[Depends(rate_limit("mailpx", 600, 600))])
def mail_open(token: str, db: Session = Depends(get_db)):
    data = M.unsign(token, "open")
    row = db.get(MailOutbox, data["o"]) if data else None
    if row and row.sent_at and not row.opened_at and not row.bounced_at:
        row.opened_at = now()
        db.commit()
    return Response(PIXEL, media_type="image/gif", headers={"Cache-Control": "no-store"})


@public_router.get("/mail/click/{token}", dependencies=[Depends(rate_limit("mailclick", 200, 600))])
def mail_click(token: str, db: Session = Depends(get_db)):
    data = M.unsign(token, "click")
    url = M.safe_url(data.get("u", "")) if data else ""
    if not url:
        raise HTTPException(400, "This link is not valid")
    row = db.get(MailOutbox, data["o"])
    if row and row.sent_at:
        row.opened_at = row.opened_at or now()
        row.clicked_at = row.clicked_at or now()
        row.clicks = [*(row.clicks or []), url]
        db.commit()
    return RedirectResponse(url, status_code=302)
