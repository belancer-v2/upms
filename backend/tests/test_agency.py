import json
from datetime import timedelta

from app.routers.agency import _today, week_start
from test_property import prop_headers

PDF = b"%PDF-1.4\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF"
PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 64


def mk_agency(client, h, name="Test Guard Co", **kw):
    body = {"name": name, "kind": "security", "psc_licence": "PSC-T-1", "trade_licence": "TL-1", "contact_name": "Boss", "contact_phone": "01700000099", **kw}
    r = client.post("/api/agency/agencies", json=body, headers=h)
    assert r.status_code == 201, r.text
    return r.json()


def mk_person(client, h, aid, name, **kw):
    r = client.post(f"/api/agency/agencies/{aid}/staff", json={"name": name, "role": "guard", "phone": "01911600000", "nid": "1990000000001", "emp_no": "T-1", **kw}, headers=h)
    assert r.status_code == 201, r.text
    return r.json()["id"]


def shift_ids(client, h):
    return {s["name"]: s["id"] for s in client.get("/api/agency/posts", headers=h).json()["shifts"]}


def slot(client, h, d, post, shift, staff, **kw):
    r = client.post("/api/agency/roster/slots", json={"date": str(d), "post_id": post, "shift_id": shift, "staff_id": staff, **kw}, headers=h)
    assert r.status_code == 201, r.text
    return r.json()


def test_agency_crud_and_roles(client):
    pa, pres, tr, gd = (prop_headers(client, w) for w in ("padmin", "president", "treasurer", "guard"))
    assert client.post("/api/agency/agencies", json={"name": "No PSC Ltd", "kind": "security"}, headers=pa).status_code == 422       # security firm needs a PSC licence
    a = mk_agency(client, pa, contract_start=str(_today() - timedelta(days=300)), contract_end=str(_today() + timedelta(days=30)), fee_mode="flat", monthly_fee=5_000_000)
    assert a["expiring"] is True and a["days_left"] == 30 and a["vendor_id"] if "vendor_id" in a else True
    assert client.post("/api/agency/agencies", json={"name": "Treasurer Co", "kind": "cleaning"}, headers=tr).status_code == 403
    far = client.put(f"/api/agency/agencies/{a['id']}", json={"name": "Test Guard Co", "kind": "security", "psc_licence": "PSC-T-1", "contract_end": str(_today() + timedelta(days=400)), "status": "active"}, headers=pres).json()
    assert far["expiring"] is False
    ended = client.put(f"/api/agency/agencies/{a['id']}", json={"name": "Test Guard Co", "kind": "security", "psc_licence": "PSC-T-1", "status": "ended"}, headers=pa).json()
    assert ended["status"] == "ended"
    assert client.get("/api/agency/agencies", headers=gd).status_code == 403
    assert any(x["name"].startswith("Shield") and x["expiring"] for x in client.get("/api/agency/agencies", headers=pa).json())       # seeded contract ends in 45 days
    # the agency is also a vendor, so its invoices sit in the normal books
    assert any(v["name"] == "Test Guard Co" for v in client.get("/api/finance/vendors", headers=tr).json())


def test_document_upload_limits(client):
    pa, tr = prop_headers(client, "padmin"), prop_headers(client, "treasurer")
    a = mk_agency(client, pa, "Docs Co")
    up = lambda data, ctype, kind="licence", h=pa: client.post(f"/api/agency/agencies/{a['id']}/docs", data={"kind": kind}, files={"file": ("f", data, ctype)}, headers=h)
    ok = up(PDF, "application/pdf")
    assert ok.status_code == 201 and ok.json()["size"] == len(PDF)
    assert up(PNG, "image/png", "insurance").status_code == 201
    assert up(PDF + b"0" * (3 * 1024 * 1024), "application/pdf").status_code == 413
    assert up(b"not a pdf at all", "application/pdf").status_code == 422             # magic bytes do not match
    assert up(b"hello", "text/plain").status_code == 422
    assert up(PDF, "application/pdf", "selfie").status_code == 422
    assert up(PDF, "application/pdf", h=tr).status_code == 403
    docs = client.get(f"/api/agency/agencies/{a['id']}", headers=pa).json()["docs"]
    assert len(docs) == 2
    assert client.get(f"/api/agency/agencies/{a['id']}/docs/{docs[0]['id']}", headers=tr).status_code == 200
    assert client.get(f"/api/agency/agencies/{a['id']}/docs/{docs[0]['id']}", headers=prop_headers(client, "guard")).status_code == 403


