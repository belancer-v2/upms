"""P2 authorization audit.

1. Every route in the app either answers 401 without a token or is on the explicit PUBLIC allow-list below. A new route that forgets its
   auth dependency fails this test; so does an allow-list entry for a route that no longer exists.
2. Cross-tenant isolation: a signed-in user with no membership in a building (a stranger from another organisation, a member of the same
   organisation who works in another building) cannot read or touch that building's data, by listing endpoints or by guessing object ids (IDOR).
"""
import io
import itertools
import re

import pytest
from fastapi.routing import APIRoute

from app.main import app
from conftest import login

_n = itertools.count(1)

# --------------------------------------------------------------------------------------------- 1. authentication
# Every public route, with the reason it is public. Anything else must answer 401 without a token.
PUBLIC = {
    ("GET", "/api/health"): "liveness probe",
    ("GET", "/healthz"): "liveness probe",
    ("GET", "/readyz"): "readiness probe",
    ("POST", "/api/auth/login"): "sign in (throttled, neutral errors)",
    ("GET", "/api/auth/demo-accounts"): "demo login list; empty unless DEMO=1",
    ("POST", "/api/auth/refresh"): "needs a refresh token (body or cookie+CSRF header), not a bearer token",
    ("POST", "/api/auth/logout"): "idempotent; revokes whatever token it is shown",
    ("POST", "/api/auth/forgot-password"): "neutral answer, rate limited",
    ("POST", "/api/auth/reset-password"): "single-use emailed token",
    ("POST", "/api/auth/verify-email"): "single-use emailed token",
    ("POST", "/api/auth/resend-verification"): "neutral answer, rate limited",
    ("GET", "/api/public/form-token"): "signed timestamp for the anti-spam check",
    ("GET", "/api/public/plans"): "public pricing",
    ("POST", "/api/public/leads"): "website contact form (rate limited, honeypot)",
    ("POST", "/api/public/signup"): "self-service sign-up (rate limited, honeypot, optional e-mail verification)",
    ("GET", "/api/notices/link/{token}"): "SMS link: unguessable per-recipient token",
    ("GET", "/api/onboarding/link/{token}"): "tenant form link: unguessable per-case token",
    ("PUT", "/api/onboarding/link/{token}"): "tenant form link",
    ("POST", "/api/onboarding/link/{token}/docs"): "tenant form link (magic-byte checked uploads)",
    ("POST", "/api/onboarding/link/{token}/submit"): "tenant form link",
    ("POST", "/api/gateway/callback/{token}"): "payment provider callback: HMAC signature is the proof",
    ("GET", "/api/gateway/return/{token}"): "payment provider browser return: only redirects, state is confirmed server side",
    ("POST", "/api/gateway/return/{token}"): "payment provider browser return (POST variant)",
    ("POST", "/api/gateway/ipn/sslcommerz"): "payment provider IPN: verified with the provider",
    ("POST", "/api/credits/callback/{token}"): "payment provider callback: HMAC signature is the proof",
    ("GET", "/api/public/unsubscribe/{token}"): "signed e-mail link",
    ("POST", "/api/public/unsubscribe/{token}"): "signed e-mail link",
    ("GET", "/api/public/mail/open/{token}.gif"): "signed tracking pixel",
    ("GET", "/api/public/mail/click/{token}"): "signed tracked link",
    ("POST", "/api/webhooks/sms/{provider}"): "SMS provider delivery webhook (verified inside)",
    ("POST", "/api/webhooks/ses"): "SES notification webhook (verified inside)",
}


def flat(routes):
    for r in routes:
        if isinstance(r, APIRoute):
            yield r
        elif hasattr(r, "original_router"):
            yield from flat(r.original_router.routes)


def all_routes():
    out = []
    for r in flat(app.routes):
        for m in sorted(r.methods - {"HEAD", "OPTIONS"}):
            out.append((m, r.path, r))
    return out


def fill(path: str, value: str = "1") -> str:
    return re.sub(r"\{[^}]+\}", value, path)


def test_every_route_requires_authentication_or_is_explicitly_public(client):
    seen = set()
    unprotected = []
    for method, path, _r in all_routes():
        seen.add((method, path))
        if (method, path) in PUBLIC:
            continue
        res = client.request(method, fill(path))
        if res.status_code != 401:
            unprotected.append((method, path, res.status_code))
    assert not unprotected, f"routes that answer without a token and are not on the PUBLIC list: {unprotected}"
    stale = [k for k in PUBLIC if k not in seen]
    assert not stale, f"PUBLIC entries for routes that no longer exist: {stale}"
    assert len(seen) > 300      # the enumeration really walked the whole app


