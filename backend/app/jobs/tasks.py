"""The scheduled jobs. Each is fn(db, at) -> dict with the time injected, idempotent, and registered with its schedule.

Schedules (Dhaka time for daily jobs):
  campaigns_run_due      every 5 min     amenities_expire     every hour      gateway_sweep       every 10 min
  billing_auto           daily 06:00     reminders_run        daily 09:00     low_credit_alerts   daily 09:30
  saas_invoices          daily 00:30     credit_grants        daily 00:45     trial_ending        daily 08:00
  saas_dunning           daily 10:00     gateway_reconcile    daily 02:00     cleanup             daily 03:00
  integrity_check        daily 03:30     sms_provider_balance every 6 h
"""
from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException
from sqlalchemy import and_, delete, func, or_, select, update
from sqlalchemy.orm import Session

from ..audit import audit
from ..models.billing import Invoice, Payment
from ..models.cash import CashEntry
from ..models.core import Organization, Property, now
from ..models.credits import CreditPurchase, CreditSetting
from ..models.finance import Journal, JournalLine
from ..models.gateway import GatewaySession
from ..models.jobs import BuildingAutomation, JobLock, JobMark, JobRun, SystemAlert
from ..models.mail import MailCampaign, MailOutbox
from ..models.saas import Plan, SaasInvoice, Subscription
from ..services import gateway as gw
from ..services import mailer as M
from ..services.entitlements import email_balance, org_features, sms_balance
from .notify import mail_org_admins
from .runner import DHAKA, Schedule, alert, aware, claim, local_date, register

APP_URL = os.getenv("APP_URL", "http://localhost:3000").rstrip("/")
LIVE_SUBS = ("trial", "active", "past_due")


def _int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except ValueError:
        return default


def _live_org(db: Session, org_id: int) -> Organization | None:
    org = db.get(Organization, org_id)
    return org if org and org.status != "suspended" else None


# ------------------------------------------------------------------ 1. daily billing run (opt-in per building)
@register("billing_auto", "Monthly service-charge invoices (buildings that opted in)", Schedule(hour=6))
def billing_auto(db: Session, at: datetime) -> dict:
    from ..routers import billing as B
    today = local_date(at)
    period = f"{today:%Y-%m}"
    made = skipped = 0
    for auto in db.scalars(select(BuildingAutomation).where(BuildingAutomation.auto_billing)):
        prop = db.get(Property, auto.property_id)
        if not prop or not _live_org(db, prop.org_id) or "billing" not in org_features(db, prop.org_id) or today.day < auto.bill_day:
            continue
        key = f"autobill:{prop.id}:{period}"
        if db.get(JobMark, key):
            continue
        try:
            n, total = B.make_invoices(db, prop.id, period, auto.due_day)
        except ValueError:      # no charge rules yet: leave it for tomorrow
            skipped += 1
            continue
        claim(db, key, at)
        audit(db, org_id=prop.org_id, property_id=prop.id, action="billing.auto", entity="period", entity_id=period, meta={"created": n, "total": total})
        made += n
    return {"period": period, "invoices": made, "skipped_no_rules": skipped}


# ------------------------------------------------------------------ 2. reminders
@register("reminders_run", "Dues reminders for every building with the feature", Schedule(hour=9))
def reminders_run(db: Session, at: datetime) -> dict:
    from ..routers import billing as B
    sent = failed = buildings = 0
    for prop in db.scalars(select(Property).order_by(Property.id)):
        feats = org_features(db, prop.org_id)
        if not {"reminders", "billing"} <= feats or not _live_org(db, prop.org_id):
            continue
        s, f = B.send_reminders(db, prop, local_date(at))
        sent, failed, buildings = sent + s, failed + f, buildings + 1
        db.commit()
    return {"buildings": buildings, "sent": sent, "failed": failed, **({"warn": True} if failed else {})}


# ------------------------------------------------------------------ 3. campaigns
@register("campaigns_run_due", "Start scheduled email campaigns and continue throttled ones", Schedule(every_minutes=5))
def campaigns_run_due(db: Session, at: datetime) -> dict:
    done = M.run_due(db, at)
    return {"campaigns": len(done), "sent": sum(d.get("sent", 0) for d in done)}


