from sqlalchemy import func, select

from app.db import SessionLocal
from app.models.billing import Message
from app.models.core import Organization
from app.models.credits import CreditPack, CreditPurchase, EmailLedger
from app.models.saas import SaasInvoice, SmsLedger
from app.services.entitlements import email_balance, sms_balance
from app.services.messaging import deliver
from conftest import login
from test_property import prop_headers

H = lambda client, who: login(client, who)[0]  # noqa: E731


def org_id(client):
    return [p for p in login(client, "padmin")[1]["properties"] if p["name"] == "Sunrise Tower"][0]["org_id"]


def summary(client, who="padmin"):
    r = client.get("/api/credits/summary", headers=prop_headers(client, who))
    assert r.status_code == 200, r.text
    return r.json()


def pack(client, kind="sms", credits=1000):
    return [p for p in summary(client)["packs"] if p["kind"] == kind and p["credits"] == credits][0]


def start(client, who="padmin", pk=None, provider="bkash"):
    h = prop_headers(client, who)
    r = client.post("/api/credits/checkout", json={"pack_id": (pk or pack(client))["id"], "provider": provider}, headers=h)
    assert r.status_code == 201, r.text
    return h, r.json()


def cb(client, sid, p):
    return client.post(f"/api/credits/callback/{sid}", json={k: p[k] for k in ("status", "trx_id", "amount", "sig")})


def test_summary_roles_and_scoping(client):
    s = summary(client)
    assert {"sms", "email", "packs", "providers"} <= set(s) and s["sms"]["balance"] == sms_balance(SessionLocal(), org_id(client))
    assert s["email"]["balance"] > 0 and {p["credits"] for p in s["packs"] if p["kind"] == "sms"} == {1000, 5000, 20000}
    for who in ("treasurer", "president"):
        assert client.get("/api/credits/summary", headers=prop_headers(client, who)).status_code == 200
    for who in ("owner2", "tenant", "ownerrep", "caretaker", "guard"):
        assert client.get("/api/credits/summary", headers=prop_headers(client, who)).status_code == 403
        assert client.post("/api/credits/checkout", json={"pack_id": 1, "provider": "bkash"}, headers=prop_headers(client, who)).status_code == 403
    assert client.get("/api/credits/summary").status_code == 401
    # another building's org has its own balance
    other = client.get("/api/saas/credits/balances?size=100", headers=H(client, "admin")).json()["rows"]
    assert len(other) >= 2 and len({r["sms"] for r in other}) > 1


def test_sandbox_purchase_grants_once_even_on_replay(client):
    oid = org_id(client)
    with SessionLocal() as db:
        before = sms_balance(db, oid)
    h, co = start(client)
    assert co["redirect_url"] == f"/pay/credits/{co['session_id']}"
    d = client.get(f"/api/credits/sandbox/{co['session_id']}", headers=h).json()
    assert client.get(f"/api/credits/sandbox/{co['session_id']}", headers=prop_headers(client, "treasurer")).status_code == 404   # not the buyer
    with SessionLocal() as db:
        assert sms_balance(db, oid) == before            # nothing before the callback
    r = cb(client, co["session_id"], d["pay"])
    assert r.status_code == 200 and r.json()["status"] == "paid"
    again = cb(client, co["session_id"], d["pay"])
    assert again.status_code == 200 and again.json()["replayed"] is True
    with SessionLocal() as db:
        assert sms_balance(db, oid) == before + 1000
        inv = db.get(SaasInvoice, r.json()["invoice_id"])
        assert inv.kind == "credits" and inv.status == "paid" and inv.amount == d["total"] and inv.items[0]["credits"] == 1000 and inv.vat_amount == 0
        rows = db.scalars(select(SmsLedger).where(SmsLedger.invoice_id == inv.id)).all()
        assert len(rows) == 1 and rows[0].delta == 1000
    page = client.get(f"/api/credits/invoices/{inv.id}", headers=h)
    assert page.status_code == 200 and page.json()["total"] == d["total"] and page.json()["buyer"]["name"]
    assert client.get(f"/api/credits/invoices/{inv.id}", headers=H(client, "tenant")).status_code == 404
    assert client.get(f"/api/credits/invoices/{inv.id}", headers=H(client, "finance")).status_code == 200


def test_forged_signature_failed_and_tampered_amount(client):
    oid = org_id(client)
    h, co = start(client, provider="card")
    d = client.get(f"/api/credits/sandbox/{co['session_id']}", headers=h).json()
    bad = {**d["pay"], "sig": "0" * 64}
    assert cb(client, co["session_id"], bad).status_code == 403
    assert cb(client, co["session_id"], {**d["pay"], "amount": 1}).status_code == 403
    with SessionLocal() as db:
        before = sms_balance(db, oid)
    f = cb(client, co["session_id"], d["fail"])
    assert f.status_code == 200 and f.json()["status"] == "failed"
    assert cb(client, co["session_id"], d["pay"]).status_code == 409          # a failed session cannot be paid later
    with SessionLocal() as db:
        assert sms_balance(db, oid) == before


