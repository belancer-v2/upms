from conftest import login
from test_property import prop_headers


def H(client, who, building="Sunrise Tower"):
    return prop_headers(client, who, building)


def unit_id(client, h, number):
    return {u["number"]: u["id"] for u in client.get("/api/units", headers=h).json()}[number]


def test_seed_shape(client):
    s = client.get("/api/parking/summary", headers=H(client, "padmin")).json()
    assert s["visitor"] == 4 and s["free"] == 2 and s["to_review"] == 2 and 26 <= s["vehicles"] <= 32 and s["flats_unmet"] == 2
    assert s["occupied"] >= 42


def test_generate_with_parking_allocates(client):
    h = H(client, "agency", "Lakeview Heights")
    r = client.post("/api/units/generate", headers=h, json={"floors": 2, "blocks": ["C"], "per_block": 1, "cars_per_flat": 1, "bikes_per_flat": 1})
    assert r.status_code == 201 and r.json()["created"] == 2
    uid = unit_id(client, h, "C-201")
    v = client.get(f"/api/parking/units/{uid}", headers=h).json()
    assert sorted(s["code"] for s in v["slots"]) == ["C-201-C1", "C-201-M1"]
    assert v["entitlement"] == {"car": 1, "motorbike": 1, "bicycle": 0} and v["held"]["car"] == 1
    # add one with parking
    one = client.post("/api/units", headers=h, json={"floor": 9, "number": "TP-9", "cars_per_flat": 2})
    assert one.status_code == 201
    v = client.get(f"/api/parking/units/{one.json()['id']}", headers=h).json()
    assert [s["code"] for s in v["slots"]] == ["TP-9-C1", "TP-9-C2"]
    # import with parking; repeating it does not double the slots
    rows = [{"number": "TP-8", "floor": 8, "cars_per_flat": 1}]
    assert client.post("/api/units/import", headers=h, json=rows).json() == {"created": 1, "updated": 0}
    assert client.post("/api/units/import", headers=h, json=rows).json() == {"created": 0, "updated": 1}
    assert len(client.get(f"/api/parking/units/{unit_id(client, h, 'TP-8')}", headers=h).json()["slots"]) == 1


def test_defaults_create_no_parking(client):
    h = H(client, "agency", "Lakeview Heights")
    assert client.post("/api/units/import", headers=h, json=[{"number": "TP-7", "floor": 7}]).json()["created"] == 1
    assert client.post("/api/units", headers=h, json={"floor": 7, "number": "TP-6"}).status_code == 201
    assert client.get(f"/api/parking/units/{unit_id(client, h, 'TP-7')}", headers=h).json()["slots"] == []
    assert client.post("/api/units", headers=h, json={"floor": 7, "number": "TP-5", "cars_per_flat": 9}).status_code == 422


def test_vehicle_rules_and_duplicate_plate(client):
    h = H(client, "owner")
    uid = unit_id(client, h, "A-501")
    mine = client.get("/api/parking/mine", headers=h).json()
    assert [m["unit"]["number"] for m in mine] == ["A-501"] and len(mine[0]["slots"]) == 2
    # a bicycle does not fit the car and motorbike slots
    r = client.post("/api/parking/vehicles", headers=h, json={"unit_id": uid, "reg_no": "DHAKA METRO GA 12-3456", "kind": "bicycle"})
    assert r.status_code == 422
    # A-501 already registered a car and a bike in the seed, so a third car is over the limit
    assert client.post("/api/parking/vehicles", headers=h, json={"unit_id": uid, "reg_no": "dhaka metro ga 12-3456", "kind": "car"}).status_code == 422
    # another flat: free its car, then register one
    ha = H(client, "padmin")
    other = unit_id(client, ha, "B-201")
    v = next(x for x in client.get(f"/api/parking/units/{other}", headers=ha).json()["vehicles"])
    assert client.delete(f"/api/parking/vehicles/{v['id']}", headers=ha).status_code == 204
    ok = client.post("/api/parking/vehicles", headers=ha, json={"unit_id": other, "reg_no": "  dhaka metro ga  12-3456 ", "kind": "car", "make_model": "Toyota", "colour": "White"})
    assert ok.status_code == 201 and ok.json()["reg_no"] == "DHAKA METRO GA 12-3456"
    dup = client.post("/api/parking/vehicles", headers=h, json={"unit_id": uid, "reg_no": "Dhaka Metro GA 123456", "kind": "motorbike"})
    assert dup.status_code == 409
    # an owner cannot register on another flat, and cannot issue a temporary permit
    assert client.post("/api/parking/vehicles", headers=h, json={"unit_id": other, "reg_no": "DHAKA METRO HA 11-1111", "kind": "car"}).status_code == 403
    assert client.post("/api/parking/vehicles", headers=h, json={"unit_id": uid, "reg_no": "DHAKA METRO HA 11-1111", "kind": "car", "temporary": True}).status_code == 403
    temp = client.post("/api/parking/vehicles", headers=ha, json={"unit_id": uid, "reg_no": "DHAKA METRO HA 11-1111", "kind": "car", "temporary": True})
    assert temp.status_code == 201 and temp.json()["temporary"]


