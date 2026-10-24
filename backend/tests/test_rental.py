from datetime import date, timedelta
from types import SimpleNamespace as NS

from conftest import login
from test_property import prop_headers

PNG = bytes.fromhex("89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4890000000d49444154789c6360000002000001e221bc330000000049454e44ae426082")
PDF = b"%PDF-1.4\n%%EOF\n"


def flat(client, who, number):
    h = prop_headers(client, who)
    rows = client.get("/api/rental/flats", headers=h).json()
    return h, [r for r in rows if r["number"] == number]


def b302(client, who):
    h, rows = flat(client, who, "B-302")
    return h, rows[0]["unit_id"] if rows else None


def pay(client, h, uid, **kw):
    body = {"period": "2026-01", "amount": 1000000, "method": "cash", "paid_on": date.today().isoformat(), **kw}
    return client.post(f"/api/rental/units/{uid}/payments", json=body, headers=h)


def set_switch(client, h, uid, on):
    return client.put(f"/api/rental/units/{uid}/switch", json={"enabled": on}, headers=h)


def test_off_by_default_and_hidden_from_tenant(client):
    ho, rows = flat(client, "owner", "A-501")                 # Mahmud's flat: seeded OFF
    assert rows and rows[0]["enabled"] is False and rows[0]["side"] == "owner"
    uid = rows[0]["unit_id"]
    assert client.get(f"/api/rental/units/{uid}", headers=ho).status_code == 403     # the owner must switch it on first
    # tenant of B-302 sees nothing when the owner turns it off, and everything once it is on
    h2, u = b302(client, "owner2")
    ht = prop_headers(client, "tenant")
    assert [r["number"] for r in client.get("/api/rental/flats", headers=ht).json()] == ["B-302"]
    assert set_switch(client, ht, u, False).status_code == 403                        # a tenant cannot switch
    assert set_switch(client, h2, u, False).status_code == 200
    try:
        assert client.get("/api/rental/flats", headers=ht).json() == []
        assert client.get(f"/api/rental/units/{u}", headers=ht).status_code == 404
        assert pay(client, ht, u).status_code == 404
        assert client.get(f"/api/rental/units/{u}", headers=h2).status_code == 403
    finally:
        assert set_switch(client, h2, u, True).status_code == 200
    assert client.get(f"/api/rental/units/{u}", headers=ht).status_code == 200


def test_admin_and_committee_blocked_but_admin_sees_switch(client):
    _, u = b302(client, "owner2")
    for who in ("padmin", "president", "secretary", "treasurer", "member", "auditor"):
        h = prop_headers(client, who)
        for path in (f"/api/rental/units/{u}", ):
            assert client.get(path, headers=h).status_code == 403, who
        assert pay(client, h, u).status_code == 403, who
        assert client.post(f"/api/rental/units/{u}/issues", data={"title": "x"}, headers=h).status_code == 403, who
        assert client.post(f"/api/rental/units/{u}/followups", json={"text": "x"}, headers=h).status_code == 403, who
        assert client.get("/api/rental/flats", headers=h).json() == []
    ha = prop_headers(client, "padmin")
    sw = {r["number"]: r["enabled"] for r in client.get("/api/rental/switches", headers=ha).json()}
    assert sw["B-302"] is True and sw["A-501"] is False                               # only on/off, nothing else
    assert client.get("/api/rental/switches", headers=prop_headers(client, "president")).status_code == 403
    # another flat's owner/tenant is blocked from this flat too
    ho = prop_headers(client, "ownerrep")
    assert client.get(f"/api/rental/units/{u}", headers=ho).status_code == 403
    # the admin may switch on the owner's behalf, and it is audit-logged
    assert set_switch(client, ha, u, True).status_code == 200