def test_manual_flow_grants_only_after_verification(client):
    oid = org_id(client)
    h = prop_headers(client, "treasurer")
    pk = pack(client, "email", 5000)
    with SessionLocal() as db:
        before = email_balance(db, oid)
    r = client.post("/api/credits/manual", headers=h, json={"pack_id": pk["id"], "method": "nagad", "trx_id": "NG77TEST01", "amount": pk["total"]})
    assert r.status_code == 201 and r.json()["status"] == "pending"
    pid = r.json()["id"]
    assert client.post("/api/credits/manual", headers=h, json={"pack_id": pk["id"], "method": "nagad", "trx_id": "NG77TEST01", "amount": pk["total"]}).status_code == 409
    with SessionLocal() as db:
        assert email_balance(db, oid) == before and db.get(SaasInvoice, r.json()["invoice_id"]).status == "pending"
    q = client.get("/api/saas/credits/queue", headers=H(client, "finance")).json()
    assert any(x["id"] == pid for x in q["rows"])
    assert client.post(f"/api/saas/credits/purchases/{pid}/verify", headers=H(client, "sales")).status_code == 403
    assert client.post(f"/api/saas/credits/purchases/{pid}/verify", headers=h).status_code == 403
    assert client.post(f"/api/saas/credits/purchases/{pid}/verify", headers=H(client, "finance")).status_code == 200
    assert client.post(f"/api/saas/credits/purchases/{pid}/verify", headers=H(client, "finance")).status_code == 200   # repeat: no second grant
    with SessionLocal() as db:
        assert email_balance(db, oid) == before + 5000
        assert db.scalar(select(func.count()).select_from(EmailLedger).where(EmailLedger.invoice_id == r.json()["invoice_id"])) == 1
        assert db.get(SaasInvoice, r.json()["invoice_id"]).status == "paid"


def test_manual_wrong_amount_cannot_verify_and_reject(client):
    oid = org_id(client)
    h = prop_headers(client, "padmin")
    pk = pack(client)
    with SessionLocal() as db:
        before = sms_balance(db, oid)
    r = client.post("/api/credits/manual", headers=h, json={"pack_id": pk["id"], "method": "bank", "trx_id": "BANKREF-22", "amount": pk["total"] - 100}).json()
    assert client.post(f"/api/saas/credits/purchases/{r['id']}/verify", headers=H(client, "finance")).status_code == 422
    assert client.post(f"/api/saas/credits/purchases/{r['id']}/reject", headers=H(client, "finance"), json={"reason": "Amount short"}).status_code == 200
    assert client.post(f"/api/saas/credits/purchases/{r['id']}/verify", headers=H(client, "finance")).status_code == 409
    with SessionLocal() as db:
        assert sms_balance(db, oid) == before and db.get(SaasInvoice, r["invoice_id"]).status == "void"


def test_email_deliver_spends_credit_and_fails_visibly(client):
    oid = org_id(client)
    pid = [p for p in login(client, "padmin")[1]["properties"] if p["name"] == "Sunrise Tower"][0]["id"]
    with SessionLocal() as db:
        before = email_balance(db, oid)
        m = deliver(db, oid, Message(property_id=pid, channel="email", to_email="a@b.test", template="notice", body="Hi", idem_key="em-ok-1"))
        db.add(m)
        assert m.status == "sent" and email_balance(db, oid) == before - 1
        n = deliver(db, oid, Message(property_id=pid, channel="email", to_email="", template="notice", body="Hi", idem_key="em-none-1"))
        assert n.status == "failed" and n.error == "No email address" and email_balance(db, oid) == before - 1
        db.rollback()
    with SessionLocal() as db:
        # an organization with no email credit fails visibly
        lone = Organization(name="No Credit Org")
        db.add(lone)
        db.flush()
        m = deliver(db, lone.id, Message(property_id=pid, channel="email", to_email="a@b.test", template="notice", body="Hi", idem_key="em-zero-1"))
        assert m.status == "failed" and m.error == "No email credit"
        s = deliver(db, lone.id, Message(property_id=pid, channel="sms", to_phone="01711111111", template="notice", body="Hi", idem_key="sm-zero-1"))
        assert s.status == "failed" and s.error == "No SMS credit"
        db.rollback()


