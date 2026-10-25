"""bKash and SSLCommerz adapters against httpx.MockTransport with example payloads written from memory of the vendor docs.
These tests prove OUR logic (server-side verification, idempotency, amount checks). They do not prove the vendors' real field names."""
import hashlib
import json
from datetime import timedelta

import httpx
import pytest
from sqlalchemy import select

from app.db import SessionLocal
from app.jobs import tasks
from app.models.billing import Payment
from app.models.core import now
from app.models.gateway import GatewaySession
from app.services import gateway as gw
from app.services import gateway_bkash as GB
from app.services import gateway_sslcommerz as GS
from app.services.http_util import ProviderError
from test_gateway import fresh_invoice, start
from test_property import prop_headers

_n = {"i": 0}


def period():
    return f"{2030 + _n['i'] // 12}-{_n['i'] % 12 + 1:02d}"


def taka(p):
    return f"{p / 100:.2f}"


class Vendor:
    """Records calls and answers like a vendor would."""

    def __init__(self):
        self.calls = []
        self.exec_amount = None       # override the amount the vendor reports
        self.exec_status = "Completed"
        self.fail_create = False
        self.down = False
        self.unpaid = set()
        self.ssl = {"status": "VALID", "risk_level": "0", "currency_type": "BDT"}
        self.charged = 0
        self.tran_id = ""

    def __call__(self, req: httpx.Request) -> httpx.Response:
        path = req.url.path
        body = {}
        if req.content and req.headers.get("content-type", "").startswith("application/json"):
            body = json.loads(req.content)
        self.calls.append((req.method, path, body, dict(req.headers), dict(req.url.params)))
        if self.down and "grant" not in path:
            return httpx.Response(500, text="boom")
        if path.endswith("/token/grant"):
            return httpx.Response(200, json={"statusCode": "0000", "statusMessage": "Successful", "id_token": "ID-TOKEN", "token_type": "Bearer", "expires_in": 3600, "refresh_token": "r"})
        if path.endswith("/checkout/create"):
            if self.fail_create:
                return httpx.Response(200, json={"statusCode": "2001", "statusMessage": "Invalid App Key"})
            return httpx.Response(200, json={"statusCode": "0000", "paymentID": "TR0011" + body["merchantInvoiceNumber"][:10], "bkashURL": "https://sbx.bka.sh/pay/TR0011" + body["merchantInvoiceNumber"][:10], "amount": body["amount"], "transactionStatus": "Initiated"})
        if path.endswith("/checkout/execute") or path.endswith("/payment/status"):
            amt = self.exec_amount if self.exec_amount is not None else taka(self.charged)
            st = "Initiated" if body["paymentID"] in self.unpaid else self.exec_status
            return httpx.Response(200, json={"statusCode": "0000", "paymentID": body["paymentID"], "trxID": "BK" + body["paymentID"][-8:], "transactionStatus": st, "amount": amt, "currency": "BDT"})
        if path.endswith("/gwprocess/v4/api.php"):
            return httpx.Response(200, json={"status": "SUCCESS", "sessionkey": "SESS-KEY-1", "GatewayPageURL": "https://sandbox.sslcommerz.com/EasyCheckOut/abc"})
        if path.endswith("/validationserverAPI.php"):
            amt = self.exec_amount if self.exec_amount is not None else taka(self.charged)
            return httpx.Response(200, json={**self.ssl, "tran_id": self.tran_id, "val_id": req.url.params["val_id"], "amount": amt, "bank_tran_id": "BANK-" + self.tran_id[:12]})
        if path.endswith("/merchantTransIDvalidationAPI.php"):
            return httpx.Response(200, json={"APIConnect": "DONE", "no_of_trans_found": 1, "element": [{"status": "VALID", "tran_id": req.url.params["tran_id"], "val_id": "VAL-9", "amount": taka(self.charged)}]})
        return httpx.Response(404)


@pytest.fixture
def vendor(monkeypatch):
    v = Vendor()
    GB._token_cache.clear()
    monkeypatch.setattr(gw, "TRANSPORT", httpx.MockTransport(v))
    for k, val in {"BKASH_MODE": "sandbox", "BKASH_APP_KEY": "APPKEY-1234", "BKASH_APP_SECRET": "APPSECRET-1234", "BKASH_USERNAME": "merch", "BKASH_PASSWORD": "PW-SECRET-1",
                   "SSLCOMMERZ_MODE": "sandbox", "SSLCOMMERZ_STORE_ID": "store1", "SSLCOMMERZ_STORE_PASSWORD": "STOREPW-1234", "API_PUBLIC_URL": "https://flat.example.test", "APP_URL": "https://flat.example.test"}.items():
        monkeypatch.setenv(k, val)
    return v


