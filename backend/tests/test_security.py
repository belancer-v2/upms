"""P2 security: sign-in throttling, password policy and flows, sessions and refresh rotation, headers, audit chain, abuse controls, uploads."""
import itertools
import re
import time
from datetime import timedelta

import pytest
from sqlalchemy import select, text

from app import config
from app.db import SessionLocal
from app.models.billing import Message
from app.models.core import AuditLog, User, now
from app.models.mail import MailOutbox
from app.models.security import AuthSession, AuthToken
from app.services import antispam, authmail, ratelimit
from conftest import login

_n = itertools.count(1)
GOOD = "Sturdy-Pass#42"


def signup(client, **over):
    """A fresh signup: own organisation, building and PROPERTY_ADMIN."""
    n = next(_n)
    body = {"name": "Sec Tester", "email": f"sec{n}@x.test", "password": "longpass1", "building": f"Secure Court {n}", "flats": 12, "plan": "standard", **over}
    r = client.post("/api/public/signup", json=body)
    assert r.status_code == 201, r.text
    return body, r.json()


def bearer(tok):
    return {"Authorization": f"Bearer {tok}"}


def sign_in(client, email, pw):
    return client.post("/api/auth/login", json={"email": email, "password": pw})


# ------------------------------------------------------------------ login throttling
def test_lockout_per_account_and_address_is_neutral_and_audited(client):
    bad = [sign_in(client, "guard@flatwise.demo", "wrong-pass") for _ in range(5)]
    assert [r.status_code for r in bad] == [401] * 5
    locked = sign_in(client, "guard@flatwise.demo", "demo1234")           # even the right password is refused while locked
    assert locked.status_code == 429 and int(locked.headers["Retry-After"]) > 0
    with SessionLocal() as db:
        assert db.scalar(select(AuditLog.id).where(AuditLog.action == "auth.lockout")) is not None
        assert db.scalar(select(AuditLog.id).where(AuditLog.action == "auth.login_failed")) is not None


def test_unknown_email_gets_the_same_answers_as_a_wrong_password(client):
    known = [sign_in(client, "member@flatwise.demo", "nope-nope") for _ in range(5)]
    unknown = [sign_in(client, "nobody-here@flatwise.demo", "nope-nope") for _ in range(5)]
    assert {r.json()["detail"] for r in known} == {r.json()["detail"] for r in unknown} == {"Wrong email or password"}
    a, b = sign_in(client, "member@flatwise.demo", "x"), sign_in(client, "nobody-here@flatwise.demo", "x")
    assert a.status_code == b.status_code == 429 and a.json() == b.json()                 # locked: same words for a real and an invented account


def test_unknown_email_still_pays_for_a_bcrypt_check(client, monkeypatch):
    import app.security as sec
    calls = []
    real = sec.bcrypt.checkpw
    monkeypatch.setattr(sec.bcrypt, "checkpw", lambda a, b: (calls.append(1), real(a, b))[1])
    assert sign_in(client, "ghost@flatwise.demo", "whatever-1").status_code == 401
    assert len(calls) == 1


def test_address_lockout_after_many_failures_across_accounts(client):
    for i in range(20):
        assert sign_in(client, f"spray{i}@nowhere.test", "Password1").status_code in (401, 429)
    assert sign_in(client, "owner@flatwise.demo", "demo1234").status_code == 429


def test_success_clears_the_account_counters(client):
    for _ in range(3):
        sign_in(client, "auditor@flatwise.demo", "bad-bad-bad")
    assert sign_in(client, "auditor@flatwise.demo", "demo1234").status_code == 200
    for _ in range(4):
        assert sign_in(client, "auditor@flatwise.demo", "bad-bad-bad").status_code == 401   # counter restarted, not at 7


