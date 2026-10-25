"""P5: CSV exports, whole-building ZIP, data retention and account deletion."""
import csv
import io
import itertools
import zipfile
from datetime import date, timedelta

from conftest import login
from test_property import prop_headers
from test_setup import NEW_PW, first_login, new_building

BOM = b"\xef\xbb\xbf"
_n = itertools.count(1)


def rows_of(resp):
    assert resp.content.startswith(BOM), "CSV needs a UTF-8 byte-order mark"
    return list(csv.reader(io.StringIO(resp.content.decode("utf-8-sig"))))


# ---------------- csv helpers
def test_csv_cell_blocks_formulas_and_keeps_numbers():
    from app.services.csvio import bdt, cell
    assert cell("=1+1") == "'=1+1" and cell("@SUM(A1)") == "'@SUM(A1)" and cell("-cmd|x") == "'-cmd|x"
    assert cell("+8801711000001") == "+8801711000001" and cell("-12.50") == "-12.50" and cell("ঢাকা") == "ঢাকা"
    assert cell(None) == "" and cell(True) == "yes" and cell(date(2026, 10, 25)) == "2026-10-25"
    assert bdt(125050) == "1250.50" and bdt(5) == "0.05" and bdt(-250) == "-2.50" and bdt(0) == "0.00" and bdt(None) == "0.00"


# ---------------- single CSV exports
def test_admin_downloads_each_list(client):
    h = prop_headers(client, "padmin")
    heads = {"invoices": "invoice_no", "payments": "receipt_no", "dues": "flat_number", "ledger": "journal_id", "expenses": "id", "people": "type", "visitors": "visitor_name"}
    for name, first in heads.items():
        r = client.get(f"/api/export/csv/{name}", headers=h)
        assert r.status_code == 200, (name, r.text)
        assert r.headers["content-type"].startswith("text/csv") and "attachment" in r.headers["content-disposition"]
        rows = rows_of(r)
        assert first in rows[0] and len(rows) > 1, name
    assert client.get("/api/export/csv/nonsense", headers=h).status_code == 404


def test_money_columns_are_decimal_taka(client):
    h = prop_headers(client, "padmin")
    api_inv = client.get("/api/billing/invoices?period=2026-10", headers=h).json()
    rows = rows_of(client.get("/api/export/csv/invoices", headers=h))
    head = rows[0]
    mine = [r for r in rows[1:] if r[head.index("invoice_no")] == api_inv[0]["number"]][0]
    assert mine[head.index("total_bdt")] == f"{api_inv[0]['total'] // 100}.{api_inv[0]['total'] % 100:02d}"


def test_resident_exports_only_own_invoices_and_not_the_ledger(client):
    ht = prop_headers(client, "tenant")
    rows = rows_of(client.get("/api/export/csv/invoices", headers=ht))
    own = {u["number"] for u in client.get("/api/units", headers=ht).json()}
    assert len(rows) > 1 and {r[rows[0].index("flat_number")] for r in rows[1:]} <= own
    assert client.get("/api/export/csv/ledger", headers=ht).status_code == 403
    assert client.get("/api/export/csv/people", headers=ht).status_code == 403
    assert client.get("/api/export/csv/dues", headers=ht).status_code == 403
    assert client.get("/api/export/csv/visitors", headers=ht).status_code == 403


def test_people_phone_hidden_from_auditor_but_exportable(client):
    ha = prop_headers(client, "auditor")
    r = client.get("/api/export/csv/people", headers=ha)
    assert r.status_code == 200
    rows = rows_of(r)
    assert all(x[rows[0].index("phone")] == "" for x in rows[1:])


# ---------------- whole building
def test_building_zip_contents_and_audit(client):
    h = prop_headers(client, "padmin")
    r = client.get("/api/export/building.zip", headers=h)
    assert r.status_code == 200 and r.headers["content-type"] == "application/zip"
    z = zipfile.ZipFile(io.BytesIO(r.content))
    names = set(z.namelist())
    want = {"flats", "people", "invoices", "invoice_lines", "payments", "ledger_journal_lines", "expenses", "staff", "notices", "requests", "visitors", "bookings", "vehicles"}
    assert {f"{n}.csv" for n in want} <= names and "README.txt" in names
    for n in want:
        raw = z.read(f"{n}.csv")
        assert raw.startswith(BOM), n
    staff = list(csv.reader(io.StringIO(z.read("staff.csv").decode("utf-8-sig"))))
    assert not any("nid" in c.lower() for c in staff[0]) and len(staff) > 1
    assert "NID" not in z.read("staff.csv").decode() and "nid_" not in z.read("staff.csv").decode()
    flats = list(csv.reader(io.StringIO(z.read("flats.csv").decode("utf-8-sig"))))
    assert len(flats) == 33                                    # 32 flats and the header
    log = client.get("/api/audit?limit=50", headers=h).json()
    assert any(a["action"] == "export.building" for a in log)