def new_session(client, vendor, provider="bkash"):
    _n["i"] += 1
    ht, inv = fresh_invoice(client, period())
    co = start(client, ht, inv, provider)
    vendor.charged, vendor.tran_id = co["charged"], co["session_id"]
    return ht, inv, co


def sessions_of(token):
    with SessionLocal() as db:
        s = db.scalar(select(GatewaySession).where(GatewaySession.token == token))
        return s.status, s.payment_id, s.provider_ref


def payments_for(inv_id):
    with SessionLocal() as db:
        return db.scalars(select(Payment).where(Payment.invoice_id == inv_id)).all()


def pay_id(co):
    return "TR0011" + co["session_id"][:10]


def ret(client, token, **params):
    return client.get(f"/api/gateway/return/{token}", params=params, follow_redirects=False)


# ---------------------------------------------------------------- bKash
def test_bkash_checkout_builds_callback_url_and_returns_vendor_page(client, vendor):
    ht, inv, co = new_session(client, vendor)
    pid = "TR0011" + co["session_id"][:10]
    assert co["redirect_url"] == f"https://sbx.bka.sh/pay/{pid}"
    grant = next(c for c in vendor.calls if c[1].endswith("/token/grant"))
    assert grant[3]["username"] == "merch" and grant[2] == {"app_key": "APPKEY-1234", "app_secret": "APPSECRET-1234"}
    create = next(c for c in vendor.calls if c[1].endswith("/checkout/create"))
    assert create[3]["authorization"] == "ID-TOKEN" and create[3]["x-app-key"] == "APPKEY-1234"
    assert create[2]["callbackURL"] == f"https://flat.example.test/api/gateway/return/{co['session_id']}" and create[2]["amount"] == taka(co["charged"]) and create[2]["currency"] == "BDT"
    assert sessions_of(co["session_id"]) == ("created", None, pid)
    assert sum(c[1].endswith("/token/grant") for c in vendor.calls) == 1


def test_bkash_return_executes_queries_and_pays_once(client, vendor):
    ht, inv, co = new_session(client, vendor)
    r = ret(client, co["session_id"], paymentID=pay_id(co), status="success")
    assert r.status_code == 303 and r.headers["location"] == f"https://flat.example.test/pay/return/success?session={co['session_id']}"
    assert [c[1].rsplit("/", 1)[-1] for c in vendor.calls if c[1].endswith(("/execute", "/payment/status"))] == ["execute", "status"]
    st, pid, _ = sessions_of(co["session_id"])
    ps = payments_for(inv["id"])
    assert st == "paid" and len(ps) == 1 and ps[0].status == "verified" and ps[0].trx_id == "BK" + pay_id(co)[-8:] and ps[0].amount == co["amount"] and ps[0].id == pid
    again = ret(client, co["session_id"], paymentID=pay_id(co), status="success")        # browser refresh / replay
    assert again.headers["location"].endswith(f"/success?session={co['session_id']}") and len(payments_for(inv["id"])) == 1


def test_bkash_vendor_amount_is_checked_server_side(client, vendor):
    ht, inv, co = new_session(client, vendor)
    vendor.exec_amount = "1.00"
    r = ret(client, co["session_id"], paymentID=pay_id(co), status="success")
    assert "/pay/return/error" in r.headers["location"] and payments_for(inv["id"]) == [] and sessions_of(co["session_id"])[0] == "created"


def test_bkash_redirect_claiming_success_is_not_believed(client, vendor):
    ht, inv, co = new_session(client, vendor)
    vendor.exec_status = "Failed"
    r = ret(client, co["session_id"], paymentID=pay_id(co), status="success")
    assert "/pay/return/fail" in r.headers["location"] and payments_for(inv["id"]) == []


def test_bkash_cancel_and_wrong_payment_id(client, vendor):
    ht, inv, co = new_session(client, vendor)
    n = len(vendor.calls)
    assert "/pay/return/cancel" in ret(client, co["session_id"], paymentID=pay_id(co), status="cancel").headers["location"]
    assert len(vendor.calls) == n and sessions_of(co["session_id"])[0] == "failed"
    ht, inv, co2 = new_session(client, vendor)
    assert "/pay/return/fail" in ret(client, co2["session_id"], paymentID="TR-OTHER", status="success").headers["location"] and payments_for(inv["id"]) == []


def test_bkash_vendor_down_leaves_session_open(client, vendor):
    ht, inv, co = new_session(client, vendor)
    vendor.down = True
    r = ret(client, co["session_id"], paymentID=pay_id(co), status="success")
    assert "/pay/return/error" in r.headers["location"] and sessions_of(co["session_id"])[0] == "created"


