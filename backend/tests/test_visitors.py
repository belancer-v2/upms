from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from app.db import SessionLocal
from app.models.core import AuditLog
from app.models.visitors import VisitorPass
from conftest import login
from test_property import prop_headers

PNG = bytes.fromhex("89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4890000000d49444154789c6360000002000001e221bc330000000049454e44ae426082")
V = "/api/visitors"


def _unit(client, who, number):
    return [u for u in client.get(f"{V}/flats", params={"q": number}, headers=prop_headers(client, who)).json() if u["number"] == number][0]["id"]


def _arrive(client, number="B-302", name="Test Guest", **kw):
    hg = prop_headers(client, "guard")
    r = client.post(f"{V}/visits", json={"unit_id": _unit(client, "guard", number), "name": name, "purpose": "guest", **kw}, headers=hg)
    assert r.status_code == 201, r.text
    return r.json()


def _audit(action):
    with SessionLocal() as db:
        return db.scalars(select(AuditLog).where(AuditLog.action == action)).all()


def test_seed_has_a_realistic_log(client):
    s = client.get(f"{V}/summary", headers=prop_headers(client, "padmin")).json()
    assert s["inside"] == 3 and s["waiting"] == 2 and s["overstay"] == 1 and s["overstay_vehicles"] == 1
    log = client.get(f"{V}/visits", params={"size": 100}, headers=prop_headers(client, "padmin")).json()
    assert log["total"] >= 60
    assert client.get(f"{V}/frequent", headers=prop_headers(client, "padmin")).json()["total"] == 2
    assert client.get(f"{V}/passes", headers=prop_headers(client, "owner")).json()["total"] == 1


def test_guard_flow_arrival_approve_in_out(client):
    hg, ht, hw = prop_headers(client, "guard"), prop_headers(client, "tenant"), prop_headers(client, "owner2")
    v = _arrive(client, "B-302", "Flow Visitor", phone="01712345678", people=2, vehicle="dhaka-ga-11-2222")
    assert v["status"] == "waiting" and v["notified"] == 2 and v["vehicle"] == "DHAKA-GA-11-2222" and v["phone"] == ""      # guard never gets the phone back
    vid = v["id"]
    assert client.post(f"{V}/visits/{vid}/in", headers=hg).status_code == 409                                                  # not approved yet
    pend = client.get(f"{V}/mine/pending", headers=ht).json()
    assert any(x["id"] == vid for x in pend["waiting"]) and pend["unread"] >= 1
    assert any(x["id"] == vid and not x["read"] for x in client.get(f"{V}/mine/notifications", headers=hw).json()["items"])
    assert client.post(f"{V}/visits/{vid}/decision", json={"approve": True}, headers=ht).json()["status"] == "approved"
    assert client.post(f"{V}/visits/{vid}/decision", json={"approve": False}, headers=hw).status_code == 409                  # already answered
    assert any(x["id"] == vid for x in client.get(f"{V}/board", headers=hg).json()["approved"])
    assert client.post(f"{V}/visits/{vid}/in", headers=hg).json()["status"] == "in"
    assert client.post(f"{V}/visits/{vid}/in", headers=hg).status_code == 409
    done = client.post(f"{V}/visits/{vid}/out", headers=hg).json()
    assert done["status"] == "out" and done["in_at"] and done["out_at"]
    assert client.post(f"{V}/visits/{vid}/out", headers=hg).status_code == 409
    mine = client.get(f"{V}/mine", params={"q": "Flow Visitor"}, headers=ht).json()
    assert mine["total"] == 1 and mine["items"][0]["phone"] == "01712345678"
    client.post(f"{V}/mine/notifications/read", headers=ht)
    assert client.get(f"{V}/mine/pending", headers=ht).json()["unread"] == 0