# ------------------------------------------------------------------ 4. amenities
@register("amenities_expire", "Free amenity slots of unpaid or past requests", Schedule(every_minutes=60))
def amenities_expire(db: Session, at: datetime) -> dict:
    from ..routers import amenities as A
    n = 0
    for prop in db.scalars(select(Property)):
        if "amenities" in org_features(db, prop.org_id):
            n += A.expire_stale(db, prop.id, at)
    return {"expired": n}


# ------------------------------------------------------------------ 5. gateway sessions
@register("gateway_sweep", "Expire payment sessions nobody finished", Schedule(every_minutes=10))
def gateway_sweep(db: Session, at: datetime) -> dict:
    a = db.execute(update(GatewaySession).where(GatewaySession.status == "created", GatewaySession.expires_at < at).values(status="expired", completed_at=at)).rowcount
    b = db.execute(update(CreditPurchase).where(CreditPurchase.mode == "gateway", CreditPurchase.status == "created", CreditPurchase.expires_at < at).values(status="expired", completed_at=at)).rowcount
    return {"payment_sessions": a, "credit_purchases": b}


# ------------------------------------------------------------------ 6. low credit alerts
@register("low_credit_alerts", "Tell building admins once a day when SMS or email credits are low", Schedule(hour=9, minute=30))
def low_credit_alerts(db: Session, at: datetime) -> dict:
    from ..routers import credits as C
    day = local_date(at)
    notified = 0
    for org in db.scalars(select(Organization)):
        sub = db.scalar(select(Subscription).where(Subscription.org_id == org.id).order_by(Subscription.id.desc()))
        if not sub or sub.status not in LIVE_SUBS or org.status == "suspended":
            continue
        sms_low, email_low = C.thresholds(db, org.id)
        for kind, bal, low, tpl in (("sms", sms_balance(db, org.id), sms_low, "credits_low"), ("email", email_balance(db, org.id), email_low, "credits_low_email")):
            if bal >= low:
                continue
            key = f"lowcredit:{org.id}:{kind}:{day}"
            if not claim(db, key, at):
                continue
            mail_org_admins(db, org, tpl, {"link": f"{APP_URL}/app/credits"}, at)
            alert(db, key, "low_credit", f"{org.name}: {kind.upper()} credits {bal} below {low}", "info", {"balance": bal, "threshold": low, "kind": kind}, org_id=org.id, at=at)
            notified += 1
    return {"notified": notified}


# ------------------------------------------------------------------ 7. SaaS subscription invoices
@register("saas_invoices", "Monthly FlatWise subscription invoices", Schedule(hour=0, minute=30))
def saas_invoices(db: Session, at: datetime) -> dict:
    from ..routers import saas as S
    period = f"{local_date(at):%Y-%m}"
    made, total = S.generate_subscription_invoices(db, period, None)
    db.flush()
    mailed = 0
    for inv in db.scalars(select(SaasInvoice).where(SaasInvoice.kind == "subscription", SaasInvoice.status == "issued", SaasInvoice.issued_at >= at - timedelta(days=2))):
        if not claim(db, f"invmail:{inv.id}", at):
            continue
        org = db.get(Organization, inv.org_id)
        sub = db.scalar(select(Subscription).where(Subscription.org_id == inv.org_id).order_by(Subscription.id.desc()))
        plan = db.get(Plan, sub.plan_key) if sub else None
        if org:
            mailed += mail_org_admins(db, org, "invoice_issued", {"plan": plan.name if plan else "", "link": f"{APP_URL}/app/credits"}, at) > 0
    if made:
        audit(db, action="saas.invoices.auto", entity="period", entity_id=period, meta={"created": made, "total": total})
    return {"period": period, "created": made, "total": total, "emailed": mailed}


# ------------------------------------------------------------------ 8. trial ending emails
@register("trial_ending", "Trial ending emails at 7, 3 and 1 days", Schedule(hour=8))
def trial_ending(db: Session, at: datetime) -> dict:
    today = local_date(at)
    sent = 0
    for sub in db.scalars(select(Subscription).where(Subscription.status == "trial", Subscription.trial_ends.is_not(None))):
        left = (local_date(sub.trial_ends) - today).days
        if left < 0 or left > 7:
            continue
        bucket = min(n for n in (1, 3, 7) if n >= left)        # a missed day still gets the next smaller notice, once
        org = _live_org(db, sub.org_id)
        if not org or not claim(db, f"trial:{sub.id}:{bucket}:{local_date(sub.trial_ends)}", at):
            continue
        plan = db.get(Plan, sub.plan_key)
        mail_org_admins(db, org, f"trial_{bucket}", {"plan": plan.name if plan else "", "trial_days_left": left, "link": f"{APP_URL}/app/credits"}, at)
        sent += 1
    return {"sent": sent}