def test_switch_audit_and_plan_flag(client):
    ho, rows = flat(client, "owner", "A-501")
    uid = rows[0]["unit_id"]
    assert set_switch(client, ho, uid, True).status_code == 200
    assert client.get(f"/api/rental/units/{uid}", headers=ho).status_code == 200
    from app.db import SessionLocal
    from app.models.core import AuditLog
    from sqlalchemy import select
    with SessionLocal() as db:
        a = db.scalars(select(AuditLog).where(AuditLog.action == "rental.switch", AuditLog.entity_id == str(uid))).all()
        assert a and a[-1].meta["enabled"] is True
    assert set_switch(client, ho, uid, False).status_code == 200
    # the Basic plan has no rental records
    from app.services.entitlements import ALL_FEATURES
    from app.models.saas import Plan
    assert "rental_records" in ALL_FEATURES
    with SessionLocal() as db:
        assert "rental_records" in db.get(Plan, "pro").features and "rental_records" in db.get(Plan, "standard").features
        assert "rental_records" not in db.get(Plan, "basic").features


def test_seed_content(client):
    h, u = b302(client, "tenant")
    d = client.get(f"/api/rental/units/{u}", headers=h).json()
    assert d["side"] == "tenant" and len(d["agreements"]) == 1 and d["agreements"][0]["expiring"] is True
    assert len(d["ledger"]["months"]) >= 6 and len(d["ledger"]["overdue"]) == 1
    assert {p["method"] for p in d["payments"]} == {"cash", "bank"}
    assert len(d["issues"]) == 2 and len(d["followups"]) == 2 and d["notes"] == []        # reminder history is the owner's


def test_owner_records_rent_and_receipts_are_sequential(client):
    h, u = b302(client, "owner2")
    ht = prop_headers(client, "tenant")
    p1 = pay(client, h, u, period="2025-12", amount=2500000, method="bank", bank_ref="TRX1").json()
    p2 = pay(client, h, u, period="2025-12", amount=500000).json()
    assert p1["status"] == p2["status"] == "confirmed"
    r1 = client.post(f"/api/rental/payments/{p1['id']}/receipt", headers=h).json()
    r2 = client.post(f"/api/rental/payments/{p2['id']}/receipt", headers=h).json()
    again = client.post(f"/api/rental/payments/{p1['id']}/receipt", headers=h).json()
    n1, n2 = int(r1["receipt_no"].rsplit("-", 1)[1]), int(r2["receipt_no"].rsplit("-", 1)[1])
    assert n2 == n1 + 1 and again["receipt_no"] == r1["receipt_no"] and r1["receipt_no"].startswith("MR-B-302-")
    assert n1 >= 4                                            # the seed already issued 1..3
    # both sides can view it, the tenant cannot create one
    for hh in (h, ht):
        rc = client.get(f"/api/rental/payments/{p1['id']}/receipt", headers=hh)
        assert rc.status_code == 200 and rc.json()["amount"] == 2500000 and rc.json()["bank_ref"] == "TRX1"
    assert client.post(f"/api/rental/payments/{p2['id']}/receipt", headers=ht).status_code == 403
    assert client.delete(f"/api/rental/payments/{p1['id']}", headers=h).status_code == 409   # receipted: kept
    # validation
    assert pay(client, h, u, method="bkash").status_code == 422
    assert pay(client, h, u, amount=0).status_code == 422
    assert pay(client, h, u, period="2026-13").status_code == 422
    assert pay(client, h, u, paid_on=(date.today() + timedelta(days=30)).isoformat()).status_code == 422
    # a number is per flat: the unit counter lives on that flat only
    assert client.get(f"/api/rental/payments/{p1['id']}/receipt", headers=prop_headers(client, "padmin")).status_code == 403


def test_tenant_i_paid_then_owner_confirms(client):
    h, u = b302(client, "owner2")
    ht = prop_headers(client, "tenant")
    before = client.get(f"/api/rental/units/{u}", headers=h).json()["ledger"]["total_received"]
    p = pay(client, ht, u, period="2025-11", amount=700000, method="bank", bank_ref="BK9").json()
    assert p["status"] == "pending" and p["source"] == "tenant"
    assert client.get(f"/api/rental/units/{u}", headers=h).json()["ledger"]["total_received"] == before     # not counted yet
    assert client.post(f"/api/rental/payments/{p['id']}/receipt", headers=h).status_code == 409          # no receipt before confirm
    assert client.post(f"/api/rental/payments/{p['id']}/confirm", headers=ht).status_code == 403
    assert client.post(f"/api/rental/payments/{p['id']}/confirm", headers=h).json()["status"] == "confirmed"
    assert client.get(f"/api/rental/units/{u}", headers=h).json()["ledger"]["total_received"] == before + 700000
    assert client.post(f"/api/rental/payments/{p['id']}/confirm", headers=h).status_code == 409
    q = pay(client, ht, u, period="2025-11", amount=100).json()
    assert client.post(f"/api/rental/payments/{q['id']}/reject", headers=h).json()["status"] == "rejected"
    assert client.get(f"/api/rental/units/{u}", headers=h).json()["ledger"]["total_received"] == before + 700000


