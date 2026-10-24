from test_property import prop_headers


def _list(client, who, **q):
    r = client.get("/api/requests", params={"size": 100, **q}, headers=prop_headers(client, who))
    assert r.status_code == 200, r.text
    return r.json()


def test_residents_see_only_their_flat(client):
    all_rows = _list(client, "padmin")
    assert all_rows["total"] == 12 and sum(1 for r in all_rows["items"] if r["overdue"]) == 1
    tenant = _list(client, "tenant")
    assert {r["unit"] for r in tenant["items"]} == {"B-302"} and 0 < tenant["total"] < 12
    rep = _list(client, "ownerrep")
    assert {r["unit"] for r in rep["items"]} == {"A-801"}
    assert _list(client, "caretaker")["total"] == 12
    assert client.get("/api/requests", headers=prop_headers(client, "guard")).status_code == 403


def test_paging_and_filters(client):
    p = _list(client, "president", size=5, page=3)
    assert len(p["items"]) == 2 and p["total"] == 12
    assert all(r["category"] == "lift" for r in _list(client, "president", category="lift")["items"])
    assert _list(client, "president", overdue=True)["total"] == 1


def test_raise_assign_progress_resolve_reopen_rate(client):
    ht, hc, hp = prop_headers(client, "tenant"), prop_headers(client, "caretaker"), prop_headers(client, "padmin")
    r = client.post("/api/requests", json={"category": "noise", "title": "Loud music at night", "text": "From the flat above."}, headers=ht)
    assert r.status_code == 201 and r.json()["unit"] == "B-302" and r.json()["sla_hours"] == 24 and not r.json()["overdue"]
    rid = r.json()["id"]
    assert client.post(f"/api/requests/{rid}/assign", json={"assignee_id": 1}, headers=ht).status_code == 403
    me = [a for a in client.get("/api/requests/assignees", headers=hp).json() if a["role"] == "CARETAKER"][0]
    assert client.post(f"/api/requests/{rid}/status", json={"status": "in_progress"}, headers=hc).status_code == 409   # nobody assigned yet
    assert client.post(f"/api/requests/{rid}/assign", json={"assignee_id": me["id"]}, headers=hp).json()["status"] == "assigned"
    assert client.post(f"/api/requests/{rid}/status", json={"status": "in_progress"}, headers=hc).json()["status"] == "in_progress"
    assert client.post(f"/api/requests/{rid}/status", json={"status": "resolved"}, headers=ht).status_code == 403          # a resident cannot resolve
    assert client.post(f"/api/requests/{rid}/rate", json={"rating": 5}, headers=ht).status_code == 409                     # not yet resolved
    assert client.post(f"/api/requests/{rid}/status", json={"status": "resolved"}, headers=hc).json()["status"] == "resolved"
    assert client.post(f"/api/requests/{rid}/status", json={"status": "in_progress"}, headers=hc).status_code == 409        # only forward
    assert client.post(f"/api/requests/{rid}/reopen", headers=ht).json()["status"] == "assigned"
    assert client.post(f"/api/requests/{rid}/status", json={"status": "resolved"}, headers=hc).status_code == 200
    assert client.post(f"/api/requests/{rid}/reopen", headers=ht).status_code == 409                                         # once only
    assert client.post(f"/api/requests/{rid}/rate", json={"rating": 6}, headers=ht).status_code == 422
    assert client.post(f"/api/requests/{rid}/rate", json={"rating": 4, "note": "ok"}, headers=ht).json()["rating"] == 4
    assert client.post(f"/api/requests/{rid}/rate", json={"rating": 5}, headers=ht).status_code == 409
    client.post(f"/api/requests/{rid}/comments", json={"text": "Thank you"}, headers=ht)
    d = client.get(f"/api/requests/{rid}", headers=ht).json()
    assert any(c["kind"] == "comment" and c["text"] == "Thank you" for c in d["thread"]) and not d["can_reopen"]
    # another flat's resident cannot open it
    assert client.get(f"/api/requests/{rid}", headers=prop_headers(client, "ownerrep")).status_code == 404
    assert client.post("/api/requests", json={"category": "lift", "title": "Not my flat", "unit_id": _list(client, "padmin")["items"][0]["unit_id"]}, headers=prop_headers(client, "ownerrep")).status_code == 403


def test_sla_is_editable_by_admin_only(client):
    hp, ht = prop_headers(client, "padmin"), prop_headers(client, "tenant")
    assert client.put("/api/requests/sla/security", json={"hours": 2}, headers=ht).status_code == 403
    assert client.put("/api/requests/sla/security", json={"hours": 2}, headers=hp).json()["hours"] == 2
    assert {s["category"]: s["hours"] for s in client.get("/api/requests/sla", headers=ht).json()}["security"] == 2
    r = client.post("/api/requests", json={"category": "security", "title": "Gate light flickers"}, headers=ht).json()
    assert r["sla_hours"] == 2
    client.put("/api/requests/sla/security", json={"hours": 6}, headers=hp)