# ------------------------------------------------------------------ 9. plan-included monthly credits
@register("credit_grants", "Plan-included SMS and email credits for the month", Schedule(hour=0, minute=45))
def credit_grants(db: Session, at: datetime) -> dict:
    from ..routers import saas as S
    period = f"{local_date(at):%Y-%m}"
    n = 0
    for sub in db.scalars(select(Subscription).where(Subscription.status.in_(("active", "past_due")))):
        plan = db.get(Plan, sub.plan_key)
        if plan and sub.band in plan.monthly and S.grant_allowance(db, sub, plan, period, None):
            n += 1
    return {"period": period, "granted": n}


# ------------------------------------------------------------------ 10. dunning
DUNNING_STEPS = (1, 7, 14, 30)


@register("saas_dunning", "Overdue FlatWise invoices: past-due status, reminder emails, escalation", Schedule(hour=10))
def saas_dunning(db: Session, at: datetime) -> dict:
    at = aware(at)
    mailed = flagged = past_due = 0
    for inv in db.scalars(select(SaasInvoice).where(SaasInvoice.status == "issued", SaasInvoice.due_at < at)):
        over = (at - aware(inv.due_at)).days + 1          # day 1 = the first day after the due date
        step = max((s for s in DUNNING_STEPS if s <= over), default=0)
        org = _live_org(db, inv.org_id)
        if not step or not org:
            continue
        sub = db.scalar(select(Subscription).where(Subscription.org_id == inv.org_id).order_by(Subscription.id.desc()))
        if sub and sub.status == "active" and inv.kind in ("subscription", "setup"):
            sub.status = "past_due"
            past_due += 1
        if not claim(db, f"dun:{inv.id}:{step}", at):
            continue
        if step >= 30:       # never suspends by itself: a person decides
            alert(db, f"dunning30:{inv.id}", "dunning", f"{org.name}: invoice {inv.number} is {over} days overdue. Consider suspending.", "error", {"invoice": inv.number, "days": over}, org_id=org.id, at=at)
            flagged += 1
        plan = db.get(Plan, sub.plan_key) if sub else None
        mailed += mail_org_admins(db, org, "invoice_overdue", {"plan": plan.name if plan else inv.kind, "link": f"{APP_URL}/app/credits"}, at) > 0
    return {"emailed": mailed, "escalated": flagged, "marked_past_due": past_due}


# ------------------------------------------------------------------ 11. cleanup
@register("cleanup", "Delete expired locks, old job history, expired OTP hashes and old outbox rows", Schedule(hour=3))
def cleanup(db: Session, at: datetime) -> dict:
    at = aware(at)
    d = lambda days: at - timedelta(days=days)   # noqa: E731
    out = {
        "locks": db.execute(delete(JobLock).where(JobLock.expires_at < d(1))).rowcount,
        "job_runs": db.execute(delete(JobRun).where(JobRun.started_at < d(_int("JOBS_RUN_RETENTION_DAYS", 90)), JobRun.status != "running")).rowcount,
        "job_marks": db.execute(delete(JobMark).where(JobMark.at < d(400))).rowcount,
        "cash_codes": db.execute(update(CashEntry).where(CashEntry.code_hash != "", CashEntry.code_expires < d(1)).values(code_hash="")).rowcount,
        "resolved_alerts": db.execute(delete(SystemAlert).where(SystemAlert.resolved_at.is_not(None), SystemAlert.resolved_at < d(365))).rowcount,
    }
    try:      # sign-in tables belong to the security module (P2); skip quietly if a deployment lacks them
        from ..models.security import AuthSession, AuthToken, RateLimit
        out["auth_tokens"] = db.execute(delete(AuthToken).where(or_(AuthToken.expires_at < d(7), AuthToken.used_at < d(7)))).rowcount
        out["auth_sessions"] = db.execute(delete(AuthSession).where(or_(AuthSession.expires_at < d(30), AuthSession.revoked_at < d(30)))).rowcount
        out["rate_limits"] = db.execute(delete(RateLimit).where(RateLimit.updated_at < d(2), or_(RateLimit.locked_until.is_(None), RateLimit.locked_until < at))).rowcount
    except ImportError:
        pass
    plain = d(_int("OUTBOX_RETENTION_DAYS", 180))
    camp = d(_int("OUTBOX_CAMPAIGN_RETENTION_DAYS", 730))
    out["outbox"] = db.execute(delete(MailOutbox).where(MailOutbox.status != "queued", or_(
        and_(MailOutbox.created_at < plain, or_(MailOutbox.campaign_id.is_(None), MailOutbox.is_test)), MailOutbox.created_at < camp))).rowcount
    return out