def test_upload_type_and_size_limits(client):
    h, u = b302(client, "owner2")
    ht = prop_headers(client, "tenant")
    f = {"title": "New agreement", "start_date": "2026-01-01", "end_date": "2027-01-01", "rent": "3000000", "advance": "6000000"}
    url = f"/api/rental/units/{u}/agreements"
    assert client.post(url, data=f, files={"file": ("a.txt", b"hello", "text/plain")}, headers=h).status_code == 422
    assert client.post(url, data=f, files={"file": ("a.pdf", b"not a pdf", "application/pdf")}, headers=h).status_code == 422       # wrong content
    assert client.post(url, data=f, files={"file": ("a.pdf", PDF + b"0" * (3 * 1024 * 1024), "application/pdf")}, headers=h).status_code == 413
    assert client.post(url, data=f, files={"file": ("a.pdf", b"", "application/pdf")}, headers=h).status_code == 422
    assert client.post(url, data={**f, "end_date": "2025-01-01"}, files={"file": ("a.pdf", PDF, "application/pdf")}, headers=h).status_code == 422
    assert client.post(url, data=f, files={"file": ("a.pdf", PDF, "application/pdf")}, headers=ht).status_code == 403              # owner only
    r = client.post(url, data=f, files={"file": ("a.pdf", PDF, "application/pdf")}, headers=h)
    assert r.status_code == 201, r.text
    a = r.json()
    assert client.get(f"/api/rental/agreements/{a['id']}/file", headers=ht).content == PDF                                           # tenant can read
    assert client.get(f"/api/rental/agreements/{a['id']}/file", headers=prop_headers(client, "padmin")).status_code == 403
    assert client.delete(f"/api/rental/agreements/{a['id']}", headers=h).status_code == 200
    # issue photo: image only
    iu = f"/api/rental/units/{u}/issues"
    assert client.post(iu, data={"title": "Door"}, files={"photo": ("a.pdf", PDF, "application/pdf")}, headers=ht).status_code == 422
    ok = client.post(iu, data={"title": "Door lock", "body": "stuck"}, files={"photo": ("d.png", PNG, "image/png")}, headers=ht)
    assert ok.status_code == 201 and ok.json()["has_photo"] and ok.json()["raised_side"] == "tenant"
    assert client.get(f"/api/rental/issues/{ok.json()['id']}/photo", headers=h).content == PNG


def test_issues_comments_cost_and_followups(client):
    h, u = b302(client, "owner2")
    ht = prop_headers(client, "tenant")
    i = client.post(f"/api/rental/units/{u}/issues", data={"title": "Wall seepage"}, headers=h).json()
    assert i["status"] == "open" and i["raised_side"] == "owner"
    assert client.post(f"/api/rental/issues/{i['id']}/comments", json={"body": "Will check"}, headers=ht).json()["side"] == "tenant"
    assert client.patch(f"/api/rental/issues/{i['id']}", json={"cost": 1000}, headers=ht).status_code == 403
    assert client.patch(f"/api/rental/issues/{i['id']}", json={"status": "weird"}, headers=h).status_code == 422
    r = client.patch(f"/api/rental/issues/{i['id']}", json={"status": "fixed", "cost": 450000, "cost_note": "Painter"}, headers=h).json()
    assert r["status"] == "fixed" and r["cost"] == 450000
    assert len(client.get(f"/api/rental/issues/{i['id']}", headers=ht).json()["comments"]) == 1
    assert client.get(f"/api/rental/issues/{i['id']}", headers=prop_headers(client, "secretary")).status_code == 403
    f = client.post(f"/api/rental/units/{u}/followups", json={"text": "Call plumber", "due_date": "2020-01-01", "ref_kind": "issue", "ref": str(i["id"])}, headers=h).json()
    assert f["done"] is False and f["overdue"] is True
    assert client.patch(f"/api/rental/followups/{f['id']}", json={"done": True}, headers=ht).json()["done"] is True
    assert client.post(f"/api/rental/units/{u}/followups", json={"text": "x", "ref_kind": "bad"}, headers=h).status_code == 422