def test_lock_lengthens_progressively():
    k = "login:test:progressive"
    first = [ratelimit.fail(k, 2, 900, 30, 1800) for _ in range(2)][-1]
    second = ratelimit.fail(k, 2, 900, 30, 1800)
    third = ratelimit.fail(k, 2, 900, 30, 1800)
    assert 25 <= first <= 31 and 55 <= second <= 61 and 115 <= third <= 121


# ------------------------------------------------------------------ password policy, change, reset
def test_policy_rules():
    from app.services.passwords import check
    assert check("longpass1") is None and check(GOOD) is None
    assert check("short1") and check("password") and check("12345678") and check("abcdefgh") and check("aaaaaaaa") and check("demo1234")
    assert check("imran hossain", name="Imran Hossain") and check("rahim@x.test", email="rahim@x.test") and check("rahim1234", email="rahim1234@x.test")
    assert check("x" * 80 + "1A")          # longer than bcrypt reads


def test_signup_enforces_the_policy(client):
    r = client.post("/api/public/signup", json={"name": "Pol Icy", "email": "policy@x.test", "password": "password1", "building": "Policy Court", "flats": 5})
    assert r.status_code == 422 and "common" in r.json()["detail"]


def test_change_password_needs_current_password_and_signs_other_devices_out(client):
    body, d = signup(client)
    h1 = bearer(d["token"])
    second = sign_in(client, body["email"], body["password"]).json()
    h2 = bearer(second["token"])
    assert client.post("/api/auth/change-password", headers=h1, json={"current_password": "wrong-one-1", "new_password": GOOD}).status_code == 400
    assert client.post("/api/auth/change-password", headers=h1, json={"current_password": body["password"], "new_password": "password1"}).status_code == 422
    assert client.post("/api/auth/change-password", headers=h1, json={"current_password": body["password"], "new_password": body["password"]}).status_code == 422
    ok = client.post("/api/auth/change-password", headers=h1, json={"current_password": body["password"], "new_password": GOOD})
    assert ok.status_code == 200 and ok.json()["token"] and ok.json()["refresh_token"]
    assert client.get("/api/me", headers=h1).status_code == 401          # the old token of this device
    assert client.get("/api/me", headers=h2).status_code == 401          # the other device
    assert client.get("/api/me", headers=bearer(ok.json()["token"])).status_code == 200
    assert sign_in(client, body["email"], body["password"]).status_code == 401
    assert sign_in(client, body["email"], GOOD).status_code == 200


def tenant_with_login(client, h):
    """Adds a flat and a tenant with a login to a fresh building. Returns (email, temporary password, occupant id)."""
    n = next(_n)
    uid = client.post("/api/units", headers=h, json={"number": f"T-{n}", "floor": 1}).json()["id"]
    email = f"tenant{n}@x.test"
    r = client.post(f"/api/units/{uid}/occupants", headers=h, json={"kind": "tenant", "name": "Temp Tenant", "email": email, "create_login": True})
    assert r.status_code == 201, r.text
    return email, r.json()["temp_password"], r.json()["occupant_id"]


def _reset_link(client, ident):
    r = client.post("/api/auth/forgot-password", json={"identifier": ident})
    assert r.status_code == 200
    return r.json()


def test_reset_flow_by_email_is_single_use_and_neutral(client):
    body, _ = signup(client)
    out = _reset_link(client, body["email"])
    assert out["ok"] and "demo_link" in out
    token = out["demo_link"].split("#token=")[1]
    unknown = _reset_link(client, "nobody@x.test")
    assert unknown["message"] == out["message"] and "demo_link" not in unknown        # same words; the demo link exists only in DEMO mode
    # the token is stored only as a hash, and the recorded e-mail has no secret in it
    with SessionLocal() as db:
        assert db.scalar(select(AuthToken.id).where(AuthToken.token_hash == token)) is None
        mail = db.scalars(select(MailOutbox).where(MailOutbox.to_email == body["email"], MailOutbox.template_key == "password_reset")).all()[-1]
        assert token not in mail.html and token not in mail.text and "[removed]" in mail.html
    assert client.post("/api/auth/reset-password", json={"token": token, "new_password": "password1"}).status_code == 422     # policy; link not burned
    assert client.post("/api/auth/reset-password", json={"token": token, "new_password": GOOD}).status_code == 200
    assert client.post("/api/auth/reset-password", json={"token": token, "new_password": GOOD + "x"}).status_code == 400      # single use
    assert sign_in(client, body["email"], GOOD).status_code == 200 and sign_in(client, body["email"], body["password"]).status_code == 401


