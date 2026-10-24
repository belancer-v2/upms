"""FlatWise's own email sending (M20): safe renderer, provider abstraction, audiences, suppression and campaign dispatch.

Providers are chosen by env MAIL_PROVIDER:
  sandbox (default)  records the rendered email in the outbox and marks it sent. No network. Can simulate engagement.
  smtp | ses         documented stub (SmtpProvider / SesProvider below). Fill in send() and set the env vars it lists.
This module is separate from services/messaging.py (customer SMS and in-app messages).
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import html as _html
import json
import os
import random
import re
from abc import ABC, abstractmethod
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..config import SECRET_KEY
from ..models.core import Membership, Organization, User, now
from ..models.mail import (MailAudience, MailCampaign, MailConsent, MailOutbox, MailProspect, MailSetting, MailSuppression, MailTemplate)
from ..models.saas import Lead, Plan, Subscription, band_for

APP_URL = os.getenv("APP_URL", "http://localhost:3000").rstrip("/")
COMPANY = "FlatWise Technologies Ltd."
ADDRESS = "House 12, Road 5, Banani, Dhaka 1213, Bangladesh"
BRAND = {"wine": "#691542", "plum": "#9D1E5F", "accent": "#EC2227"}
ALLOWED_VARS = ("name", "building", "plan", "trial_days_left", "link")
BLOCK_TYPES = ("heading", "paragraph", "button", "image", "divider", "footer")
HARD_BLOCK = ("bounce", "complaint", "manual")  # these also block transactional mail
DEFAULTS = {"weekly_cap": "2", "throttle_per_hour": "200", "sim_seed": "20261024"}


def _aware(dt):
    return dt.replace(tzinfo=timezone.utc) if dt and dt.tzinfo is None else dt


# ------------------------------------------------------------------ settings
def get_setting(db: Session, key: str) -> str:
    row = db.get(MailSetting, key)
    return row.value if row else DEFAULTS[key]


def get_int(db: Session, key: str) -> int:
    try:
        return int(get_setting(db, key))
    except ValueError:
        return int(DEFAULTS[key])


def set_setting(db: Session, key: str, value) -> None:
    if key not in DEFAULTS:
        raise ValueError("Unknown setting")
    row = db.get(MailSetting, key)
    if row:
        row.value = str(value)
    else:
        db.add(MailSetting(key=key, value=str(value)))


# ------------------------------------------------------------------ signed tokens (no login needed)
def _b64(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode()


def _unb64(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def sign(payload: dict) -> str:
    body = _b64(json.dumps(payload, separators=(",", ":"), sort_keys=True).encode())
    mac = hmac.new(SECRET_KEY.encode(), body.encode(), hashlib.sha256).digest()[:18]
    return f"{body}.{_b64(mac)}"


def unsign(token: str, purpose: str) -> dict | None:
    try:
        body, mac = token.split(".", 1)
        good = hmac.new(SECRET_KEY.encode(), body.encode(), hashlib.sha256).digest()[:18]
        if not hmac.compare_digest(_unb64(mac), good):
            return None
        data = json.loads(_unb64(body))
        return data if isinstance(data, dict) and data.get("p") == purpose else None
    except Exception:
        return None


def unsubscribe_token(email: str, outbox_id: int = 0) -> str:
    return sign({"p": "unsub", "e": email.lower(), "o": outbox_id})


# ------------------------------------------------------------------ blocks and the safe renderer
def clean_blocks(blocks) -> list[dict]:
    """Validate editor blocks. Raises ValueError with a readable message."""
    if not isinstance(blocks, list) or len(blocks) > 40:
        raise ValueError("A template can have up to 40 blocks")
    out = []
    for b in blocks:
        if not isinstance(b, dict) or b.get("type") not in BLOCK_TYPES:
            raise ValueError("Unknown block type")
        item = {"type": b["type"]}
        for f, mx in (("text", 4000), ("label", 80), ("url", 500), ("alt", 160)):
            v = b.get(f, "")
            if not isinstance(v, str) or len(v) > mx:
                raise ValueError(f"Block field '{f}' is too long")
            if v:
                item[f] = v
        out.append(item)
    return out


_VAR = re.compile(r"\{\{\s*([A-Za-z_]+)\s*\}\}")


def subst(text: str, vars: dict, escape: bool = True) -> str:
    """Replace {{name}}. Text is escaped first, values are escaped too, unknown variables become empty. One pass, nothing is evaluated."""
    if escape:
        text = _html.escape(text or "", quote=True)

    def one(m):
        k = m.group(1)
        v = str(vars.get(k, "")) if k in ALLOWED_VARS else ""
        return _html.escape(v, quote=True) if escape else v
    return _VAR.sub(one, text or "")


def safe_url(url: str) -> str:
    u = (url or "").strip()
    return u if re.match(r"^(https?://|mailto:)", u, re.I) else ""


LEGAL = {
    "en": {"why_promo": "You are receiving this because you asked about FlatWise or are in our contact list.", "why_tx": "You are receiving this service email because of your FlatWise account or request.",
           "unsub": "Unsubscribe", "unsub_tx": "Stop promotional emails"},
    "bn": {"why_promo": "আপনি ফ্ল্যাটওয়াইজ সম্পর্কে জানতে চেয়েছেন বা আমাদের যোগাযোগ তালিকায় আছেন, তাই এই ইমেইল পাচ্ছেন।", "why_tx": "আপনার ফ্ল্যাটওয়াইজ অ্যাকাউন্ট বা অনুরোধের কারণে এই সেবা-ইমেইল পাঠানো হয়েছে।",
           "unsub": "সাবস্ক্রিপশন বাতিল করুন", "unsub_tx": "প্রচারণামূলক ইমেইল বন্ধ করুন"},
}


def _css(prefix: str) -> str:
    p = prefix
    return (f"{p} .fw-bg{{background:#150911 !important}}{p} .fw-card{{background:#1F0F19 !important}}{p} .fw-tx{{color:#F7F3F3 !important}}"
            f"{p} .fw-hd{{color:#F1B8D3 !important}}{p} .fw-mut{{color:#B9A9B2 !important}}{p} .fw-ln{{border-color:#35202C !important}}"
            f"{p} .fw-btn{{background:#B02371 !important}}{p} .fw-lnk{{color:#F1B8D3 !important}}")


@dataclass
class Rendered:
    subject: str
    html: str
    text: str
    links: list[str]


def render_email(subject: str, blocks: list[dict], vars: dict, lang: str = "bn", kind: str = "promotional", email: str = "",
                 outbox_id: int = 0, theme: str = "auto") -> Rendered:
    """theme: auto (follows the reader's mode), light or dark (previews)."""
    lang = "en" if lang == "en" else "bn"
    L = LEGAL[lang]
    token = unsubscribe_token(email, outbox_id) if email else "preview"
    unsub_url = f"{APP_URL}/unsubscribe/{token}"
    parts, text, links = [], [], []

    def track(url: str) -> str:
        if outbox_id and url:
            return f"{APP_URL}/api/public/mail/click/{sign({'p': 'click', 'o': outbox_id, 'u': url})}"
        return url

    for b in blocks:
        t = b.get("type")
        if t == "heading":
            parts.append(f'<h1 class="fw-hd" style="margin:0 0 14px;font-size:24px;line-height:1.3;color:{BRAND["wine"]}">{subst(b.get("text", ""), vars)}</h1>')
            text.append(subst(b.get("text", ""), vars, False).upper() + "\n")
        elif t == "paragraph":
            parts.append(f'<p class="fw-tx" style="margin:0 0 16px;font-size:16px;line-height:1.65;color:#2A1520">{subst(b.get("text", ""), vars).replace(chr(10), "<br>")}</p>')
            text.append(subst(b.get("text", ""), vars, False) + "\n")
        elif t == "button":
            url = safe_url(subst(b.get("url", ""), vars, False))
            label = subst(b.get("label", ""), vars)
            if url:
                links.append(url)
                parts.append(f'<table role="presentation" cellpadding="0" cellspacing="0" style="margin:6px 0 20px"><tr><td class="fw-btn" style="background:{BRAND["plum"]};border-radius:12px">'
                             f'<a href="{_html.escape(track(url), quote=True)}" style="display:inline-block;padding:13px 26px;color:#FFFFFF;font-weight:700;font-size:16px;text-decoration:none">{label}</a></td></tr></table>')
                text.append(f"{subst(b.get('label', ''), vars, False)}: {url}\n")
        elif t == "image":
            url = safe_url(subst(b.get("url", ""), vars, False))
            if url:
                parts.append(f'<img src="{_html.escape(url, quote=True)}" alt="{subst(b.get("alt", ""), vars)}" width="536" style="display:block;max-width:100%;height:auto;border-radius:12px;margin:0 0 18px">')
                if b.get("alt"):
                    text.append(f"[{subst(b.get('alt', ''), vars, False)}]\n")
        elif t == "divider":
            parts.append('<hr class="fw-ln" style="border:0;border-top:1px solid #ECE6E6;margin:22px 0">')
            text.append("----------\n")
        elif t == "footer":
            parts.append(f'<p class="fw-mut" style="margin:0 0 8px;font-size:13px;line-height:1.5;color:#6D6E70">{subst(b.get("text", ""), vars).replace(chr(10), "<br>")}</p>')
            text.append(subst(b.get("text", ""), vars, False) + "\n")
    pixel = (f'<img src="{APP_URL}/api/public/mail/open/{sign({"p": "open", "o": outbox_id})}.gif" width="1" height="1" alt="" style="display:block;border:0">' if outbox_id else "")
    why = L["why_promo"] if kind == "promotional" else L["why_tx"]
    label = L["unsub"] if kind == "promotional" else L["unsub_tx"]
    legal = (f'<p class="fw-mut" style="margin:0 0 6px;font-size:12px;line-height:1.5;color:#6D6E70">{COMPANY} · {_html.escape(ADDRESS)}</p>'
             f'<p class="fw-mut" style="margin:0;font-size:12px;line-height:1.5;color:#6D6E70">{_html.escape(why)} '
             f'<a class="fw-lnk" href="{_html.escape(unsub_url, quote=True)}" style="color:{BRAND["plum"]}">{_html.escape(label)}</a></p>')
    text.append(f"\n--\n{COMPANY}, {ADDRESS}\n{why}\n{label}: {unsub_url}\n")
    subj = subst(subject, vars, False).replace("\n", " ").strip()
    dark = _css(".fw-dark") if theme == "dark" else ""
    auto = f"@media (prefers-color-scheme: dark){{{_css('')}}}" if theme == "auto" else ""
    doc = (f'<!doctype html><html lang="{lang}"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
           f'<meta name="color-scheme" content="light dark"><meta name="supported-color-schemes" content="light dark"><title>{_html.escape(subj)}</title>'
           f'<style>body{{margin:0}}img{{border:0}}{auto}{dark}</style></head>'
           f'<body class="fw-bg {"fw-dark" if theme == "dark" else ""}" style="margin:0;background:#F7F3F3;font-family:\'Nunito Sans\',\'Hind Siliguri\',Arial,sans-serif">'
           f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" class="fw-bg" style="background:#F7F3F3"><tr><td align="center" style="padding:24px 12px">'
           f'<table role="presentation" width="600" cellpadding="0" cellspacing="0" style="width:100%;max-width:600px">'
           f'<tr><td style="background:{BRAND["wine"]};border-top:3px solid {BRAND["accent"]};border-radius:16px 16px 0 0;padding:20px 32px;color:#FFFFFF;font-size:22px;font-weight:800;letter-spacing:.2px">FlatWise</td></tr>'
           f'<tr><td class="fw-card" style="background:#FFFFFF;padding:32px;border-radius:0 0 16px 16px">{"".join(parts)}'
           f'<hr class="fw-ln" style="border:0;border-top:1px solid #ECE6E6;margin:24px 0 16px">{legal}{pixel}</td></tr>'
           f'</table></td></tr></table></body></html>')
    return Rendered(subj, doc, "\n".join(text), links)


def template_side(tpl: MailTemplate, lang: str) -> tuple[str, list[dict], str]:
    """Subject, blocks and the language actually used. Falls back to the other language if one side is empty."""
    lang = "en" if lang == "en" else "bn"
    s, b = (tpl.subject_en, tpl.blocks_en) if lang == "en" else (tpl.subject_bn, tpl.blocks_bn)
    if not b:
        lang = "bn" if lang == "en" else "en"
        s, b = (tpl.subject_en, tpl.blocks_en) if lang == "en" else (tpl.subject_bn, tpl.blocks_bn)
    return s, b, lang


# ------------------------------------------------------------------ providers
@dataclass
class Mail:
    to: str
    subject: str
    html: str
    text: str


class EmailProvider(ABC):
    name = ""
    simulates = False

    @abstractmethod
    def send(self, mail: Mail) -> str:
        """Hand the email over. Returns a provider message id. Raise on failure."""


class SandboxProvider(EmailProvider):
    """No network. The caller records the rendered email in mail_outbox; this only acknowledges it."""
    name = "sandbox"
    simulates = True

    def send(self, mail: Mail) -> str:
        return "sandbox-" + hashlib.sha1(f"{mail.to}{mail.subject}".encode()).hexdigest()[:10]

    @staticmethod
    def simulate(key: str) -> dict:
        """Deterministic engagement for demo stats: the same key always gives the same result."""
        r = random.Random(key)
        bounced = r.random() < 0.04
        opened = (not bounced) and r.random() < 0.52
        clicked = opened and r.random() < 0.34
        return {"bounced": bounced, "opened": opened, "clicked": clicked, "open_min": r.randint(3, 600), "click_min": r.randint(1, 90), "pick": r.random()}


class SmtpProvider(EmailProvider):
    """STUB. To go live: set MAIL_PROVIDER=smtp and MAIL_SMTP_HOST, MAIL_SMTP_PORT, MAIL_SMTP_USER, MAIL_SMTP_PASSWORD, MAIL_FROM.
    Implement send() with smtplib (STARTTLS), add the List-Unsubscribe and List-Unsubscribe-Post headers, and feed bounce/open/click
    webhooks back into mail_outbox. Until then it refuses to send rather than pretend."""
    name = "smtp"

    def send(self, mail: Mail) -> str:
        raise NotImplementedError("SMTP provider is not wired yet. See SmtpProvider in services/mailer.py.")


class SesProvider(SmtpProvider):
    """STUB for Amazon SES (MAIL_PROVIDER=ses). Use boto3 sesv2 send_email and SNS notifications for bounces and complaints."""
    name = "ses"


def get_provider() -> EmailProvider:
    kind = os.getenv("MAIL_PROVIDER", "sandbox").lower()
    return {"smtp": SmtpProvider, "ses": SesProvider}.get(kind, SandboxProvider)()


# ------------------------------------------------------------------ audiences
STAGES = ["new", "contacted", "demo", "trial", "won", "lost"]
AUDIENCE_KINDS = ("stage", "trial", "active", "churned", "plan", "city", "band", "csv")
EMAIL_RE = re.compile(r"^[A-Za-z0-9._%+\-']+@[A-Za-z0-9\-]+(\.[A-Za-z0-9\-]+)*\.[A-Za-z]{2,}$")


def valid_email(e: str) -> bool:
    return bool(e) and len(e) <= 160 and bool(EMAIL_RE.match(e))


def _org_contacts(db: Session) -> dict[int, User]:
    rows = db.execute(select(Membership.org_id, User).join(User, User.id == Membership.user_id)
                      .where(Membership.role.in_(("PROPERTY_ADMIN", "AGENCY_MANAGER", "PRESIDENT")), User.is_active == True)  # noqa: E712
                      .order_by(Membership.id)).all()
    out: dict[int, User] = {}
    for org_id, u in rows:
        out.setdefault(org_id, u)
    return out


def resolve_audience(db: Session, aud: MailAudience) -> list[dict]:
    """People an audience reaches right now: one dict per distinct email (first one wins). Suppression is applied at send time, not here."""
    p = aud.params or {}
    city = (p.get("city") or "").strip().lower()
    band = p.get("band")
    plan = p.get("plan")
    out: dict[str, dict] = {}

    def add(r: dict):
        e = (r["email"] or "").strip().lower()
        if valid_email(e) and e not in out:
            out[e] = {**r, "email": e}

    def lead_rows(filter_fn):
        cons = {c.lead_id: c for c in db.scalars(select(MailConsent))}
        for l in db.scalars(select(Lead).order_by(Lead.id)):
            if l.email and filter_fn(l):
                c = cons.get(l.id)
                add({"email": l.email, "name": l.name, "lang": (c.lang if c and c.lang else "") or "bn", "lead_id": l.id, "org_id": None, "building": l.building,
                     "plan": "", "plan_bn": "", "trial_days_left": "", "city": l.city, "source": "lead", "link": f"{APP_URL}/demo"})

    def org_rows(filter_fn):
        contacts = _org_contacts(db)
        plans = {x.key: x for x in db.scalars(select(Plan))}
        for o in db.scalars(select(Organization).order_by(Organization.id)):
            sub = db.scalar(select(Subscription).where(Subscription.org_id == o.id).order_by(Subscription.id.desc()))
            u = contacts.get(o.id)
            if not u or not sub or not filter_fn(o, sub):
                continue
            pl = plans.get(sub.plan_key)
            left = ""
            if sub.trial_ends:
                left = str(max(0, (_aware(sub.trial_ends) - now()).days))
            add({"email": u.email, "name": u.name, "lang": u.lang or "bn", "lead_id": None, "org_id": o.id, "building": o.name, "building_bn": o.name_bn,
                 "plan": pl.name if pl else sub.plan_key, "plan_bn": (pl.name_bn if pl else "") or "", "trial_days_left": left, "city": o.city, "source": "org", "link": f"{APP_URL}/app"})

    if aud.kind == "stage":
        stages = set(p.get("stages") or [])
        lead_rows(lambda l: l.status in stages)
    elif aud.kind == "trial":
        org_rows(lambda o, s: s.status == "trial")
    elif aud.kind == "active":
        org_rows(lambda o, s: s.status in ("active", "past_due"))
    elif aud.kind == "churned":
        org_rows(lambda o, s: s.status in ("suspended", "cancelled"))
    elif aud.kind == "plan":
        org_rows(lambda o, s: s.plan_key == plan)
    elif aud.kind == "city":
        lead_rows(lambda l: l.city.strip().lower() == city)
        org_rows(lambda o, s: (o.city or "").strip().lower() == city)
    elif aud.kind == "band":
        lead_rows(lambda l: l.flats > 0 and band_for(l.flats) == band)
        org_rows(lambda o, s: s.band == band)
    elif aud.kind == "csv":
        for r in db.scalars(select(MailProspect).where(MailProspect.audience_id == aud.id).order_by(MailProspect.id)):
            add({"email": r.email, "name": r.name, "lang": r.lang or "bn", "lead_id": None, "org_id": None, "building": r.company, "plan": "", "plan_bn": "",
                 "trial_days_left": "", "city": r.city, "source": "csv", "link": f"{APP_URL}/pricing"})
    return list(out.values())


CSV_CAP = 5000


def parse_prospects_csv(text: str) -> dict:
    """Validate an uploaded CSV (email, name, company, city; lang optional). Returns rows kept, invalid rows and duplicates. Raises ValueError over the cap."""
    import csv
    import io
    text = text.lstrip("﻿")
    rows = list(csv.reader(io.StringIO(text)))
    rows = [r for r in rows if any(c.strip() for c in r)]
    if not rows:
        raise ValueError("The file is empty")
    head = [h.strip().lower() for h in rows[0]]
    if "email" not in head:
        raise ValueError("The first row must have an 'email' column")
    body = rows[1:]
    if len(body) > CSV_CAP:
        raise ValueError(f"Too many rows: {len(body)}. The limit is {CSV_CAP}.")
    idx = {k: head.index(k) for k in ("email", "name", "company", "city", "lang") if k in head}
    seen, good, invalid, dupes = set(), [], [], 0
    for n, r in enumerate(body, start=2):
        g = lambda k: (r[idx[k]].strip() if k in idx and idx[k] < len(r) else "")
        email = g("email").lower()
        if not valid_email(email):
            invalid.append({"row": n, "email": g("email")[:80], "reason": "bad_email"})
            continue
        if email in seen:
            dupes += 1
            continue
        seen.add(email)
        lang = g("lang").lower()
        good.append({"email": email, "name": g("name")[:120], "company": g("company")[:160], "city": g("city")[:80], "lang": lang if lang in ("bn", "en") else ""})
    return {"rows": good, "invalid": invalid, "duplicates": dupes, "total": len(body)}


# ------------------------------------------------------------------ suppression and caps
def suppression_for(db: Session, email: str) -> MailSuppression | None:
    return db.scalar(select(MailSuppression).where(MailSuppression.email == email.strip().lower()))


def promo_count_7d(db: Session, email: str, at: datetime) -> int:
    return db.scalar(select(func.count()).select_from(MailOutbox).where(
        MailOutbox.to_email == email.lower(), MailOutbox.kind == "promotional", MailOutbox.is_test == False,  # noqa: E712
        MailOutbox.sent_at != None, MailOutbox.sent_at >= at - timedelta(days=7))) or 0  # noqa: E711


def block_reason(db: Session, email: str, kind: str, at: datetime) -> tuple[str, str] | None:
    """(status, reason) when this address must not be emailed now, else None."""
    s = suppression_for(db, email)
    if s and (kind == "promotional" or s.reason in HARD_BLOCK):
        return "suppressed", s.reason
    if kind == "promotional" and promo_count_7d(db, email, at) >= get_int(db, "weekly_cap"):
        return "skipped", "weekly_cap"
    return None


def add_suppression(db: Session, email: str, reason: str, source: str = "", by_user_id: int | None = None) -> MailSuppression:
    email = email.strip().lower()
    s = suppression_for(db, email)
    if s:
        if reason in HARD_BLOCK and s.reason not in HARD_BLOCK:
            s.reason = reason  # a bounce outranks an unsubscribe
        return s
    s = MailSuppression(email=email, reason=reason, source=source[:80], by_user_id=by_user_id)
    db.add(s)
    db.flush()
    return s


# ------------------------------------------------------------------ delivery
def _vars(r: dict, lang: str) -> dict:
    bn = lang == "bn"
    return {"name": r.get("name", ""), "building": (r.get("building_bn") if bn and r.get("building_bn") else r.get("building", "")),
            "plan": (r.get("plan_bn") if bn and r.get("plan_bn") else r.get("plan", "")), "trial_days_left": r.get("trial_days_left", ""), "link": r.get("link", APP_URL)}


def _deliver(db: Session, row: MailOutbox, tpl: MailTemplate, at: datetime, simulate: bool, sim_key: str) -> None:
    """Render, hand to the provider, record the result."""
    prov = get_provider()
    subject, blocks, lang = template_side(tpl, row.lang)
    row.lang = lang
    row.provider = prov.name
    rendered = render_email(subject, blocks, row.vars or {}, lang, tpl.kind, row.to_email, row.id)
    row.subject, row.html, row.text = rendered.subject, rendered.html, rendered.text
    try:
        prov.send(Mail(row.to_email, rendered.subject, rendered.html, rendered.text))
    except Exception as e:  # real providers can fail; record it, do not crash the run
        row.status, row.reason = "failed", str(e)[:60]
        return
    row.status, row.sent_at = "sent", at
    if not prov.simulates:
        return
    row.delivered_at = at + timedelta(seconds=3)
    if not simulate:
        return
    soon = lambda d: min(d, now())  # simulated events never sit in the future
    ev = SandboxProvider.simulate(f"{get_setting(db, 'sim_seed')}:{sim_key}")
    if ev["bounced"]:
        row.status, row.delivered_at, row.bounced_at = "bounced", None, soon(at + timedelta(seconds=5))
        add_suppression(db, row.to_email, "bounce", f"hard bounce, outbox {row.id}")
        return
    if ev["opened"]:
        row.opened_at = soon(at + timedelta(minutes=ev["open_min"]))
    if ev["clicked"] and rendered.links:
        row.clicked_at = soon(row.opened_at + timedelta(minutes=ev["click_min"]))
        row.clicks = [rendered.links[int(ev["pick"] * len(rendered.links)) % len(rendered.links)]]


def send_template(db: Session, key: str, to_email: str, to_name: str = "", lang: str = "", vars: dict | None = None, lead_id: int | None = None,
                  org_id: int | None = None, at: datetime | None = None, simulate: bool = False, campaign_id: int | None = None, force: bool = False) -> MailOutbox:
    """Send one email from a template (transactional events call this). Honours suppression; promotional also honours the weekly cap."""
    tpl = db.scalar(select(MailTemplate).where(MailTemplate.key == key))
    if not tpl:
        raise ValueError(f"No template '{key}'")
    at = at or now()
    lang = lang if lang in ("bn", "en") else "bn"
    v = {k: str(x) for k, x in (vars or {}).items() if k in ALLOWED_VARS}
    v.setdefault("name", to_name)
    row = MailOutbox(campaign_id=campaign_id, template_key=tpl.key, kind=tpl.kind, to_email=to_email.strip().lower(), to_name=to_name, lang=lang,
                     lead_id=lead_id, org_id=org_id, vars=v, status="queued", created_at=at)
    db.add(row)
    db.flush()
    blocked = None if force else block_reason(db, row.to_email, tpl.kind, at)
    if blocked:
        row.status, row.reason = blocked
        return row
    _deliver(db, row, tpl, at, simulate, f"tx:{key}:{row.to_email}")
    return row


def resolve_lang(rule: str, recipient_lang: str) -> str:
    if rule in ("bn", "en"):
        return rule
    return "en" if recipient_lang == "en" else "bn"


def queue_campaign(db: Session, c: MailCampaign, at: datetime | None = None) -> int:
    """Create one queued outbox row per recipient (once). Returns how many."""
    if db.scalar(select(func.count()).select_from(MailOutbox).where(MailOutbox.campaign_id == c.id, MailOutbox.is_test == False)):  # noqa: E712
        return 0
    aud = db.get(MailAudience, c.audience_id)
    tpl = db.get(MailTemplate, c.template_id)
    n = 0
    for r in resolve_audience(db, aud):
        lang = resolve_lang(c.lang_rule, r["lang"])
        db.add(MailOutbox(campaign_id=c.id, template_key=tpl.key, kind=tpl.kind, to_email=r["email"], to_name=r["name"], lang=lang, lead_id=r["lead_id"],
                          org_id=r["org_id"], vars=_vars(r, lang), status="queued", created_at=at or now()))
        n += 1
    db.flush()
    return n


def dispatch(db: Session, c: MailCampaign, at: datetime | None = None) -> dict:
    """Send queued rows within this hour's throttle budget. Rows blocked by suppression or the weekly cap do not use budget."""
    at = at or now()
    tpl = db.get(MailTemplate, c.template_id)
    limit = c.throttle_per_hour or get_int(db, "throttle_per_hour")
    used = db.scalar(select(func.count()).select_from(MailOutbox).where(MailOutbox.campaign_id == c.id, MailOutbox.sent_at != None,  # noqa: E711
                                                                       MailOutbox.sent_at > at - timedelta(hours=1), MailOutbox.is_test == False)) or 0  # noqa: E712
    budget = max(0, limit - used)
    if c.started_at is None:
        c.started_at = at
    c.status = "sending"
    sent = blocked = 0
    rows = db.scalars(select(MailOutbox).where(MailOutbox.campaign_id == c.id, MailOutbox.status == "queued", MailOutbox.is_test == False).order_by(MailOutbox.id)).all()  # noqa: E712
    for row in rows:
        b = block_reason(db, row.to_email, tpl.kind, at)
        if b:
            row.status, row.reason = b
            blocked += 1
            continue
        if sent >= budget:
            break
        _deliver(db, row, tpl, at, c.simulate, f"{c.id}:{row.to_email}")
        sent += 1
    left = db.scalar(select(func.count()).select_from(MailOutbox).where(MailOutbox.campaign_id == c.id, MailOutbox.status == "queued")) or 0
    if left == 0:
        c.status, c.finished_at = "sent", at
    db.flush()
    return {"sent": sent, "blocked": blocked, "queued": left, "status": c.status}


def send_test(db: Session, c: MailCampaign, to_email: str, to_name: str, lang: str) -> MailOutbox:
    """One preview send to the person testing. Skips suppression and caps. Never counted in stats or the weekly cap."""
    tpl = db.get(MailTemplate, c.template_id)
    lang = resolve_lang(c.lang_rule, lang)
    v = _vars({"name": to_name, "building": "Sunrise Tower", "plan": "Standard", "trial_days_left": "7", "link": f"{APP_URL}/pricing"}, lang)
    row = MailOutbox(campaign_id=c.id, template_key=tpl.key, kind=tpl.kind, to_email=to_email.lower(), to_name=to_name, lang=lang, vars=v, status="queued", is_test=True)
    db.add(row)
    db.flush()
    _deliver(db, row, tpl, now(), False, "test")
    row.subject = "[TEST] " + row.subject
    return row


def run_due(db: Session, at: datetime | None = None) -> list[dict]:
    """Start scheduled campaigns whose time has come and continue throttled ones. Call from a cron or the run-due endpoint."""
    at = at or now()
    done = []
    for c in db.scalars(select(MailCampaign).where(MailCampaign.status.in_(("scheduled", "sending"))).order_by(MailCampaign.id)).all():
        if c.status == "scheduled" and (not c.scheduled_at or _aware(c.scheduled_at) > at):
            continue
        queue_campaign(db, c, at)
        done.append({"id": c.id, **dispatch(db, c, at)})
    return done


# ------------------------------------------------------------------ unsubscribe, stats
def unsubscribe(db: Session, token: str) -> dict | None:
    """Apply an unsubscribe from a signed link. Returns None for a forged token. Safe to repeat."""
    data = unsign(token, "unsub")
    if not data or not valid_email(str(data.get("e", ""))):
        return None
    email = data["e"]
    already = suppression_for(db, email) is not None
    if not already:
        add_suppression(db, email, "unsubscribe", f"link, outbox {data.get('o', 0)}")
    row = db.get(MailOutbox, data["o"]) if data.get("o") else None
    if row and row.to_email == email and not row.unsubscribed_at:
        row.unsubscribed_at = now()
    return {"email": email, "already": already, "outbox_id": data.get("o", 0)}


def mask(email: str) -> str:
    a, _, d = email.partition("@")
    return (a[:1] + "***" if a else "***") + "@" + d


def _pct(a: int, b: int) -> float:
    return round(100 * a / b, 1) if b else 0.0


def campaign_stats(db: Session, c: MailCampaign) -> dict:
    rows = db.scalars(select(MailOutbox).where(MailOutbox.campaign_id == c.id, MailOutbox.is_test == False)).all()  # noqa: E712
    sent = sum(1 for r in rows if r.sent_at)
    delivered = sum(1 for r in rows if r.delivered_at)
    opened = sum(1 for r in rows if r.opened_at)
    clicked = sum(1 for r in rows if r.clicked_at)
    bounced = sum(1 for r in rows if r.bounced_at)
    unsub = sum(1 for r in rows if r.unsubscribed_at)
    links = Counter(u for r in rows for u in (r.clicks or []))
    return {"id": c.id, "name": c.name, "status": c.status, "recipients": len(rows), "queued": sum(r.status == "queued" for r in rows),
            "suppressed": sum(r.status == "suppressed" for r in rows), "skipped": sum(r.status == "skipped" for r in rows),
            "sent": sent, "delivered": delivered, "opened": opened, "clicked": clicked, "bounced": bounced, "unsubscribed": unsub,
            "rates": {"delivered": _pct(delivered, sent), "opened": _pct(opened, delivered), "clicked": _pct(clicked, delivered),
                      "bounced": _pct(bounced, sent), "unsubscribed": _pct(unsub, delivered)},
            "top_links": [{"url": u, "clicks": n} for u, n in links.most_common(5)],
            "started_at": c.started_at.isoformat() if c.started_at else None}


def lead_timeline(db: Session, lead_id: int) -> list[dict]:
    """Email events for the lead page, newest first."""
    ev = []
    tpl = {t.key: t for t in db.scalars(select(MailTemplate))}
    for r in db.scalars(select(MailOutbox).where(MailOutbox.lead_id == lead_id, MailOutbox.is_test == False)):  # noqa: E712
        t = tpl.get(r.template_key)
        name = t.name if t else r.template_key
        name_bn = (t.name_bn if t else "") or name
        for field, kind in (("sent_at", "sent"), ("opened_at", "opened"), ("clicked_at", "clicked"), ("bounced_at", "bounced"), ("unsubscribed_at", "unsubscribed")):
            at = getattr(r, field)
            if at:
                ev.append({"outbox_id": r.id, "template": r.template_key, "name": name, "name_bn": name_bn, "event": kind, "at": _aware(at).isoformat(), "campaign_id": r.campaign_id})
        if r.status in ("suppressed", "skipped"):
            ev.append({"outbox_id": r.id, "template": r.template_key, "name": name, "name_bn": name_bn, "event": r.status, "at": _aware(r.created_at).isoformat(), "campaign_id": r.campaign_id})
    ev.sort(key=lambda e: e["at"], reverse=True)
    return ev
