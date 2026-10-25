from datetime import date, timedelta

from app.models.contracts import Contract
from app.routers.contracts import flags
from conftest import login
from test_property import prop_headers

PDF = b"%PDF-1.4 test"
C = "/api/contracts"


def _c(start, end, every=90, status="active"):
    return Contract(kind="lift", title="t", start_date=start, end_date=end, interval_days=every, status=status)


def test_flags_renewal_visit_and_expiry():
    today = date(2026, 10, 25)
    f = flags(_c(today - timedelta(days=200), today + timedelta(days=60)), today - timedelta(days=10), today)
    assert f["renewal_due"] is True and f["days_left"] == 60 and f["visit_overdue"] is False and f["next_due"] == (today + timedelta(days=80)).isoformat()
    assert flags(_c(today - timedelta(days=200), today + timedelta(days=61)), None, today)["renewal_due"] is False          # alert starts 60 days before
    f = flags(_c(today - timedelta(days=200), today + timedelta(days=100), every=30), today - timedelta(days=40), today)
    assert f["visit_overdue"] is True and f["renewal_due"] is False
    f = flags(_c(today - timedelta(days=400), today - timedelta(days=1)), today - timedelta(days=100), today)
    assert f["expired"] is True and f["renewal_due"] is False and f["next_due"] is None and f["visit_overdue"] is False
    assert flags(_c(today, today + timedelta(days=30), status="ended"), None, today)["renewal_due"] is False
    assert flags(_c(today - timedelta(days=30), today + timedelta(days=300), every=40), today - timedelta(days=30), today)["visit_due_soon"] is True


def test_seed_and_access(client):
    h = prop_headers(client, "padmin")
    s = client.get(f"{C}/summary", headers=h).json()
    assert s["active"] == 5 and s["renewal"] == 3 and s["expired"] == 1 and s["visit_overdue"] >= 1 and s["annual_cost"] > 0
    lst = client.get(C, headers=h).json()
    assert lst["total"] == 5 and {r["kind"] for r in lst["items"]} == {"lift", "generator", "cctv", "fire", "pest"}
    assert client.get(C, params={"q": "lift"}, headers=h).json()["total"] >= 1
    assert client.get(C, params={"size": 2, "page": 2}, headers=h).json()["items"].__len__() == 2
    for who, code in (("president", 200), ("auditor", 200), ("caretaker", 200), ("tenant", 403), ("guard", 403), ("owner2", 403)):
        assert client.get(C, headers=prop_headers(client, who)).status_code == code, who
    assert client.get(C, headers=prop_headers(client, "agency", "Lakeview Heights")).json()["total"] == 0                      # per building
    # Lakeview is on the Pro plan too, but a Basic building has no contracts screen
    h2, d = login(client, "super")
    assert client.get(C).status_code in (400, 401)


def _fresh(client, email):
    r = client.post("/api/public/signup", json={"name": "Contract Admin", "email": email, "password": "longpass1", "building": f"Villa {email}", "flats": 12, "plan": "standard", "city": "Dhaka"})
    assert r.status_code == 201, r.text
    d = r.json()
    return {"Authorization": f"Bearer {d['token']}", "X-Property-Id": str(d["properties"][0]["id"])}