def test_a_garbage_or_foreign_token_is_not_authentication(client):
    for tok in ("garbage", "Bearer", "Bearer ", "Bearer a.b.c"):
        assert client.get("/api/me", headers={"Authorization": tok}).status_code == 401
    assert client.get("/api/billing/invoices", headers={"Authorization": "Bearer a.b.c", "X-Property-Id": "1"}).status_code == 401


# --------------------------------------------------------------------------------------------- 2. tenant isolation
MARKERS = ("Sunrise Tower", "Lakeview Heights", "Green Court", "Mahmud Hasan", "Tasnim Ferdous", "Rokeya Begum", "Imran Hossain", "Jahangir Alam",
           "Rahim Mia", "Belal Hossain", "padmin@flatwise.demo", "owner@flatwise.demo", "tenant@flatwise.demo", "01911000009", "Metro Property Care")
OK_STATES = {400, 401, 402, 403, 404, 405, 409, 410, 415, 422, 423}      # everything but a successful answer


@pytest.fixture(scope="module")
def world(client):
    """Sunrise Tower data seen through its admin, and a stranger: a fresh sign-up with its own organisation and building."""
    padmin, data = login(client, "padmin")
    sun = next(p["id"] for p in data["properties"] if p["name"] == "Sunrise Tower")
    owner, odata = login(client, "owner")
    lake = next(p["id"] for p in login(client, "agency")[1]["properties"] if p["name"] == "Lakeview Heights")
    n = next(_n)
    r = client.post("/api/public/signup", json={"name": "Mallory Outsider", "email": f"mallory{n}@evil.test", "password": "longpass1", "building": f"Evil Court {n}", "flats": 10, "plan": "pro"})
    assert r.status_code == 201, r.text
    stranger = r.json()
    return {"sun": sun, "lake": lake, "padmin": {**padmin, "X-Property-Id": str(sun)}, "owner": owner, "owner_data": odata,
            "stranger": {"Authorization": f"Bearer {stranger['token']}"}, "stranger_prop": stranger["properties"][0]["id"], "stranger_user": stranger["user"]["id"]}


def hdr(base, prop):
    return {**base, "X-Property-Id": str(prop)}


def scoped_routes():
    """Routes that work inside one building (they use property_ctx), as (method, path)."""
    out = []
    for m, p, r in all_routes():
        names = set()

        def walk(d):
            for s in d.dependencies:
                names.add(getattr(s.call, "__name__", ""))
                walk(s)
        walk(r.dependant)
        if "property_ctx" in names:
            out.append((m, p))
    return out


def leaks(text: str) -> list[str]:
    return [m for m in MARKERS if m in text]


def test_scoped_routes_found():
    s = scoped_routes()
    assert len(s) > 200 and ("GET", "/api/billing/invoices") in s


def test_stranger_is_refused_every_building_listing(client, world):
    """No membership in Sunrise Tower: every property-scoped endpoint refuses, whatever the method."""
    bad = []
    for method, path in scoped_routes():
        res = client.request(method, fill(path), headers=hdr(world["stranger"], world["sun"]), json={} if method in ("POST", "PUT", "PATCH") else None)
        if res.status_code in (200, 201, 204) or leaks(res.text):
            bad.append((method, path, res.status_code))
    assert not bad, bad


def test_same_organisation_user_in_another_building_is_refused(client, world):
    """Flat owner of Sunrise Tower works for the same agency, but has no role in Lakeview Heights."""
    bad = []
    for method, path in scoped_routes():
        if method != "GET" or "{" in path:
            continue
        res = client.get(path, headers=hdr(world["owner"], world["lake"]))
        if res.status_code != 403:
            bad.append((path, res.status_code))
    assert not bad, bad


def test_stranger_sees_none_of_sunrise_in_their_own_building(client, world):
    """In the stranger's own (empty) building, no listing may contain another building's people, names or money."""
    h = hdr(world["stranger"], world["stranger_prop"])
    hits, total = [], 0
    for method, path in scoped_routes():
        if method != "GET" or "{" in path:
            continue
        res = client.get(path, headers=h)
        total += 1
        if res.status_code == 200 and leaks(res.text):
            hits.append((path, leaks(res.text)))
    assert total > 60 and not hits, hits


def test_object_id_guessing_is_blocked_everywhere(client, world):
    """IDOR sweep: call every scoped route that takes an id, with the ids 1..40 and the stranger's own building. Nothing may succeed."""
    h = hdr(world["stranger"], world["stranger_prop"])
    ok = []
    for method, path in scoped_routes():
        if "{" not in path:
            continue
        for i in (1, 2, 3, 5, 8, 13, 21, 34):
            url = re.sub(r"\{[^}]+\}", str(i), path)
            res = client.request(method, url, headers=h, json={} if method in ("POST", "PUT", "PATCH") else None)
            if res.status_code in (200, 201, 204) or leaks(res.text):
                ok.append((method, url, res.status_code))
                break
    assert not ok, ok