# ------------------------------------------------------------------ 11b. retention purge (settings live in the SaaS console)
@register("retention_purge", "Purge old visitor logs, outbox rows and former-resident data using the saved retention settings", Schedule(hour=4))
def retention_purge(db: Session, at: datetime) -> dict:
    from ..services import retention
    res = retention.run_purge(db, dry_run=False, at=at)
    return {k: v for k, v in res.items() if k in ("visitors", "outbox", "former_residents")}


# ------------------------------------------------------------------ 12. integrity check
def integrity_problems(db: Session, property_id: int | None = None) -> list[dict]:
    """Ledger entries that do not balance, invoices whose paid total differs from verified payments, gateway sessions without a verified payment."""
    out: list[dict] = []
    jq = (select(Journal.id, Journal.property_id, func.coalesce(func.sum(JournalLine.debit), 0), func.coalesce(func.sum(JournalLine.credit), 0))
          .join(JournalLine, JournalLine.journal_id == Journal.id, isouter=True).group_by(Journal.id, Journal.property_id))
    if property_id:
        jq = jq.where(Journal.property_id == property_id)
    for jid, pid, d, c in db.execute(jq):
        if int(d) != int(c):
            out.append({"kind": "journal_unbalanced", "property_id": pid, "journal_id": jid, "debit": int(d), "credit": int(c)})
    totals = select(Journal.property_id, func.sum(JournalLine.debit), func.sum(JournalLine.credit)).join(JournalLine, JournalLine.journal_id == Journal.id).group_by(Journal.property_id)
    if property_id:
        totals = totals.where(Journal.property_id == property_id)
    for pid, d, c in db.execute(totals):
        if int(d or 0) != int(c or 0):
            out.append({"kind": "ledger_unbalanced", "property_id": pid, "debit": int(d or 0), "credit": int(c or 0)})
    verified = (select(Payment.invoice_id.label("iid"), func.sum(Payment.amount).label("s")).where(Payment.status == "verified").group_by(Payment.invoice_id).subquery())
    iq = select(Invoice.id, Invoice.property_id, Invoice.paid, func.coalesce(verified.c.s, 0)).outerjoin(verified, verified.c.iid == Invoice.id).where(Invoice.status != "void")
    if property_id:
        iq = iq.where(Invoice.property_id == property_id)
    for iid, pid, paid, s in db.execute(iq):
        if int(paid) != int(s):
            out.append({"kind": "invoice_paid_mismatch", "property_id": pid, "invoice_id": iid, "paid": int(paid), "verified_payments": int(s)})
    gq = select(GatewaySession.id, GatewaySession.property_id, GatewaySession.amount, Payment.status, Payment.amount).join(Payment, Payment.id == GatewaySession.payment_id, isouter=True).where(GatewaySession.status == "paid")
    if property_id:
        gq = gq.where(GatewaySession.property_id == property_id)
    for sid, pid, amt, pst, pamt in db.execute(gq):
        if pst != "verified" or pamt != amt:
            out.append({"kind": "gateway_paid_without_payment", "property_id": pid, "session_id": sid, "amount": amt, "payment_status": pst})
    return out


