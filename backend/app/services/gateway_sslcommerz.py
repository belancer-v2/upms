"""SSLCommerz adapter: init session, validation API (val_id), transaction query, IPN with hash verification.

VERIFIED ONLY AGAINST MOCKS (httpx.MockTransport with example payloads written from memory of the SSLCommerz docs).
Every URL, field name and status value below must be certified in the SSLCommerz sandbox with the merchant's own store before live use.
See docs/PAYMENTS_SETUP.md.

Env: SSLCOMMERZ_MODE=off|sandbox|live (off = built-in simulator), SSLCOMMERZ_STORE_ID, SSLCOMMERZ_STORE_PASSWORD,
SSLCOMMERZ_KEYS (which of our payment methods go through it, default "card"), API_PUBLIC_URL, APP_URL.
"""
from __future__ import annotations

import hashlib
import hmac
import os

import httpx

from .gateway_bkash import public_origin, taka, to_paisa
from .http_util import ProviderError, send

HOSTS = {"sandbox": "https://sandbox.sslcommerz.com", "live": "https://securepay.sslcommerz.com"}   # TO VERIFY
GOOD = ("VALID", "VALIDATED")


def verify_ipn_hash(params: dict, store_password: str) -> bool:
    """verify_key names the fields that were signed; verify_sign = md5 of those fields (sorted by name) plus md5(store_password)."""
    keys, sign = str(params.get("verify_key", "")), str(params.get("verify_sign", ""))
    if not keys or not sign:
        return False
    data = {k: str(params.get(k, "")) for k in keys.split(",") if k}
    data["store_passwd"] = hashlib.md5(store_password.encode()).hexdigest()
    base = "&".join(f"{k}={data[k]}" for k in sorted(data))
    return hmac.compare_digest(hashlib.md5(base.encode()).hexdigest(), sign.lower())


class SslCommerzProvider:
    live = True

    def __init__(self, key: str = "card", transport: httpx.BaseTransport | None = None, sleep=None):
        e = os.getenv
        self.key = key
        self.mode = e("SSLCOMMERZ_MODE", "sandbox")
        self.host = HOSTS.get(self.mode, HOSTS["sandbox"])
        self.store, self.pw = e("SSLCOMMERZ_STORE_ID", ""), e("SSLCOMMERZ_STORE_PASSWORD", "")
        self.transport = transport
        self.kw = {"sleep": sleep} if sleep else {}

    def _call(self, method: str, path: str, safe: bool = True, **kw) -> dict:
        if not (self.store and self.pw):
            raise ProviderError("SSLCommerz is not configured (SSLCOMMERZ_STORE_ID, SSLCOMMERZ_STORE_PASSWORD)", code="config")
        r = send(method, f"{self.host}{path}", secrets=[self.pw], transport=self.transport, timeout=float(os.getenv("SSLCOMMERZ_TIMEOUT", "20")),
                 retries=2 if safe else 0, retry_on_read_timeout=safe, **self.kw, **kw)
        try:
            j = r.json()
        except ValueError:
            raise ProviderError(f"SSLCommerz answered HTTP {r.status_code} with a non-JSON body", retryable=r.status_code >= 500, code="parse")
        return j if isinstance(j, dict) else {}

    def create_checkout(self, invoice, amount: int, *, token: str, user=None) -> dict:
        base = f"{public_origin()}/api/gateway"
        form = {"store_id": self.store, "store_passwd": self.pw, "total_amount": taka(amount), "currency": "BDT", "tran_id": token,
                "success_url": f"{base}/return/{token}?r=success", "fail_url": f"{base}/return/{token}?r=fail", "cancel_url": f"{base}/return/{token}?r=cancel",
                "ipn_url": f"{base}/ipn/sslcommerz", "cus_name": getattr(user, "name", "") or "Resident", "cus_email": getattr(user, "email", "") or "noreply@example.com",
                "cus_add1": "Dhaka", "cus_city": "Dhaka", "cus_country": "Bangladesh", "cus_phone": getattr(user, "phone", "") or "01700000000",
                "shipping_method": "NO", "product_name": f"Service charge {getattr(invoice, 'number', '')}"[:100], "product_category": "Service", "product_profile": "non-physical-goods"}
        j = self._call("POST", "/gwprocess/v4/api.php", False, data=form)
        if j.get("status") != "SUCCESS" or not j.get("GatewayPageURL"):
            raise ProviderError(f"SSLCommerz could not start the payment: {str(j.get('failedreason', ''))[:80]}", code="init")
        return {"session_id": token, "redirect_url": j["GatewayPageURL"], "provider_ref": str(j.get("sessionkey", ""))[:40]}

    def validate(self, val_id: str) -> dict:
        """The validation API: the only thing that proves a payment. Returns the normalised result."""
        j = self._call("GET", "/validator/api/validationserverAPI.php", params={"val_id": val_id, "store_id": self.store, "store_passwd": self.pw, "format": "json"})
        return self._read(j)

    @staticmethod
    def _read(j: dict) -> dict:
        st = str(j.get("status", ""))
        paid = st in GOOD and str(j.get("currency_type", j.get("currency", "BDT"))) == "BDT"
        flagged = str(j.get("risk_level", "0")) not in ("0", "")
        return {"status": "paid" if paid and not flagged else "failed" if st in ("FAILED", "INVALID_TRANSACTION") else "cancelled" if st == "CANCELLED" else "pending" if not paid else "failed",
                "trx_id": str(j.get("bank_tran_id") or j.get("val_id") or "")[:40], "amount": to_paisa(j["amount"]) if j.get("amount") not in (None, "") else 0,
                "tran_id": str(j.get("tran_id", "")), "val_id": str(j.get("val_id", "")), "raw_status": st, "risk": flagged}

    def query(self, s) -> dict:
        j = self._call("GET", "/validator/api/merchantTransIDvalidationAPI.php", params={"tran_id": s.token, "store_id": self.store, "store_passwd": self.pw, "format": "json"})
        els = [x for x in j.get("element", []) if isinstance(x, dict)]
        good = [x for x in els if x.get("status") in GOOD]
        if good:
            return self.validate(str(good[0].get("val_id", "")))      # re-validate by val_id before believing it
        return {"status": "pending" if not els else "failed", "trx_id": "", "amount": 0, "raw_status": str(els[0].get("status", "")) if els else "none"}

    def finalize(self, s, params: dict) -> dict:
        r = str(params.get("r", ""))
        if r == "cancel" or str(params.get("status", "")).upper() == "CANCELLED":
            return {"status": "cancelled", "trx_id": "", "amount": 0}
        val = str(params.get("val_id", ""))
        if r == "fail" or not val:
            return {"status": "failed", "trx_id": "", "amount": 0}
        res = self.validate(val)
        if res["status"] == "paid" and res["tran_id"] != s.token:
            return {"status": "failed", "trx_id": "", "amount": 0, "detail": "tran_id mismatch"}
        return res

    def ipn(self, params: dict) -> dict | None:
        """Hash check first, then the validation API. None when the hash is wrong."""
        if not verify_ipn_hash(params, self.pw):
            return None
        return self.finalize(type("S", (), {"token": str(params.get("tran_id", ""))})(), {"val_id": params.get("val_id", ""), "status": params.get("status", "")})