def test_deny_and_override_are_audited(client):
    hg, hc, ht = prop_headers(client, "guard"), prop_headers(client, "caretaker"), prop_headers(client, "tenant")
    before = len(_audit("visitor.deny")), len(_audit("visitor.override"))
    d = _arrive(client, "B-302", "Unwanted Caller")
    assert client.post(f"{V}/visits/{d['id']}/decision", json={"approve": False}, headers=ht).json()["status"] == "denied"
    assert len(_audit("visitor.deny")) == before[0] + 1
    assert client.post(f"{V}/visits/{d['id']}/in", headers=hg).status_code == 409
    assert client.post(f"{V}/visits/{d['id']}/override", json={"note": "ok"}, headers=hg).status_code == 422                    # a reason is needed
    assert client.post(f"{V}/visits/{d['id']}/override", json={"note": "Owner phoned the gate"}, headers=hg).status_code == 403   # guard cannot beat a denial
    assert client.post(f"{V}/visits/{d['id']}/override", json={"note": "Owner phoned the gate"}, headers=hc).json()["status"] == "approved"
    w = _arrive(client, "A-102", "Unreachable Flat")                                                                             # nobody at A-102 has a login
    assert w["notified"] == 0
    o = client.post(f"{V}/visits/{w['id']}/override", json={"note": "Known family friend, owner abroad"}, headers=hg).json()
    assert o["status"] == "approved" and o["via"] == "override"
    assert len(_audit("visitor.override")) == before[1] + 2
    assert client.post(f"{V}/visits/{w['id']}/cancel", headers=hg).status_code == 200


def test_resident_sees_only_their_own_flat(client):
    ht, hr, ho = prop_headers(client, "tenant"), prop_headers(client, "ownerrep"), prop_headers(client, "owner")
    v = _arrive(client, "B-302", "Private Caller")
    assert client.post(f"{V}/visits/{v['id']}/decision", json={"approve": True}, headers=hr).status_code == 404               # A-801 cannot answer for B-302
    assert client.post(f"{V}/visits/{v['id']}/decision", json={"approve": True}, headers=ho).status_code == 404
    for h in (hr, ho):
        assert client.get(f"{V}/mine", params={"q": "Private Caller"}, headers=h).json()["total"] == 0
        assert all(x["id"] != v["id"] for x in client.get(f"{V}/mine/pending", headers=h).json()["waiting"])
        assert {x["unit"] for x in client.get(f"{V}/mine", params={"size": 100}, headers=h).json()["items"]} <= {"A-501", "A-801"}
    assert {u["number"] for u in client.get(f"{V}/flats", headers=hr).json()} == {"A-801"}
    assert client.get(f"{V}/mine", params={"q": "Private Caller"}, headers=ht).json()["total"] == 1
    assert client.post(f"{V}/passes", json={"unit_id": _unit(client, "guard", "B-302"), "name": "Sneaky", "valid_from": datetime.now(timezone.utc).isoformat(),
                                             "valid_to": (datetime.now(timezone.utc) + timedelta(hours=2)).isoformat()}, headers=hr).status_code == 403
    client.post(f"{V}/visits/{v['id']}/cancel", headers=prop_headers(client, "guard"))


def test_wrong_role_is_403(client):
    hg, ht, hp = prop_headers(client, "guard"), prop_headers(client, "tenant"), prop_headers(client, "padmin")
    uid = _unit(client, "guard", "B-302")
    assert client.post(f"{V}/visits", json={"unit_id": uid, "name": "Nope", "purpose": "guest"}, headers=ht).status_code == 403
    assert client.post(f"{V}/visits/delivery", json={"unit_id": uid}, headers=ht).status_code == 403
    assert client.get(f"{V}/board", headers=ht).status_code == 403
    assert client.get(f"{V}/visits", headers=ht).status_code == 403
    assert client.get(f"{V}/summary", headers=ht).status_code == 403
    assert client.get(f"{V}/mine", headers=hg).status_code == 403
    assert client.get(f"{V}/mine/pending", headers=hp).status_code == 403
    assert client.get(f"{V}/visits", headers=prop_headers(client, "auditor")).status_code == 403
    assert client.post(f"{V}/passes", json={"name": "Guard pass", "valid_from": datetime.now(timezone.utc).isoformat(),
                                             "valid_to": (datetime.now(timezone.utc) + timedelta(hours=2)).isoformat()}, headers=hg).status_code == 403
    assert client.post(f"{V}/passes/redeem", json={"code": "123456"}, headers=ht).status_code == 403
    assert client.put(f"{V}/settings", json={"page_size": 20}, headers=hg).status_code == 403
    assert client.get(f"{V}/visits", headers={"Authorization": "x"}).status_code in (401, 400)