@register("integrity_check", "Nightly check: ledger balanced, invoice paid totals equal verified payments", Schedule(hour=3, minute=30))
def integrity_check(db: Session, at: datetime) -> dict:
    problems = integrity_problems(db)
    if problems:
        alert(db, f"integrity:{local_date(at)}", "integrity", f"Integrity check found {len(problems)} problem(s)", "error", {"problems": problems[:50], "total": len(problems)}, at=at)
        return {"problems": len(problems), "sample": problems[:10], "warn": True}
    return {"problems": 0}


# ------------------------------------------------------------------ 13. gateway reconciliation
@register("gateway_reconcile", "Re-query yesterday's stuck online payments at the provider", Schedule(hour=2))
def gateway_reconcile(db: Session, at: datetime) -> dict:
    from ..routers import gateway as G
    local = aware(at).astimezone(DHAKA)
    start = (local - timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0).astimezone(timezone.utc)
    end = local.replace(hour=0, minute=0, second=0, microsecond=0).astimezone(timezone.utc)
    stats = {"checked": 0, "recovered": 0, "expired": 0, "flagged": 0, "errors": 0}
    rows = db.scalars(select(GatewaySession).where(GatewaySession.created_at >= start, GatewaySession.created_at < end, GatewaySession.status.in_(("created", "failed"))).order_by(GatewaySession.id)).all()
    for s in rows:
        stats["checked"] += 1
        prov = gw.provider(s.provider)
        if not prov.live:
            if s.status == "created" and aware(s.expires_at) < at:
                s.status, s.completed_at = "expired", at
                stats["expired"] += 1
            continue
        try:
            res = prov.query(s)
        except Exception as e:      # provider down: try again tomorrow, tell a person if it keeps happening
            stats["errors"] += 1
            alert(db, f"reconcile-err:{s.id}:{local_date(at)}", "payment_stuck", f"Could not query {s.provider} for session {s.id}: {type(e).__name__}", "warn", {"session": s.id}, property_id=s.property_id, at=at)
            continue
        if res["status"] == "paid":
            if res["amount"] != s.charged:
                alert(db, f"reconcile-amt:{s.id}", "payment_stuck", f"{s.provider} says paid {res['amount']} but the checkout was {s.charged} (session {s.id})", "error", {"session": s.id, "trx": res.get("trx_id")}, property_id=s.property_id, at=at)
                stats["flagged"] += 1
                continue
            try:
                G.settle_paid(db, s, res["trx_id"], res["amount"], confirmed=True, source="reconcile")
                stats["recovered"] += 1
            except HTTPException:
                db.rollback()
                alert(db, f"reconcile-cant:{s.id}", "payment_stuck", f"{s.provider} took the money but the invoice would not accept it (session {s.id}): refund or fix by hand", "error", {"session": s.id, "trx": res.get("trx_id")}, property_id=s.property_id, at=at)
                stats["flagged"] += 1
        elif res["status"] in ("failed", "cancelled"):
            if s.status == "created":
                s.status, s.completed_at = "failed", at
        elif s.status == "created" and aware(s.expires_at) < at:
            s.status, s.completed_at = "expired", at
            stats["expired"] += 1
    if stats["flagged"] or stats["errors"]:
        stats["warn"] = True
    return stats


# ------------------------------------------------------------------ 14. SMS provider balance
@register("sms_provider_balance", "Check the SMS provider's own balance (BulkSMSBD) and alert when low", Schedule(every_minutes=360))
def sms_provider_balance(db: Session, at: datetime) -> dict:
    from ..services import sms
    prov = sms.get_provider()
    if prov.simulates:
        return {"provider": prov.name, "skipped": "sandbox provider"}
    try:
        bal = prov.balance()
    except Exception as e:
        alert(db, f"smsbal-err:{local_date(at)}", "provider_balance", f"Could not read the {prov.name} balance: {str(e)[:150]}", "warn", at=at)
        return {"provider": prov.name, "error": type(e).__name__, "warn": True}
    if bal is None:
        return {"provider": prov.name, "balance": None}
    low = float(os.getenv("SMS_PROVIDER_LOW_BALANCE", "500"))
    out = {"provider": prov.name, "balance": bal, "threshold": low}
    if bal < low:
        alert(db, f"smsbal-low:{prov.name}:{local_date(at)}", "provider_balance", f"{prov.name} balance is {bal}, below {low}. Top up before customers' reminders fail.", "error", {"balance": bal}, at=at)
        out["warn"] = True
    return out
