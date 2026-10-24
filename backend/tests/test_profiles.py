from conftest import login
from test_property import prop_headers

from app.seed import _placeholder_png

PNG = _placeholder_png(1)
JPG = b"\xff\xd8\xff\xe0" + b"0" * 200


def occ_id(client, h, unit="B-302", kind="tenant"):
    u = [x for x in client.get("/api/units", headers=h).json() if x["number"] == unit][0]
    return (u["tenants"] if kind == "tenant" else u["owners"])[0]["id"]


def test_upload_ok_and_served_with_cache_headers(client):
    h = prop_headers(client, "tenant")
    me = client.get("/api/me", headers=h).json()["user"]["id"]
    r = client.post(f"/api/profiles/user/{me}/photo", headers=h, files={"file": ("a.png", PNG, "image/png")})
    assert r.status_code == 200 and r.json()["has_photo"] and r.json()["photo_ver"] >= 1
    got = client.get(f"/api/profiles/user/{me}/photo?v=1", headers=h)
    assert got.status_code == 200 and got.content == PNG and "max-age" in got.headers["cache-control"]
    assert client.post(f"/api/profiles/user/{me}/photo", headers=h, files={"file": ("a.jpg", JPG, "image/jpeg")}).status_code == 200
    idx = client.get("/api/profiles/photos", headers=h).json()
    assert str(me) in {str(k) for k in idx["user"]}
    assert client.delete(f"/api/profiles/user/{me}/photo", headers=h).json()["has_photo"] is False


def test_wrong_type_and_too_big_and_fake_content(client):
    h = prop_headers(client, "padmin")
    me = client.get("/api/me", headers=h).json()["user"]["id"]
    url = f"/api/profiles/user/{me}/photo"
    assert client.post(url, headers=h, files={"file": ("a.gif", b"GIF89a", "image/gif")}).status_code == 422
    assert client.post(url, headers=h, files={"file": ("a.png", b"not an image", "image/png")}).status_code == 422
    assert client.post(url, headers=h, files={"file": ("a.png", PNG + b"0" * (2 * 1024 * 1024), "image/png")}).status_code == 413


def test_details_privacy(client):
    th, mh, ah = prop_headers(client, "tenant"), prop_headers(client, "president"), prop_headers(client, "padmin")
    oh = prop_headers(client, "owner2")
    oid = occ_id(client, ah, "B-302", "tenant")           # Tasnim, the tenant
    owner2_occ = occ_id(client, ah, "B-302", "owner")     # Rokeya, another person in the building
    assert client.put(f"/api/profiles/occupant/{oid}", headers=ah, json={"about": "Hello", "blood_group": "A+", "emergency_phone": "017"}).status_code == 200
    assert client.put(f"/api/profiles/occupant/{owner2_occ}", headers=ah, json={"profession": "Teacher", "address": "Dhanmondi"}).status_code == 200
    # a tenant cannot read another person's details, only name and photo flag
    other = client.get(f"/api/profiles/occupant/{owner2_occ}", headers=th).json()
    assert other["details"] is None and other["can_see_details"] is False and other["name"]
    assert client.put(f"/api/profiles/occupant/{owner2_occ}", headers=th, json={"about": "x"}).status_code == 403
    assert client.post(f"/api/profiles/occupant/{owner2_occ}/photo", headers=th, files={"file": ("a.png", PNG, "image/png")}).status_code == 403
    # the person themself and a manager can
    assert client.get(f"/api/profiles/occupant/{oid}", headers=th).json()["details"]["about"] == "Hello"
    assert client.get(f"/api/profiles/occupant/{owner2_occ}", headers=ah).json()["details"]["address"] == "Dhanmondi"
    assert client.get(f"/api/profiles/occupant/{owner2_occ}", headers=mh).json()["details"]["profession"] == "Teacher"
    # a tenant sees only name and photo of staff
    sid = client.get("/api/staff", headers=ah).json()[0]["id"]
    s = client.get(f"/api/profiles/staff/{sid}", headers=th).json()
    assert s["details"] is None and s["can_edit"] is False
    assert client.get(f"/api/profiles/staff/{sid}", headers=ah).json()["details"] is not None
    # validation
    assert client.put(f"/api/profiles/occupant/{oid}", headers=ah, json={"blood_group": "Z"}).status_code == 422
    assert client.put(f"/api/profiles/occupant/{oid}", headers=ah, json={"dob": "2999-01-01"}).status_code == 422
    # owner may set the photo of their own tenant
    assert client.post(f"/api/profiles/occupant/{oid}/photo", headers=oh, files={"file": ("a.png", PNG, "image/png")}).status_code == 200


def test_staff_photo_by_admin_and_audit(client):
    ah, th = prop_headers(client, "padmin"), prop_headers(client, "tenant")
    sid = client.get("/api/staff", headers=ah).json()[1]["id"]
    assert client.post(f"/api/profiles/staff/{sid}/photo", headers=ah, files={"file": ("a.png", PNG, "image/png")}).status_code == 200
    assert client.get(f"/api/profiles/staff/{sid}/photo", headers=th).status_code == 200    # residents may see the photo
    assert client.post(f"/api/profiles/staff/{sid}/photo", headers=th, files={"file": ("a.png", PNG, "image/png")}).status_code == 403
    log = client.get("/api/audit", headers=ah)
    if log.status_code == 200:
        assert "profile.photo" in str(log.json())


def test_seeded_people_have_photos(client):
    h = prop_headers(client, "president")
    idx = client.get("/api/profiles/photos", headers=h).json()
    assert len(idx["user"]) >= 4 and len(idx["staff"]) == 4
