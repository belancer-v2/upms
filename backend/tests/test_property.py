from conftest import login


def prop_headers(client, who, building="Sunrise Tower"):
    h, data = login(client, who)
    p = [x for x in data["properties"] if x["name"] == building][0]
    return {**h, "X-Property-Id": str(p["id"])}


def test_admin_sees_all_units_owner_sees_own(client):
    assert len(client.get("/api/units", headers=prop_headers(client, "padmin")).json()) == 32
    mine = client.get("/api/units", headers=prop_headers(client, "owner2")).json()
    assert [u["number"] for u in mine] == ["B-302"]          # a plain flat owner sees only their own flat
    both = client.get("/api/units", headers=prop_headers(client, "owner")).json()
    assert len(both) == 32                                    # owner + committee member gets the union of both roles


def test_contacts_hidden_from_auditor(client):
    rows = client.get("/api/units", headers=prop_headers(client, "auditor")).json()
    assert all(p["phone"] == "" for u in rows for p in u["owners"] + u["tenants"])
    rows = client.get("/api/units", headers=prop_headers(client, "padmin")).json()
    assert any(p["phone"] for u in rows for p in u["owners"])


def test_summary_counts(client):
    s = client.get("/api/units/summary", headers=prop_headers(client, "president")).json()
    assert s["units"] == 32 and s["occupied"] + s["vacant"] + s["to_let"] + s["to_let_pending"] == 32
    assert client.get("/api/units/summary", headers=prop_headers(client, "tenant")).status_code == 403


def test_tenant_cannot_add_people_owner_can_add_own_tenant_only(client):
    units = {u["number"]: u for u in client.get("/api/units", headers=prop_headers(client, "padmin")).json()}
    tenant_h = prop_headers(client, "tenant")
    assert client.post(f"/api/units/{units['A-101']['id']}/occupants", headers=tenant_h, json={"kind": "tenant", "name": "Some One"}).status_code == 403
    owner_h = prop_headers(client, "owner")
    other = client.post(f"/api/units/{units['A-102']['id']}/occupants", headers=owner_h, json={"kind": "tenant", "name": "Some One"})
    assert other.status_code == 403
    own = client.post(f"/api/units/{units['A-501']['id']}/occupants", headers=owner_h, json={"kind": "tenant", "name": "New Tenant", "phone": "01712345678"})
    assert own.status_code == 201
    tid = own.json()["unit"]["tenants"][0]["id"]
    assert client.post(f"/api/occupants/{tid}/move-out", headers=owner_h).status_code == 200


def test_one_tenant_per_flat(client):
    units = {u["number"]: u for u in client.get("/api/units", headers=prop_headers(client, "padmin")).json()}
    r = client.post(f"/api/units/{units['B-302']['id']}/occupants", headers=prop_headers(client, "padmin"), json={"kind": "tenant", "name": "Second Tenant"})
    assert r.status_code == 409


def test_to_let_needs_owner_approval(client):
    padmin, rep = prop_headers(client, "padmin"), prop_headers(client, "ownerrep")
    a801 = [u for u in client.get("/api/units", headers=padmin).json() if u["number"] == "A-801"][0]
    assert a801["status"] == "to_let_pending"
    assert client.post(f"/api/units/{a801['id']}/to-let/approve", headers=padmin).status_code == 403   # admin cannot approve for the owner
    ok = client.post(f"/api/units/{a801['id']}/to-let/approve", headers=rep)
    assert ok.status_code == 200 and ok.json()["status"] == "to_let"


def test_generate_is_idempotent(client):
    h = prop_headers(client, "agency", "Green Court")
    first = client.post("/api/units/generate", headers=h, json={"floors": 7, "blocks": ["A", "B"], "per_block": 2}).json()
    second = client.post("/api/units/generate", headers=h, json={"floors": 7, "blocks": ["A", "B"], "per_block": 2}).json()
    assert first["created"] == 4 and second["created"] == 0   # floor 7 is new (floors 1-6 were seeded)


def test_import_rows(client):
    h = prop_headers(client, "agency", "Lakeview Heights")
    r = client.post("/api/units/import", headers=h, json=[{"number": "PH-1", "floor": 11, "area_sqft": 2400, "owner_name": "Penthouse Owner", "owner_phone": "01711111111"}])
    assert r.json() == {"created": 1, "updated": 0}


def test_portfolio_for_agency_not_for_others(client):
    assert len(client.get("/api/portfolio", headers=login(client, "agency")[0]).json()) == 3
    assert client.get("/api/portfolio", headers=login(client, "padmin")[0]).status_code == 403