def test_reset_token_expires_and_new_request_voids_the_old_one(client):
    body, _ = signup(client)
    first = _reset_link(client, body["email"])["demo_link"].split("#token=")[1]
    second = _reset_link(client, body["email"])["demo_link"].split("#token=")[1]
    assert client.post("/api/auth/reset-password", json={"token": first, "new_password": GOOD}).status_code == 400
    with SessionLocal() as db:
        t = db.scalar(select(AuthToken).where(AuthToken.token_hash == authmail.hash_token(second)))
        t.expires_at = now() - timedelta(minutes=1)
        db.commit()
    assert client.post("/api/auth/reset-password", json={"token": second, "new_password": GOOD}).status_code == 400


def test_reset_by_phone_goes_through_sms_and_keeps_no_secret(client):
    body, d = signup(client, phone="01955123456")
    h = {"Authorization": f"Bearer {d['token']}", "X-Property-Id": str(d["properties"][0]["id"])}
    with SessionLocal() as db:                      # give the new building SMS credit so deliver() can send
        from app.models.saas import SmsLedger
        db.add(SmsLedger(org_id=d["properties"][0]["org_id"], delta=50, reason="test"))
        db.commit()
    out = _reset_link(client, "+880 1955-123456")
    assert "demo_link" in out
    with SessionLocal() as db:
        m = db.scalars(select(Message).where(Message.template == "password_reset", Message.to_phone == "01955123456")).all()[-1]
        assert m.status == "sent" and "[removed]" in m.body and out["demo_link"].split("#token=")[1] not in m.body
    assert h  # the header dict is valid for the new building


def test_forgot_password_is_rate_limited_per_account_and_address(client):
    body, _ = signup(client)
    links = [_reset_link(client, body["email"]).get("demo_link") for _ in range(5)]
    assert [bool(x) for x in links] == [True, True, True, False, False]            # 3 per hour per account, silently
    for i in range(10):
        r = client.post("/api/auth/forgot-password", json={"identifier": f"other{i}@x.test"})
    assert r.status_code == 429                                                       # 8 per hour per address


# ------------------------------------------------------------------ forced change on first login
def test_temporary_password_forces_a_change_before_anything_else(client):
    body, d = signup(client)
    h = {"Authorization": f"Bearer {d['token']}", "X-Property-Id": str(d["properties"][0]["id"])}
    email, temp, _occ = tenant_with_login(client, h)
    lg = sign_in(client, email, temp).json()
    assert lg["must_change_password"] is True and lg["user"]["must_change_password"] is True
    th = {**bearer(lg["token"]), "X-Property-Id": h["X-Property-Id"]}
    assert client.get("/api/me", headers=th).status_code == 200                       # the screen can still learn who you are
    blocked = client.get("/api/billing/invoices", headers=th)
    assert blocked.status_code == 403 and blocked.headers["X-Error-Code"] == "password_change_required"
    assert client.post("/api/me/lang", headers=th, json={"lang": "bn"}).status_code == 403
    assert client.post("/api/auth/change-password", headers=th, json={"current_password": temp, "new_password": GOOD}).status_code == 200
    again = sign_in(client, email, GOOD).json()
    assert again["must_change_password"] is False
    assert client.get("/api/billing/invoices", headers={**bearer(again["token"]), "X-Property-Id": h["X-Property-Id"]}).status_code == 200


