"""bKash tokenized checkout adapter: grant token, create payment, execute payment, query payment.

VERIFIED ONLY AGAINST MOCKS (httpx.MockTransport with example payloads written from memory of the bKash docs).
Every URL path, header name, field name and status code below must be certified in the bKash sandbox with the merchant's own
credentials before live use. See docs/PAYMENTS_SETUP.md.

Env: BKASH_MODE=off|sandbox|live (off = built-in simulator), BKASH_APP_KEY, BKASH_APP_SECRET, BKASH_USERNAME, BKASH_PASSWORD,
BKASH_BASE_URL (optional override), API_PUBLIC_URL (public https origin used to build the callback URL).
"""
from __future__ import annotations

import os
import threading
import time
from decimal import Decimal, InvalidOperation

import httpx

from .http_util import ProviderError, send

BASES = {"sandbox": "https://tokenized.sandbox.bka.sh/v1.2.0-beta", "live": "https://tokenized.pay.bka.sh/v1.2.0-beta"}   # TO VERIFY
_token_cache: dict = {}
_lock = threading.Lock()


def taka(paisa: int) -> str:
    return f"{Decimal(paisa) / 100:.2f}"


def to_paisa(value) -> int:
    try:
        return int((Decimal(str(value)) * 100).to_integral_value())
    except (InvalidOperation, ValueError):
        raise ProviderError("Provider sent an unreadable amount", code="parse")


def public_origin() -> str:
    return (os.getenv("API_PUBLIC_URL") or os.getenv("APP_URL", "http://localhost:3000")).rstrip("/")


class BkashProvider:
    key = "bkash"
    live = True

    def __init__(self, transport: httpx.BaseTransport | None = None, sleep=None):
        e = os.getenv
        self.mode = e("BKASH_MODE", "sandbox")
        self.base = (e("BKASH_BASE_URL") or BASES.get(self.mode, BASES["sandbox"])).rstrip("/")
        self.app_key, self.app_secret, self.user, self.pw = e("BKASH_APP_KEY", ""), e("BKASH_APP_SECRET", ""), e("BKASH_USERNAME", ""), e("BKASH_PASSWORD", "")
        self.transport = transport
        self.kw = {"sleep": sleep} if sleep else {}

    # -- plumbing
    def _secrets(self) -> list[str]:
        return [self.app_secret, self.pw, self.app_key]

    def _post(self, path: str, body: dict, headers: dict, safe_to_repeat: bool) -> dict:
        if not all((self.app_key, self.app_secret, self.user, self.pw)):
            raise ProviderError("bKash is not configured (BKASH_APP_KEY, BKASH_APP_SECRET, BKASH_USERNAME, BKASH_PASSWORD)", code="config")
        r = send("POST", f"{self.base}{path}", secrets=self._secrets(), transport=self.transport, timeout=float(os.getenv("BKASH_TIMEOUT", "15")),
                 retries=2 if safe_to_repeat else 0, retry_on_read_timeout=safe_to_repeat, headers={"Accept": "application/json", **headers}, json=body, **self.kw)
        try:
            j = r.json()
        except ValueError:
            raise ProviderError(f"bKash answered HTTP {r.status_code} with a non-JSON body", retryable=r.status_code >= 500, code="parse")
        return j if isinstance(j, dict) else {}

    def token(self) -> str:
        with _lock:
            c = _token_cache.get((self.base, self.app_key))
            if c and c[1] > time.time() + 30:
                return c[0]
            j = self._post("/tokenized/checkout/token/grant", {"app_key": self.app_key, "app_secret": self.app_secret}, {"username": self.user, "password": self.pw}, True)
            if j.get("statusCode") != "0000" or not j.get("id_token"):
                raise ProviderError(f"bKash refused the token request: {str(j.get('statusMessage', ''))[:80]}", code=str(j.get("statusCode", "")))
            _token_cache[(self.base, self.app_key)] = (j["id_token"], time.time() + int(j.get("expires_in", 3600)))
            return j["id_token"]

    def _auth(self) -> dict:
        return {"Authorization": self.token(), "X-APP-Key": self.app_key}

    # -- the four calls
    def create_checkout(self, invoice, amount: int, *, token: str, user=None) -> dict:
        body = {"mode": "0011", "payerReference": str(getattr(user, "phone", "") or getattr(user, "id", "") or "01"), "callbackURL": f"{public_origin()}/api/gateway/return/{token}",
                "amount": taka(amount), "currency": "BDT", "intent": "sale", "merchantInvoiceNumber": token[:30]}
        j = self._post("/tokenized/checkout/create", body, self._auth(), False)
        if j.get("statusCode") != "0000" or not j.get("paymentID") or not j.get("bkashURL"):
            raise ProviderError(f"bKash could not start the payment: {str(j.get('statusMessage', ''))[:80]}", code=str(j.get("statusCode", "")))
        return {"session_id": token, "redirect_url": j["bkashURL"], "provider_ref": str(j["paymentID"])[:40]}

    def execute(self, payment_id: str) -> dict:
        return self._post("/tokenized/checkout/execute", {"paymentID": payment_id}, self._auth(), False)

    def query_payment(self, payment_id: str) -> dict:
        return self._post("/tokenized/checkout/payment/status", {"paymentID": payment_id}, self._auth(), True)

    @staticmethod
    def _read(j: dict) -> dict:
        st = str(j.get("transactionStatus", ""))
        status = "paid" if st == "Completed" else "pending" if st in ("Initiated", "Authorized", "") else "cancelled" if st == "Cancelled" else "failed"
        return {"status": status, "trx_id": str(j.get("trxID", "")), "amount": to_paisa(j["amount"]) if j.get("amount") not in (None, "") else 0, "raw_status": st}

    def query(self, s) -> dict:
        j = self.query_payment(s.provider_ref)
        if str(j.get("statusCode", "0000")) not in ("0000", ""):
            raise ProviderError(f"bKash query failed: {str(j.get('statusMessage', ''))[:80]}", code=str(j.get("statusCode")))
        return self._read(j)

    def finalize(self, s, params: dict) -> dict:
        """The customer came back. The redirect parameters only say which branch to take; what counts is what bKash itself reports to us."""
        if params.get("paymentID") and params["paymentID"] != s.provider_ref:
            return {"status": "failed", "trx_id": "", "amount": 0, "detail": "payment id mismatch"}
        outcome = str(params.get("status", "")).lower()
        if outcome in ("cancel", "cancelled"):
            return {"status": "cancelled", "trx_id": "", "amount": 0}
        if outcome == "failure":
            return {"status": "failed", "trx_id": "", "amount": 0}
        ex = self.execute(s.provider_ref)
        if ex.get("statusCode") == "0000" and ex.get("transactionStatus") == "Completed":
            q = self.query_payment(s.provider_ref)      # second, independent confirmation of trxID and amount
            if q.get("transactionStatus") == "Completed" and str(q.get("trxID")) == str(ex.get("trxID")):
                return self._read(q)
            return {"status": "failed", "trx_id": "", "amount": 0, "detail": "query did not confirm execute"}
        # execute refused: maybe it already ran (replayed redirect). The query tells the truth.
        return self.query(s) if ex.get("statusCode") not in (None, "0000") else {"status": "failed", "trx_id": "", "amount": 0}