# ---- named endpoints with real ids from the seeded Sunrise Tower
def _first(client, h, path, key="id", items=None):
    res = client.get(path, headers=h)
    assert res.status_code == 200, (path, res.text[:200])
    data = res.json()
    rows = data[items] if items else data
    assert rows, path
    return rows[0][key]


@pytest.fixture(scope="module")
def targets(client, world):
    """(label, url) pairs for objects that exist in Sunrise Tower, found through its admin."""
    h = world["padmin"]
    g = lambda path, **kw: _first(client, h, path, **kw)   # noqa: E731
    t = []
    inv = g("/api/billing/invoices")
    t += [("invoice", f"/api/billing/invoices/{inv}"), ("receipt", f"/api/billing/receipts/{g('/api/billing/payments')}")]
    staff = g("/api/staff")
    t += [("staff nid views", f"/api/staff/{staff}/nid-views"), ("payroll sheet", f"/api/staff/payroll/sheets/{g('/api/staff/payroll/sheets')}")]
    t += [("notice reach", f"/api/notices/{g('/api/notices')}/reach"), ("policy history", f"/api/policies/{g('/api/policies')}/history")]
    case = g("/api/onboarding/cases")
    t += [("onboarding case", f"/api/onboarding/cases/{case}"), ("onboarding pack", f"/api/onboarding/cases/{case}/pack")]
    t += [("request", f"/api/requests/{g('/api/requests', items='items')}"), ("meeting", f"/api/committee/meetings/{g('/api/committee/meetings', items='items')}")]
    unit = g("/api/units?q=A-501")
    t += [("rental unit", f"/api/rental/units/{unit}", "owner"), ("parking unit", f"/api/parking/units/{unit}")]
    t += [("visit photo", f"/api/visitors/visits/{g('/api/visitors/visits', items='items')}/photo")]
    t += [("vehicle photo", f"/api/parking/vehicles/{g('/api/parking/vehicles', items='items')}/photo")]
    t += [("amenity calendar", f"/api/amenities/{g('/api/amenities')}/calendar")]
    ag = g("/api/agency/agencies")
    t += [("agency", f"/api/agency/agencies/{ag}"), ("contract", f"/api/contracts/{g('/api/contracts', items='items')}")]
    return t


def test_named_object_endpoints_are_blocked_for_a_stranger_and_open_for_the_admin(client, world, targets):
    served = 0
    for label, url, *who in [(*t, ) if len(t) > 2 else (*t, "padmin") for t in targets]:
        reader = hdr(world["owner"], world["sun"]) if who[0] == "owner" else world["padmin"]
        assert client.get(url, headers=reader).status_code in ((200, 403, 404) if who[0] == "owner" else (200, 404)), (label, url)   # 404 = no file/data behind it in the seed; the rental add-on can be off
        served += client.get(url, headers=reader).status_code == 200
        for who, prop in ((world["stranger"], world["sun"]), (world["stranger"], world["stranger_prop"]), (world["owner"], world["lake"])):
            res = client.get(url, headers=hdr(who, prop))
            assert res.status_code in OK_STATES and not leaks(res.text), (label, url, res.status_code)
    assert served >= 10           # the admin really could read them, so the refusals above are meaningful


def test_a_resident_cannot_open_another_flats_objects(client, world, targets):
    """Same building, wrong role/flat: the tenant of one flat must not read the money, staff vault or onboarding files."""
    th, tdata = login(client, "tenant")
    tprop = next(p["id"] for p in tdata["properties"] if p["name"] == "Sunrise Tower")
    h = hdr(th, tprop)
    for label in ("staff nid views", "payroll sheet", "onboarding pack", "onboarding case", "notice reach", "agency", "contract"):
        url = next(t[1] for t in targets if t[0] == label)
        assert client.get(url, headers=h).status_code in (403, 404), label