def test_building_zip_roles_and_rate_limit(client, monkeypatch):
    assert client.get("/api/export/building.zip", headers=prop_headers(client, "treasurer")).status_code == 403
    assert client.get("/api/export/building.zip", headers=prop_headers(client, "tenant")).status_code == 403
    assert client.get("/api/export/building.zip", headers=prop_headers(client, "president")).status_code == 200
    monkeypatch.setattr("app.routers.exports.ZIP_PER_DAY", 2)
    h, _ = new_building(client)
    st = client.get("/api/export/status", headers=h).json()
    assert st["can_export"] is True and st["left_today"] == 2
    assert client.get("/api/export/building.zip", headers=h).status_code == 200
    assert client.get("/api/export/building.zip", headers=h).status_code == 200
    r = client.get("/api/export/building.zip", headers=h)
    assert r.status_code == 429
    assert client.get("/api/export/status", headers=h).json()["left_today"] == 0
    # the limit is per building: the demo building still works
    assert client.get("/api/export/building.zip", headers=prop_headers(client, "padmin")).status_code in (200, 429)


# ---------------- retention
def _admin(client, who="super"):
    h, _ = login(client, who)
    return h


def test_retention_is_for_saas_admins_only(client):
    for who in ("padmin", "finance", "sales"):
        h, _ = login(client, who)
        assert client.get("/api/saas/retention", headers=h).status_code == 403
        assert client.post("/api/saas/retention/run", json={}, headers=h).status_code == 403


def test_retention_settings_validate_and_save(client):
    h = _admin(client)
    s = client.get("/api/saas/retention", headers=h).json()
    assert s["settings"]["audit"] == "never" and s["settings"]["visitor_months"] == 24
    assert client.put("/api/saas/retention", json={"visitor_months": 2}, headers=h).status_code == 422
    assert client.put("/api/saas/retention", json={"visitor_months": 999}, headers=h).status_code == 422
    s = client.put("/api/saas/retention", json={"visitor_months": 18, "outbox_months": 0}, headers=h).json()
    assert s["settings"]["visitor_months"] == 18 and s["settings"]["outbox_months"] == 0
    client.put("/api/saas/retention", json={"visitor_months": 24, "outbox_months": 12, "former_months": 36}, headers=h)


def test_purge_removes_only_old_records_and_never_the_audit_log(client):
    from sqlalchemy import func, select

    from app.db import SessionLocal
    from app.models.billing import Message
    from app.models.core import AuditLog, now
    from app.models.mail import MailOutbox
    from app.models.property import Occupancy, Unit
    from app.models.visitors import Visit
    hb, d = new_building(client)
    pid = int(hb["X-Property-Id"])
    client.post("/api/units/generate", json={"floors": 1, "blocks": ["Z"], "per_block": 2}, headers=hb)
    occ = client.post(f"/api/units/{client.get('/api/units', headers=hb).json()[0]['id']}/occupants", json={"kind": "tenant", "name": "Old Tenant", "phone": "01712345678", "email": "old@x.test"}, headers=hb).json()
    occ_id = occ["unit"]["tenants"][0]["id"]
    assert client.post(f"/api/occupants/{occ_id}/move-out", headers=hb).status_code == 200
    old = now() - timedelta(days=40 * 31)
    with SessionLocal() as db:
        uid = db.scalar(select(Unit.id).where(Unit.property_id == pid))
        db.add_all([Visit(property_id=pid, unit_id=uid, name="Old Visitor", purpose="guest", created_by=1, created_at=old, status="out"),
                    Visit(property_id=pid, unit_id=uid, name="New Visitor", purpose="guest", created_by=1, status="out")])
        db.add(MailOutbox(to_email="old@x.test", subject="old", status="sent", created_at=old))
        db.add(MailOutbox(to_email="queued@x.test", subject="queued", status="queued", created_at=old))
        db.add(Message(property_id=pid, to_name="x", to_phone="017", template="t", body="b", status="sent", idem_key="p5-old-msg", created_at=old))
        o = db.get(Occupancy, occ_id)
        o.end_date = date.today() - timedelta(days=4 * 366)
        db.commit()
        audit_before = db.scalar(select(func.count()).select_from(AuditLog))
    h = _admin(client)
    prev = client.post("/api/saas/retention/run", json={"dry_run": True}, headers=h).json()
    assert prev["dry_run"] is True and prev["visitors"]["visits"] >= 1 and prev["outbox"]["emails"] >= 1 and prev["outbox"]["sms"] >= 1 and prev["former_residents"]["contacts"] >= 1
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(Visit).where(Visit.name == "Old Visitor")) == 1   # a dry run deletes nothing
    res = client.post("/api/saas/retention/run", json={"dry_run": False}, headers=h).json()
    assert res["visitors"]["visits"] >= 1
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(Visit).where(Visit.name == "Old Visitor")) == 0
        assert db.scalar(select(func.count()).select_from(Visit).where(Visit.name == "New Visitor")) == 1
        assert db.scalar(select(func.count()).select_from(MailOutbox).where(MailOutbox.subject == "old")) == 0
        assert db.scalar(select(func.count()).select_from(MailOutbox).where(MailOutbox.subject == "queued")) == 1   # queued mail is never purged
        assert db.scalar(select(func.count()).select_from(Message).where(Message.idem_key == "p5-old-msg")) == 0
        o = db.get(Occupancy, occ_id)
        assert o.phone == "" and o.email == "" and o.name == "Old Tenant"                                         # name stays for the flat's history
        assert db.scalar(select(func.count()).select_from(AuditLog)) > audit_before                              # only grows
    assert any(a["action"] == "retention.purge" for a in client.get("/api/audit?limit=20", headers=h).json())


