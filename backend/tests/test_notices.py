from conftest import login
from test_property import prop_headers


def test_audience_filtering(client):
    titles = lambda who: {n["title"] for n in client.get("/api/notices", headers=prop_headers(client, who)).json()}
    tenant, owner, pres = titles("tenant"), titles("owner2"), titles("president")
    assert any(t.startswith("Reminder for tenants") for t in tenant) and not any(t.startswith("Annual general") for t in tenant)
    assert any(t.startswith("Annual general") for t in owner) and not any(t.startswith("Reminder for tenants") for t in owner)
    assert any(t.startswith("Committee meeting") for t in pres) and not any(t.startswith("Committee meeting") for t in owner)


def test_publish_reach_and_link_read_proof(client):
    h = prop_headers(client, "secretary")
    r = client.post("/api/notices", json={"title": "Gate closed for repair", "body": "The main gate is closed on Sunday.", "audience": "all", "sms": True}, headers=h)
    assert r.status_code == 201 and r.json()["sms_sent"] > 0
    nid = r.json()["id"]
    reach = client.get(f"/api/notices/{nid}/reach", headers=h).json()
    assert len(reach["read"]) == 0 and len(reach["not_read"]) > 20
    token = None
    from app.db import SessionLocal
    from app.models.notice import Receipt
    from sqlalchemy import select
    with SessionLocal() as db:
        token = db.scalars(select(Receipt).where(Receipt.notice_id == nid)).first().token
    page = client.get(f"/api/notices/link/{token}")                      # no sign-in
    assert page.status_code == 200 and page.json()["title"] == "Gate closed for repair"
    after = client.get(f"/api/notices/{nid}/reach", headers=h).json()
    assert len(after["read"]) == 1 and after["read"][0]["via"] == "link"
    assert client.get("/api/notices/link/not-a-token").status_code == 404


def test_app_read_and_nudge_once_a_day(client):
    h, ht = prop_headers(client, "secretary"), prop_headers(client, "tenant")
    n = [x for x in client.get("/api/notices", headers=ht).json() if x["title"].startswith("Water supply")][0]
    assert not n["read"]
    assert client.post(f"/api/notices/{n['id']}/read", headers=ht).status_code == 200
    assert [x for x in client.get("/api/notices", headers=ht).json() if x["id"] == n["id"]][0]["read"]
    first = client.post(f"/api/notices/{n['id']}/nudge", headers=h).json()
    second = client.post(f"/api/notices/{n['id']}/nudge", headers=h).json()
    assert first["sent"] >= 0 and second["sent"] == 0


def test_roles_for_publishing(client):
    body = {"title": "Not allowed", "body": "A resident tries to publish."}
    assert client.post("/api/notices", json=body, headers=prop_headers(client, "tenant")).status_code == 403
    assert client.post("/api/notices", json=body, headers=prop_headers(client, "caretaker")).status_code == 403


def test_policy_versions_need_acceptance_again(client):
    hs, ho = prop_headers(client, "secretary"), prop_headers(client, "owner2")
    p = [x for x in client.get("/api/policies", headers=ho).json() if x["title"] == "Guest and parking policy"][0]
    assert p["accepted"] and p["version"] == 1
    v2 = client.post(f"/api/policies/{p['id']}/versions", json={"body": "Visitor cars may stay up to 2 hours only.", "change_note": "Shorter stay"}, headers=hs).json()
    assert v2["version"] == 2
    mine = [x for x in client.get("/api/policies", headers=ho).json() if x["id"] == p["id"]][0]
    assert not mine["accepted"] and mine["accepted_before"]
    assert client.post(f"/api/policies/{p['id']}/accept", headers=ho).json()["accepted"]
    hist = client.get(f"/api/policies/{p['id']}/history", headers=hs).json()
    assert [v["version"] for v in hist["versions"]] == [2, 1] and hist["pending"]
    assert client.post(f"/api/policies/{p['id']}/versions", json={"body": "A tenant edits the policy text."}, headers=prop_headers(client, "tenant")).status_code == 403