# ------------------------------------------------------------------ sessions and refresh tokens
def test_login_response_is_compatible_and_sets_an_httponly_cookie(client):
    r = sign_in(client, "secretary@flatwise.demo", "demo1234")
    d = r.json()
    assert d["token"] and d["refresh_token"] and d["expires_in"] == config.ACCESS_TOKEN_MINUTES * 60 and d["user"]["email"] == "secretary@flatwise.demo"
    cookie = r.headers["set-cookie"]
    assert "fw_refresh=" in cookie and "HttpOnly" in cookie and "SameSite=lax" in cookie and "Path=/api/auth" in cookie
    assert d["refresh_token"] not in client.get("/api/me", headers=bearer(d["token"])).text   # never echoed back


def test_refresh_rotates_and_reuse_revokes_the_session(client):
    d = sign_in(client, "treasurer@flatwise.demo", "demo1234").json()
    client.cookies.clear()
    r1 = client.post("/api/auth/refresh", json={"refresh_token": d["refresh_token"]})
    assert r1.status_code == 200 and r1.json()["refresh_token"] != d["refresh_token"]
    assert client.get("/api/me", headers=bearer(r1.json()["token"])).status_code == 200
    # a second tab racing within the grace window gets an access token but is not punished
    race = client.post("/api/auth/refresh", json={"refresh_token": d["refresh_token"]})
    assert race.status_code == 200 and "refresh_token" not in race.json()
    # the stolen copy shown after the grace window kills the whole session
    with SessionLocal() as db:
        s = db.scalar(select(AuthSession).where(AuthSession.prev_hash == authmail.hash_token(d["refresh_token"])))
        s.rotated_at = now() - timedelta(minutes=5)
        db.commit()
    assert client.post("/api/auth/refresh", json={"refresh_token": d["refresh_token"]}).status_code == 401
    assert client.post("/api/auth/refresh", json={"refresh_token": r1.json()["refresh_token"]}).status_code == 401
    assert client.get("/api/me", headers=bearer(r1.json()["token"])).status_code == 401
    with SessionLocal() as db:
        assert db.scalar(select(AuditLog.id).where(AuditLog.action == "auth.refresh_reuse")) is not None


def test_refresh_cookie_needs_the_csrf_header_and_garbage_is_rejected(client):
    client.cookies.clear()
    sign_in(client, "caretaker@flatwise.demo", "demo1234")           # the cookie jar now holds fw_refresh
    assert client.post("/api/auth/refresh").status_code == 403       # cookie alone: no X-Requested-With
    ok = client.post("/api/auth/refresh", headers={"X-Requested-With": "fetch"})
    assert ok.status_code == 200 and ok.json()["token"]
    client.cookies.clear()
    assert client.post("/api/auth/refresh", json={"refresh_token": "not-a-token"}).status_code == 401
    assert client.post("/api/auth/refresh", headers={"X-Requested-With": "fetch"}).status_code == 401


def test_logout_really_revokes(client):
    d = sign_in(client, "ownerrep@flatwise.demo", "demo1234").json()
    h = bearer(d["token"])
    assert client.get("/api/me", headers=h).status_code == 200
    assert client.post("/api/auth/logout", headers=h).status_code == 200
    assert client.get("/api/me", headers=h).status_code == 401
    assert client.post("/api/auth/refresh", json={"refresh_token": d["refresh_token"]}).status_code == 401


def test_logout_works_with_only_the_refresh_token(client):
    d = sign_in(client, "owner2@flatwise.demo", "demo1234").json()
    assert client.post("/api/auth/logout", json={"refresh_token": d["refresh_token"]}).status_code == 200
    assert client.get("/api/me", headers=bearer(d["token"])).status_code == 401