def test_bkash_create_failure_is_a_clean_502_and_no_session(client, vendor):
    _n["i"] += 1
    ht, inv = fresh_invoice(client, period())
    vendor.fail_create = True
    with SessionLocal() as db:
        before = db.query(GatewaySession).count()
    r = client.post("/api/gateway/checkout", json={"invoice_id": inv["id"], "provider": "bkash"}, headers=ht)
    assert r.status_code == 502 and "APPSECRET" not in r.text
    with SessionLocal() as db:
        assert db.query(GatewaySession).count() == before


def test_return_endpoint_404_for_sandbox_sessions(client):
    ht, inv = fresh_invoice(client, "2028-12")
    co = start(client, ht, inv, "bkash")      # no BKASH_MODE: built-in simulator
    assert ret(client, co["session_id"], status="success").status_code == 404
    assert client.get("/api/gateway/return/nonexistent").status_code == 404


def test_bkash_secrets_never_in_errors():
    def boom(req):
        raise httpx.ConnectError("could not connect with APPSECRET-1234")
    p = GB.BkashProvider(transport=httpx.MockTransport(boom), sleep=lambda s: None)
    p.app_key, p.app_secret, p.user, p.pw = "APPKEY-1234", "APPSECRET-1234", "u", "PW-SECRET-1"
    GB._token_cache.clear()
    with pytest.raises(ProviderError) as e:
        p.token()
    assert "APPSECRET" not in str(e.value) and e.value.retryable


# ---------------------------------------------------------------- SSLCommerz
def post_ret(client, token, **form):
    return client.post(f"/api/gateway/return/{token}?r=success", data=form, follow_redirects=False)


def test_sslcommerz_init_and_validation_flow(client, vendor):
    ht, inv, co = new_session(client, vendor, "card")
    assert co["redirect_url"] == "https://sandbox.sslcommerz.com/EasyCheckOut/abc"
    init = next(c for c in vendor.calls if c[1].endswith("/gwprocess/v4/api.php"))
    # init is a form post: re-read it from the recorded request is not possible, so check what the provider would send
    p = GS.SslCommerzProvider(transport=httpx.MockTransport(vendor))
    assert p.host == "https://sandbox.sslcommerz.com"
    assert init[1] == "/gwprocess/v4/api.php"
    r = post_ret(client, co["session_id"], val_id="VAL-1", status="VALID", amount=taka(co["charged"]), tran_id=co["session_id"])
    assert r.status_code == 303 and "/pay/return/success" in r.headers["location"]
    val = next(c for c in vendor.calls if c[1].endswith("/validationserverAPI.php"))
    assert val[4]["val_id"] == "VAL-1" and val[4]["store_id"] == "store1" and val[4]["store_passwd"] == "STOREPW-1234"
    ps = payments_for(inv["id"])
    assert len(ps) == 1 and ps[0].trx_id == "BANK-" + co["session_id"][:12] and ps[0].amount == co["amount"] and sessions_of(co["session_id"])[0] == "paid"
    post_ret(client, co["session_id"], val_id="VAL-1", status="VALID")
    assert len(payments_for(inv["id"])) == 1


def test_sslcommerz_amount_risk_and_tran_id_checks(client, vendor):
    ht, inv, co = new_session(client, vendor, "card")
    vendor.exec_amount = "5.00"
    assert "/pay/return/error" in post_ret(client, co["session_id"], val_id="V", status="VALID").headers["location"] and payments_for(inv["id"]) == []
    vendor.exec_amount = None
    vendor.ssl["risk_level"] = "1"
    assert "/pay/return/fail" in post_ret(client, co["session_id"], val_id="V", status="VALID").headers["location"]
    vendor.ssl["risk_level"] = "0"
    vendor.tran_id = "SOMEONE-ELSES"
    assert "/pay/return/fail" in post_ret(client, co["session_id"], val_id="V", status="VALID").headers["location"] and payments_for(inv["id"]) == []
    vendor.ssl["status"] = "INVALID_TRANSACTION"
    vendor.tran_id = co["session_id"]
    assert "/pay/return/fail" in post_ret(client, co["session_id"], val_id="V", status="VALID").headers["location"]


def test_sslcommerz_fail_and_cancel_return(client, vendor):
    ht, inv, co = new_session(client, vendor, "card")
    r = client.post(f"/api/gateway/return/{co['session_id']}?r=cancel", data={"status": "CANCELLED"}, follow_redirects=False)
    assert "/pay/return/cancel" in r.headers["location"] and sessions_of(co["session_id"])[0] == "failed" and payments_for(inv["id"]) == []


