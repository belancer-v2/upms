from datetime import date, datetime, timedelta, timezone

from sqlalchemy import select

from conftest import login
from test_property import prop_headers

D = lambda n: (date.today() + timedelta(days=n)).isoformat()


def hall(client, h):
    return [a for a in client.get("/api/amenities", headers=h).json() if a["kind"] == "hall"][0]


def req(client, h, aid, day, slot="evening", **kw):
    body = {"amenity_id": aid, "on_date": D(day), "slot": slot, "purpose": "birthday", "guests": 50, "contact": "01711000000", **kw}
    return client.post("/api/amenities/bookings", json=body, headers=h)


def test_double_booking_is_prevented_by_db_and_api(client):
    ht, ho, hp = prop_headers(client, "tenant"), prop_headers(client, "ownerrep"), prop_headers(client, "secretary")
    a = hall(client, ht)
    r1, r2 = req(client, ht, a["id"], 60), req(client, ho, a["id"], 60)
    assert r1.status_code == 201 and r2.status_code == 201                  # both may ask; only one can win
    assert req(client, ht, a["id"], 60, "night").status_code == 409         # one open request per flat per date
    first = client.post(f"/api/amenities/bookings/{r1.json()['id']}/approve", headers=hp)
    assert first.status_code == 200 and first.json()["status"] == "approved"
    second = client.post(f"/api/amenities/bookings/{r2.json()['id']}/approve", headers=hp)
    assert second.status_code == 409 and "already booked" in second.json()["detail"]
    assert client.get(f"/api/amenities/bookings/{r2.json()['id']}", headers=ho).json()["status"] == "pending"
    assert req(client, ho, a["id"], 60, "full").status_code == 409          # a full day overlaps the held evening
    # the database itself refuses a second hold
    from app.db import SessionLocal
    from app.models.amenities import SlotHold
    import pytest
    from sqlalchemy.exc import IntegrityError
    with SessionLocal() as db:
        dup = db.scalar(select(SlotHold).where(SlotHold.booking_id == r1.json()["id"]))
        db.add(SlotHold(amenity_id=dup.amenity_id, on_date=dup.on_date, part=dup.part, booking_id=r2.json()["id"]))
        with pytest.raises(IntegrityError):
            db.flush()
        db.rollback()


def test_owner_pays_less_than_tenant_and_quote_matches_invoice(client):
    a = hall(client, prop_headers(client, "padmin"))
    q = lambda who: client.get("/api/amenities/quote", params={"amenity_id": a["id"], "on_date": D(62), "slot": "evening", "generator": True, "ext_hours": 1}, headers=prop_headers(client, who)).json()
    own, ten = q("ownerrep"), q("tenant")
    assert own["party"] == "owner" and ten["party"] == "tenant"
    assert own["fee"] == 1_200_000 and ten["fee"] == 1_500_000
    assert own["total"] == 1_200_000 + 150_000 + 150_000 + 300_000 + 1_000_000        # rent + 1 extra hour + cleaning + generator + deposit
    assert ten["total"] - own["total"] == 300_000
    assert client.get("/api/amenities/quote", params={"amenity_id": a["id"], "on_date": D(62), "slot": "evening", "ext_hours": 5}, headers=prop_headers(client, "tenant")).status_code == 422