def test_sessions_list_revoke_one_and_all(client):
    body, d1 = signup(client)
    d2 = sign_in(client, body["email"], body["password"]).json()
    d3 = sign_in(client, body["email"], body["password"]).json()
    h1 = bearer(d1["token"])
    rows = client.get("/api/me/sessions", headers=h1).json()
    assert len(rows) == 3 and sum(r["current"] for r in rows) == 1 and all(r["device"] for r in rows)
    other = next(r for r in rows if not r["current"])
    assert client.delete(f"/api/me/sessions/{other['id']}", headers=h1).status_code == 200
    assert client.delete(f"/api/me/sessions/{other['id']}", headers=h1).status_code == 404
    assert len(client.get("/api/me/sessions", headers=h1).json()) == 2
    # someone else's session id is a 404, not a 403
    stranger = sign_in(client, "member@flatwise.demo", "demo1234").json()
    sid = client.get("/api/me/sessions", headers=bearer(stranger["token"])).json()[0]["id"]
    assert client.delete(f"/api/me/sessions/{sid}", headers=h1).status_code == 404
    keep = client.post("/api/me/sessions/revoke-all", headers=h1, json={"keep_current": True})
    assert keep.status_code == 200 and client.get("/api/me", headers=h1).status_code == 200
    assert client.post("/api/me/sessions/revoke-all", headers=h1, json={}).status_code == 200
    assert client.get("/api/me", headers=h1).status_code == 401
    assert client.get("/api/me", headers=bearer(d2["token"])).status_code == 401 and client.get("/api/me", headers=bearer(d3["token"])).status_code == 401


def test_access_token_lifetime_and_forgery(client, monkeypatch):
    import app.security as sec
    d = sign_in(client, "president@flatwise.demo", "demo1234").json()
    assert client.get("/api/me", headers=bearer(d["token"] + "x")).status_code == 401
    assert client.get("/api/me", headers={"Authorization": "Basic abc"}).status_code == 401
    monkeypatch.setattr(config, "ACCESS_TOKEN_MINUTES", -1)
    expired = sec.make_access_token(1, 1, 0)
    assert client.get("/api/me", headers=bearer(expired)).status_code == 401
    import jwt
    forged = jwt.encode({"sub": "1", "sid": 1, "tv": 0, "typ": "access", "exp": time.time() + 999}, "dev-only-change-me-flatwise-secret-key-32b", algorithm="HS256")
    assert client.get("/api/me", headers=bearer(forged)).status_code == 401       # signed with SECRET_KEY itself, not the derived JWT key


def test_role_removal_signs_the_person_out(client):
    body, d = signup(client)
    h = {"Authorization": f"Bearer {d['token']}", "X-Property-Id": str(d["properties"][0]["id"])}
    email, temp, occ = tenant_with_login(client, h)
    th = bearer(sign_in(client, email, temp).json()["token"])
    assert client.get("/api/me", headers=th).status_code == 200
    assert client.post(f"/api/occupants/{occ}/move-out", headers=h).status_code == 200
    assert client.get("/api/me", headers=th).status_code == 401


def test_deactivated_saas_staff_loses_every_session(client):
    sup = login(client, "super")[0]
    r = client.post("/api/saas/staff", headers=sup, json={"name": "Temp Staff", "email": "tempstaff@x.test", "role": "SAAS_USER", "password": "Quite-Long#9"})
    assert r.status_code == 201
    tok = sign_in(client, "tempstaff@x.test", "Quite-Long#9").json()
    assert tok["must_change_password"] is True                                    # an admin-chosen password is temporary
    assert client.patch(f"/api/saas/staff/{r.json()['id']}", headers=sup, json={"active": False}).status_code == 200
    assert client.get("/api/me", headers=bearer(tok["token"])).status_code == 401