def ipn_form(tran_id, val_id="VAL-IPN", status="VALID", pw="STOREPW-1234", tamper=False):
    f = {"tran_id": tran_id, "val_id": val_id, "status": status, "amount": "1.00", "currency": "BDT", "bank_tran_id": "B1"}
    keys = ["tran_id", "val_id", "status", "amount", "currency", "bank_tran_id"]
    f["verify_key"] = ",".join(keys)
    data = {k: f[k] for k in keys} | {"store_passwd": hashlib.md5(pw.encode()).hexdigest()}
    f["verify_sign"] = hashlib.md5("&".join(f"{k}={data[k]}" for k in sorted(data)).encode()).hexdigest()
    if tamper:
        f["amount"] = "9999.00"
    return f


def test_sslcommerz_ipn_hash_then_validation(client, vendor):
    ht, inv, co = new_session(client, vendor, "card")
    t = co["session_id"]
    assert GS.verify_ipn_hash(ipn_form(t), "STOREPW-1234") and not GS.verify_ipn_hash(ipn_form(t, pw="wrong"), "STOREPW-1234")
    assert client.post("/api/gateway/ipn/sslcommerz", data=ipn_form(t, tamper=True)).status_code == 403
    assert client.post("/api/gateway/ipn/sslcommerz", data=ipn_form(t, pw="wrong")).status_code == 403
    assert client.post("/api/gateway/ipn/sslcommerz", data={k: v for k, v in ipn_form(t).items() if k != "verify_sign"}).status_code == 403
    assert payments_for(inv["id"]) == []
    r = client.post("/api/gateway/ipn/sslcommerz", data=ipn_form(t))
    assert r.status_code == 200 and r.json()["ok"] and sessions_of(t)[0] == "paid"
    client.post("/api/gateway/ipn/sslcommerz", data=ipn_form(t))                     # SSLCommerz retries IPNs
    assert len(payments_for(inv["id"])) == 1
    assert client.post("/api/gateway/ipn/sslcommerz", data=ipn_form("nope")).status_code == 404


def test_ipn_with_valid_hash_but_vendor_validation_down_is_retryable(client, vendor):
    ht, inv, co = new_session(client, vendor, "card")
    vendor.down = True
    assert client.post("/api/gateway/ipn/sslcommerz", data=ipn_form(co["session_id"])).status_code == 502 and payments_for(inv["id"]) == []


# ---------------------------------------------------------------- reconciliation job
def age(token, hours=26, status=None):
    with SessionLocal() as db:
        s = db.scalar(select(GatewaySession).where(GatewaySession.token == token))
        s.created_at = now() - timedelta(hours=hours)
        s.expires_at = s.created_at + timedelta(minutes=30)
        if status:
            s.status = status
        db.commit()


def test_reconcile_recovers_paid_at_provider_and_expires_the_rest(client, vendor):
    ht, inv, co = new_session(client, vendor)                # customer paid at bKash but never came back
    ht2, inv2, co2 = new_session(client, vendor)             # this one was abandoned
    age(co["session_id"])
    age(co2["session_id"])
    vendor.unpaid.add(pay_id(co2))
    with SessionLocal() as db:
        out = tasks.gateway_reconcile(db, now())
        db.commit()
    assert out["checked"] >= 2 and out["recovered"] >= 1 and out["expired"] >= 1
    assert sessions_of(co["session_id"])[0] == "paid" and len(payments_for(inv["id"])) == 1
    assert sessions_of(co2["session_id"])[0] == "expired" and payments_for(inv2["id"]) == []
    with SessionLocal() as db:
        again = tasks.gateway_reconcile(db, now())
        db.commit()
    assert again["recovered"] == 0 and len(payments_for(inv["id"])) == 1


def test_reconcile_flags_amount_mismatch(client, vendor):
    from app.models.jobs import SystemAlert
    ht, inv, co = new_session(client, vendor)
    age(co["session_id"], status="failed")
    vendor.exec_amount = "2.00"
    with SessionLocal() as db:
        out = tasks.gateway_reconcile(db, now())
        db.commit()
        assert out["flagged"] >= 1 and out.get("warn")
        assert db.scalar(select(SystemAlert).where(SystemAlert.dedupe_key.like("reconcile-amt:%")))
    assert payments_for(inv["id"]) == []


def test_reconcile_survives_provider_errors(client, vendor):
    ht, inv, co = new_session(client, vendor)
    age(co["session_id"])
    vendor.down = True
    with SessionLocal() as db:
        out = tasks.gateway_reconcile(db, now())
        assert out["errors"] >= 1