def test_payroll_excludes_agency_staff_and_staff_filter(client):
    pa, tr = prop_headers(client, "padmin"), prop_headers(client, "treasurer")
    a = mk_agency(client, pa, "Payroll Co")
    sid = mk_person(client, pa, a["id"], "Agency Guard P")
    direct = client.get("/api/staff", headers=tr).json()
    assert len(direct) == 4 and all(r["agency"] is None for r in direct)              # default list: the building's own staff
    allr = client.get("/api/staff?employer=all", headers=tr).json()
    mine = [r for r in allr if r["id"] == sid][0]
    assert mine["agency"]["name"] == "Payroll Co" and mine["agency"]["emp_no"] == "T-1" and mine["nid"].endswith("0001") and mine["salary"] == 0
    assert [r["id"] for r in client.get(f"/api/staff?employer={a['id']}", headers=tr).json()] == [sid]
    sh = client.post("/api/staff/payroll/sheets", json={"period": "2020-01"}, headers=tr).json()
    assert sh["people"] == 4 and sid not in [l["staff_id"] for l in sh["lines"]]
    # agency staff use the same encrypted vault and view log
    full = client.post(f"/api/staff/{sid}/reveal-nid", headers=prop_headers(client, "president")).json()["nid"]
    assert full == "1990000000001"
    assert client.get(f"/api/staff/{sid}/nid-views", headers=prop_headers(client, "president")).json()
    # moving a person to direct puts them back on payroll lists
    assert client.put(f"/api/agency/staff/{sid}/posting", json={"agency_id": None}, headers=pa).status_code == 200
    assert [r for r in client.get("/api/staff", headers=tr).json() if r["id"] == sid]
    assert client.put(f"/api/agency/staff/{sid}/posting", json={"agency_id": a["id"], "emp_no": "T-2"}, headers=pa).status_code == 200      # back to the agency, so later tests see the usual 4 direct staff
    assert not [r for r in client.get("/api/staff", headers=tr).json() if r["id"] == sid]


def test_roster_conflict_warnings(client):
    pa, ct = prop_headers(client, "padmin"), prop_headers(client, "caretaker")
    a = mk_agency(client, pa, "Roster Co")
    sid = mk_person(client, pa, a["id"], "Roster Guard")
    sh = shift_ids(client, pa)
    post = client.post("/api/agency/posts", json={"name": "Test gate", "kind": "security", "headcount": 1, "agency_id": a["id"]}, headers=ct).json()
    base = week_start(_today() - timedelta(days=200))
    first = slot(client, ct, base, post["id"], sh["Day"], sid)
    assert first["warnings"] == []
    second = slot(client, ct, base, post["id"], sh["Evening"], sid)                    # two shifts the same day, 16 hours
    kinds = {w["type"] for w in second["warnings"]}
    assert kinds == {"two_shifts", "over_12h"}
    assert client.post("/api/agency/roster/slots", json={"date": str(base), "post_id": post["id"], "shift_id": sh["Evening"], "staff_id": sid}, headers=ct).status_code == 409
    client.delete(f"/api/agency/roster/slots/{second['id']}", headers=ct)
    for i in range(1, 7):
        last = slot(client, ct, base + timedelta(days=i), post["id"], sh["Day"], sid)
    assert [w["type"] for w in last["warnings"]] == ["seven_days"]                     # 7 days in a row with no day off
    r = client.get(f"/api/agency/roster?start={base}", headers=ct).json()
    assert any(w["type"] == "seven_days" and w["staff_id"] == sid for w in r["warnings"]) and r["can_edit"]
    # a leave day clears the warning
    leave = [s for s in r["slots"] if s["staff_id"] == sid][2]
    client.post(f"/api/agency/roster/slots/{leave['id']}/mark", json={"status": "leave"}, headers=ct)
    r = client.get(f"/api/agency/roster?start={base}", headers=ct).json()
    assert not any(w["type"] == "seven_days" for w in r["warnings"])
    # unknown shift for the post is refused
    p2 = client.post("/api/agency/posts", json={"name": "Day only", "kind": "cleaning", "shift_ids": [sh["Day"]]}, headers=ct).json()
    assert client.post("/api/agency/roster/slots", json={"date": str(base), "post_id": p2["id"], "shift_id": sh["Night"], "staff_id": sid}, headers=ct).status_code == 422