# ------------------------------------------------------------------ headers and size limits
def test_security_headers_on_api_responses(client):
    r = client.get("/api/health")
    h = r.headers
    assert h["x-content-type-options"] == "nosniff" and h["x-frame-options"] == "DENY" and h["referrer-policy"] == "no-referrer"
    assert "frame-ancestors 'none'" in h["content-security-policy"] and "default-src 'none'" in h["content-security-policy"]
    assert "camera=()" in h["permissions-policy"] and h["cache-control"] == "no-store" and "server" not in h
    assert "strict-transport-security" not in h             # development only: HSTS is sent when ENV=production


def test_hsts_in_production(monkeypatch):
    from starlette.testclient import TestClient
    from app import secure
    monkeypatch.setattr(config, "PRODUCTION", True)
    from fastapi import FastAPI
    a = FastAPI()
    a.add_middleware(secure.SecurityHeadersMiddleware)

    @a.get("/api/x")
    def x():
        return {}
    assert "max-age=31536000" in TestClient(a).get("/api/x").headers["strict-transport-security"]


def test_oversized_json_is_rejected(client):
    big = {"email": "a@b.test", "password": "x" * (config.MAX_BODY_BYTES + 10)}
    assert client.post("/api/auth/login", json=big).status_code == 413
    r = client.post("/api/auth/login", content=b"{" + b" " * (config.MAX_BODY_BYTES + 10) + b"}", headers={"Content-Type": "application/json", "Transfer-Encoding": "chunked"})
    assert r.status_code in (413, 422)


def test_trusted_proxy_handling(monkeypatch):
    from app import netutil
    assert netutil.client_ip_from("203.0.113.9", "198.51.100.1") == "203.0.113.9"              # no trusted proxies: header ignored
    monkeypatch.setattr(config, "TRUSTED_PROXIES", ["10.0.0.0/8"])
    netutil._nets.cache_clear()
    try:
        assert netutil.client_ip_from("10.1.1.1", "6.6.6.6, 198.51.100.7, 10.2.2.2") == "198.51.100.7"   # right-most untrusted wins; the spoofed 6.6.6.6 is ignored
        assert netutil.client_ip_from("203.0.113.9", "6.6.6.6") == "203.0.113.9"                    # peer not trusted
        assert netutil.client_ip_from("10.1.1.1", "garbage") == "10.1.1.1"
    finally:
        monkeypatch.setattr(config, "TRUSTED_PROXIES", [])
        netutil._nets.cache_clear()


# ------------------------------------------------------------------ audit log
def test_audit_chain_verifies_and_detects_tampering(client):
    sign_in(client, "guard@flatwise.demo", "demo1234")
    su = login(client, "super")[0]
    assert client.get("/api/audit/verify", headers=su).json()["ok"] is True
    assert client.get("/api/audit/verify", headers=login(client, "support")[0]).status_code == 403
    try:
        with SessionLocal() as db:
            rid = db.scalar(select(AuditLog.id).where(AuditLog.row_hash != "").order_by(AuditLog.id.desc()).offset(2).limit(1))
            db.execute(text("UPDATE audit_log SET action = 'forged.action' WHERE id = :i"), {"i": rid})      # raw SQL, as an intruder with database access would
            db.commit()
        bad = client.get("/api/audit/verify", headers=su).json()
        assert bad["ok"] is False and bad["bad_id"] == rid
        with SessionLocal() as db:                                                                          # removing the newest rows is caught by the stored head
            db.execute(text("UPDATE audit_log SET action = 'auth.login' WHERE id = :i"), {"i": rid})
            db.commit()
    finally:
        with SessionLocal() as db:       # start a fresh chain so the rest of the suite sees an intact log
            db.execute(text("UPDATE audit_log SET row_hash = '', prev_hash = ''"))
            db.execute(text("UPDATE audit_head SET hash = ''"))
            db.commit()
    assert client.get("/api/audit/verify", headers=su).json()["ok"] is True


