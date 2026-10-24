from conftest import login


def test_plans_have_three_plans_and_bands(client):
    d = client.get("/api/public/plans").json()
    assert [p["key"] for p in d["plans"]] == ["basic", "standard", "pro"]
    assert [b["key"] for b in d["bands"]] == ["S", "M", "L", "XL"]
    std = [p for p in d["plans"] if p["key"] == "standard"][0]
    assert std["monthly"]["M"] == 450000  # BDT 4,500 in paisa


def test_lead_created(client):
    r = client.post("/api/public/leads", json={"name": "Test Committee", "phone": "01700000000", "flats": 40})
    assert r.status_code == 201


def test_signup_creates_trial_building_and_logs_in(client):
    r = client.post("/api/public/signup", json={"name": "New Admin", "email": "new@x.test", "password": "longpass1",
                    "building": "Moon Villa", "flats": 45, "plan": "standard"})
    assert r.status_code == 201, r.text
    d = r.json()
    assert d["properties"][0]["roles"] == ["PROPERTY_ADMIN"]
    again = client.post("/api/public/signup", json={"name": "Nn Nn", "email": "new@x.test", "password": "longpass1", "building": "Moon", "flats": 5})
    assert again.status_code == 409


def test_signup_rejects_short_password(client):
    r = client.post("/api/public/signup", json={"name": "A B", "email": "s@x.test", "password": "123", "building": "Villa", "flats": 5})
    assert r.status_code == 422
