import hashlib
import hmac
import json

import httpx
import pytest
from sqlalchemy import select

from app.db import SessionLocal
from app.models.billing import Message
from app.models.core import Organization, Property
from app.models.jobs import SmsDispatch
from app.models.saas import SmsLedger
from app.services import messaging, sms
from app.services.entitlements import sms_balance

BN = "বকেয়া সার্ভিস চার্জ পরিশোধ করুন"


def test_segments_gsm_and_bangla():
    assert sms.segments("a" * 160) == (1, "gsm") and sms.segments("a" * 161) == (2, "gsm") and sms.segments("a" * 306) == (2, "gsm") and sms.segments("a" * 307)[0] == 3
    assert sms.segments("{" * 80) == (1, "gsm") and sms.segments("{" * 81)[0] == 2      # extension characters count twice
    assert sms.segments(BN) == (1, "unicode") and sms.segments("ক" * 70)[0] == 1 and sms.segments("ক" * 71)[0] == 2 and sms.segments("ক" * 135)[0] == 3
    assert sms.segments("hello ক")[1] == "unicode"


def test_credit_rules_are_configurable(monkeypatch):
    assert sms.credits_for("ক" * 71) == (2, 2, "unicode")
    monkeypatch.setenv("SMS_BILL_BY_SEGMENT", "0")
    assert sms.credits_for("ক" * 71)[0] == 1
    monkeypatch.setenv("SMS_BILL_BY_SEGMENT", "1")
    monkeypatch.setenv("SMS_CREDITS_PER_SEGMENT", "2")
    assert sms.credits_for("hi")[0] == 2
    monkeypatch.setenv("SMS_UNICODE_SINGLE", "100")
    monkeypatch.setenv("SMS_CREDITS_PER_SEGMENT", "1")
    assert sms.segments("ক" * 100)[0] == 1


@pytest.mark.parametrize("raw", ["01712345678", "+8801712345678", "8801712345678", "017-1234 5678", "008801712345678"])
def test_msisdn_normalised(raw):
    assert sms.normalize_msisdn(raw) == "8801712345678"


@pytest.mark.parametrize("raw", ["", "12345", "0171234567", "01212345678", "abc", "+441234567890"])
def test_bad_msisdn(raw):
    with pytest.raises(ValueError):
        sms.normalize_msisdn(raw)


def mock(handler):
    return httpx.MockTransport(handler)


def bulk(handler, **kw):
    return sms.BulkSmsBd(transport=mock(handler), api_key="KEY-SECRET-123", sender_id="FlatWise", base_url="http://bulksmsbd.test/api", sleep=lambda s: None, **kw)


def test_bulksmsbd_success_and_unicode_type():
    seen = []

    def h(req: httpx.Request):
        seen.append(dict(httpx.QueryParams(req.content.decode())))
        return httpx.Response(200, json={"response_code": 202, "message": "SMS Submitted Successfully"})
    p = bulk(h)
    r = p.send_one("01712345678", BN, "ref-1")
    assert r.ok and r.ref == "ref-1"
    assert seen[0]["type"] == "unicode" and seen[0]["number"] == "8801712345678" and seen[0]["senderid"] == "FlatWise" and seen[0]["api_key"] == "KEY-SECRET-123"
    p.send_one("01712345678", "hello", "ref-2")
    assert seen[1]["type"] == "text"


@pytest.mark.parametrize("code,fragment,retry", [(1007, "insufficient", False), (1002, "Sender", False), (1032, "whitelisted", False), (1005, "Internal", True), (9999, "9999", False)])
def test_bulksmsbd_error_codes(code, fragment, retry):
    r = bulk(lambda req: httpx.Response(200, json={"response_code": code})).send_one("01712345678", "x", "r")
    assert not r.ok and fragment in r.error and r.code == str(code) and r.retryable is retry


def test_bulksmsbd_invalid_number_never_calls_provider():
    called = []
    r = bulk(lambda req: called.append(1) or httpx.Response(200, json={"response_code": 202})).send_one("12345", "x")
    assert not r.ok and r.code == "1001" and not called


