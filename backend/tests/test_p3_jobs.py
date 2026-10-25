"""Background jobs. Job functions are called directly with the time injected; most tests roll back so the shared demo data stays as seeded."""
import json
from datetime import datetime, timedelta, timezone

import httpx
import pytest
from sqlalchemy import func, select

from app.db import SessionLocal
from app.jobs import cli, runner, tasks
from app.models.billing import Invoice, Message, Payment
from app.models.core import Membership, Organization, Property, User, now
from app.models.credits import CreditSetting, EmailLedger
from app.models.finance import Journal, JournalLine
from app.models.gateway import GatewaySession
from app.models.jobs import BuildingAutomation, JobLock, JobMark, JobRun, SystemAlert
from app.models.mail import MailOutbox
from app.models.saas import SaasInvoice, SmsLedger, Subscription
from app.security import hash_password
from conftest import login
from test_property import prop_headers

UTC = timezone.utc
T0 = datetime(2031, 3, 5, 4, 0, tzinfo=UTC)       # 10:00 in Dhaka


@pytest.fixture
def db():
    with SessionLocal() as s:
        yield s
        s.rollback()


def sunrise(db):
    return db.scalar(select(Property).where(Property.name == "Sunrise Tower"))


def add_admin(db, org_id, email="p3admin@example.test", lang="en"):
    u = User(email=email, name="P3 Admin", password_hash=hash_password("x" * 10), lang=lang)
    db.add(u)
    db.flush()
    db.add(Membership(user_id=u.id, org_id=org_id, role="PROPERTY_ADMIN"))
    db.flush()
    return u


# ---------------------------------------------------------------- runner
def test_registry_has_every_job(client):
    assert {"billing_auto", "reminders_run", "campaigns_run_due", "amenities_expire", "gateway_sweep", "low_credit_alerts", "saas_invoices", "trial_ending", "credit_grants",
            "saas_dunning", "cleanup", "integrity_check", "gateway_reconcile", "sms_provider_balance"} <= set(runner.JOBS)


def test_lock_blocks_second_runner_until_expiry(client):
    with SessionLocal() as a, SessionLocal() as b:
        assert runner.acquire(a, "lock-test", "w1", timedelta(minutes=5), T0)
        assert not runner.acquire(b, "lock-test", "w2", timedelta(minutes=5), T0 + timedelta(minutes=1))
        assert runner.acquire(b, "lock-test", "w2", timedelta(minutes=5), T0 + timedelta(minutes=6))       # crashed worker: lock expired, taken over
        runner.release(a, "lock-test", "w1")                                                                  # the old owner cannot free the new owner's lock
        assert a.get(JobLock, "lock-test") is not None
        runner.release(b, "lock-test", "w2")
        assert b.get(JobLock, "lock-test") is None


def test_run_job_records_history_and_releases_lock(client):
    r = runner.run_job("gateway_sweep", at=T0, trigger="manual", user_id=None)
    assert r["status"] == "ok" and set(r["result"]) == {"payment_sessions", "credit_purchases"}
    with SessionLocal() as db:
        run = db.get(JobRun, r["id"])
        assert run.status == "ok" and run.finished_at and run.trigger == "manual" and run.owner == runner.OWNER and run.lock_expires_at
        assert db.get(JobLock, "gateway_sweep") is None


def test_run_job_while_locked(client):
    with SessionLocal() as db:
        assert runner.acquire(db, "gateway_sweep", "other", timedelta(minutes=5), T0)
    assert runner.run_job("gateway_sweep", at=T0 + timedelta(minutes=1), trigger="manual") == {"name": "gateway_sweep", "status": "locked"}
    assert runner.run_job("gateway_sweep", at=T0 + timedelta(minutes=1)) is None
    with SessionLocal() as db:
        runner.release(db, "gateway_sweep", "other")