def test_photo_checks(client):
    ha = H(client, "padmin")
    other = unit_id(client, ha, "B-201")
    vid = client.get(f"/api/parking/units/{other}", headers=ha).json()["vehicles"][0]["id"]
    files = lambda data, ct: {"file": ("p.jpg", data, ct)}
    assert client.post(f"/api/parking/vehicles/{vid}/photo", headers=ha, files=files(b"%PDF-1.4", "application/pdf")).status_code == 422
    assert client.post(f"/api/parking/vehicles/{vid}/photo", headers=ha, files=files(b"notajpeg", "image/jpeg")).status_code == 422
    assert client.post(f"/api/parking/vehicles/{vid}/photo", headers=ha, files=files(b"\xff\xd8\xff" + b"0" * (2 * 1024 * 1024), "image/jpeg")).status_code == 413
    assert client.post(f"/api/parking/vehicles/{vid}/photo", headers=ha, files=files(b"\xff\xd8\xff\xe0abc", "image/jpeg")).json()["has_photo"]
    assert client.get(f"/api/parking/vehicles/{vid}/photo", headers=ha).status_code == 200


def test_resident_sees_only_own(client):
    h = H(client, "owner2")
    assert [m["unit"]["number"] for m in client.get("/api/parking/mine", headers=h).json()] == ["B-302"]
    assert client.get("/api/parking/slots", headers=h).status_code == 403
    assert client.get("/api/parking/vehicles", headers=h).status_code == 403
    assert client.get("/api/parking/lookup?reg=DHAKA", headers=h).status_code == 403
    other = unit_id(client, H(client, "padmin"), "A-101")
    assert client.get(f"/api/parking/units/{other}", headers=h).status_code == 404
    assert client.post("/api/parking/slots", headers=h, json={"code": "X-1"}).status_code == 403


def test_guard_lookup_hides_phone(client):
    ha = H(client, "padmin")
    vs = client.get("/api/parking/vehicles?size=100", headers=ha).json()["items"]
    plate = next(v for v in vs if v["unit"] == "A-101")["reg_no"]
    hg = H(client, "guard")
    r = client.get("/api/parking/lookup", params={"reg": plate.lower()}, headers=hg)
    assert r.status_code == 200 and r.json()["items"][0]["unit"] == "A-101" and r.json()["items"][0]["slots"] == ["A-101-C1"]
    assert r.json()["items"][0]["owner"] and "phone" not in r.text and "01" not in "".join(i["owner"] for i in r.json()["items"])
    assert client.get("/api/parking/vehicles", headers=hg).status_code == 403


def test_slot_add_reassign_swap_unallocate(client):
    ha = H(client, "padmin")
    assert client.post("/api/parking/slots", headers=ha, json={"code": "p-a-01", "level": "Basement", "kind": "car", "cover": "covered"}).status_code == 201
    assert client.post("/api/parking/slots", headers=ha, json={"code": "P-A-01"}).status_code == 409
    s = client.get("/api/parking/slots?q=P-A-01", headers=ha).json()["items"][0]
    assert s["state"] == "free"
    u1, u2 = unit_id(client, ha, "A-201"), unit_id(client, ha, "A-202")
    assert client.post(f"/api/parking/slots/{s['id']}/allocate", headers=ha, json={"unit_id": u1}).json()["unit"] == "A-201"
    assert client.post(f"/api/parking/slots/{s['id']}/allocate", headers=ha, json={"unit_id": u1}).status_code == 409
    assert client.post(f"/api/parking/slots/{s['id']}/allocate", headers=ha, json={"unit_id": u2}).json()["unit"] == "A-202"
    # swap A-202's P-A-01 with A-201's own car slot
    mine = client.get(f"/api/parking/units/{u1}", headers=ha).json()["slots"][0]
    assert client.post("/api/parking/swap", headers=ha, json={"slot_a": s["id"], "slot_b": mine["id"]}).status_code == 200
    assert client.get(f"/api/parking/slots?q={mine['code']}", headers=ha).json()["items"][0]["unit"] == "A-202"
    assert client.post("/api/parking/swap", headers=ha, json={"slot_a": s["id"], "slot_b": s["id"]}).status_code == 422
    assert client.post(f"/api/parking/slots/{s['id']}/unallocate", headers=ha).json()["state"] == "free"
    assert client.post(f"/api/parking/slots/{s['id']}/unallocate", headers=ha).status_code == 409
    # a bike slot cannot be swapped with a car slot
    bike = client.get("/api/parking/slots?kind=motorbike&state=occupied", headers=ha).json()["items"][0]
    assert client.post("/api/parking/swap", headers=ha, json={"slot_a": mine["id"], "slot_b": bike["id"]}).status_code == 422
    # visitor and blocked slots are not given to flats
    v = client.get("/api/parking/slots?state=visitor", headers=ha).json()["items"][0]
    assert client.post(f"/api/parking/slots/{v['id']}/allocate", headers=ha, json={"unit_id": u1}).status_code == 422
    # paging and handover
    page = client.get("/api/parking/slots?size=10&page=2", headers=ha).json()
    assert page["size"] == 10 and len(page["items"]) == 10 and page["total"] > 40
    assert client.put("/api/parking/settings", headers=ha, json={"page_size": 12}).json() == {"page_size": 12}
    assert client.get("/api/parking/slots", headers=ha).json()["size"] == 12
    ho = client.get("/api/parking/handover?which=unmet", headers=ha).json()
    assert {r["unit"] for r in ho["items"]} == {"A-802", "B-402"} and ho["items"][0]["missing"] == {"car": 1}
    assert client.get("/api/parking/handover?which=free", headers=ha).json()["total"] >= 3
    # committee can look but not change
    hp = H(client, "president")
    assert client.get("/api/parking/slots", headers=hp).status_code == 200
    assert client.post(f"/api/parking/slots/{s['id']}/allocate", headers=hp, json={"unit_id": u1}).status_code == 403
    logs = client.get("/api/audit", headers=ha)
    if logs.status_code == 200:
        assert "parking.swap" in logs.text


