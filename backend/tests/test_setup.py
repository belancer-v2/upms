"""P5: setup wizard progress endpoints."""
import itertools

from conftest import login
from test_property import prop_headers

_n = itertools.count(1)


NEW_PW = "Zx9!kLm2#Qw8"


def first_login(client, email, temp):
    """A sign-in made with a temporary password must set its own password first. Returns auth headers for the new session."""
    lg = client.post("/api/auth/login", json={"email": email, "password": temp})
    assert lg.status_code == 200, lg.text
    assert lg.json()["user"]["must_change_password"] is True
    h = {"Authorization": f"Bearer {lg.json()['token']}"}
    r = client.post("/api/auth/change-password", json={"current_password": temp, "new_password": NEW_PW}, headers=h)
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['token']}"}, lg.json()


def new_building(client, flats=20):
    """A fresh signup: its own organisation, building and PROPERTY_ADMIN. Returns auth + property headers."""
    n = next(_n)
    r = client.post("/api/public/signup", json={"name": "Setup Admin", "email": f"setup{n}@x.test", "password": "longpass1", "building": f"Wizard Court {n}", "flats": flats, "plan": "standard"})
    assert r.status_code == 201, r.text
    d = r.json()
    h = {"Authorization": f"Bearer {d['token']}", "X-Property-Id": str(d["properties"][0]["id"])}
    return h, d


def test_fresh_building_gets_the_wizard(client):
    h, _ = new_building(client)
    s = client.get("/api/setup", headers=h).json()
    assert s["applicable"] is True and s["completed"] is False
    assert [x["step"] for x in s["steps"]] == ["building", "flats", "charges", "reminders", "committee", "review"]
    assert s["next_step"] == "building" and s["percent"] == 0
    assert s["known"]["units"] == 0 and s["known"]["building"]["name"].startswith("Wizard Court")


def test_demo_building_never_sees_the_wizard(client):
    assert client.get("/api/setup", headers=prop_headers(client, "padmin")).json()["applicable"] is False


def test_residents_and_committee_are_not_asked(client):
    assert client.get("/api/setup", headers=prop_headers(client, "tenant")).json()["applicable"] is False
    assert client.get("/api/setup", headers=prop_headers(client, "treasurer")).json()["applicable"] is False
    assert client.put("/api/setup/steps/building", json={"state": "done"}, headers=prop_headers(client, "tenant")).status_code == 403


def test_steps_are_saved_and_skippable(client):
    h, _ = new_building(client)
    client.get("/api/setup", headers=h)
    s = client.put("/api/setup/steps/building", json={"state": "skipped"}, headers=h).json()
    assert s["steps"][0]["state"] == "skipped" and s["percent"] == 17 and s["next_step"] == "flats"
    s = client.put("/api/setup/steps/flats", json={"state": "done"}, headers=h).json()
    assert s["percent"] == 33
    # saved on the server: a second device sees the same
    assert client.get("/api/setup", headers=h).json()["percent"] == 33
    assert client.put("/api/setup/steps/nonsense", json={"state": "done"}, headers=h).status_code == 404
    assert client.put("/api/setup/steps/flats", json={"state": "maybe"}, headers=h).status_code == 422
    s = client.put("/api/setup/steps/flats", json={"state": "todo"}, headers=h).json()
    assert s["steps"][1]["state"] == "todo"


def test_what_is_already_known_is_not_asked_again(client):
    h, _ = new_building(client)
    client.get("/api/setup", headers=h)
    assert client.put("/api/property", json={"name": "Wizard Court", "address": "Road 5, Dhanmondi", "city": "Dhaka", "floors": 8}, headers=h).status_code == 200
    assert client.post("/api/units/generate", json={"floors": 2, "blocks": ["A"], "per_block": 2}, headers=h).status_code == 201
    assert client.post("/api/billing/rules", json={"name": "Service charge", "name_bn": "সার্ভিস চার্জ", "kind": "per_sqft", "amount": 300}, headers=h).status_code == 201
    s = client.get("/api/setup", headers=h).json()
    st = {x["step"]: x["state"] for x in s["steps"]}
    assert st["building"] == st["flats"] == st["charges"] == "known"
    assert st["reminders"] == "todo" and st["committee"] == "todo" and s["next_step"] == "reminders"
    assert s["percent"] == 50


def test_due_day_and_reminders_validate(client):
    h, _ = new_building(client)
    client.get("/api/setup", headers=h)
    s = client.put("/api/setup/data", json={"due_day": 7, "reminders_enabled": True, "reminder_steps": ["before", "o7"]}, headers=h).json()
    assert s["data"]["due_day"] == 7 and s["data"]["reminders"]["steps"] == ["before", "o7"]
    assert {x["step"]: x["state"] for x in s["steps"]}["reminders"] == "known"
    assert client.put("/api/setup/data", json={"due_day": 31}, headers=h).status_code == 422
    assert client.put("/api/setup/data", json={"reminder_steps": ["whenever"]}, headers=h).status_code == 422


def test_committee_logins_with_temp_passwords(client):
    h, _ = new_building(client)
    client.get("/api/setup", headers=h)
    n = next(_n)
    body = {"members": [{"name": "Pres Ident", "email": f"pres{n}@x.test", "role": "PRESIDENT", "phone": "01711000001"},
                        {"name": "Treas Urer", "email": f"treas{n}@x.test", "role": "TREASURER"},
                        {"name": "Dup", "email": "setup1@x.test", "role": "MEMBER"}]}
    r = client.post("/api/setup/committee", json=body, headers=h)
    assert r.status_code == 201
    res = r.json()["results"]
    assert [x["ok"] for x in res] == [True, True, False]
    assert res[2]["error"] and res[0]["temp_password"] and len(res[0]["temp_password"]) >= 8
    # the new president can sign in with the temporary password and holds the role in this building
    hp0, lg = first_login(client, f"pres{n}@x.test", res[0]["temp_password"])
    assert lg["properties"][0]["roles"] == ["PRESIDENT"]
    assert client.get("/api/setup", headers=h).json()["known"]["committee"] == 2
    assert client.post("/api/setup/committee", json={"members": [{"name": "X Y", "email": "a@b.c", "role": "ADMIN"}]}, headers=h).status_code == 422
    # only a manager can create sign-ins
    hp = {**hp0, "X-Property-Id": h["X-Property-Id"]}
    assert client.post("/api/setup/committee", json=body, headers=hp).status_code == 403


def test_complete_and_dismiss(client):
    h, _ = new_building(client)
    client.get("/api/setup", headers=h)
    s = client.post("/api/setup/dismiss", headers=h).json()
    assert s["dismissed"] is True and s["completed"] is False
    s = client.post("/api/setup/complete", headers=h).json()
    assert s["completed"] is True
    assert {x["step"]: x["state"] for x in s["steps"]}["review"] == "done"
    # going back to a step re-opens the wizard
    assert client.put("/api/setup/steps/charges", json={"state": "todo"}, headers=h).json()["completed"] is False
