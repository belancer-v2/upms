from sqlalchemy import select

from app.db import SessionLocal
from app.models.billing import Payment
from app.models.finance import Journal
from app.services import gateway as gw
from conftest import login
from test_property import prop_headers


def fresh_invoice(client, period="2027-02"):
    client.post("/api/billing/run", json={"period": period}, headers=prop_headers(client, "padmin"))
    ht = prop_headers(client, "tenant")
    return ht, client.get(f"/api/billing/invoices?period={period}", headers=ht).json()[0]


def start(client, ht, inv, provider="bkash", amount=None):
    body = {"invoice_id": inv["id"], "provider": provider, **({"amount": amount} if amount else {})}
    r = client.post("/api/gateway/checkout", json=body, headers=ht)
    assert r.status_code == 201, r.text
    return r.json()


def payloads(client, ht, sid):
    d = client.get(f"/api/gateway/sandbox/{sid}", headers=ht).json()
    return d["pay"], d["fail"], d


def cb(client, sid, p):
    return client.post(f"/api/gateway/callback/{sid}", json={k: p[k] for k in ("status", "trx_id", "amount", "sig")})


def test_fee_maths_integer_paisa():
    assert gw.fee_for(100000, 150) == 1500
    assert gw.fee_for(33333, 150) == 500 and isinstance(gw.fee_for(33333, 150), int)   # 499.995 rounds half up
    assert gw.fee_for(1, 150) == 0 and gw.fee_for(100000, 0) == 0


def test_success_creates_one_verified_payment_and_ledger_entry(client):
    ht, inv = fresh_invoice(client, "2027-02")
    co = start(client, ht, inv, "nagad")
    assert co["redirect_url"] == f"/pay/sandbox/{co['session_id']}" and co["charged"] == co["amount"] + co["fee"] and co["fee"] == gw.fee_for(co["amount"], 150)
    pay, _, _ = payloads(client, ht, co["session_id"])
    r = cb(client, co["session_id"], pay)
    assert r.status_code == 200 and r.json()["status"] == "paid"
    pid = r.json()["payment_id"]
    with SessionLocal() as db:
        ps = db.scalars(select(Payment).where(Payment.invoice_id == inv["id"])).all()
        assert len(ps) == 1 and ps[0].status == "verified" and ps[0].method == "nagad" and ps[0].receipt_no and ps[0].amount == inv["total"]
        assert len(db.scalars(select(Journal).where(Journal.source == "payment", Journal.source_id == str(pid))).all()) == 1
    assert client.get(f"/api/billing/invoices/{inv['id']}", headers=ht).json()["status"] == "paid"
    # replay: same answer, still one payment, still one journal entry
    again = cb(client, co["session_id"], pay)
    assert again.status_code == 200 and again.json()["payment_id"] == pid
    with SessionLocal() as db:
        assert len(db.scalars(select(Payment).where(Payment.invoice_id == inv["id"])).all()) == 1
        assert len(db.scalars(select(Journal).where(Journal.source == "payment", Journal.source_id == str(pid))).all()) == 1


def test_forged_signature_and_amount_tampering_rejected(client):
    ht, inv = fresh_invoice(client, "2027-03")
    co = start(client, ht, inv, "card", amount=50000)
    pay, fail, d = payloads(client, ht, co["session_id"])
    assert d["charged"] == 50000 + gw.fee_for(50000, 150)
    assert cb(client, co["session_id"], {**pay, "sig": "0" * 64}).status_code == 403
    assert cb(client, co["session_id"], {"status": "success", "trx_id": "X1", "amount": d["charged"], "sig": fail["sig"]}).status_code == 403   # a "failed" signature cannot be turned into success
    assert cb(client, co["session_id"], {**pay, "amount": 1}).status_code == 403                    # edited amount breaks the signature
    low = {"status": "success", "trx_id": "T9", "amount": 100, "sig": gw.sign(co["session_id"], "success", 100, "T9")}   # even a correctly signed odd amount is not accepted
    assert cb(client, co["session_id"], low).status_code == 422
    with SessionLocal() as db:
        assert db.scalars(select(Payment).where(Payment.invoice_id == inv["id"])).all() == []
    # and the checkout itself refuses more than the balance
    assert client.post("/api/gateway/checkout", json={"invoice_id": inv["id"], "provider": "bkash", "amount": inv["total"] + 1}, headers=ht).status_code == 422
    # a failed callback marks the session failed and creates nothing
    assert cb(client, co["session_id"], fail).json()["status"] == "failed"
    assert cb(client, co["session_id"], pay).status_code == 409