def test_committee_tenure_and_expiring(client):
    h = prop_headers(client, "secretary")
    cur = client.get("/api/committee/members", headers=h).json()
    assert cur["total"] == 4 and cur["expiring"] == 1
    assert [m["role"] for m in cur["items"] if m["expiring_soon"]] == ["treasurer"]
    hist = client.get("/api/committee/members", params={"scope": "history"}, headers=h).json()
    assert hist["total"] == 5 and any(m["expired"] for m in hist["items"])
    assert client.get("/api/committee/members", headers=prop_headers(client, "tenant")).status_code == 403
    bad = {"name": "Test Person", "role": "member", "start_date": "2026-05-01", "end_date": "2026-04-01"}
    assert client.post("/api/committee/members", json=bad, headers=h).status_code == 422
    ok = client.post("/api/committee/members", json={**bad, "end_date": "2028-04-01"}, headers=h)
    assert ok.status_code == 201
    ext = client.put(f"/api/committee/members/{ok.json()['id']}", json={"end_date": "2029-04-01"}, headers=h).json()
    assert ext["end_date"] == "2029-04-01"


def test_meetings_minutes_flow(client):
    h = prop_headers(client, "secretary")
    ms = client.get("/api/committee/meetings", headers=h).json()
    assert ms["total"] == 3 and {m["status"] for m in ms["items"]} == {"held", "scheduled"}
    held = [m for m in ms["items"] if m["status"] == "held"][0]
    d = client.get(f"/api/committee/meetings/{held['id']}", headers=h).json()
    assert d["decisions"] and d["minutes"] and len(d["attendance"]) == 4
    new = client.post("/api/committee/meetings", json={"title": "Special meeting", "held_on": "2026-01-05", "place": "Hall", "agenda": "Gate repair"}, headers=h)
    assert new.status_code == 201
    mid, ids = new.json()["id"], [a["member_id"] for a in new.json()["attendance"]]
    done = client.post(f"/api/committee/meetings/{mid}/minutes", json={"present": ids[:2], "minutes": "Discussed.", "decisions": ["Repair the gate", " "]}, headers=h).json()
    assert done["status"] == "held" and done["present"] == 2 and done["decisions"] == ["Repair the gate"]
    fut = client.post("/api/committee/meetings", json={"title": "Future one", "held_on": "2099-01-01"}, headers=h).json()
    assert client.post(f"/api/committee/meetings/{fut['id']}/minutes", json={}, headers=h).status_code == 409
    assert client.post(f"/api/committee/meetings/{fut['id']}/cancel", headers=h).json()["status"] == "cancelled"
    assert client.post("/api/committee/meetings", json={"title": "Nope nope", "held_on": "2026-12-01"}, headers=prop_headers(client, "member")).status_code == 403


def test_vote_majority_one_vote_and_lock(client):
    hp, hm, ho = prop_headers(client, "president"), prop_headers(client, "member"), prop_headers(client, "owner")
    p = client.post("/api/committee/proposals", json={"title": "Paint the lobby", "text": "Quote BDT 45,000."}, headers=hp).json()
    assert p["status"] == "open" and p["can_vote"]
    assert client.post(f"/api/committee/proposals/{p['id']}/vote", json={"choice": "approve"}, headers=hm).json()["my_vote"] == "approve"
    assert client.post(f"/api/committee/proposals/{p['id']}/vote", json={"choice": "reject"}, headers=hm).status_code == 409     # one vote per person
    assert client.post(f"/api/committee/proposals/{p['id']}/vote", json={"choice": "approve"}, headers=prop_headers(client, "padmin")).status_code == 403   # managers do not vote
    client.post(f"/api/committee/proposals/{p['id']}/vote", json={"choice": "reject"}, headers=ho)
    tied = client.post(f"/api/committee/proposals/{p['id']}/close", headers=hp).json()
    assert tied["status"] == "closed" and tied["result"] == "tied" and tied["tally"]["approve"] == 1 and len(tied["votes"]) == 2
    assert client.post(f"/api/committee/proposals/{p['id']}/vote", json={"choice": "approve"}, headers=hp).status_code == 409    # locked
    assert client.post(f"/api/committee/proposals/{p['id']}/close", headers=hp).status_code == 409
    q = client.post("/api/committee/proposals", json={"title": "Buy a water pump"}, headers=hp).json()
    client.post(f"/api/committee/proposals/{q['id']}/vote", json={"choice": "approve"}, headers=hp)
    assert client.post(f"/api/committee/proposals/{q['id']}/close", headers=hm).status_code == 403
    assert client.post(f"/api/committee/proposals/{q['id']}/close", headers=hp).json()["result"] == "approved"
    seeded = client.get("/api/committee/proposals", params={"status": "open"}, headers=hp).json()
    assert any(x["title"].startswith("Approve the lift motor") and x["voted"] == 3 for x in seeded["items"])
    assert client.get("/api/committee/proposals", headers=prop_headers(client, "owner2")).status_code == 403