def test_copy_and_autofill_week(client):
    pa, ct = prop_headers(client, "padmin"), prop_headers(client, "caretaker")
    a = mk_agency(client, pa, "Copy Co")
    s1, s2 = mk_person(client, pa, a["id"], "Copy One"), mk_person(client, pa, a["id"], "Copy Two")
    sh = shift_ids(client, pa)
    post = client.post("/api/agency/posts", json={"name": "Copy gate", "kind": "security", "agency_id": a["id"]}, headers=ct).json()
    w1 = week_start(_today() + timedelta(days=220))
    for i in range(3):
        slot(client, ct, w1 + timedelta(days=i), post["id"], sh["Day"], s1)
        slot(client, ct, w1 + timedelta(days=i), post["id"], sh["Night"], s2)
    w2 = w1 + timedelta(days=7)
    sug = client.post("/api/agency/roster/autofill", json={"start": str(w2), "apply": False}, headers=ct).json()
    assert sug["added"] == 6 and not sug["applied"]
    assert client.get(f"/api/agency/roster?start={w2}", headers=ct).json()["slots"] == []        # a suggestion saves nothing
    done = client.post("/api/agency/roster/copy", json={"start": str(w2)}, headers=ct).json()
    assert done["added"] == 6
    assert client.post("/api/agency/roster/copy", json={"start": str(w2)}, headers=ct).json()["added"] == 0   # copying twice never doubles
    got = client.get(f"/api/agency/roster?start={w2}", headers=ct).json()["slots"]
    assert len(got) == 6
    client.delete(f"/api/agency/roster/slots/{got[0]['id']}", headers=ct)
    assert client.post("/api/agency/roster/autofill", json={"start": str(w2)}, headers=ct).json()["added"] == 1   # fills only the gap
    assert client.post("/api/agency/roster/copy", json={"start": str(w2)}, headers=prop_headers(client, "treasurer")).status_code == 403