def test_balance_rechecked_at_callback(client):
    ht, inv = fresh_invoice(client, "2027-04")
    co = start(client, ht, inv, "bkash")
    pay, _, _ = payloads(client, ht, co["session_id"])
    assert client.post(f"/api/billing/invoices/{inv['id']}/payments", json={"amount": 100, "method": "cash"}, headers=prop_headers(client, "treasurer")).status_code == 201
    assert cb(client, co["session_id"], pay).status_code == 409                                      # balance shrank, full amount no longer fits


def test_access_rules_config_and_sessions(client):
    ht, inv = fresh_invoice(client, "2027-05")
    assert client.get("/api/gateway/config", headers=ht).status_code == 403
    assert client.post("/api/gateway/checkout", json={"invoice_id": inv["id"], "provider": "bkash"}, headers=prop_headers(client, "owner")).status_code == 403   # not their flat
    ha = prop_headers(client, "treasurer")
    c = client.get("/api/gateway/config", headers=ha).json()
    assert c["enabled"] and c["providers"] == ["bkash", "nagad", "card"] and "credentials" not in c and "credentials_enc" not in c and c["has_credentials"]
    r = client.put("/api/gateway/config", json={**{k: c[k] for k in ("enabled", "providers", "fee_mode", "fee_bps")}, "credentials": {"store_id": "x", "secret": "y"}}, headers=ha)
    assert r.status_code == 200 and "secret" not in r.text and r.json()["has_credentials"]
    assert client.put("/api/gateway/config", json={"enabled": True, "providers": ["paypal"]}, headers=ha).status_code == 422
    assert client.put("/api/gateway/config", json={"enabled": True, "providers": ["bkash"], "fee_bps": 5000}, headers=ha).status_code == 422
    s = client.get("/api/gateway/sessions?size=2", headers=ha).json()
    assert s["total"] >= 3 and len(s["rows"]) == 2 and s["rows"][0]["unit"]
    assert client.get("/api/gateway/sessions", headers=ht).status_code == 403
    assert client.get("/api/gateway/options", headers=ht).json()["enabled"]


def test_building_without_feature_gets_402(client):
    hs, d = login(client, "padmin")
    org = [p for p in d["properties"] if p["name"] == "Sunrise Tower"][0]["org_id"]
    hsa, _ = login(client, "super")
    assert client.put(f"/api/saas/orgs/{org}/features", json={"key": "gateway", "enabled": False}, headers=hsa).status_code == 200
    try:
        ht, inv = prop_headers(client, "tenant"), None
        inv = client.get("/api/billing/invoices", headers=ht).json()[0]
        assert client.post("/api/gateway/checkout", json={"invoice_id": inv["id"], "provider": "bkash"}, headers=ht).status_code == 402
        assert client.get("/api/gateway/config", headers=prop_headers(client, "padmin")).status_code == 402
        assert client.get("/api/gateway/sessions", headers=prop_headers(client, "padmin")).status_code == 402
        assert client.get("/api/gateway/options", headers=ht).json()["enabled"] is False
    finally:
        client.put(f"/api/saas/orgs/{org}/features", json={"key": "gateway", "enabled": True}, headers=hsa)