def test_audit_rows_cannot_be_updated_or_deleted_by_the_app(client):
    sign_in(client, "guard@flatwise.demo", "demo1234")
    with SessionLocal() as db:
        row = db.scalar(select(AuditLog).order_by(AuditLog.id.desc()).limit(1))
        row.note = "edited"
        with pytest.raises(RuntimeError):
            db.commit()
        db.rollback()
        row = db.scalar(select(AuditLog).order_by(AuditLog.id.desc()).limit(1))
        db.delete(row)
        with pytest.raises(RuntimeError):
            db.commit()
        db.rollback()


def test_no_audit_write_endpoints():
    from fastapi.routing import APIRoute
    from app.main import app

    def flat(routes):
        for r in routes:
            if isinstance(r, APIRoute):
                yield r
            elif hasattr(r, "original_router"):
                yield from flat(r.original_router.routes)
    for r in flat(app.routes):
        if "audit" in r.path:
            assert r.methods <= {"GET", "HEAD"}, (r.path, r.methods)


def test_audit_log_never_records_secrets(client):
    body, _ = signup(client)
    _reset_link(client, body["email"])
    sign_in(client, body["email"], body["password"])
    with SessionLocal() as db:
        blob = " ".join(f"{a.action} {a.meta} {a.note}" for a in db.scalars(select(AuditLog)))
    assert body["password"] not in blob and "refresh_token" not in blob and "#token=" not in blob


# ------------------------------------------------------------------ abuse controls
def test_public_lead_form_is_rate_limited_and_honeypot_drops_bots(client):
    ok = {"name": "Real Person", "phone": "01711223344", "source": "demo"}
    assert client.post("/api/public/leads", json={**ok, "hp": "http://spam.example"}).json() == {"ok": True, "id": 0}
    with SessionLocal() as db:
        from app.models.saas import Lead
        assert db.scalar(select(Lead.id).where(Lead.phone == "01711223344")) is None
    codes = [client.post("/api/public/leads", json=ok).status_code for _ in range(11)]
    assert codes[:9] == [201] * 9 and codes[9] == 429          # the honeypot request above used one of the 10 hourly slots


def test_form_token_timing_in_strict_mode(client, monkeypatch):
    monkeypatch.setattr(config, "ANTISPAM_STRICT", True)
    ok = {"name": "Slow Person", "phone": "01899887766"}
    from app.models.saas import Lead
    assert client.post("/api/public/leads", json=ok).json()["id"] == 0                       # no token: dropped quietly
    fresh = client.get("/api/public/form-token").json()["ft"]
    assert client.post("/api/public/leads", json={**ok, "ft": fresh}).json()["id"] == 0      # under 3 seconds: a bot
    monkeypatch.setattr(antispam, "MIN_SECONDS", 0)
    assert client.post("/api/public/leads", json={**ok, "ft": fresh}).json()["id"] > 0       # the same token once it is old enough
    assert client.post("/api/public/leads", json={**ok, "ft": fresh[:-3] + "abc"}).json()["id"] == 0   # forged
    with SessionLocal() as db:
        assert len(db.scalars(select(Lead).where(Lead.phone == "01899887766")).all()) == 1


def test_signup_is_rate_limited(client):
    codes = []
    for i in range(12):
        codes.append(client.post("/api/public/signup", json={"name": "Rate Test", "email": f"rate{next(_n)}@x.test", "password": "longpass1", "building": "Rate Court", "flats": 5}).status_code)
    assert codes[:10] == [201] * 10 and codes[10:] == [429, 429]


def test_unsubscribe_and_link_endpoints_are_rate_limited(client):
    codes = [client.get("/api/public/unsubscribe/not-a-real-token").status_code for _ in range(70)]
    assert codes.count(429) > 0 and set(codes) <= {400, 429}
    codes = [client.get("/api/onboarding/link/not-a-real-token").status_code for _ in range(130)]
    assert codes.count(429) > 0 and set(codes) <= {404, 429}


