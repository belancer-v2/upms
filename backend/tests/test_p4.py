"""P4 gap closure: photo after create, plan email credits, subscription cancel flow, parking review flags, hall reminder wording."""
from datetime import timedelta

from sqlalchemy import select

from app.db import SessionLocal
from app.models.core import now
from app.models.parking import ParkingSlot, Vehicle
from app.models.saas import CancellationRequest
from conftest import login
from test_property import prop_headers

PNG = bytes.fromhex("89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4890000000d49444154789c6360000002000001e221bc330000000049454e44ae426082")


def _signup(client, email, name="Plan Tester"):
    r = client.post("/api/public/signup", json={"name": name, "email": email, "password": "longpass1", "building": f"Villa {email}", "flats": 12, "plan": "standard", "city": "Dhaka"})
    assert r.status_code == 201, r.text
    d = r.json()
    return {"Authorization": f"Bearer {d['token']}", "X-Property-Id": str(d["properties"][0]["id"])}, d["properties"][0]["org_id"]


def test_new_person_can_get_a_photo_right_after_create(client):
    h, _ = _signup(client, "photo1@x.test")
    uid = client.post("/api/units", headers=h, json={"floor": 1, "number": "P-1"}).json()["id"]
    r = client.post(f"/api/units/{uid}/occupants", headers=h, json={"kind": "tenant", "name": "Photo Person"})
    assert r.status_code == 201 and r.json()["occupant_id"]
    up = client.post(f"/api/profiles/occupant/{r.json()['occupant_id']}/photo", headers=h, files={"file": ("p.png", PNG, "image/png")})
    assert up.status_code == 200, up.text


def test_plans_editor_saves_email_credits(client):
    hs, _ = login(client, "super")
    plans = client.get("/api/saas/plans", headers=hs).json()["plans"]
    p = next(x for x in plans if x["key"] == "standard")
    body = {"monthly": p["monthly"], "setup": p["setup"], "sms_included": p["sms_included"], "email_included": {"S": 100, "M": 250, "L": 500}, "features": p["features"]}
    assert client.put("/api/saas/plans/standard", headers=hs, json=body).status_code == 200
    assert next(x for x in client.get("/api/saas/plans", headers=hs).json()["plans"] if x["key"] == "standard")["email_included"] == {"S": 100, "M": 250, "L": 500}
    assert "maintenance" in p["features"]   # maintenance contracts are part of Standard


def test_cancel_request_approve_grace_then_read_only(client):
    h, org = _signup(client, "cancel1@x.test")
    hs, _ = login(client, "super")
    assert client.post("/api/plan/cancel-request", headers=h, json={"reason": "x"}).status_code == 422
    r = client.post("/api/plan/cancel-request", headers=h, json={"reason": "We are moving to another system"})
    assert r.status_code == 201 and r.json()["status"] == "pending"
    assert client.post("/api/plan/cancel-request", headers=h, json={"reason": "again please"}).status_code == 409
    assert client.get("/api/plan", headers=h).json()["request"]["status"] == "pending"
    # only a building admin can ask; saas staff other than admin cannot decide
    assert client.get("/api/plan", headers=prop_headers(client, "caretaker")).status_code == 403
    assert client.get("/api/saas/cancellations", headers=login(client, "sales")[0]).status_code == 403
    pend = [x for x in client.get("/api/saas/cancellations", params={"status": "pending"}, headers=hs).json() if x["org_id"] == org]
    assert len(pend) == 1 and pend[0]["requested_by"] == "Plan Tester"
    assert any(x["org_id"] == org for x in client.get("/api/saas/overview", headers=hs).json()["cancel_requests"])
    # withdraw then ask again
    assert client.delete("/api/plan/cancel-request", headers=h).json()["status"] == "withdrawn"
    assert client.delete("/api/plan/cancel-request", headers=h).status_code == 404
    client.post("/api/plan/cancel-request", headers=h, json={"reason": "Budget cut this year"})
    rid = [x for x in client.get("/api/saas/cancellations", params={"status": "pending"}, headers=hs).json() if x["org_id"] == org][0]["id"]
    ok = client.post(f"/api/saas/cancellations/{rid}/decide", headers=hs, json={"approve": True, "note": "Sorry to see you go"})
    assert ok.status_code == 200 and ok.json()["status"] == "approved"
    assert client.post(f"/api/saas/cancellations/{rid}/decide", headers=hs, json={"approve": False}).status_code == 409
    d = client.get(f"/api/saas/orgs/{org}", headers=hs).json()
    assert d["sub_status"] == "cancelled" and d["cancellation"]["status"] == "approved"
    # history event written
    from app.models.saas_reports import SubscriptionEvent
    with SessionLocal() as db:
        ev = db.scalars(select(SubscriptionEvent).where(SubscriptionEvent.org_id == org, SubscriptionEvent.kind == "cancel")).all()
        assert len(ev) == 1 and ev[0].mrr == 0 and ev[0].status == "cancelled"
    # 30 days of normal use: writes still work, the plan page shows the countdown and export works
    plan = client.get("/api/plan", headers=h).json()
    assert plan["cancelled"]["readonly"] is False and 28 <= plan["cancelled"]["days_left"] <= 30
    assert client.post("/api/units", headers=h, json={"floor": 1, "number": "G-1"}).status_code == 201
    z = client.get("/api/plan/export", headers=h)
    assert z.status_code == 200 and z.headers["content-type"] == "application/zip" and z.content[:2] == b"PK"
    # after the window the data is read-only: reads and export work, writes are refused
    with SessionLocal() as db:
        req = db.get(CancellationRequest, rid)
        req.decided_at = now() - timedelta(days=31)
        db.commit()
    assert client.get("/api/plan", headers=h).json()["cancelled"]["readonly"] is True
    assert client.get("/api/units", headers=h).status_code == 200
    assert client.get("/api/plan/export", headers=h).status_code == 200
    ro = client.post("/api/units", headers=h, json={"floor": 1, "number": "G-2"})
    assert ro.status_code == 403 and "read-only" in ro.json()["detail"]
    # FlatWise can reactivate
    assert client.post(f"/api/saas/orgs/{org}/status", headers=hs, json={"status": "active"}).status_code == 200
    assert client.post("/api/units", headers=h, json={"floor": 1, "number": "G-2"}).status_code == 201