def test_zero_months_keeps_everything():
    from app.db import SessionLocal
    from app.services import retention
    with SessionLocal() as db:
        assert retention.purge_visitors(db, 0) == {"visits": 0, "notices": 0, "parking_visits": 0, "passes": 0, "photos": 0}
        assert retention.purge_outbox(db, 0) == {"emails": 0, "sms": 0}


# ---------------- account deletion
def _resident(client, hb, n):
    """A resident with a sign-in, living in a flat of the new building."""
    units = client.get("/api/units", headers=hb).json()
    r = client.post(f"/api/units/{units[0]['id']}/occupants", json={"kind": "owner", "name": f"Erase Me {n}", "phone": "01799999999", "email": f"erase{n}@x.test", "create_login": True}, headers=hb)
    assert r.status_code == 201, r.text
    pw = r.json()["temp_password"]
    auth, lg = first_login(client, f"erase{n}@x.test", pw)
    return {**auth, "X-Property-Id": hb["X-Property-Id"]}, NEW_PW, lg["user"]["id"], units[0]


def test_deletion_request_flow_keeps_the_ledger(client):
    hb, _ = new_building(client)
    client.post("/api/units/generate", json={"floors": 1, "blocks": ["E"], "per_block": 2}, headers=hb)
    client.post("/api/billing/rules", json={"name": "Service", "kind": "flat", "amount": 500000}, headers=hb)
    client.post("/api/billing/run", json={"period": "2026-10"}, headers=hb)
    n = next(_n)
    hr, pw, uid, unit = _resident(client, hb, n)
    inv = client.get("/api/billing/invoices", headers=hr).json()
    assert inv, "the resident should see the flat's invoice"
    pay = client.post(f"/api/billing/invoices/{inv[0]['id']}/payments", json={"amount": 100000, "method": "bank", "paid_on": "2026-10-20"}, headers=hr)
    assert pay.status_code == 201
    assert client.post(f"/api/billing/payments/{pay.json()['id']}/verify", headers=hb).status_code == 200

    def ledger():
        rows = rows_of(client.get("/api/export/csv/ledger", headers=hb))
        h = rows[0]
        return [(r[h.index("journal_id")], r[h.index("debit_bdt")], r[h.index("credit_bdt")]) for r in rows[1:]]
    before = ledger()
    assert before and sum(float(d) for _, d, _c in before) == sum(float(c) for _, _d, c in before)

    assert client.post("/api/me/deletion", json={"password": "wrong"}, headers=hr).status_code == 403
    r = client.post("/api/me/deletion", json={"password": pw, "reason": "moving abroad"}, headers=hr)
    assert r.status_code == 201 and r.json()["status"] == "pending"
    assert client.post("/api/me/deletion", json={"password": pw}, headers=hr).status_code == 409        # already asked
    st = client.get("/api/me/deletion", headers=hr).json()
    assert st["request"]["status"] == "pending" and st["blockers"] == []

    assert client.get("/api/saas/deletions", headers=hr).status_code == 403                             # not for residents
    hs = _admin(client)
    rows = client.get("/api/saas/deletions", headers=hs).json()
    mine = [x for x in rows if x["user_id"] == uid][0]
    assert mine["email"] == f"erase{n}@x.test"
    done = client.post(f"/api/saas/deletions/{mine['id']}/process", headers=hs)
    assert done.status_code == 200 and done.json()["status"] == "completed"

    # the person is gone
    assert client.post("/api/auth/login", json={"email": f"erase{n}@x.test", "password": pw}).status_code == 401
    assert client.get("/api/me", headers=hr).status_code == 401
    people = client.get("/api/units", headers=hb).json()
    owner = [o for u in people if u["id"] == unit["id"] for o in u["owners"]][0]
    assert owner["name"] == "Former resident" and owner["phone"] == "" and owner["email"] == "" and owner["has_login"] is False
    # the books are untouched
    assert ledger() == before
    inv_after = client.get(f"/api/billing/invoices/{inv[0]['id']}", headers=hb).json()
    assert inv_after["paid"] == 100000