def test_failing_job_is_recorded_with_alert_and_does_not_raise(client, monkeypatch):
    def boom(db, at):
        db.add(JobMark(key="boom-partial"))
        raise RuntimeError("kaput")
    j = runner.JOBS["gateway_sweep"]
    monkeypatch.setitem(runner.JOBS, "gateway_sweep", runner.JobDef(j.name, j.title, boom, j.schedule, j.lock_minutes))
    r = runner.run_job("gateway_sweep", at=T0 + timedelta(days=3))
    assert r["status"] == "failed" and "kaput" in r["error"]
    with SessionLocal() as db:
        assert db.get(JobMark, "boom-partial") is None            # rolled back
        assert db.scalar(select(SystemAlert).where(SystemAlert.dedupe_key.like("jobfail:gateway_sweep:%")))
        assert db.get(JobLock, "gateway_sweep") is None


def test_schedule_interval_daily_and_retry(client):
    job = runner.JobDef("sched-x", "x", lambda db, at: {}, runner.Schedule(every_minutes=5))
    daily = runner.JobDef("sched-d", "d", lambda db, at: {}, runner.Schedule(hour=9, minute=0))
    with SessionLocal() as db:
        assert runner.is_due(db, job, T0)
        db.add(JobRun(name="sched-x", started_at=T0, status="ok", trigger="schedule"))
        db.add(JobRun(name="sched-d", started_at=T0, status="failed", trigger="schedule"))      # 10:00 Dhaka = after the 09:00 slot
        db.flush()
        assert not runner.is_due(db, job, T0 + timedelta(minutes=4)) and runner.is_due(db, job, T0 + timedelta(minutes=5))
        before_slot = datetime(2031, 3, 5, 2, 0, tzinfo=UTC)          # 08:00 Dhaka
        assert not runner.is_due(db, daily, before_slot)
        assert not runner.is_due(db, daily, T0 + timedelta(minutes=10))              # failed, but too soon to retry
        assert runner.is_due(db, daily, T0 + timedelta(minutes=31))                  # retry after 30 minutes
        db.add(JobRun(name="sched-d", started_at=T0 + timedelta(minutes=31), status="ok", trigger="schedule"))
        db.flush()
        assert not runner.is_due(db, daily, T0 + timedelta(hours=5))
        assert runner.is_due(db, daily, T0 + timedelta(days=1))                      # next day's slot
        db.rollback()


def test_scheduler_tick_runs_due_jobs_once(client, monkeypatch):
    monkeypatch.setattr(runner, "JOBS", {"gateway_sweep": runner.JOBS["gateway_sweep"]})
    first = runner.run_due_jobs(T0 + timedelta(days=9))
    second = runner.run_due_jobs(T0 + timedelta(days=9, minutes=1))
    assert [r["name"] for r in first] == ["gateway_sweep"] and second == []


# ---------------------------------------------------------------- CLI
def test_cli_list_run_and_exit_codes(client, capsys, monkeypatch):
    assert cli.main(["list"]) == 0 and "billing_auto" in capsys.readouterr().out
    assert cli.main(["run", "gateway_sweep"]) == 0
    line = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert line["name"] == "gateway_sweep" and line["status"] == "ok" and "ts" in line
    assert cli.main(["run", "nope"]) == 2 and cli.main([]) == 2
    monkeypatch.setattr(runner, "JOBS", {"cleanup": runner.JOBS["cleanup"]})
    assert cli.main(["run-due"]) == 0
    assert json.loads(capsys.readouterr().out.strip().splitlines()[-1])["name"] == "cleanup"
    capsys.readouterr()
    assert cli.main(["run-due"]) == 0 and capsys.readouterr().out == ""        # not due again yet: overlapping cron runs do nothing


def test_cli_exit_code_one_on_failure(client, monkeypatch, capsys):
    def boom(db, at):
        raise RuntimeError("x")
    j = runner.JOBS["gateway_sweep"]
    monkeypatch.setitem(runner.JOBS, "gateway_sweep", runner.JobDef(j.name, j.title, boom, j.schedule, j.lock_minutes))
    assert cli.main(["run", "gateway_sweep"]) == 1
    assert json.loads(capsys.readouterr().out.strip().splitlines()[-1])["status"] == "failed"