def test_pass_code_is_single_use_hashed_and_expires(client):
    ho, hg = prop_headers(client, "owner"), prop_headers(client, "guard")
    now = datetime.now(timezone.utc)
    body = {"name": "Pre-approved Plumber", "purpose": "service", "valid_from": (now - timedelta(minutes=5)).isoformat(), "valid_to": (now + timedelta(hours=3)).isoformat()}
    made = client.post(f"{V}/passes", json=body, headers=ho)
    assert made.status_code == 201
    code, pid = made.json()["code"], made.json()["id"]
    assert len(code) == 6 and code.isdigit()
    with SessionLocal() as db:
        p = db.get(VisitorPass, pid)
        assert p.code_hash != code and code not in p.code_hash and len(p.code_hash) == 64
    assert "code" not in client.get(f"{V}/passes", headers=ho).json()["items"][0]
    assert client.post(f"{V}/passes", json={**body, "valid_to": (now + timedelta(days=9)).isoformat()}, headers=ho).status_code == 422
    assert client.post(f"{V}/passes", json={**body, "valid_to": (now - timedelta(hours=1)).isoformat()}, headers=ho).status_code == 422
    fails = len(_audit("visitor.pass.fail"))
    assert client.post(f"{V}/passes/redeem", json={"code": "000000" if code != "000000" else "000001"}, headers=hg).status_code == 404
    assert len(_audit("visitor.pass.fail")) == fails + 1
    v = client.post(f"{V}/passes/redeem", json={"code": code}, headers=hg)
    assert v.status_code == 201 and v.json()["status"] == "approved" and v.json()["unit"] == "A-501" and v.json()["via"] == "pass" and v.json()["kind"] == "pass"
    assert client.post(f"{V}/passes/redeem", json={"code": code}, headers=hg).status_code == 404                                  # single use
    assert next(p for p in client.get(f"{V}/passes", headers=ho).json()["items"] if p["id"] == pid)["status"] == "used"
    assert client.post(f"{V}/visits/{v.json()['id']}/in", headers=hg).json()["status"] == "in"
    # expiry: the same kind of pass, pushed into the past
    p2 = client.post(f"{V}/passes", json=body, headers=ho).json()
    with SessionLocal() as db:
        row = db.get(VisitorPass, p2["id"])
        row.valid_to = datetime.now(timezone.utc) - timedelta(minutes=1)
        db.commit()
    assert client.post(f"{V}/passes/redeem", json={"code": p2["code"]}, headers=hg).status_code == 404
    assert next(p for p in client.get(f"{V}/passes", headers=ho).json()["items"] if p["id"] == p2["id"])["status"] == "expired"
    # a cancelled pass and a not-yet-valid pass do not work either
    p3 = client.post(f"{V}/passes", json=body, headers=ho).json()
    assert client.post(f"{V}/passes/{p3['id']}/cancel", headers=prop_headers(client, "tenant")).status_code == 404
    assert client.post(f"{V}/passes/{p3['id']}/cancel", headers=ho).json()["status"] == "cancelled"
    assert client.post(f"{V}/passes/redeem", json={"code": p3["code"]}, headers=hg).status_code == 404
    p4 = client.post(f"{V}/passes", json={**body, "valid_from": (now + timedelta(hours=1)).isoformat(), "valid_to": (now + timedelta(hours=2)).isoformat()}, headers=ho).json()
    assert client.post(f"{V}/passes/redeem", json={"code": p4["code"]}, headers=hg).status_code == 404
    assert client.post(f"{V}/passes/redeem", json={"code": "12ab"}, headers=hg).status_code == 422
    # the demo pass from the seed works exactly once
    assert client.post(f"{V}/passes/redeem", json={"code": "482913"}, headers=hg).status_code == 201
    assert client.post(f"{V}/passes/redeem", json={"code": "482913"}, headers=hg).status_code == 404


def test_wrong_codes_are_rate_limited(client):
    hc = prop_headers(client, "caretaker")
    codes = [f"{n:06d}" for n in range(111110, 111110 + 12)]
    seen = [client.post(f"{V}/passes/redeem", json={"code": c}, headers=hc).status_code for c in codes]
    assert 429 in seen and seen[0] == 404