def test_attendance_shortfall_bill_and_expense(client):
    pa, pres, tr, ct = (prop_headers(client, w) for w in ("padmin", "president", "treasurer", "caretaker"))
    a = mk_agency(client, pa, "Bill Co", fee_mode="per_post", monthly_fee=1_000_000)
    s1, s2, s3 = (mk_person(client, pa, a["id"], f"Bill Guard {i}") for i in range(3))
    sh = shift_ids(client, pa)
    pA = client.post("/api/agency/posts", json={"name": "Bill A", "kind": "security", "headcount": 2, "shift_ids": [sh["Day"]], "agency_id": a["id"]}, headers=ct).json()
    pB = client.post("/api/agency/posts", json={"name": "Bill B", "kind": "security", "headcount": 1, "shift_ids": [sh["Day"]], "agency_id": a["id"]}, headers=ct).json()
    assert client.put("/api/agency/settings", json={"shortfall_rate": 25_000}, headers=pres).status_code == 200
    d1, d2 = week_start(__import__("datetime").date(2025, 3, 5)), None
    d2 = d1 + timedelta(days=1)
    x = slot(client, ct, d1, pA["id"], sh["Day"], s1)
    y = slot(client, ct, d1, pA["id"], sh["Day"], s2)
    z = slot(client, ct, d1, pB["id"], sh["Day"], s3)
    w = slot(client, ct, d2, pA["id"], sh["Day"], s1)
    v = slot(client, ct, d2, pA["id"], sh["Day"], s2)
    for sl, st in ((x, "present"), (y, "absent"), (z, "late"), (w, "present"), (v, "present")):
        assert client.post(f"/api/agency/roster/slots/{sl['id']}/mark", json={"status": st}, headers=ct).json()["status"] == st
    # day 1: post A has 1 of 2 present (short 1), post B late counts as present. day 2: A full, B nobody (short 1). Total 2 missing person-shifts.
    chk = client.get(f"/api/agency/bills/check?agency_id={a['id']}&period=2025-03", headers=tr).json()
    assert chk["shortfall_units"] == 2 and chk["contract"] == 2_000_000 and chk["deduction"] == 50_000 and chk["expected"] == 1_950_000
    assert all(isinstance(chk[k], int) for k in ("contract", "deduction", "expected", "rate"))
    summ = client.get("/api/agency/attendance/summary?period=2025-03", headers=pa).json()
    row = [r for r in summ["staff"] if r["staff_id"] == s2][0]
    assert row["absent"] == 1 and row["present"] == 1 and row["scheduled"] == 2
    ag = [r for r in summ["agencies"] if r["agency_id"] == a["id"]][0]
    assert ag["absent"] == 1 and ag["late"] == 1 and ag["shortfall_units"] == 2 and ag["shortfall_days"] == 2
    # the treasurer records the invoice, which becomes a normal expense
    assert client.post("/api/agency/bills", json={"agency_id": a["id"], "period": "2025-03", "number": "B-1", "amount": 1_950_000}, headers=pres).status_code == 403
    bill = client.post("/api/agency/bills", json={"agency_id": a["id"], "period": "2025-03", "number": "B-1", "amount": 2_000_000}, headers=tr).json()
    assert bill["expected"] == 1_950_000 and bill["variance"] == 50_000 and bill["status"] == "pending" and bill["approvals_needed"] == 1
    exp = [e for e in client.get("/api/finance/expenses", headers=tr).json() if e["id"] == bill["expense_id"]][0]
    assert exp["category"] == "services" and exp["vendor"] == "Bill Co" and exp["amount"] == 2_000_000 and not exp["needs_two"]
    assert client.post("/api/agency/bills", json={"agency_id": a["id"], "period": "2025-03", "number": "B-2", "amount": 1}, headers=tr).status_code == 409
    # a big bill follows the two-approver rule and posts to the ledger only when paid
    big = client.post("/api/agency/bills", json={"agency_id": a["id"], "period": "2025-04", "number": "B-3", "amount": 6_000_000}, headers=tr).json()
    eid = big["expense_id"]
    assert big["approvals_needed"] == 2
    assert client.post(f"/api/finance/expenses/{eid}/approve", headers=tr).status_code == 403      # no self approval
    assert client.post(f"/api/finance/expenses/{eid}/approve", headers=pres).json()["status"] == "pending"
    assert client.post(f"/api/finance/expenses/{eid}/pay", json={"method": "bank"}, headers=tr).status_code == 422
    assert client.post(f"/api/finance/expenses/{eid}/approve", headers=pa).json()["status"] == "approved"
    assert client.post(f"/api/finance/expenses/{eid}/pay", json={"method": "bank"}, headers=tr).json()["status"] == "paid"
    assert client.get("/api/finance/trial-balance", headers=tr).json()["debit"] == client.get("/api/finance/trial-balance", headers=tr).json()["credit"]
    bills = client.get("/api/agency/bills", headers=tr).json()
    assert bills["total"] >= 3 and [b for b in bills["items"] if b["id"] == big["id"]][0]["status"] == "paid"
    client.put("/api/agency/settings", json={"shortfall_rate": 40_000}, headers=pres)


