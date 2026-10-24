from conftest import login


def test_health(client):
    assert client.get("/api/health").json()["ok"]


def test_login_wrong_password(client):
    r = client.post("/api/auth/login", json={"email": "owner@flatwise.demo", "password": "nope"})
    assert r.status_code == 401


def test_owner_has_two_roles(client):
    _, data = login(client, "owner")
    sunrise = [p for p in data["properties"] if p["name"] == "Sunrise Tower"][0]
    assert set(sunrise["roles"]) == {"FLAT_OWNER", "MEMBER"}


def test_agency_manager_sees_all_buildings(client):
    _, data = login(client, "agency")
    assert len(data["properties"]) == 3


def test_tenant_sees_one_building(client):
    _, data = login(client, "tenant")
    assert len(data["properties"]) == 1


def test_saas_staff_roles(client):
    for who, role in [("super", "SUPER_ADMIN"), ("finance", "SAAS_FINANCE"), ("sales", "SAAS_SALES"), ("support", "SAAS_USER")]:
        _, data = login(client, who)
        assert data["user"]["saas_role"] == role


def test_me_requires_login(client):
    assert client.get("/api/me").status_code == 401


def test_demo_accounts_listed(client):
    r = client.get("/api/auth/demo-accounts").json()
    assert r["enabled"] and len(r["accounts"]) >= 18