def test_blackout_notice_window_guests_and_roles(client):
    ht, hp, hpres = prop_headers(client, "tenant"), prop_headers(client, "padmin"), prop_headers(client, "president")
    a = hall(client, ht)
    assert req(client, ht, a["id"], 21).status_code == 422                  # seeded blackout (floor polishing)
    assert req(client, ht, a["id"], 1).status_code == 422                   # inside the 3 day notice
    assert req(client, ht, a["id"], 400).status_code == 422                 # beyond 90 days
    assert req(client, ht, a["id"], 66, guests=a["capacity"] + 1).status_code == 422
    assert req(client, ht, a["id"], 66, "morning", ext_hours=9).status_code == 422
    assert client.post("/api/amenities/blackouts", json={"on_date": D(67)}, headers=ht).status_code == 403
    b = client.post("/api/amenities/blackouts", json={"on_date": D(67), "amenity_id": a["id"], "reason": "Eid prayers"}, headers=hpres)
    assert b.status_code == 201
    assert client.post("/api/amenities/blackouts", json={"on_date": D(67), "amenity_id": a["id"]}, headers=hpres).status_code == 409
    assert req(client, ht, a["id"], 67).status_code == 422
    cal = client.get(f"/api/amenities/{a['id']}/calendar", params={"month": D(67)[:7]}, headers=ht).json()
    assert [d for d in cal["days"] if d["date"] == D(67)][0]["blackout"]["reason"] == "Eid prayers"
    assert client.delete(f"/api/amenities/blackouts/{b.json()['id']}", headers=hpres).status_code == 204
    assert req(client, ht, a["id"], 67, "morning").status_code == 201
    # a committee member who is not a resident cannot book; guard cannot approve
    assert req(client, prop_headers(client, "treasurer"), a["id"], 68).status_code == 403


def test_approval_invoice_payment_confirms_and_lands_in_4020(client):
    ht, hs, htr, hg, hp = (prop_headers(client, w) for w in ("tenant", "secretary", "treasurer", "guard", "padmin"))
    a = hall(client, ht)
    tb0 = {r["code"]: r for r in client.get("/api/finance/trial-balance", headers=htr).json()["rows"]}
    b = req(client, ht, a["id"], 72, "night", use_generator=True).json()
    assert client.post(f"/api/amenities/bookings/{b['id']}/approve", headers=ht).status_code == 403
    assert client.post(f"/api/amenities/bookings/{b['id']}/reject", json={"reason": ""}, headers=hs).status_code == 422
    ap = client.post(f"/api/amenities/bookings/{b['id']}/approve", headers=hs).json()
    assert ap["status"] == "approved" and ap["total"] == 1_500_000 + 150_000 + 300_000 + 1_000_000 and ap["invoice_id"]
    inv = client.get(f"/api/billing/invoices/{ap['invoice_id']}", headers=ht).json()
    assert inv["period"] == f"HALL-{b['id']}" and inv["total"] == ap["total"] == sum(l["amount"] for l in inv["lines"]) and len(inv["lines"]) == 4
    assert client.get("/api/amenities/bookings", params={"scope": "mine"}, headers=ht).json()["items"][0]["balance"] > 0
    # a part payment keeps it waiting, the full payment confirms it
    assert client.post(f"/api/billing/invoices/{inv['id']}/payments", json={"amount": 100_000, "method": "cash"}, headers=htr).status_code == 201
    assert client.get(f"/api/amenities/bookings/{b['id']}", headers=ht).json()["status"] == "approved"
    assert client.get(f"/api/amenities/bookings/{b['id']}/permit", headers=hg).status_code == 409
    assert client.post(f"/api/billing/invoices/{inv['id']}/payments", json={"amount": ap["total"] - 100_000, "method": "cash"}, headers=htr).status_code == 201
    done = client.get(f"/api/amenities/bookings/{b['id']}", headers=ht).json()
    assert done["status"] == "confirmed" and done["balance"] == 0
    permit = client.get(f"/api/amenities/bookings/{b['id']}/permit", headers=hg).json()
    assert permit["unit"] == "B-302" and permit["permit_no"].startswith("PM-") and permit["slot"] == "night"
    assert client.get(f"/api/amenities/bookings/{b['id']}/permit", headers=prop_headers(client, "ownerrep")).status_code == 404
    # ledger: fees to 4020, deposit to 2010, and the books still balance
    tb = client.get("/api/finance/trial-balance", headers=htr).json()
    rows = {r["code"]: r for r in tb["rows"]}
    assert rows["4020"]["credit"] - tb0.get("4020", {"credit": 0})["credit"] == ap["total"] - 1_000_000
    assert rows["2010"]["credit"] - tb0.get("2010", {"credit": 0})["credit"] == 1_000_000
    assert tb["debit"] == tb["credit"]
    # SMS notices were sent for approval and confirmation
    tpl = {m["template"] for m in client.get("/api/billing/messages", headers=hp).json()}
    assert {"booking_approved", "booking_confirmed"} <= tpl
    # nobody can take that night now
    assert req(client, prop_headers(client, "ownerrep"), a["id"], 72, "night").status_code == 409