def test_replacement_request_and_substitute(client):
    pa, ct = prop_headers(client, "padmin"), prop_headers(client, "caretaker")
    a = mk_agency(client, pa, "Sub Co", contact_phone="01700012345")
    sid = mk_person(client, pa, a["id"], "Sick Guard")
    sh = shift_ids(client, pa)
    post = client.post("/api/agency/posts", json={"name": "Sub gate", "kind": "security", "agency_id": a["id"]}, headers=ct).json()
    d = _today() - timedelta(days=2)
    sl = slot(client, ct, d, post["id"], sh["Night"], sid)
    assert client.post("/api/agency/replacements", json={"slot_id": sl["id"]}, headers=ct).status_code == 422       # not marked absent yet
    client.post(f"/api/agency/roster/slots/{sl['id']}/mark", json={"status": "absent"}, headers=ct)
    r = client.post("/api/agency/replacements", json={"slot_id": sl["id"], "note": "urgent"}, headers=ct)
    assert r.status_code == 201 and r.json()["status"] == "requested" and r.json()["sms_status"] in ("sent", "failed")
    assert client.post("/api/agency/replacements", json={"slot_id": sl["id"]}, headers=ct).status_code == 409
    msgs = client.get("/api/messages", headers=pa)
    if msgs.status_code == 200:
        body = json.dumps(msgs.json())
        assert "roster_replacement" in body
    done = client.post(f"/api/agency/replacements/{r.json()['id']}/fulfil", json={"new": {"name": "Temp Guard", "role": "guard", "phone": "01700055555", "emp_no": "TMP-1"}}, headers=ct).json()
    assert done["status"] == "fulfilled" and done["slot"]["substitute"] is True and done["slot"]["agency"] == "Sub Co"
    pg = client.get("/api/agency/replacements", headers=pa).json()
    assert pg["total"] >= 1 and pg["items"][0]["substitute"] == "Temp Guard"
    people = client.get("/api/staff?employer=all", headers=pa).json()
    assert [p for p in people if p["name"] == "Temp Guard"][0]["agency"]["substitute"] is True
    # a direct employee has no agency to ask
    direct = client.get("/api/staff", headers=pa).json()[0]["id"]
    own = client.post("/api/agency/posts", json={"name": "Own post", "kind": "security"}, headers=ct).json()
    s2 = slot(client, ct, d, own["id"], sh["Day"], direct)
    client.post(f"/api/agency/roster/slots/{s2['id']}/mark", json={"status": "absent"}, headers=ct)
    assert client.post("/api/agency/replacements", json={"slot_id": s2["id"]}, headers=ct).status_code == 422


def test_guard_sees_roster_only_and_no_phones(client):
    pa, ct, gd, tn, au = (prop_headers(client, w) for w in ("padmin", "caretaker", "guard", "tenant", "auditor"))
    r = client.get("/api/agency/roster", headers=gd)
    assert r.status_code == 200 and r.json()["slots"] is not None and r.json()["staff"] == [] and not r.json()["can_edit"]
    text = json.dumps(r.json()) + json.dumps(client.get("/api/agency/today", headers=gd).json()) + json.dumps(client.get("/api/agency/posts", headers=gd).json())
    assert "phone" not in text and "0191150" not in text and "0171122" not in text and "nid" not in text.lower()
    for path in ("/api/staff", "/api/agency/agencies", "/api/agency/bills", "/api/agency/replacements", "/api/agency/attendance/summary?period=2026-10", "/api/agency/settings"):
        assert client.get(path, headers=gd).status_code == 403, path
    some = client.get("/api/staff?employer=all", headers=pa).json()[0]["id"]
    assert client.post(f"/api/staff/{some}/reveal-nid", headers=gd).status_code == 403
    assert client.post("/api/agency/roster/slots", json={"date": str(_today()), "post_id": 1, "shift_id": 1, "staff_id": some}, headers=gd).status_code == 403
    assert client.post("/api/agency/roster/slots", json={"date": str(_today()), "post_id": 1, "shift_id": 1, "staff_id": some}, headers=au).status_code == 403
    assert client.get("/api/agency/roster", headers=au).status_code == 200          # the auditor can view
    assert client.get("/api/agency/roster", headers=tn).status_code == 403          # a resident cannot open the roster