def test_email_verification_before_trial_when_enabled(client, monkeypatch):
    monkeypatch.setattr(config, "REQUIRE_EMAIL_VERIFICATION", True)
    n = next(_n)
    body = {"name": "Verify Me", "email": f"verify{n}@x.test", "password": "longpass1", "building": f"Verify Court {n}", "flats": 9}
    r = client.post("/api/public/signup", json=body)
    assert r.status_code == 201 and r.json()["verification_required"] is True and "token" not in r.json()
    link = r.json()["demo_link"]
    lg = sign_in(client, body["email"], body["password"])
    assert lg.status_code == 403 and lg.headers["X-Error-Code"] == "email_unverified"
    # a repeat sign-up with the same address looks identical: nothing reveals that the address is registered
    again = client.post("/api/public/signup", json=body)
    assert again.status_code == 201 and again.json() == {"verification_required": True, "email": body["email"]}
    tok = link.split("#token=")[1]
    assert client.post("/api/auth/verify-email", json={"token": tok}).status_code == 200
    assert client.post("/api/auth/verify-email", json={"token": tok}).status_code == 400
    assert sign_in(client, body["email"], body["password"]).status_code == 200
    resend = client.post("/api/auth/resend-verification", json={"email": body["email"]})
    assert resend.status_code == 200 and "demo_link" not in resend.json()              # already verified: nothing sent


# ------------------------------------------------------------------ uploads and payments
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64


def test_upload_content_is_checked_against_its_magic_bytes():
    from fastapi import HTTPException
    from app.services import uploads
    assert uploads.check(PNG, "image/png", {"image/png", "image/jpeg"}) == "image/png"
    with pytest.raises(HTTPException):
        uploads.check(b"<script>alert(1)</script>", "image/png", {"image/png"})          # text claiming to be a picture
    with pytest.raises(HTTPException):
        uploads.check(PNG, "image/jpeg", {"image/png", "image/jpeg"})                    # claim and bytes disagree
    with pytest.raises(HTTPException):
        uploads.check(b"MZ\x90\x00", "application/pdf", {"application/pdf"})


def test_filenames_are_sanitised():
    from app.services.uploads import safe_filename
    assert safe_filename("../../etc/passwd") == "passwd"
    assert safe_filename("C:\\Users\\x\\nid front.png") == "nid front.png"
    assert not set('"\r\n\\/:<>') & set(safe_filename('evil"\r\nSet-Cookie: <x>=1.png'))
    assert safe_filename("") == "file" and safe_filename("...") == "file" and len(safe_filename("a" * 500)) <= 120
    assert safe_filename("নথি.pdf") == "নথি.pdf"


def test_sandbox_payment_endpoints_vanish_in_production(client, monkeypatch):
    h = login(client, "padmin")[0]
    monkeypatch.setattr(config, "SANDBOX_PAYMENTS", False)
    assert client.get("/api/gateway/sandbox/anything", headers=h).status_code == 404
    assert client.get("/api/credits/sandbox/anything", headers=h).status_code == 404
    from app.services import gateway as gw
    sig = gw.sign("s", "success", 100, "T1")
    assert gw.provider("bkash").verify({"session": "s", "status": "success", "trx_id": "T1", "amount": 100, "sig": sig})["valid"] is False   # a signed success is worthless
    monkeypatch.setattr(config, "SANDBOX_PAYMENTS", True)
    assert gw.provider("bkash").verify({"session": "s", "status": "success", "trx_id": "T1", "amount": 100, "sig": "é" * 64})["valid"] is False   # non-ASCII signature: no crash


def test_validation_errors_never_echo_what_was_sent(client):
    r = client.post("/api/auth/login", json={"email": "a@b.test", "password": 12345})
    assert r.status_code == 422 and "12345" not in r.text and "input" not in r.text
    body, d = signup(client)
    r = client.post("/api/auth/change-password", headers=bearer(d["token"]), json={"current_password": body["password"], "new_password": "N" * 300})
    assert r.status_code == 422 and "NNNNN" not in r.text