def test_bulksmsbd_retries_5xx_then_succeeds_and_gives_up():
    n = {"c": 0}

    def flaky(req):
        n["c"] += 1
        return httpx.Response(503) if n["c"] < 3 else httpx.Response(200, json={"response_code": 202})
    assert bulk(flaky).send_one("01712345678", "x", "r").ok and n["c"] == 3
    r = bulk(lambda req: httpx.Response(502)).send_one("01712345678", "x", "r")
    assert not r.ok and r.retryable and "502" in r.error


def test_bulksmsbd_network_error_does_not_leak_key():
    def boom(req):
        raise httpx.ConnectError("cannot connect to http://bulksmsbd.test/api?api_key=KEY-SECRET-123")
    r = bulk(boom).send_one("01712345678", "x", "r")
    assert not r.ok and "KEY-SECRET-123" not in r.error and r.retryable


def test_read_timeout_is_not_retried_for_sends():
    n = {"c": 0}

    def slow(req):
        n["c"] += 1
        raise httpx.ReadTimeout("slow")
    r = bulk(slow).send_one("01712345678", "x", "r")
    assert not r.ok and n["c"] == 1          # the message may already have been accepted: never send twice


def test_bulksmsbd_not_configured():
    r = sms.BulkSmsBd(transport=mock(lambda r: httpx.Response(200)), api_key="", sender_id="").send_one("01712345678", "x")
    assert not r.ok and "not configured" in r.error


def test_bulk_chunks_and_per_item_results():
    bodies = []

    def h(req):
        bodies.append(json.loads(req.content))
        return httpx.Response(200, json={"response_code": 202})
    items = [sms.SmsItem(f"0171234{i:04d}", f"m{i}", f"r{i}") for i in range(5)] + [sms.SmsItem("bad", "x", "rb")]
    out = bulk(h).send_many(items, chunk=2)
    assert [len(b["messages"]) for b in bodies] == [2, 2, 1] and bodies[0]["messages"][0] == {"to": "8801712340000", "message": "m0"} and bodies[0]["senderid"] == "FlatWise"
    assert [o.ok for o in out] == [True] * 5 + [False] and out[5].code == "1001" and out[0].ref == "r0"


def test_balance():
    assert bulk(lambda r: httpx.Response(200, json={"balance": "1234.50"})).balance() == 1234.5
    assert bulk(lambda r: httpx.Response(200, text="Balance: 99")).balance() == 99.0


def test_generic_http_gateway_preset_style():
    seen = {}

    def h(req):
        seen["url"], seen["body"], seen["auth"] = str(req.url), json.loads(req.content), req.headers.get("authorization")
        return httpx.Response(200, json={"status": "SUCCESS", "smsinfo": [{"sms_info": [{"reference_id": "R-9"}]}]})
    p = sms.HttpSms("sslwireless", {**sms.PRESETS["sslwireless"], "auth": "Authorization: Bearer {api_key}"}, transport=mock(h), api_key="K", sender_id="FW", sleep=lambda s: None)
    r = p.send_one("01712345678", "hi", "c1")
    assert r.ok and r.ref == "R-9" and seen["body"]["msisdn"] == "8801712345678" and seen["body"]["csms_id"] == "c1" and seen["auth"] == "Bearer K"
    bad = sms.HttpSms("x", {**sms.PRESETS["sslwireless"]}, transport=mock(lambda r: httpx.Response(200, json={"status": "FAILED"})), api_key="K", sleep=lambda s: None)
    assert not bad.send_one("01712345678", "hi").ok


def test_provider_selection(monkeypatch):
    assert sms.get_provider().name == "sandbox"
    monkeypatch.setenv("SMS_PROVIDER", "bulksmsbd")
    assert sms.get_provider().name == "bulksmsbd"
    monkeypatch.setenv("SMS_PROVIDER", "greenweb")
    assert sms.get_provider().name == "greenweb"


# ---------------------------------------------------------------- charging through messaging.deliver
def _org_and_prop(db):
    prop = db.scalar(select(Property).order_by(Property.id))
    return prop.org_id, prop


