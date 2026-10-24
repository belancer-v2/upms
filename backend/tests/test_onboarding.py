import datetime

from conftest import login
from test_property import prop_headers

PNG = bytes.fromhex("89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4890000000d49444154789c6360000002000001e221bc330000000049454e44ae426082")


def free_unit(client, h):
    units = client.get("/api/units", headers=h).json()
    return [u for u in units if u["status"] == "to_let" and not u["tenants"]]


def test_full_flow_from_invite_to_police_receipt(client):
    ha = prop_headers(client, "padmin")
    cases = client.get("/api/onboarding/cases", headers=ha).json()
    open_units = {c["unit_id"] for c in cases if c["status"] in ("invited", "review", "verified", "police")}
    u = [x for x in client.get("/api/units", headers=ha).json() if x["status"] == "to_let" and x["id"] not in open_units]
    if not u:   # the owner of a vacant flat has approved letting (set directly, that step belongs to M3)
        from app.db import SessionLocal
        from app.models.property import Unit
        v = [x for x in client.get("/api/units", headers=ha).json() if x["status"] == "vacant" and not x["tenants"] and x["id"] not in open_units][0]
        with SessionLocal() as db:
            db.get(Unit, v["id"]).status = "to_let"
            db.commit()
        u = [v]
    r = client.post("/api/onboarding/cases", json={"unit_id": u[0]["id"], "name": "Test Tenant", "phone": "01700001111", "rent": 2500000, "advance": 5000000, "start_date": "2026-12-01"}, headers=ha)
    assert r.status_code == 201, r.text
    case = r.json()
    tok = case["token"]
    assert case["status"] == "invited" and client.get(f"/api/onboarding/link/{tok}").status_code == 200
    # incomplete form cannot be sent
    assert client.post(f"/api/onboarding/link/{tok}/submit").status_code == 422
    body = {"father_name": "A", "permanent_address": "Village X", "profession": "Teacher", "nid": "12", "emergency_name": "B", "emergency_phone": "017", "reference_name": "C", "reference_phone": "018"}
    assert client.put(f"/api/onboarding/link/{tok}", json=body).status_code == 422          # bad NID length
    body["nid"] = "1992456789012"
    assert client.put(f"/api/onboarding/link/{tok}", json=body).status_code == 200
    bad = client.post(f"/api/onboarding/link/{tok}/docs", data={"kind": "photo"}, files={"file": ("a.txt", b"hello", "text/plain")})
    assert bad.status_code == 422
    big = client.post(f"/api/onboarding/link/{tok}/docs", data={"kind": "photo"}, files={"file": ("a.png", b"0" * (3 * 1024 * 1024 + 5), "image/png")})
    assert big.status_code == 413
    for k in ("nid_front", "nid_back", "photo"):
        assert client.post(f"/api/onboarding/link/{tok}/docs", data={"kind": k}, files={"file": (f"{k}.png", PNG, "image/png")}).status_code == 201
    assert client.post(f"/api/onboarding/link/{tok}/submit").json()["status"] == "review"
    assert client.put(f"/api/onboarding/link/{tok}", json=body).status_code == 423           # locked once sent
    # staff
    assert client.post(f"/api/onboarding/cases/{case['id']}/verify", headers=ha).status_code == 422   # documents not accepted yet
    full = client.get(f"/api/onboarding/cases/{case['id']}", headers=ha).json()
    for d in full["docs"]:
        assert client.post(f"/api/onboarding/cases/{case['id']}/docs/{d['id']}/review", json={"status": "accepted"}, headers=ha).status_code == 200
    assert client.get(f"/api/onboarding/cases/{case['id']}/docs/{full['docs'][0]['id']}/file", headers=ha).status_code == 200
    assert client.get(f"/api/onboarding/cases/{case['id']}/pack", headers=ha).status_code == 422       # not verified yet
    assert client.post(f"/api/onboarding/cases/{case['id']}/verify", headers=ha).json()["status"] == "verified"
    pack = client.get(f"/api/onboarding/cases/{case['id']}/pack", headers=ha).json()
    assert pack["tenant"]["nid"] == "1992456789012" and pack["unit"]
    assert client.post(f"/api/onboarding/cases/{case['id']}/done", json={"receipt_no": "X1"}, headers=ha).status_code == 422
    assert client.post(f"/api/onboarding/cases/{case['id']}/police", json={"reference_no": "DMP/1", "submitted_on": datetime.date.today().isoformat()}, headers=ha).json()["status"] == "police"
    assert client.post(f"/api/onboarding/cases/{case['id']}/done", json={"receipt_no": "RCPT-9"}, headers=ha).json()["status"] == "done"
    assert any(x["name"] == "Test Tenant" for x in client.get("/api/people", headers=ha).json())


def test_rejected_document_goes_back_to_tenant(client):
    ha = prop_headers(client, "padmin")
    case = [c for c in client.get("/api/onboarding/cases", headers=ha).json() if c["status"] == "review" and c["name"] == "Mizanur Rahman"][0]
    full = client.get(f"/api/onboarding/cases/{case['id']}", headers=ha).json()
    r = client.post(f"/api/onboarding/cases/{case['id']}/docs/{full['docs'][0]['id']}/review", json={"status": "rejected", "note": "Photo is blurred"}, headers=ha).json()
    assert r["status"] == "invited" and any(d["status"] == "rejected" for d in r["docs"])


def test_roles_and_rules(client):
    assert client.get("/api/onboarding/cases", headers=prop_headers(client, "tenant")).status_code == 403
    ha = prop_headers(client, "padmin")
    vacant = [x for x in client.get("/api/units", headers=ha).json() if x["status"] == "occupied" and x["tenants"]][0]
    r = client.post("/api/onboarding/cases", json={"unit_id": vacant["id"], "name": "Someone", "phone": "01700000000", "rent": 100, "start_date": "2026-12-01"}, headers=ha)
    assert r.status_code == 422                                   # flat already has a tenant, or owner has not approved
    assert client.get("/api/onboarding/link/nope").status_code == 404
