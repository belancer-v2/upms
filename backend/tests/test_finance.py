from conftest import login
from test_property import prop_headers


def test_ledger_balances_and_trial_balance(client):
    h = prop_headers(client, "treasurer")
    tb = client.get("/api/finance/trial-balance", headers=h).json()
    assert tb["debit"] == tb["credit"] and tb["debit"] > 0
    j = client.get("/api/finance/ledger?limit=100", headers=h).json()
    assert j["total"] > 100
    for row in j["rows"]:
        assert sum(l["debit"] for l in row["lines"]) == sum(l["credit"] for l in row["lines"])


def test_new_payment_lands_in_ledger(client):
    h = prop_headers(client, "treasurer")
    before = client.get("/api/finance/ledger?limit=1", headers=h).json()["total"]
    inv = [i for i in client.get("/api/billing/invoices?period=2026-10", headers=h).json() if i["status"] != "paid"][-1]
    assert client.post(f"/api/billing/invoices/{inv['id']}/payments", json={"amount": 100, "method": "cash"}, headers=h).status_code == 201
    assert client.get("/api/finance/ledger?limit=1", headers=h).json()["total"] == before + 1


def test_dual_approval_above_limit(client):
    ht, hp, ha = prop_headers(client, "treasurer"), prop_headers(client, "president"), prop_headers(client, "padmin")
    e = client.post("/api/finance/expenses", json={"category": "repairs", "title": "Roof repair test", "amount": 6_000_000}, headers=ht).json()
    assert e["needs_two"] and e["approvals_needed"] == 2
    assert client.post(f"/api/finance/expenses/{e['id']}/approve", headers=ht).status_code == 403   # no self approval
    one = client.post(f"/api/finance/expenses/{e['id']}/approve", headers=hp).json()
    assert one["status"] == "pending"
    assert client.post(f"/api/finance/expenses/{e['id']}/approve", headers=hp).status_code == 422    # same person twice
    two = client.post(f"/api/finance/expenses/{e['id']}/approve", headers=ha).json()
    assert two["status"] == "approved"
    assert client.post(f"/api/finance/expenses/{e['id']}/pay", json={"method": "bank"}, headers=hp).status_code == 403   # a president approves but does not pay
    assert client.post(f"/api/finance/expenses/{e['id']}/pay", json={"method": "bank"}, headers=ht).json()["status"] == "paid"
    tb = client.get("/api/finance/trial-balance", headers=ht).json()
    assert tb["debit"] == tb["credit"]


def test_single_approval_below_limit_and_reject(client):
    ht, hp = prop_headers(client, "treasurer"), prop_headers(client, "president")
    e = client.post("/api/finance/expenses", json={"category": "other", "title": "Small purchase", "amount": 150000}, headers=ht).json()
    assert not e["needs_two"]
    assert client.post(f"/api/finance/expenses/{e['id']}/approve", headers=hp).json()["status"] == "approved"
    r = client.post("/api/finance/expenses", json={"category": "other", "title": "Another one", "amount": 100000}, headers=ht).json()
    assert client.post(f"/api/finance/expenses/{r['id']}/reject", json={"reason": "No bill"}, headers=hp).json()["status"] == "rejected"


def test_resident_cannot_see_finance(client):
    h = prop_headers(client, "tenant")
    assert client.get("/api/finance/summary", headers=h).status_code == 403
    assert client.get("/api/finance/expenses", headers=h).status_code == 403


def test_asset_threshold_and_budget(client):
    h = prop_headers(client, "padmin")
    big = client.post("/api/finance/assets", json={"name": "Test pump", "cost": 3_000_000, "life_years": 5}, headers=h).json()
    small = client.post("/api/finance/assets", json={"name": "Test stool", "cost": 500_000}, headers=h).json()
    assert big["capitalised"] and not small["capitalised"]
    b = client.get("/api/finance/budget?year=2026", headers=h).json()
    assert b["lines"]["salary"] > 0
    s = client.get("/api/finance/summary?year=2026", headers=h).json()
    assert s["income"] > 0 and s["expense"] > 0 and s["cash_total"] != 0


def test_assets_need_a_plan_with_the_feature(client):
    r = client.post("/api/auth/login", json={"email": "admin2@customers.demo", "password": "demo1234"})
    assert r.status_code == 200
    d = r.json()
    h = {"Authorization": f"Bearer {d['token']}", "X-Property-Id": str(d["properties"][0]["id"])}
    assert "assets" not in d["properties"][0]["features"]
    assert client.get("/api/finance/assets", headers=h).status_code == 402