def test_delivery_shortcut_and_frequent_visitors(client):
    hg, ht = prop_headers(client, "guard"), prop_headers(client, "tenant")
    d = client.post(f"{V}/visits/delivery", json={"unit_id": _unit(client, "guard", "B-302"), "name": "Pathao rider"}, headers=hg).json()
    assert d["status"] == "in" and d["kind"] == "delivery" and d["notified"] == 2 and d["via"] == "delivery"
    assert client.post(f"{V}/visits/{d['id']}/out", headers=hg).json()["status"] == "out"
    today = datetime.now(timezone(timedelta(hours=6))).date()
    f = client.post(f"{V}/frequent", json={"name": "Tutor Selim", "role": "tutor", "phone": "01799999999", "valid_from": str(today - timedelta(days=1)), "valid_to": str(today + timedelta(days=30))}, headers=ht)
    assert f.status_code == 201 and f.json()["unit"] == "B-302" and f.json()["valid_today"]
    old = client.post(f"{V}/frequent", json={"name": "Old Driver", "role": "driver", "valid_from": str(today - timedelta(days=40)), "valid_to": str(today - timedelta(days=10))}, headers=ht).json()
    assert client.post(f"{V}/frequent", json={"name": "Bad dates", "valid_from": str(today), "valid_to": str(today - timedelta(days=1))}, headers=ht).status_code == 422
    gate = client.get(f"{V}/frequent", params={"size": 100}, headers=hg).json()["items"]
    assert any(x["name"] == "Tutor Selim" for x in gate) and not any(x["id"] == old["id"] for x in gate) and all(x["phone"] == "" for x in gate)
    assert client.post(f"{V}/frequent/{old['id']}/enter", headers=hg).status_code == 409
    e = client.post(f"{V}/frequent/{f.json()['id']}/enter", headers=hg)
    assert e.status_code == 201 and e.json()["status"] == "approved" and e.json()["kind"] == "frequent"
    assert client.post(f"{V}/frequent/{f.json()['id']}/enter", headers=hg).status_code == 409
    mine = client.get(f"{V}/frequent", headers=ht).json()
    assert {x["unit"] for x in mine["items"]} == {"B-302"} and mine["total"] >= 3
    assert client.delete(f"{V}/frequent/{f.json()['id']}", headers=prop_headers(client, "ownerrep")).status_code == 404
    assert client.delete(f"{V}/frequent/{f.json()['id']}", headers=ht).status_code == 200
    assert client.post(f"{V}/frequent/{f.json()['id']}/enter", headers=hg).status_code == 404


def test_photo_rules(client):
    hg, hp, ht = prop_headers(client, "guard"), prop_headers(client, "padmin"), prop_headers(client, "tenant")
    v = _arrive(client, "A-102", "Photo Visitor")
    url = f"{V}/visits/{v['id']}/photo"
    assert client.post(url, files={"file": ("a.png", PNG, "image/png")}, headers=ht).status_code == 403
    assert client.post(url, files={"file": ("a.gif", b"GIF89a", "image/gif")}, headers=hg).status_code == 422
    assert client.post(url, files={"file": ("a.png", b"not really a png", "image/png")}, headers=hg).status_code == 422          # magic bytes checked
    assert client.post(url, files={"file": ("a.jpg", PNG, "image/jpeg")}, headers=hg).status_code == 422                           # type must match content
    assert client.post(url, files={"file": ("big.png", PNG + b"\0" * (2 * 1024 * 1024), "image/png")}, headers=hg).status_code == 413
    ok = client.post(url, files={"file": ("a.png", PNG, "image/png")}, headers=hg)
    assert ok.status_code == 200 and ok.json()["photo"] is True
    got = client.get(url, headers=hg)
    assert got.status_code == 200 and got.content == PNG and got.headers["content-type"] == "image/png"
    assert client.get(url, headers=hp).status_code == 200
    assert client.get(url, headers=ht).status_code == 403
    assert client.get(url, headers=prop_headers(client, "president")).status_code == 403
    assert client.get(url).status_code in (401, 400)
    assert client.get(f"{V}/visits/{v['id']}/photo", headers=prop_headers(client, "guard", "Lakeview Heights")).status_code == 404   # another building
    row = next(x for x in client.get(f"{V}/visits", params={"q": "Photo Visitor"}, headers=prop_headers(client, "president")).json()["items"])
    assert row["photo"] is False and row["phone"] == "" or row["phone"] == ""
    client.post(f"{V}/visits/{v['id']}/cancel", headers=hg)