def test_reminder_sms_uses_credit_and_is_private(client):
    from app.db import SessionLocal
    from app.models.billing import Message
    from app.services.entitlements import sms_balance
    h, u = b302(client, "owner2")
    ht = prop_headers(client, "tenant")
    ha = prop_headers(client, "padmin")
    with SessionLocal() as db:
        from app.models.property import Unit
        org = db.get(Unit, u).property_id
        from app.models.core import Property
        org_id = db.get(Property, org).org_id
        bal = sms_balance(db, org_id)
        msgs = db.query(Message).count()
    assert client.post(f"/api/rental/units/{u}/remind", json={"period": "bad"}, headers=h).status_code == 422
    assert client.post(f"/api/rental/units/{u}/remind", json={"period": "2026-07"}, headers=ht).status_code == 403
    r = client.post(f"/api/rental/units/{u}/remind", json={"period": "2026-07"}, headers=h)
    assert r.status_code == 200 and r.json()["status"] in ("sent", "failed")
    with SessionLocal() as db:
        assert sms_balance(db, org_id) == (bal - 1 if r.json()["status"] == "sent" else bal)
        assert db.query(Message).count() == msgs                 # not in the building's Messages list
    notes = client.get(f"/api/rental/units/{u}", headers=h).json()["notes"]
    assert notes and notes[0]["kind"] == "reminder"
    assert client.get(f"/api/rental/units/{u}", headers=ht).json()["notes"] == []
    assert client.post(f"/api/rental/units/{u}/notes", json={"body": "Said he will pay Friday", "period": "2026-07"}, headers=h).status_code == 201


def test_balance_maths():
    from app.routers.rental import agreement_flags, build_ledger
    ag = lambda s, e, rent: NS(start_date=s, end_date=e, rent=rent)
    py = lambda period, amt, status="confirmed": NS(period=period, amount=amt, status=status)
    today = date(2026, 10, 24)
    led = build_ledger([ag(date(2026, 6, 15), None, 1000)], [py("2026-06", 1000), py("2026-07", 400), py("2026-07", 600), py("2026-08", 300),
                                                                  py("2026-09", 5000, "pending"), py("2026-10", 1000, "rejected")], today)
    m = {x["period"]: x for x in led["months"]}
    assert list(m) == ["2026-06", "2026-07", "2026-08", "2026-09", "2026-10"]
    assert m["2026-07"]["received"] == 1000 and m["2026-07"]["overdue"] is False
    assert m["2026-08"]["outstanding"] == 700 and m["2026-08"]["overdue"] is True
    assert m["2026-09"]["outstanding"] == 1000 and m["2026-09"]["overdue"] is True       # pending is not money received
    assert m["2026-10"]["outstanding"] == 1000 and m["2026-10"]["overdue"] is False       # this month is due, not late
    assert [x["balance"] for x in led["months"]] == [0, 0, 700, 1700, 2700]
    assert led["total_due"] == 5000 and led["total_received"] == 2300 and led["balance"] == 2700 and led["overdue_amount"] == 1700
    # a rent change: the later agreement wins from its start month; an overpayment makes the balance go down
    led2 = build_ledger([ag(date(2026, 8, 1), date(2026, 9, 30), 1000), ag(date(2026, 10, 1), None, 1200)], [py("2026-08", 1500)], today)
    assert [(x["period"], x["due"]) for x in led2["months"]] == [("2026-08", 1000), ("2026-09", 1000), ("2026-10", 1200)]
    assert led2["months"][0]["balance"] == -500 and led2["balance"] == 1700
    assert build_ledger([], [], today)["months"] == []
    assert agreement_flags(ag(date(2026, 1, 1), today + timedelta(days=60), 1), today)["expiring"] is True
    assert agreement_flags(ag(date(2026, 1, 1), today + timedelta(days=61), 1), today)["expiring"] is False
    assert agreement_flags(ag(date(2026, 1, 1), today - timedelta(days=1), 1), today) == {"days_left": -1, "expired": True, "expiring": False}