def test_saas_admin_can_end_a_subscription_directly(client):
    h, org = _signup(client, "cancel2@x.test")
    hs, _ = login(client, "super")
    assert client.post(f"/api/saas/orgs/{org}/cancel", headers=login(client, "sales")[0], json={"reason": "Customer asked"}).status_code == 403
    assert client.post(f"/api/saas/orgs/{org}/cancel", headers=hs, json={"reason": "Customer asked by phone"}).status_code == 200
    assert client.post(f"/api/saas/orgs/{org}/cancel", headers=hs, json={"reason": "Customer asked by phone"}).status_code == 409
    assert client.get(f"/api/saas/orgs/{org}", headers=hs).json()["sub_status"] == "cancelled"
    assert client.get("/api/plan", headers=h).json()["cancelled"] is not None


def test_taking_back_a_slot_flags_vehicles_that_no_longer_fit(client):
    h, _ = _signup(client, "parking1@x.test")
    # a fresh flat with two car slots and two cars
    u = client.post("/api/units", headers=h, json={"floor": 9, "number": "PK-1", "cars_per_flat": 2})
    assert u.status_code == 201
    uid = u.json()["id"]
    for plate in ("DHAKA METRO GA 11-1111", "DHAKA METRO GA 11-2222"):
        assert client.post("/api/parking/vehicles", headers=h, json={"unit_id": uid, "reg_no": plate, "kind": "car"}).status_code == 201
    slots = client.get(f"/api/parking/units/{uid}", headers=h).json()["slots"]
    r = client.post(f"/api/parking/slots/{slots[1]['id']}/unallocate", headers=h)
    assert r.status_code == 200 and r.json()["vehicles_to_review"] == 1
    vs = client.get(f"/api/parking/units/{uid}", headers=h).json()["vehicles"]
    assert sorted(v["status"] for v in vs) == ["active", "to_review"]
    assert [v["reg_no"] for v in vs if v["status"] == "to_review"] == ["DHAKA METRO GA 11-2222"]    # the newest one is flagged
    # moving a slot to another flat flags the flat that lost it
    other = client.post("/api/units", headers=h, json={"floor": 9, "number": "PK-2", "cars_per_flat": 0}).json()["id"]
    r = client.post(f"/api/parking/slots/{slots[0]['id']}/allocate", headers=h, json={"unit_id": other})
    assert r.status_code == 200 and r.json()["vehicles_to_review"] == 1
    assert all(v["status"] == "to_review" for v in client.get(f"/api/parking/units/{uid}", headers=h).json()["vehicles"])
    # a free slot given out and taken back with no vehicle flags nothing
    assert client.post(f"/api/parking/slots/{slots[0]['id']}/unallocate", headers=h).json()["vehicles_to_review"] == 0


def test_hall_reminder_wording():
    from app.routers.billing import _text
    for lang in ("en", "bn"):
        for step in ("before", "due", "o7", "o15", "o30"):
            hall = _text(step, lang, "Sunrise", "BDT 5,000", "HALL-12", "10 Oct", hall=True)
            fee = _text(step, lang, "Sunrise", "BDT 5,000", "2026-10", "10 Oct")
            assert "HALL-12" not in hall and "12" in hall
            assert ("service charge" not in hall.lower()) and ("সার্ভিস চার্জ" not in hall)
            assert ("hall booking" in hall) if lang == "en" else ("হল বুকিং" in hall)
            assert "BDT 5,000" in hall and "2026-10" in fee