def test_residents_duty_strip_has_no_phones(client):
    pa, ct, tn, ow = (prop_headers(client, w) for w in ("padmin", "caretaker", "tenant", "owner2"))
    a = mk_agency(client, pa, "Duty Co", contact_phone="01788899900", emergency_phone="01788899911")
    sid = mk_person(client, pa, a["id"], "Duty Guard", name_bn="ডিউটি গার্ড", phone="01788877766")
    sh = shift_ids(client, pa)
    post = client.post("/api/agency/posts", json={"name": "Duty gate", "name_bn": "ডিউটি গেট", "kind": "security", "agency_id": a["id"]}, headers=ct).json()
    for d in (_today() - timedelta(days=1), _today()):
        for name in ("Day", "Evening", "Night"):
            slot(client, ct, d, post["id"], sh[name], sid)
    for h in (tn, ow):
        r = client.get("/api/agency/duty", headers=h)
        assert r.status_code == 200
        mine = [i for i in r.json()["items"] if i["name"] == "Duty Guard"]
        assert len(mine) == 1 and mine[0]["agency"] == "Duty Co" and mine[0]["post"] == "Duty gate"
        text = json.dumps(r.json())
        assert "phone" not in text and "01788" not in text and "0191150" not in text and "nid" not in text.lower()
    td = client.get("/api/agency/today", headers=ct).json()
    assert td["can_edit"] and any(i["name"] == "Duty Guard" and i["now"] for i in td["items"])
    # marking attendance for today is one call
    item = [i for i in td["items"] if i["name"] == "Duty Guard" and i["now"]][0]
    assert client.post(f"/api/agency/roster/slots/{item['id']}/mark", json={"status": "present"}, headers=ct).json()["status"] == "present"
    # someone marked absent drops off the strip
    client.post(f"/api/agency/roster/slots/{item['id']}/mark", json={"status": "absent"}, headers=ct)
    assert not [i for i in client.get("/api/agency/duty", headers=tn).json()["items"] if i["name"] == "Duty Guard"]


def test_seed_demo_is_consistent(client):
    pa = prop_headers(client, "padmin")
    names = {a["name"] for a in client.get("/api/agency/agencies", headers=pa).json()}
    assert {"Shield Guard Services Ltd", "CleanPro Facility Services"} <= names
    ps = client.get("/api/agency/posts", headers=pa).json()
    assert len([p for p in ps["posts"] if p["name"] in ("Main gate", "Lobby / CCTV", "Block A cleaning", "Common-area cleaning")]) == 4 and len([s for s in ps["shifts"] if s["name"] in ("Day", "Evening", "Night")]) == 3
    assert {s["name"]: s["hours"] for s in ps["shifts"]}["Night"] == 8
    r = client.get(f"/api/agency/roster?start={week_start(_today()) - timedelta(days=7)}", headers=pa).json()
    assert len(r["slots"]) > 30 and {"absent", "late", "leave"} <= {s["status"] for s in r["slots"]} and any(s["substitute"] for s in r["slots"])
    assert client.get(f"/api/agency/roster?start={week_start(_today())}", headers=pa).json()["slots"]