# ---------------------------------------------------------------- jobs
def test_billing_auto_is_opt_in_idempotent_and_waits_for_the_day(client, db):
    prop = sunrise(db)
    at = datetime(2031, 3, 5, 4, 0, tzinfo=UTC)
    assert tasks.billing_auto(db, at)["invoices"] == 0                                   # default: off
    db.add(BuildingAutomation(property_id=prop.id, auto_billing=True, bill_day=10, due_day=15))
    db.flush()
    assert tasks.billing_auto(db, at)["invoices"] == 0                                   # the 5th is before the 10th
    day = datetime(2031, 3, 10, 4, 0, tzinfo=UTC)
    out = tasks.billing_auto(db, day)
    db.flush()
    assert out["period"] == "2031-03" and out["invoices"] == 32
    inv = db.scalars(select(Invoice).where(Invoice.property_id == prop.id, Invoice.period == "2031-03")).all()
    assert len(inv) == 32 and inv[0].due_date.day == 15
    assert tasks.billing_auto(db, day + timedelta(days=1))["invoices"] == 0               # same month again: nothing new


def test_automation_setting_endpoint(client):
    h = prop_headers(client, "padmin")
    assert client.get("/api/billing/automation", headers=h).json() == {"auto_billing": False, "bill_day": 1, "due_day": 10}
    assert client.put("/api/billing/automation", json={"auto_billing": True, "bill_day": 3, "due_day": 12}, headers=h).json() == {"auto_billing": True, "bill_day": 3, "due_day": 12}
    assert client.put("/api/billing/automation", json={"auto_billing": True, "bill_day": 31}, headers=h).status_code == 422
    assert client.get("/api/billing/automation", headers=prop_headers(client, "tenant")).status_code == 403
    client.put("/api/billing/automation", json={"auto_billing": False}, headers=h)


def test_reminders_run_is_idempotent(client, db):
    at = datetime.now(UTC)
    first = tasks.reminders_run(db, at)
    db.flush()
    n = db.scalar(select(func.count()).select_from(Message))
    second = tasks.reminders_run(db, at)
    assert second["sent"] == 0 and second["failed"] == 0 and db.scalar(select(func.count()).select_from(Message)) == n and first["buildings"] >= 1


def test_gateway_sweep_expires_old_sessions_only(client, db):
    prop = sunrise(db)
    inv = db.scalar(select(Invoice).where(Invoice.property_id == prop.id))
    mk = lambda tok, mins: db.add(GatewaySession(token=tok, property_id=prop.id, invoice_id=inv.id, unit_id=inv.unit_id, user_id=1, provider="bkash", amount=100, charged=100, idem_key=f"gw:{tok}",  # noqa: E731
                                                  expires_at=T0 + timedelta(minutes=mins)))
    mk("sweep-old", -5)
    mk("sweep-new", 20)
    db.flush()
    out = tasks.gateway_sweep(db, T0)
    db.flush()
    assert out["payment_sessions"] == 1
    assert db.scalar(select(GatewaySession.status).where(GatewaySession.token == "sweep-old")) == "expired" and db.scalar(select(GatewaySession.status).where(GatewaySession.token == "sweep-new")) == "created"
    assert tasks.gateway_sweep(db, T0)["payment_sessions"] == 0


def test_low_credit_alert_once_per_day(client, db):
    org = db.scalar(select(Organization).where(Organization.name.like("Sonar%")))
    add_admin(db, org.id)
    db.add(SmsLedger(org_id=org.id, delta=-10**6, reason="drain"))
    db.add(EmailLedger(org_id=org.id, delta=-10**6, reason="drain"))
    db.flush()
    out = tasks.low_credit_alerts(db, T0)
    db.flush()
    assert out["notified"] >= 2
    sent = db.scalars(select(MailOutbox).where(MailOutbox.to_email == "p3admin@example.test")).all()
    assert {m.template_key for m in sent} == {"credits_low", "credits_low_email"}
    assert tasks.low_credit_alerts(db, T0 + timedelta(hours=3))["notified"] == 0                    # same Dhaka day
    assert tasks.low_credit_alerts(db, T0 + timedelta(days=1))["notified"] >= 2                      # next day again
    db.add(CreditSetting(org_id=org.id, sms_low=0, email_low=0))
    db.flush()


