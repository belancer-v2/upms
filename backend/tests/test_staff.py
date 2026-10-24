from conftest import login
from test_property import prop_headers


def test_nid_is_masked_and_reveal_is_logged(client):
    ht, hp = prop_headers(client, "treasurer"), prop_headers(client, "president")
    rows = client.get("/api/staff", headers=ht).json()
    assert len(rows) == 4 and all(r["nid"].startswith("••••••") and "198" not in r["nid"] for r in rows)
    sid = rows[0]["id"]
    assert client.post(f"/api/staff/{sid}/reveal-nid", headers=ht).status_code == 403          # treasurer cannot reveal
    full = client.post(f"/api/staff/{sid}/reveal-nid", headers=hp).json()["nid"]
    assert full.isdigit() and len(full) == 13 and full.endswith(rows[0]["nid"][-4:])
    views = client.get(f"/api/staff/{sid}/nid-views", headers=hp).json()
    assert views and views[0]["viewer"]


def test_payroll_flow_eid_and_ledger(client):
    ht, hp, ha = prop_headers(client, "treasurer"), prop_headers(client, "president"), prop_headers(client, "padmin")
    sheets = client.get("/api/staff/payroll/sheets", headers=ht).json()
    draft = [s for s in sheets if s["status"] == "draft"][0]
    full = client.get(f"/api/staff/payroll/sheets/{draft['id']}", headers=ht).json()
    base_total = sum(l["base"] for l in full["lines"])
    e1 = client.post(f"/api/staff/payroll/sheets/{draft['id']}/eid-bonus", json={"percent": 50}, headers=ht).json()
    e2 = client.post(f"/api/staff/payroll/sheets/{draft['id']}/eid-bonus", json={"percent": 50}, headers=ht).json()
    assert e1["total"] == e2["total"] == round(base_total * 1.5)                  # running it twice never doubles it
    assert client.post(f"/api/staff/payroll/sheets/{draft['id']}/approve", headers=ht).status_code == 403   # preparer cannot approve
    assert client.post(f"/api/staff/payroll/sheets/{draft['id']}/pay", json={"method": "bank"}, headers=ht).status_code == 422
    assert client.post(f"/api/staff/payroll/sheets/{draft['id']}/approve", headers=hp).json()["status"] == "approved"
    assert client.put(f"/api/staff/payroll/lines/{full['lines'][0]['id']}", json={"bonus": 0}, headers=ht).status_code == 422   # locked after approval
    paid = client.post(f"/api/staff/payroll/sheets/{draft['id']}/pay", json={"method": "bank"}, headers=ht).json()
    assert paid["status"] == "paid" and paid["sms_sent"] + paid["sms_failed"] == 4
    tb = client.get("/api/finance/trial-balance", headers=ht).json()
    assert tb["debit"] == tb["credit"]


def test_duplicate_month_and_roles(client):
    assert client.post("/api/staff/payroll/sheets", json={"period": "2026-09"}, headers=prop_headers(client, "treasurer")).status_code == 409
    assert client.get("/api/staff", headers=prop_headers(client, "tenant")).status_code == 403
    assert client.post("/api/staff", json={"name": "New Guard", "role": "guard", "salary": 900000, "nid": "123"}, headers=prop_headers(client, "padmin")).status_code == 422