def test_console_permissions_and_pack_editing(client):
    body = {"kind": "sms", "name": "SMS 2,000", "name_bn": "এসএমএস ২,০০০", "credits": 2000, "price": 150000, "active": True, "sort": 9}
    assert client.get("/api/saas/credits/packs", headers=H(client, "sales")).status_code == 200            # read-only
    assert client.post("/api/saas/credits/packs", headers=H(client, "sales"), json=body).status_code == 403
    assert client.put("/api/saas/credits/settings", headers=H(client, "sales"), json={"vat_bps": 500}).status_code == 403
    assert client.get("/api/saas/credits/sales", headers=H(client, "sales")).status_code == 403
    assert client.get("/api/saas/credits/packs", headers=H(client, "owner")).status_code == 403
    r = client.post("/api/saas/credits/packs", headers=H(client, "finance"), json=body)
    assert r.status_code == 201
    pk = r.json()
    assert client.put(f"/api/saas/credits/packs/{pk['id']}", headers=H(client, "admin"), json={**body, "price": 160000, "active": False}).json()["price"] == 160000
    assert pk["id"] not in [p["id"] for p in summary(client)["packs"]]        # inactive packs are not sold
    assert client.post("/api/credits/checkout", json={"pack_id": pk["id"], "provider": "bkash"}, headers=prop_headers(client, "padmin")).status_code == 404


def test_vat_line_and_sales_list(client):
    assert client.put("/api/saas/credits/settings", headers=H(client, "finance"), json={"vat_bps": 1500, "pay_bkash": "017", "pay_nagad": "018", "pay_bank": "Bank"}).status_code == 200
    try:
        pk = pack(client)
        assert pk["vat"] == 12000 and pk["total"] == pk["price"] + 12000       # 15% of BDT 800, integer paisa
        h, co = start(client, pk=pk)
        d = client.get(f"/api/credits/sandbox/{co['session_id']}", headers=h).json()
        r = cb(client, co["session_id"], d["pay"]).json()
        inv = client.get(f"/api/credits/invoices/{r['invoice_id']}", headers=h).json()
        assert inv["vat"] == 12000 and inv["subtotal"] == pk["price"] and inv["total"] == pk["total"] and inv["vat_bps"] == 1500
    finally:
        client.put("/api/saas/credits/settings", headers=H(client, "finance"), json={"vat_bps": 0})
    s = client.get("/api/saas/credits/sales?q=Sunrise&status=paid", headers=H(client, "finance")).json()
    assert s["total"] >= 1 and s["paid_total"] > 0 and "org" in s["rows"][0]


def test_bonus_grant_audited_and_balances_low_flag(client):
    oid = org_id(client)
    h = H(client, "finance")
    assert client.post("/api/saas/credits/grant", headers=H(client, "sales"), json={"org_id": oid, "kind": "email", "credits": 10, "reason": "Goodwill"}).status_code == 403
    assert client.post("/api/saas/credits/grant", headers=h, json={"org_id": oid, "kind": "email", "credits": 10, "reason": ""}).status_code == 422
    with SessionLocal() as db:
        before = email_balance(db, oid)
    r = client.post("/api/saas/credits/grant", headers=h, json={"org_id": oid, "kind": "email", "credits": 10, "reason": "Goodwill"})
    assert r.status_code == 201 and r.json()["balance"] == before + 10
    log = client.get("/api/audit", headers=H(client, "admin"))
    if log.status_code == 200:
        assert "credits.grant" in log.text
    low = client.get("/api/saas/credits/balances?low=true&size=100", headers=H(client, "sales")).json()
    assert low["total"] >= 1 and all(r["low"] for r in low["rows"])
    assert client.get("/api/saas/credits/balances?q=zzzznope", headers=H(client, "sales")).json()["total"] == 0


def test_threshold_and_usage(client):
    hp = prop_headers(client, "padmin")
    assert client.put("/api/credits/threshold", headers=prop_headers(client, "treasurer"), json={"sms_low": 5, "email_low": 5}).status_code == 403   # admins only
    assert client.put("/api/credits/threshold", headers=hp, json={"sms_low": 10**9, "email_low": 5}).status_code == 422
    assert client.put("/api/credits/threshold", headers=hp, json={"sms_low": 10**6, "email_low": 5}).status_code == 200
    s = summary(client)
    assert s["sms"]["is_low"] is True and s["sms"]["threshold"] == 10**6
    client.put("/api/credits/threshold", headers=hp, json={"sms_low": 100, "email_low": 100})
    assert isinstance(s["sms"]["by_purpose"], dict) and s["sms"]["total"] == sum(s["sms"]["by_purpose"].values())
    p = client.get("/api/credits/purchases?size=2", headers=hp).json()
    assert p["total"] >= 1 and len(p["rows"]) <= 2