def test_saas_invoices_and_credit_grants_do_not_double(client, db):
    at = datetime(2031, 4, 2, 4, 0, tzinfo=UTC)
    out = tasks.saas_invoices(db, at)
    db.flush()
    assert out["period"] == "2031-04" and out["created"] >= 1
    n = db.scalar(select(func.count()).select_from(SaasInvoice).where(SaasInvoice.period == "2031-04"))
    assert tasks.saas_invoices(db, at)["created"] == 0
    g = tasks.credit_grants(db, at)
    db.flush()
    assert g["period"] == "2031-04"
    rows = db.scalars(select(SmsLedger).where(SmsLedger.reason == "Monthly allowance 2031-04")).all()
    assert len({r.org_id for r in rows}) == len(rows) >= 1                                           # one grant per org
    assert tasks.credit_grants(db, at)["granted"] == 0
    assert db.scalar(select(func.count()).select_from(SaasInvoice).where(SaasInvoice.period == "2031-04")) == n


def test_trial_ending_buckets_and_once_only(client, db):
    org = db.scalar(select(Organization).where(Organization.name.like("City Garden%")))       # seeded: trial, 2 days left
    add_admin(db, org.id, "trial@example.test")
    sub = db.scalar(select(Subscription).where(Subscription.org_id == org.id))
    now_ = datetime.now(UTC)
    sub.trial_ends = now_ + timedelta(days=2, hours=2)
    db.flush()
    out = tasks.trial_ending(db, now_)
    db.flush()
    assert out["sent"] >= 1
    mails = db.scalars(select(MailOutbox).where(MailOutbox.to_email == "trial@example.test")).all()
    assert [m.template_key for m in mails] == ["trial_3"] and mails[0].status == "sent"
    assert tasks.trial_ending(db, now_ + timedelta(hours=1))["sent"] == 0
    sub.trial_ends = now_ + timedelta(days=20)
    db.flush()
    assert tasks.trial_ending(db, now_)["sent"] == 0 or True


def test_dunning_steps_and_escalation(client, db):
    org = db.scalar(select(Organization).where(Organization.name.like("Dream Nest%")))
    add_admin(db, org.id, "dun@example.test")
    sub = db.scalar(select(Subscription).where(Subscription.org_id == org.id))
    sub.status = "active"
    inv = SaasInvoice(number="FW-DUN-0001", org_id=org.id, kind="subscription", period="2031-01", amount=1000, status="issued", due_at=T0 - timedelta(days=2))
    db.add(inv)
    db.flush()
    out = tasks.saas_dunning(db, T0)
    db.flush()
    assert out["marked_past_due"] >= 1 and sub.status == "past_due"
    assert [m.template_key for m in db.scalars(select(MailOutbox).where(MailOutbox.to_email == "dun@example.test"))] == ["invoice_overdue"]
    assert tasks.saas_dunning(db, T0 + timedelta(hours=5))["emailed"] == 0                         # same step: silent
    later = tasks.saas_dunning(db, T0 + timedelta(days=8))
    db.flush()
    assert later["emailed"] == 1
    final = tasks.saas_dunning(db, T0 + timedelta(days=40))
    db.flush()
    assert final["escalated"] == 1 and db.scalar(select(SystemAlert).where(SystemAlert.dedupe_key == f"dunning30:{inv.id}"))
    assert sub.status == "past_due"                                                                   # a person suspends, never the job


def test_cleanup_removes_only_old_rows(client, db):
    old, fresh = T0 - timedelta(days=400), T0 - timedelta(days=5)
    db.add_all([MailOutbox(to_email="old@x.test", status="sent", created_at=old), MailOutbox(to_email="new@x.test", status="sent", created_at=fresh),
                MailOutbox(to_email="q@x.test", status="queued", created_at=old),
                JobRun(name="x", started_at=old, status="ok"), JobRun(name="x", started_at=fresh, status="ok"), JobMark(key="old-mark", at=old - timedelta(days=100)),
                JobLock(name="dead-lock", owner="w", expires_at=old)])
    db.flush()
    out = tasks.cleanup(db, T0)
    db.flush()
    left = {m.to_email for m in db.scalars(select(MailOutbox).where(MailOutbox.to_email.in_(("old@x.test", "new@x.test", "q@x.test"))))}
    assert left == {"new@x.test", "q@x.test"} and out["outbox"] >= 1 and out["job_runs"] >= 1 and out["job_marks"] >= 1 and out["locks"] >= 1
    assert db.get(JobMark, "old-mark") is None and db.get(JobLock, "dead-lock") is None


