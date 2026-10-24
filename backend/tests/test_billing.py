from conftest import login
from test_property import prop_headers


def unit_id(client, h, number):
    return [u for u in client.get("/api/units", headers=h).json() if u["number"] == number][0]["id"]


def test_run_is_idempotent_and_per_sqft(client):
    h = prop_headers(client, "padmin")
    assert client.post("/api/billing/run", json={"period": "2026-11"}, headers=h).json()["created"] == 32
    assert client.post("/api/billing/run", json={"period": "2026-11"}, headers=h).json()["created"] == 0
    inv = client.get("/api/billing/invoices?period=2026-11", headers=h).json()
    full = client.get(f"/api/billing/invoices/{inv[0]['id']}", headers=h).json()
    area = [u for u in client.get("/api/units", headers=h).json() if u["id"] == inv[0]["unit_id"]][0]["area_sqft"]
    assert full["lines"][0]["amount"] == 200 * area and full["total"] == sum(l["amount"] for l in full["lines"])


def test_tenant_submits_treasurer_verifies(client):
    ht = prop_headers(client, "tenant")
    inv = [i for i in client.get("/api/billing/invoices?period=2026-10", headers=ht).json()]
    assert len(inv) == 1
    r = client.post(f"/api/billing/invoices/{inv[0]['id']}/payments", json={"amount": 1000, "method": "bkash"}, headers=ht)
    assert r.status_code == 422                                     # bKash needs a transaction id
    r = client.post(f"/api/billing/invoices/{inv[0]['id']}/payments", json={"amount": 1000, "method": "bkash", "trx_id": "BKTEST1"}, headers=ht)
    assert r.status_code == 201 and r.json()["status"] == "pending"
    pid = r.json()["id"]
    assert client.post(f"/api/billing/payments/{pid}/verify", headers=ht).status_code == 403
    ht2 = prop_headers(client, "treasurer")
    v = client.post(f"/api/billing/payments/{pid}/verify", headers=ht2)
    assert v.status_code == 200 and v.json()["receipt_no"].startswith("RC-")
    dup = client.post(f"/api/billing/invoices/{inv[0]['id']}/payments", json={"amount": 500, "method": "bkash", "trx_id": "BKTEST1"}, headers=ht)
    assert dup.status_code in (409, 422)


def test_resident_sees_only_own_invoices(client):
    mine = client.get("/api/billing/invoices", headers=prop_headers(client, "owner2")).json()
    assert {i["unit"] for i in mine} == {"B-302"}
    assert len(client.get("/api/billing/invoices", headers=prop_headers(client, "auditor")).json()) > 100
    assert client.post("/api/billing/run", json={"period": "2027-01"}, headers=prop_headers(client, "owner2")).status_code == 403


def test_dues_and_summary(client):
    h = prop_headers(client, "treasurer")
    d = client.get("/api/billing/dues", headers=h).json()
    assert d
    s = client.get("/api/billing/summary", headers=h).json()
    assert s["pending"] >= 1


def test_reminders_need_a_plan_with_the_feature(client):
    h = prop_headers(client, "padmin")
    r = client.post("/api/billing/reminders/run", headers=h)
    assert r.status_code == 200
    again = client.post("/api/billing/reminders/run", headers=h).json()
    assert again["sent"] == 0 and again["failed"] == 0              # same step is never sent twice