def _msg(db, prop, body, key):
    m = Message(property_id=prop.id, to_name="T", to_phone="01712345678", template="notice", lang="bn", body=body, idem_key=key)
    db.add(m)
    return m


def test_deliver_charges_per_segment_and_records_dispatch(client):
    with SessionLocal() as db:
        org, prop = _org_and_prop(db)
        db.add(SmsLedger(org_id=org, delta=1000, reason="test"))
        db.flush()
        before = sms_balance(db, org)
        m = _msg(db, prop, "ক" * 71, "p3-seg-1")
        messaging.deliver(db, org, m)
        db.commit()
        assert m.status == "sent" and before - sms_balance(db, org) == 2
        d = db.get(SmsDispatch, m.id)
        assert d.segments == 2 and d.encoding == "unicode" and d.credits == 2 and d.provider == "sandbox"


def test_provider_failure_charges_nothing(client, monkeypatch):
    monkeypatch.setenv("SMS_PROVIDER", "bulksmsbd")
    monkeypatch.setattr(sms, "get_provider", lambda: bulk(lambda r: httpx.Response(200, json={"response_code": 1007})))
    with SessionLocal() as db:
        org, prop = _org_and_prop(db)
        before = sms_balance(db, org)
        m = _msg(db, prop, "hello", "p3-fail-1")
        messaging.deliver(db, org, m)
        db.commit()
        assert m.status == "failed" and "insufficient" in m.error and sms_balance(db, org) == before


# ---------------------------------------------------------------- delivery report webhook
def test_dlr_webhook_signature_status_and_refund(client, monkeypatch):
    with SessionLocal() as db:
        org, prop = _org_and_prop(db)
        db.add(SmsLedger(org_id=org, delta=100, reason="test"))
        m = _msg(db, prop, "dlr test", "p3-dlr-1")
        messaging.deliver(db, org, m)
        db.commit()
        mid, bal = m.id, sms_balance(db, org)
        ref = db.get(SmsDispatch, mid).provider_ref
    body = json.dumps({"ref": ref, "status": "FAILED", "reason": "handset off"}).encode()
    # not configured
    assert client.post("/api/webhooks/sms/x", content=body).status_code == 503
    monkeypatch.setenv("SMS_DLR_SECRET", "topsecret")
    assert client.post("/api/webhooks/sms/x", content=body).status_code == 403
    assert client.post("/api/webhooks/sms/x", content=body, headers={"X-Signature": "00"}).status_code == 403
    sig = hmac.new(b"topsecret", body, hashlib.sha256).hexdigest()
    r = client.post("/api/webhooks/sms/x", content=body, headers={"X-Signature": sig})
    assert r.status_code == 200 and r.json()["status"] == "undelivered"
    again = client.post("/api/webhooks/sms/x", content=body, headers={"X-Signature": sig})
    assert again.json().get("replayed")
    with SessionLocal() as db:
        m = db.get(Message, mid)
        assert m.status == "failed" and "handset off" in m.error and sms_balance(db, org) == bal + 1      # refunded exactly once
        assert db.get(SmsDispatch, mid).dlr_status == "undelivered"


def test_dlr_token_auth_and_delivered(client, monkeypatch):
    monkeypatch.setenv("SMS_DLR_TOKEN", "tok-123")
    with SessionLocal() as db:
        org, prop = _org_and_prop(db)
        db.add(SmsLedger(org_id=org, delta=10, reason="test"))
        m = _msg(db, prop, "ok test", "p3-dlr-2")
        messaging.deliver(db, org, m)
        db.commit()
    assert client.post("/api/webhooks/sms/x?token=nope", data={"ref": "p3-dlr-2", "status": "Delivered"}).status_code == 403
    r = client.post("/api/webhooks/sms/x?token=tok-123", data={"ref": "p3-dlr-2", "status": "Delivered"})   # looked up by our idempotency key too
    assert r.status_code == 200 and r.json()["status"] == "delivered"
    with SessionLocal() as db:
        assert db.scalar(select(Message.status).where(Message.idem_key == "p3-dlr-2")) == "sent"