def test_lifecycle_in_a_building_of_its_own(client):
    h = _fresh(client, "contracts1@x.test")                     # a building of its own, so the shared demo data keeps its counts
    body = {"kind": "fire", "title": "Hydrant service", "vendor_name": "Hydrant Co", "start_date": date.today().isoformat(), "end_date": (date.today() + timedelta(days=365)).isoformat(), "annual_cost": 5000000}
    assert client.post(C, headers=h, json={**body, "end_date": (date.today() - timedelta(days=1)).isoformat()}).status_code == 422
    assert client.post(C, headers=h, json={**body, "vendor_name": ""}).status_code == 422
    assert client.post(C, headers=h, json={**body, "vendor_id": 999999}).status_code == 422
    c = client.post(C, headers=h, json=body)
    assert c.status_code == 201 and c.json()["renewal_due"] is False
    cid = c.json()["id"]
    assert client.put(f"{C}/{cid}", headers=h, json={"annual_cost": 6000000, "interval_days": 60}).json()["annual_cost"] == 6000000
    assert client.post(f"{C}/{cid}/visits", headers=h, json={"visited_on": (date.today() + timedelta(days=2)).isoformat()}).status_code == 422     # no future dates
    v = client.post(f"{C}/{cid}/visits", headers=h, json={"technician": "Mizan", "notes": "All extinguishers checked", "cost": 250000})
    assert v.status_code == 201
    vid = v.json()["id"]
    d = client.get(f"{C}/{cid}", headers=h).json()
    assert d["last_visit"] == date.today().isoformat() and d["next_due"] == (date.today() + timedelta(days=60)).isoformat() and d["visit_list"][0]["technician"] == "Mizan"
    assert d["can_log"] is True and d["can_write"] is True
    # documents: type and content are checked
    assert client.post(f"{C}/{cid}/docs", headers=h, data={"kind": "report", "visit_id": vid}, files={"file": ("r.pdf", PDF, "application/pdf")}).status_code == 201
    assert client.post(f"{C}/{cid}/docs", headers=h, data={"kind": "report"}, files={"file": ("r.gif", b"GIF89a", "image/gif")}).status_code == 422
    assert client.post(f"{C}/{cid}/docs", headers=h, data={"kind": "report"}, files={"file": ("r.pdf", b"not a pdf", "application/pdf")}).status_code == 422
    docs = client.get(f"{C}/{cid}", headers=h).json()["docs"]
    assert len(docs) == 1 and docs[0]["visit_id"] == vid
    got = client.get(f"{C}/{cid}/docs/{docs[0]['id']}", headers=h)
    assert got.status_code == 200 and got.content == PDF
    assert client.get(f"{C}/{cid}/docs/{docs[0]['id']}", headers=prop_headers(client, "padmin")).status_code == 404       # another building cannot read it
    # expense linkage: a pending finance expense, once per visit
    e = client.post(f"{C}/{cid}/visits/{vid}/expense", headers=h)
    assert e.status_code == 201 and e.json()["amount"] == 250000
    exp = [x for x in client.get("/api/finance/expenses", headers=h).json() if x["id"] == e.json()["expense_id"]][0]
    assert exp["status"] == "pending" and exp["category"] == "services" and exp["amount"] == 250000 and "service visit" in exp["title"]
    assert client.post(f"{C}/{cid}/visits/{vid}/expense", headers=h).status_code == 409
    assert client.delete(f"{C}/{cid}/visits/{vid}", headers=h).status_code == 409                                  # linked to an expense
    # a visit with no cost needs an amount
    v2 = client.post(f"{C}/{cid}/visits", headers=h, json={"notes": "covered by AMC"}).json()["id"]
    assert client.post(f"{C}/{cid}/visits/{v2}/expense", headers=h).status_code == 422
    assert client.post(f"{C}/{cid}/visits/{v2}/expense", headers=h, json={"amount": 120000}).status_code == 201
    assert client.delete(f"{C}/{cid}/visits/{v2}", headers=h).status_code == 409
    v3 = client.post(f"{C}/{cid}/visits", headers=h, json={"notes": "wrong entry"}).json()["id"]
    assert client.delete(f"{C}/{cid}/visits/{v3}", headers=h).status_code == 200
    # end the contract: the renewal alert disappears; documents can be removed
    assert client.put(f"{C}/{cid}", headers=h, json={"status": "ended"}).json()["renewal_due"] is False
    assert client.delete(f"{C}/{cid}/docs/{docs[0]['id']}", headers=h).status_code == 200
    assert client.get(C, params={"status": "ended"}, headers=h).json()["total"] == 1


def test_roles_on_the_seeded_contracts(client):
    h, hc, hp, ht = prop_headers(client, "padmin"), prop_headers(client, "caretaker"), prop_headers(client, "president"), prop_headers(client, "secretary")
    cid = client.get(C, params={"kind": "lift"}, headers=h).json()["items"][0]["id"]
    body = {"kind": "fire", "title": "Not allowed", "vendor_name": "X Co", "start_date": date.today().isoformat(), "end_date": (date.today() + timedelta(days=30)).isoformat()}
    assert client.post(C, headers=hc, json=body).status_code == 403                                                # the caretaker cannot create contracts
    assert client.post(C, headers=hp, json=body).status_code == 403                                                # nor can the president
    assert client.put(f"{C}/{cid}", headers=hc, json={"annual_cost": 1}).status_code == 403
    assert client.get(f"{C}/{cid}", headers=hc).json()["can_log"] is True and client.get(f"{C}/{cid}", headers=hc).json()["can_write"] is False
    assert client.get(f"{C}/{cid}", headers=hp).json()["can_log"] is False
    assert client.post(f"{C}/{cid}/visits", headers=hp, json={"notes": "x"}).status_code == 403
    vid = client.post(f"{C}/{cid}/visits", headers=hc, json={"technician": "Habib", "notes": "Spot check by the caretaker"}).json()["id"]    # the caretaker logs visits
    assert client.post(f"{C}/{cid}/visits/{vid}/expense", headers=hp, json={"amount": 5000}).status_code == 403    # the president cannot raise the expense
    assert client.delete(f"{C}/{cid}/visits/{vid}", headers=hc).status_code == 403
    assert client.delete(f"{C}/{cid}/visits/{vid}", headers=ht).status_code == 200                                   # the secretary can correct entries
    assert client.get(f"{C}/999999", headers=h).status_code == 404


def test_feature_gate_for_basic_plan(client):
    r = client.post("/api/public/signup", json={"name": "Basic Admin", "email": "basic-c@x.test", "password": "longpass1", "building": "Basic Villa", "flats": 8, "plan": "basic", "city": "Dhaka"})
    assert r.status_code == 201
    d = r.json()
    h = {"Authorization": f"Bearer {d['token']}", "X-Property-Id": str(d["properties"][0]["id"])}
    assert client.get(C, headers=h).status_code == 402