def test_visitor_bays(client):
    hg = H(client, "guard")
    d = client.get("/api/parking/visits", headers=hg).json()
    bay = next(b for b in d["bays"] if not b["busy"])
    r = client.post("/api/parking/visits", headers=hg, json={"plate": "dhaka metro la 13-5555", "slot_id": bay["id"]})
    assert r.status_code == 201
    assert client.post("/api/parking/visits", headers=hg, json={"plate": "DHAKA METRO LA 13-6666", "slot_id": bay["id"]}).status_code == 409
    own = client.get("/api/parking/slots?q=A-501", headers=hg).json()["items"][0]
    assert client.post("/api/parking/visits", headers=hg, json={"plate": "DHAKA METRO LA 13-6666", "slot_id": own["id"]}).status_code == 422
    assert client.post(f"/api/parking/visits/{r.json()['id']}/out", headers=hg).json()["out_at"]
    assert client.post(f"/api/parking/visits/{r.json()['id']}/out", headers=hg).status_code == 409
    assert client.get("/api/parking/visits", headers=H(client, "owner")).status_code == 403


def test_tenant_move_out_flags_vehicles(client):
    ha = H(client, "agency", "Lakeview Heights")
    uid = unit_id(client, ha, "C-101")
    t = client.post(f"/api/units/{uid}/occupants", headers=ha, json={"kind": "tenant", "name": "Move Out Tenant", "email": "c101tenant@flatwise.demo", "create_login": True})
    assert t.status_code == 201
    th, data = login(client, "c101tenant", t.json()["temp_password"])
    ht = {**th, "X-Property-Id": str(next(p["id"] for p in data["properties"] if p["name"] == "Lakeview Heights"))}
    car = client.post("/api/parking/vehicles", headers=ht, json={"unit_id": uid, "reg_no": "DHAKA METRO CHA 21-0001", "kind": "car"})
    assert car.status_code == 201 and car.json()["holder_kind"] == "tenant"
    tid = t.json()["unit"]["tenants"][0]["id"]
    assert client.post(f"/api/occupants/{tid}/move-out", headers=ha).status_code == 200
    after = client.get(f"/api/parking/units/{uid}", headers=ha).json()
    assert [v["status"] for v in after["vehicles"]] == ["to_review"] and len(after["slots"]) == 2   # the vehicle waits for review, the slots stay with the flat
    assert client.post(f"/api/parking/vehicles/{car.json()['id']}/keep", headers=ha).json()["status"] == "active"


def test_402_without_plan_feature(client):
    hs, d = login(client, "padmin")
    org = [p for p in d["properties"] if p["name"] == "Sunrise Tower"][0]["org_id"]
    hsa, _ = login(client, "super")
    assert client.put(f"/api/saas/orgs/{org}/features", json={"key": "parking", "enabled": False}, headers=hsa).status_code == 200
    try:
        ha = H(client, "padmin")
        hl = H(client, "agency", "Lakeview Heights")
        assert client.get("/api/parking/summary", headers=ha).status_code == 402
        assert client.get("/api/parking/mine", headers=H(client, "owner")).status_code == 402
        assert client.get("/api/parking/lookup?reg=DHAKA", headers=H(client, "guard")).status_code == 402
        # creating flats still works with no parking asked for, but asking for parking is refused
        assert client.post("/api/units", headers=hl, json={"floor": 9, "number": "ZZ-1"}).status_code == 201
        assert client.post("/api/units", headers=hl, json={"floor": 9, "number": "ZZ-2", "cars_per_flat": 1}).status_code == 402
    finally:
        client.put(f"/api/saas/orgs/{org}/features", json={"key": "parking", "enabled": True}, headers=hsa)