def test_unpaid_approval_expires_and_frees_the_slot(client):
    ho, hs, ht = prop_headers(client, "ownerrep"), prop_headers(client, "secretary"), prop_headers(client, "tenant")
    a = hall(client, ho)
    b = req(client, ho, a["id"], 76).json()
    ap = client.post(f"/api/amenities/bookings/{b['id']}/approve", headers=hs).json()
    assert req(client, ht, a["id"], 76).status_code == 409
    from app.db import SessionLocal
    from app.models.amenities import Booking
    with SessionLocal() as db:
        db.get(Booking, b["id"]).expires_at = datetime.now(timezone.utc) - timedelta(hours=1)
        db.commit()
    got = client.get(f"/api/amenities/bookings/{b['id']}", headers=ho)
    assert client.get("/api/amenities/bookings", headers=ho).status_code == 200      # listing runs the expiry
    got = client.get(f"/api/amenities/bookings/{b['id']}", headers=ho).json()
    assert got["status"] == "expired" and got["invoice_status"] == "void"
    assert req(client, ht, a["id"], 76).status_code == 201                           # the slot is free again


def test_cancel_refund_and_handover(client):
    ho, hs, htr, hc = prop_headers(client, "owner"), prop_headers(client, "secretary"), prop_headers(client, "treasurer"), prop_headers(client, "caretaker")
    a = hall(client, ho)
    # cancel 20 days ahead: fees back in full once paid
    b = req(client, ho, a["id"], 80).json()
    ap = client.post(f"/api/amenities/bookings/{b['id']}/approve", headers=hs).json()
    client.post(f"/api/billing/invoices/{ap['invoice_id']}/payments", json={"amount": ap["total"], "method": "bank"}, headers=htr)
    c = client.post(f"/api/amenities/bookings/{b['id']}/cancel", json={"reason": "Plans changed"}, headers=ho).json()
    assert c["status"] == "cancelled" and c["refund_amount"] == ap["total"]
    assert client.post(f"/api/amenities/bookings/{b['id']}/refund", json={"method": "bank"}, headers=ho).status_code == 403
    assert client.post(f"/api/amenities/bookings/{b['id']}/refund", json={"method": "bank"}, headers=htr).json()["refunded_at"]
    # handover: needs a confirmed booking whose day has come; damage is deducted from the deposit
    b2 = req(client, ho, a["id"], 81, "morning").json()
    ap2 = client.post(f"/api/amenities/bookings/{b2['id']}/approve", headers=hs).json()
    client.post(f"/api/billing/invoices/{ap2['invoice_id']}/payments", json={"amount": ap2["total"], "method": "cash"}, headers=htr)
    assert client.post(f"/api/amenities/bookings/{b2['id']}/handover", json={}, headers=hc).status_code == 409          # event is in the future
    from app.db import SessionLocal
    from app.models.amenities import Booking, SlotHold
    with SessionLocal() as db:
        db.get(Booking, b2["id"]).on_date = date.today() - timedelta(days=1)
        db.commit()
    assert client.post(f"/api/amenities/bookings/{b2['id']}/handover", json={"damage_amount": 99_999_999}, headers=hc).status_code == 422
    assert client.post(f"/api/amenities/bookings/{b2['id']}/handover", json={}, headers=ho).status_code == 403
    h = client.post(f"/api/amenities/bookings/{b2['id']}/handover", json={"damage_amount": 250_000, "damage_note": "Broken chairs", "refund_method": "cash"}, headers=hc).json()
    assert h["status"] == "completed" and h["refund_amount"] == 1_000_000 - 250_000 and h["damage_amount"] == 250_000
    with SessionLocal() as db:   # tidy: this booking now sits in the past
        for s in db.scalars(select(SlotHold).where(SlotHold.booking_id == b2["id"])):
            db.delete(s)
        db.commit()