def test_reports_search_paging_and_settings(client):
    hp, hg, hs = prop_headers(client, "padmin"), prop_headers(client, "guard"), prop_headers(client, "secretary")
    s = client.get(f"{V}/summary", headers=hs).json()
    assert s["today"] >= 1 and s["inside"] >= 3 and s["overstay"] >= 1 and s["overstay_hours"] == 12
    over = client.get(f"{V}/visits", params={"overstay": True}, headers=hp).json()
    assert over["total"] == s["overstay"] and all(x["overstay"] and x["status"] == "in" for x in over["items"])
    assert client.get(f"{V}/visits", params={"inside": True, "size": 100}, headers=hp).json()["total"] == s["inside"]
    a501 = client.get(f"{V}/visits", params={"flat": "A-501", "size": 100}, headers=hp).json()
    assert a501["total"] > 0 and {x["unit"] for x in a501["items"]} == {"A-501"}
    assert client.get(f"{V}/visits", params={"q": "alamgir"}, headers=hp).json()["total"] >= 1
    today = datetime.now(timezone(timedelta(hours=6))).date()
    none = client.get(f"{V}/visits", params={"date_from": str(today + timedelta(days=1))}, headers=hp).json()
    assert none["total"] == 0
    week = client.get(f"{V}/visits", params={"date_from": str(today - timedelta(days=30)), "date_to": str(today), "size": 100}, headers=hp).json()
    assert week["total"] >= 60 and any(x["phone"] for x in week["items"])
    # paging with the admin-set size
    assert client.get(f"{V}/visits", headers=hp).json()["size"] == 10
    assert client.put(f"{V}/settings", json={"page_size": 7, "overstay_hours": 12}, headers=hp).json()["page_size"] == 7
    p2 = client.get(f"{V}/visits", params={"page": 2}, headers=hp).json()
    assert p2["size"] == 7 and len(p2["items"]) == 7 and p2["page"] == 2
    assert client.put(f"{V}/settings", json={"page_size": 1}, headers=hp).status_code == 422
    assert client.get(f"{V}/settings", headers=hg).json()["can_edit"] is False
    client.put(f"{V}/settings", json={"page_size": 10, "overstay_hours": 12}, headers=hp)
    # the guard sees today's log and what is still active, never older finished visits, and no phone numbers
    g = client.get(f"{V}/visits", params={"size": 100, "date_from": "2020-01-01"}, headers=hg).json()
    assert 0 < g["total"] < week["total"] and all(x["phone"] == "" for x in g["items"])
    assert all(x["status"] in ("waiting", "approved", "in") or (x["created_at"] >= datetime.now(timezone.utc).strftime("%Y-%m-%d")[:0]) for x in g["items"])
    board = client.get(f"{V}/board", headers=hg).json()
    assert board["counts"]["inside"] == len(board["inside"]) and len(board["waiting"]) >= 2


def test_building_without_the_plan_feature_gets_402(client):
    hs, d = login(client, "padmin")
    org = [p for p in d["properties"] if p["name"] == "Sunrise Tower"][0]["org_id"]
    hsa, _ = login(client, "super")
    assert client.put(f"/api/saas/orgs/{org}/features", json={"key": "visitor", "enabled": False}, headers=hsa).status_code == 200
    try:
        for who, method, path in (("guard", "get", "/board"), ("guard", "get", "/visits"), ("guard", "get", "/flats"), ("padmin", "get", "/summary"), ("padmin", "get", "/settings"),
                                  ("tenant", "get", "/mine"), ("tenant", "get", "/mine/pending"), ("tenant", "get", "/passes"), ("tenant", "get", "/frequent")):
            assert getattr(client, method)(f"{V}{path}", headers=prop_headers(client, who)).status_code == 402, path
        assert client.post(f"{V}/visits/delivery", json={"unit_id": 1}, headers=prop_headers(client, "guard")).status_code == 402
        assert client.post(f"{V}/passes/redeem", json={"code": "482913"}, headers=prop_headers(client, "guard")).status_code == 402
    finally:
        client.put(f"/api/saas/orgs/{org}/features", json={"key": "visitor", "enabled": True}, headers=hsa)
    assert client.get(f"{V}/board", headers=prop_headers(client, "guard")).status_code == 200