def test_deletion_is_blocked_for_last_admin_and_staff_and_can_be_withdrawn(client):
    hb, d = new_building(client)
    h = {"Authorization": hb["Authorization"]}
    st = client.get("/api/me/deletion", headers=h).json()
    assert st["blockers"] == ["last_admin"]
    r = client.post("/api/me/deletion", json={"password": "longpass1"}, headers=h)
    assert r.status_code == 409 and r.json()["detail"] == "last_admin"
    hsup, _ = login(client, "support")
    assert client.get("/api/me/deletion", headers=hsup).json()["blockers"] == ["saas_staff"]
    # a normal member can ask, then withdraw
    n = next(_n)
    res = client.post("/api/setup/committee", json={"members": [{"name": "Wd Raw", "email": f"wd{n}@x.test", "role": "MEMBER"}]}, headers=hb).json()["results"][0]
    hm, _ = first_login(client, f"wd{n}@x.test", res["temp_password"])
    assert client.post("/api/me/deletion", json={"password": NEW_PW}, headers=hm).status_code == 201
    assert client.delete("/api/me/deletion", headers=hm).status_code == 204
    assert client.get("/api/me/deletion", headers=hm).json()["request"]["status"] == "cancelled"
    assert client.delete("/api/me/deletion", headers=hm).status_code == 404


def test_reject_keeps_the_account_and_a_sole_admin_cannot_ask(client):
    hb, _ = new_building(client)
    h = {"Authorization": hb["Authorization"]}
    hs = _admin(client)
    # the sole admin cannot even ask
    assert client.post("/api/me/deletion", json={"password": "longpass1"}, headers=h).status_code == 409
    n = next(_n)
    res = client.post("/api/setup/committee", json={"members": [{"name": "Rej Ect", "email": f"rej{n}@x.test", "role": "TREASURER"}]}, headers=hb).json()["results"][0]
    hm, _ = first_login(client, f"rej{n}@x.test", res["temp_password"])
    rid = client.post("/api/me/deletion", json={"password": NEW_PW}, headers=hm).json()["id"]
    assert client.post(f"/api/saas/deletions/{rid}/reject", json={"note": "x"}, headers=hs).status_code == 422
    r = client.post(f"/api/saas/deletions/{rid}/reject", json={"note": "Please settle the open expense first"}, headers=hs)
    assert r.status_code == 200 and r.json()["status"] == "rejected"
    assert client.post(f"/api/saas/deletions/{rid}/process", headers=hs).status_code == 404
    assert client.get("/api/me", headers=hm).status_code == 200      # still active


# ---------------- OpenAPI
def test_openapi_is_documented(client):
    d = client.get("/openapi.json").json()
    assert d["components"]["securitySchemes"]["BearerAuth"] and d["components"]["securitySchemes"]["PropertyId"]
    tags = {t["name"] for t in d["tags"]}
    ops = [(p, m, o) for p, i in d["paths"].items() for m, o in i.items() if m in ("get", "post", "put", "patch", "delete")]
    assert len(ops) > 300
    assert all(o.get("description") for _, _, o in ops)
    assert {t for _, _, o in ops for t in o.get("tags", [])} <= tags
    assert d["paths"]["/api/public/plans"]["get"]["security"] == []
    assert d["paths"]["/api/export/building.zip"]["get"]["security"] == [{"BearerAuth": [], "PropertyId": []}]
    assert "PlansDoc" in d["components"]["schemas"]
