from test_property import prop_headers

U = "/api/finance/budget/monthly"


def test_resident_gets_403(client):
    h = prop_headers(client, "tenant")
    assert client.get(f"{U}?year=2026", headers=h).status_code == 403
    assert client.get(f"{U}/vs-actual?year=2026", headers=h).status_code == 403
    assert client.put(U, json={"year": 2026, "months": {"1": {"other": 1}}}, headers=h).status_code == 403
    assert client.post(f"{U}/lock", json={"year": 2024, "month": 1}, headers=h).status_code == 403


def test_seeded_2026_is_seasonal(client):
    h = prop_headers(client, "treasurer")
    g = client.get(f"{U}?year=2026", headers=h).json()
    m = {x["month"]: x for x in g["months"]}
    assert m[6]["source"] == "monthly"
    assert m[6]["lines"]["utilities"] > m[1]["lines"]["utilities"] and m[6]["lines"]["fuel"] > m[12]["lines"]["fuel"]
    assert g["total"] == sum(x["total"] for x in g["months"])


def test_yearly_fallback_splits_evenly_and_adds_up(client):
    ha = prop_headers(client, "padmin")
    assert client.put("/api/finance/budget", json={"year": 2031, "lines": {"salary": 1_000_001, "utilities": 1_200_000}}, headers=ha).status_code == 200
    g = client.get(f"{U}?year=2031", headers=ha).json()
    assert all(x["source"] == "yearly" for x in g["months"])
    assert sum(x["lines"]["salary"] for x in g["months"]) == 1_000_001
    assert {x["lines"]["utilities"] for x in g["months"]} == {100_000}
    assert max(x["lines"]["salary"] for x in g["months"]) - min(x["lines"]["salary"] for x in g["months"]) <= 1


def test_set_month_and_even_split_button(client):
    h = prop_headers(client, "treasurer")
    g = client.put(U, json={"year": 2032, "months": {"3": {"repairs": 500_000}}}, headers=h).json()
    assert g["months"][2]["source"] == "monthly" and g["months"][2]["lines"]["repairs"] == 500_000
    assert client.put("/api/finance/budget", json={"year": 2032, "lines": {"repairs": 1_200_001}}, headers=h).status_code == 200
    r = client.post(f"{U}/copy-forward", json={"year": 2032, "mode": "even_split"}, headers=h).json()
    reps = [x["lines"]["repairs"] for x in r["months"]]
    assert sum(reps) == 1_200_001 and max(reps) - min(reps) <= 1 and len(r["copied"]) == 12


def test_copy_forward_month_to_following_months(client):
    h = prop_headers(client, "padmin")
    client.put(U, json={"year": 2033, "months": {"4": {"utilities": 777_000, "fuel": 111_000}}}, headers=h)
    r = client.post(f"{U}/copy-forward", json={"year": 2033, "mode": "month", "from_month": 4}, headers=h).json()
    assert r["copied"] == list(range(5, 13))
    for x in r["months"][4:]:
        assert x["lines"]["utilities"] == 777_000 and x["lines"]["fuel"] == 111_000
    assert r["months"][1]["lines"]["utilities"] == 0 and r["months"][2]["source"] == "yearly"


def test_lock_rule_and_audit(client):
    ht, hp, ha, hs = (prop_headers(client, w) for w in ("treasurer", "president", "padmin", "secretary"))
    assert client.post(f"{U}/lock", json={"year": 2024, "month": 5}, headers=ht).status_code == 403     # treasurer edits but does not lock
    assert client.post(f"{U}/lock", json={"year": 2999, "month": 5}, headers=hp).status_code == 422     # not closed yet
    assert client.put(U, json={"year": 2024, "months": {"5": {"other": 100}}}, headers=ht).status_code == 200
    assert client.post(f"{U}/lock", json={"year": 2024, "month": 5}, headers=hp).json()["months"][4]["locked"] is True
    body = {"year": 2024, "months": {"5": {"other": 200}}}
    assert client.put(U, json=body, headers=ht).status_code == 423
    assert client.put(U, json=body, headers=hs).status_code == 403
    assert client.put(U, json={**body, "override": True}, headers=ht).json()["months"][4]["lines"]["other"] == 200
    # copy-forward skips a locked month unless overridden
    r = client.post(f"{U}/copy-forward", json={"year": 2024, "mode": "month", "from_month": 4, "to_months": [5, 6]}, headers=ha).json()
    assert r["skipped"] == [5] and r["copied"] == [6]
    # audit trail
    from app.db import SessionLocal
    from app.models.core import AuditLog
    from sqlalchemy import select
    with SessionLocal() as db:
        acts = {a.action for a in db.scalars(select(AuditLog))}
    assert {"budget.month.lock", "budget.month.edit_locked"} <= acts
    assert client.post(f"{U}/lock", json={"year": 2024, "month": 5, "locked": False}, headers=ha).json()["months"][4]["locked"] is False


def test_vs_actual_matches_ledger_and_status(client):
    ht, hp = prop_headers(client, "treasurer"), prop_headers(client, "president")
    v = client.get(f"{U}/vs-actual?year=2026", headers=ht).json()
    s = client.get("/api/finance/summary?year=2026", headers=ht).json()
    by_cat = {c["category"]: c["actual"] for c in s["categories"]}
    for c, a in by_cat.items():
        assert sum(m["categories"][c]["actual"] for m in v["months"]) == a
    assert sum(m["actual"] for m in v["months"]) == s["expense"]
    # a controlled month: budget 1,000.00, spend 950.00 -> near; add more -> over
    client.put(U, json={"year": 2035, "months": {"3": {"repairs": 100_000}}}, headers=ht)
    e = client.post("/api/finance/expenses", json={"category": "repairs", "title": "Vs actual test", "amount": 95_000, "spent_on": "2035-03-10"}, headers=ht).json()
    client.post(f"/api/finance/expenses/{e['id']}/approve", headers=hp)
    client.post(f"/api/finance/expenses/{e['id']}/pay", json={"method": "cash", "paid_on": "2035-03-10"}, headers=ht)
    c = client.get(f"{U}/vs-actual?year=2035", headers=ht).json()["months"][2]["categories"]["repairs"]
    assert (c["budget"], c["actual"], c["pct"], c["status"]) == (100_000, 95_000, 95, "near")
    e2 = client.post("/api/finance/expenses", json={"category": "repairs", "title": "Vs actual test 2", "amount": 10_000, "spent_on": "2035-03-11"}, headers=ht).json()
    client.post(f"/api/finance/expenses/{e2['id']}/approve", headers=hp)
    client.post(f"/api/finance/expenses/{e2['id']}/pay", json={"method": "cash", "paid_on": "2035-03-11"}, headers=ht)
    assert client.get(f"{U}/vs-actual?year=2035", headers=ht).json()["months"][2]["categories"]["repairs"]["status"] == "over"
    assert client.get(f"{U}/vs-actual?year=2035", headers=ht).json()["months"][0]["categories"]["repairs"]["status"] == "under"