def test_resident_sees_only_own_bookings_and_staff_see_all(client):
    ho, ht, hp, hg = (prop_headers(client, w) for w in ("ownerrep", "tenant", "padmin", "guard"))
    a = hall(client, ho)
    mine = client.get("/api/amenities/bookings", params={"scope": "all", "size": 100}, headers=ho).json()
    assert mine["total"] > 0 and {b["unit"] for b in mine["items"]} == {"A-801"}
    ten = client.get("/api/amenities/bookings", params={"scope": "all", "size": 100}, headers=ht).json()
    assert {b["unit"] for b in ten["items"]} == {"B-302"}
    allb = client.get("/api/amenities/bookings", params={"scope": "all", "size": 100}, headers=hp).json()
    assert {"A-801", "B-302", "A-501"} <= {b["unit"] for b in allb["items"]} and allb["total"] >= 8
    other = [b for b in allb["items"] if b["unit"] == "B-302"][0]
    assert client.get(f"/api/amenities/bookings/{other['id']}", headers=ho).status_code == 404
    assert client.post(f"/api/amenities/bookings/{other['id']}/cancel", json={}, headers=ho).status_code == 404
    assert client.get("/api/amenities/bookings", params={"scope": "all"}, headers=hg).status_code == 200
    page = client.get("/api/amenities/bookings", params={"scope": "all", "size": 3, "page": 2}, headers=hp).json()
    assert len(page["items"]) == 3 and page["size"] == 3
    # calendar hides who booked: a resident sees the state, not the booking id of other flats
    cal = client.get(f"/api/amenities/{a['id']}/calendar", params={"month": D(9)[:7]}, headers=ho).json()
    cell = [d for d in cal["days"] if d["date"] == D(9)][0]["slots"]["evening"]
    assert cell["state"] == "booked" and cell["booking_id"] is None and not cell["mine"]


def test_settings_edit_and_plan_gate(client):
    hp, ht = prop_headers(client, "padmin"), prop_headers(client, "tenant")
    a = hall(client, hp)
    body = {k: a[k] for k in ("kind", "name", "name_bn", "capacity", "rules", "rules_bn", "photo_url", "active", "slots", "ext_hour_fee", "max_ext_hours", "deposit", "cleaning_fee", "generator_fee", "free_quota", "min_notice_days", "max_advance_days", "hold_days", "cancel_rules")}
    assert client.put(f"/api/amenities/{a['id']}", json={**body, "deposit": 1}, headers=ht).status_code == 403
    assert client.put(f"/api/amenities/{a['id']}", json={**body, "hold_days": 5}, headers=hp).json()["hold_days"] == 5
    assert client.put(f"/api/amenities/{a['id']}", json={**body, "min_notice_days": 90, "max_advance_days": 10}, headers=hp).status_code == 422
    client.put(f"/api/amenities/{a['id']}", json=body, headers=hp)
    r = client.post("/api/auth/login", json={"email": "admin2@customers.demo", "password": "demo1234"}).json()
    hb = {"Authorization": f"Bearer {r['token']}", "X-Property-Id": str(r["properties"][0]["id"])}
    assert client.get("/api/amenities", headers=hb).status_code == 402
    assert client.get("/api/amenities/bookings", headers=hb).status_code == 402


def test_free_quota_waives_the_slot_fee(client):
    ht = prop_headers(client, "owner2")
    roof = [a for a in client.get("/api/amenities", headers=ht).json() if a["kind"] == "rooftop"][0]
    ask = lambda h: client.get("/api/amenities/quote", params={"amenity_id": roof["id"], "on_date": D(30), "slot": "night"}, headers=h).json()
    fresh = ask(prop_headers(client, "ownerrep"))          # A-801 has not used its yearly free booking
    assert fresh["free"] is True and fresh["fee"] == 0 and fresh["total"] == 50_000 + 200_000       # only cleaning and deposit
    used = ask(ht)                                         # B-302 already has a free rooftop booking in the demo data
    assert used["free"] is False and used["fee"] == 300_000