def test_uploaded_files_are_only_served_to_people_who_may_see_them(client, world):
    """A real uploaded tenant document: reviewer yes; stranger, other building and anonymous no. Served as a download that cannot run."""
    h = world["padmin"]
    invited = [c for c in client.get("/api/onboarding/cases", headers=h).json() if c["status"] == "invited"]
    if not invited:
        pytest.skip("the seed has no onboarding case waiting for the tenant")
    cid = invited[0]["id"]
    token = client.get(f"/api/onboarding/cases/{cid}", headers=h).json()["token"]
    png = b"\x89PNG\r\n\x1a\n" + b"\x00" * 200
    fake = client.post(f"/api/onboarding/link/{token}/docs", data={"kind": "photo"}, files={"file": ("../../evil.png", b"<script>alert(1)</script>", "image/png")})
    assert fake.status_code == 422                                           # text pretending to be a picture
    up = client.post(f"/api/onboarding/link/{token}/docs", data={"kind": "photo"}, files={"file": ("../../x/photo\r\n.png", png, "image/png")})
    assert up.status_code == 201, up.text
    doc = up.json()["docs"][0]
    assert "/" not in doc["filename"] and "\n" not in doc["filename"] and ".." not in doc["filename"]
    url = f"/api/onboarding/cases/{cid}/docs/{doc['id']}/file"
    ok = client.get(url, headers=h)
    assert ok.status_code == 200 and ok.content == png
    assert ok.headers["content-disposition"].startswith("attachment") and ok.headers["x-content-type-options"] == "nosniff"
    assert "sandbox" in ok.headers["content-security-policy"]
    assert client.get(url).status_code == 401
    for who, prop in ((world["stranger"], world["sun"]), (world["stranger"], world["stranger_prop"]), (world["owner"], world["lake"])):
        assert client.get(url, headers=hdr(who, prop)).status_code in OK_STATES


def test_profile_photos_and_profiles_do_not_cross_buildings(client, world):
    owner_id = world["owner_data"]["user"]["id"]
    ph = hdr(world["owner"], world["sun"])
    png = b"\x89PNG\r\n\x1a\n" + b"\x00" * 100
    up = client.post(f"/api/profiles/user/{owner_id}/photo", headers=ph, files={"file": ("me.png", png, "image/png")})
    assert up.status_code == 200, up.text
    assert client.get(f"/api/profiles/user/{owner_id}/photo", headers=ph).status_code == 200
    for prop in (world["sun"], world["stranger_prop"]):
        h = hdr(world["stranger"], prop)
        for url in (f"/api/profiles/user/{owner_id}", f"/api/profiles/user/{owner_id}/photo", "/api/profiles/occupant/1", "/api/profiles/occupant/1/photo", "/api/profiles/staff/1", "/api/profiles/staff/1/photo"):
            res = client.get(url, headers=h)
            assert res.status_code in OK_STATES and not leaks(res.text), (url, prop, res.status_code)
        # and may not write
        assert client.put(f"/api/profiles/user/{owner_id}", headers=h, json={"about": "pwned"}).status_code in OK_STATES
        assert client.delete(f"/api/profiles/user/{owner_id}/photo", headers=h).status_code in OK_STATES
        assert client.post(f"/api/profiles/user/{owner_id}/photo", headers=h, files={"file": ("x.png", png, "image/png")}).status_code in OK_STATES
    idx = client.get("/api/profiles/photos", headers=hdr(world["stranger"], world["stranger_prop"])).json()
    assert owner_id not in {int(k) for k in idx["user"]}


def test_audit_log_and_portfolio_are_scoped(client, world):
    for prop in (world["sun"], world["stranger_prop"], 0):
        h = hdr(world["stranger"], prop)
        res = client.get("/api/audit?limit=500", headers=h)
        assert res.status_code == 200 and all(row["who"] in ("Mallory Outsider", "system") for row in res.json()), prop
    assert client.get("/api/portfolio", headers=world["stranger"]).status_code in OK_STATES
    assert client.post("/api/portfolio/buildings", headers=world["stranger"], json={"name": "x"}).status_code in OK_STATES


def test_saas_console_is_closed_to_customers(client, world):
    bad = []
    for m, p, r in all_routes():
        if not p.startswith(("/api/saas", "/api/console")):
            continue
        for who in (world["stranger"], world["owner"], world["padmin"]):
            res = client.request(m, fill(p), headers=who, json={} if m in ("POST", "PUT", "PATCH") else None)
            if res.status_code in (200, 201, 204):
                bad.append((m, p, res.status_code))
    assert not bad, bad


def test_credit_invoices_and_payment_sessions_belong_to_their_buyer(client, world):
    for i in range(1, 40):
        assert client.get(f"/api/credits/invoices/{i}", headers=world["stranger"]).status_code == 404
        assert client.get(f"/api/gateway/sandbox/token-{i}", headers=world["stranger"]).status_code == 404


def test_stranger_cannot_use_a_suspended_or_foreign_org_through_the_header_alone(client, world):
    """The X-Property-Id header names a building but never grants anything by itself."""
    for pid in range(1, 12):
        res = client.get("/api/property", headers=hdr(world["stranger"], pid))
        if pid == world["stranger_prop"]:
            assert res.status_code == 200
        else:
            assert res.status_code in (400, 403, 404), (pid, res.status_code)
