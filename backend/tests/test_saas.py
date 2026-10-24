from conftest import login


def H(client, who):
    return login(client, who)[0]


def test_only_staff_reach_saas(client):
    assert client.get("/api/saas/overview", headers=H(client, "owner")).status_code == 403
    assert client.get("/api/saas/overview").status_code == 401


def test_overview_hides_money_from_sales(client):
    d = client.get("/api/saas/overview", headers=H(client, "sales")).json()
    assert d["mrr"] is None and d["leads"]["new"] >= 1
    f = client.get("/api/saas/overview", headers=H(client, "finance")).json()
    assert f["mrr"] > 0


def test_sales_cannot_see_invoices_finance_can(client):
    assert client.get("/api/saas/invoices", headers=H(client, "sales")).status_code == 403
    assert client.get("/api/saas/invoices", headers=H(client, "finance")).status_code == 200


def test_invoice_run_is_idempotent(client):
    h = H(client, "finance")
    first = client.post("/api/saas/invoices/run", headers=h, json={"period": "2026-11"}).json()
    second = client.post("/api/saas/invoices/run", headers=h, json={"period": "2026-11"}).json()
    assert first["created"] > 0 and second["created"] == 0


def test_pay_invoice(client):
    h = H(client, "finance")
    open_ = [i for i in client.get("/api/saas/invoices?status=issued", headers=h).json()][0]
    r = client.post(f"/api/saas/invoices/{open_['id']}/pay", headers=h, json={"method": "bkash", "trx_id": "TX1"})
    assert r.json()["status"] == "paid"


def test_suspend_blocks_that_building_and_reactivate_restores(client):
    org = [o for o in client.get("/api/saas/orgs", headers=H(client, "super")).json() if o["name"].startswith("Rupayan")][0]
    uh, me = login(client, "admin1", "demo1234") if False else (None, None)
    r = client.post("/api/auth/login", json={"email": "admin1@customers.demo", "password": "demo1234"})
    token = {"Authorization": f"Bearer {r.json()['token']}", "X-Property-Id": str(r.json()["properties"][0]["id"])}
    assert client.get("/api/property", headers=token).status_code == 200
    client.post(f"/api/saas/orgs/{org['id']}/status", headers=H(client, "admin"), json={"status": "suspended"})
    assert client.get("/api/property", headers=token).status_code == 403
    client.post(f"/api/saas/orgs/{org['id']}/status", headers=H(client, "admin"), json={"status": "active"})
    assert client.get("/api/property", headers=token).status_code == 200


def test_feature_gating_follows_plan_and_override(client):
    r = client.post("/api/auth/login", json={"email": "admin2@customers.demo", "password": "demo1234"}).json()  # Basic plan
    assert "staff" not in r["properties"][0]["features"]
    org_id = r["properties"][0]["org_id"]
    client.put(f"/api/saas/orgs/{org_id}/features", headers=H(client, "admin"), json={"key": "staff", "enabled": True})
    r2 = client.post("/api/auth/login", json={"email": "admin2@customers.demo", "password": "demo1234"}).json()
    assert "staff" in r2["properties"][0]["features"]
    client.put(f"/api/saas/orgs/{org_id}/features", headers=H(client, "admin"), json={"key": "staff", "enabled": False})


def test_only_super_admin_edits_plans_and_staff(client):
    body = {"monthly": {"S": 1, "M": 1, "L": 1}, "setup": {"S": 1, "M": 1, "L": 1}, "sms_included": {"S": 1, "M": 1, "L": 1}, "features": []}
    assert client.put("/api/saas/plans/basic", headers=H(client, "admin"), json=body).status_code == 403
    assert client.post("/api/saas/staff", headers=H(client, "admin"), json={"name": "X Y", "email": "x@y.test", "role": "SAAS_USER", "password": "longpass1"}).status_code == 403
    assert client.post("/api/saas/staff", headers=H(client, "super"), json={"name": "X Y", "email": "x@y.test", "role": "SAAS_USER", "password": "longpass1"}).status_code == 201


def test_sales_lead_flow(client):
    h = H(client, "sales")
    lead = client.get("/api/saas/leads", headers=h).json()[0]
    r = client.patch(f"/api/saas/leads/{lead['id']}", headers=h, json={"status": "contacted"}).json()
    assert r["status"] == "contacted"
    assert client.post(f"/api/saas/leads/{lead['id']}/notes", headers=h, json={"text": "Called back"}).status_code == 201
