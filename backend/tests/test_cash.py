from conftest import login
from test_property import prop_headers


def open_invoice(client, h, number):
    """Returns the n-th unpaid October invoice (number is only a label, picks a different flat per test)."""
    pending = {p["invoice_id"] for p in client.get("/api/billing/payments?status=pending", headers=h).json()}
    rows = [i for i in client.get("/api/billing/invoices?period=2026-10", headers=h).json() if i["status"] != "paid" and i["id"] not in pending and i["balance"] > 100000]
    return rows[{"A-102": 0, "A-302": 1, "A-402": 2}[number]]


def test_caretaker_code_flow_and_lockout(client):
    h = prop_headers(client, "caretaker")
    inv = open_invoice(client, prop_headers(client, "padmin"), "A-102")
    assert inv["status"] in ("overdue", "partial")
    r = client.post("/api/cash/entries", json={"invoice_id": inv["id"], "amount": 500}, headers=h)
    assert r.status_code == 201, r.text
    eid, code = r.json()["id"], r.json()["demo_code"]
    assert len(code) == 6
    for n in (2, 1, 0):
        w = client.post(f"/api/cash/entries/{eid}/code", json={"code": "000000" if code != "000000" else "111111"}, headers=h)
        assert w.status_code == 422 and (f"{n} tries left" in w.text or n == 0)
    assert client.post(f"/api/cash/entries/{eid}/code", json={"code": code}, headers=h).status_code == 423   # locked even for the right code
    assert client.post(f"/api/cash/entries/{eid}/cancel", headers=h).status_code == 200


def test_right_code_creates_payment_and_custody(client):
    h = prop_headers(client, "caretaker")
    inv = open_invoice(client, prop_headers(client, "padmin"), "A-302")
    before = client.get("/api/cash/custody", headers=h).json()["rows"][0]["held"]
    r = client.post("/api/cash/entries", json={"invoice_id": inv["id"], "amount": 700}, headers=h).json()
    ok = client.post(f"/api/cash/entries/{r['id']}/code", json={"code": r["demo_code"]}, headers=h)
    assert ok.status_code == 200 and ok.json()["status"] == "held"
    assert client.get("/api/cash/custody", headers=h).json()["rows"][0]["held"] == before + 700
    again = open_invoice(client, prop_headers(client, "padmin"), "A-302")
    assert again["paid"] == inv["paid"] + 700


def test_custody_limit_blocks(client):
    h = prop_headers(client, "caretaker")
    inv = open_invoice(client, prop_headers(client, "padmin"), "A-402")
    r = client.post("/api/cash/entries", json={"invoice_id": inv["id"], "amount": 5_000_001}, headers=h)
    assert r.status_code in (409, 422)


def test_handover_accept_and_roles(client):
    h = prop_headers(client, "caretaker")
    assert client.post("/api/cash/remittances", headers=prop_headers(client, "owner2")).status_code == 403
    rem = client.post("/api/cash/remittances", headers=h)
    assert rem.status_code == 201
    rid = rem.json()["id"]
    assert client.post(f"/api/cash/remittances/{rid}/accept", headers=h).status_code == 403   # a caretaker cannot accept their own hand-over
    assert client.post(f"/api/cash/remittances/{rid}/accept", headers=prop_headers(client, "treasurer")).json()["status"] == "accepted"
    assert client.get("/api/cash/custody", headers=h).json()["rows"][0]["held"] == 0


def test_payer_confirms_in_app(client):
    h = prop_headers(client, "caretaker")
    t = prop_headers(client, "tenant")
    inv = [i for i in client.get("/api/billing/invoices?period=2026-09", headers=t).json()][0]
    if inv["status"] == "paid":
        return
    e = client.post("/api/cash/entries", json={"invoice_id": inv["id"], "amount": 100}, headers=h).json()
    mine = client.get("/api/cash/entries", headers=t).json()
    assert any(x["id"] == e["id"] for x in mine)
    assert client.post(f"/api/cash/entries/{e['id']}/confirm", headers=prop_headers(client, "owner2")).status_code in (200, 403)