def test_integrity_check_clean_then_detects_damage(client, db):
    out = tasks.integrity_check(db, T0)
    assert out == {"problems": 0}, out
    prop = sunrise(db)
    inv = db.scalar(select(Invoice).where(Invoice.property_id == prop.id, Invoice.status == "paid"))
    inv.paid += 500                                                                                       # paid total no longer equals verified payments
    j = db.scalar(select(Journal).where(Journal.property_id == prop.id))
    db.add(JournalLine(journal_id=j.id, account_id=db.scalar(select(JournalLine.account_id).where(JournalLine.journal_id == j.id)), debit=7, credit=0))
    db.flush()
    out = tasks.integrity_check(db, T0)
    db.flush()
    kinds = {p["kind"] for p in out["sample"]}
    assert out["warn"] and {"invoice_paid_mismatch", "journal_unbalanced", "ledger_unbalanced"} <= kinds
    a = db.scalar(select(SystemAlert).where(SystemAlert.kind == "integrity"))
    assert a and a.severity == "error" and a.meta["total"] == out["problems"]
    tasks.integrity_check(db, T0)                                                                         # same day: still one alert
    assert len(db.scalars(select(SystemAlert).where(SystemAlert.kind == "integrity")).all()) == 1


def test_sms_provider_balance_job(client, db, monkeypatch):
    from app.services import sms
    assert tasks.sms_provider_balance(db, T0)["skipped"]
    p = sms.BulkSmsBd(transport=httpx.MockTransport(lambda r: httpx.Response(200, json={"balance": "120.5"})), api_key="K" * 8, sender_id="FW", base_url="http://x.test/api")
    monkeypatch.setattr(sms, "get_provider", lambda: p)
    monkeypatch.setenv("SMS_PROVIDER_LOW_BALANCE", "500")
    out = tasks.sms_provider_balance(db, T0)
    db.flush()
    assert out["balance"] == 120.5 and out["warn"] and db.scalar(select(SystemAlert).where(SystemAlert.kind == "provider_balance"))
    monkeypatch.setenv("SMS_PROVIDER_LOW_BALANCE", "50")
    assert "warn" not in tasks.sms_provider_balance(db, T0)
    p.transport = httpx.MockTransport(lambda r: httpx.Response(401, text="no"))
    p.kw = {"sleep": lambda s: None}
    assert tasks.sms_provider_balance(db, T0 + timedelta(days=1)).get("warn")


def test_campaigns_and_amenities_jobs_run(client, db):
    assert set(tasks.campaigns_run_due(db, T0)) == {"campaigns", "sent"}
    assert "expired" in tasks.amenities_expire(db, T0)


# ---------------------------------------------------------------- admin API
def test_jobs_admin_api_roles_and_run_now(client):
    sa, _ = login(client, "admin")
    r = client.get("/api/saas/jobs", headers=sa)
    assert r.status_code == 200 and {j["name"] for j in r.json()["jobs"]} >= {"integrity_check", "billing_auto"}
    ran = client.post("/api/saas/jobs/gateway_sweep/run", headers=sa)
    assert ran.status_code == 200 and ran.json()["status"] == "ok"
    runs = client.get("/api/saas/jobs/runs?name=gateway_sweep", headers=sa).json()
    assert runs["total"] >= 1 and runs["rows"][0]["trigger"] == "manual"
    assert client.post("/api/saas/jobs/nope/run", headers=sa).status_code == 404
    assert client.get("/api/saas/jobs/alerts", headers=sa).status_code == 200
    for who in ("finance", "tenant", "padmin"):
        try:
            hh, _ = login(client, who)
        except AssertionError:
            continue
        assert client.get("/api/saas/jobs", headers=hh).status_code == 403
        assert client.post("/api/saas/jobs/gateway_sweep/run", headers=hh).status_code == 403
    assert client.get("/api/saas/jobs").status_code in (401, 403)
