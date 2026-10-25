"""SMS providers. SMS_PROVIDER selects one:

  sandbox (default)   no network; the message counts as sent
  bulksmsbd           BulkSMSBD HTTP API (first-class)
  http                generic HTTP gateway driven only by env (URL template, method, params, auth header)
  sslwireless | greenweb | alphasms | mimsms   presets of the generic adapter (field names from memory, see docs/SMS_SETUP.md)

Every adapter implements SmsProvider.send_one / send_many / balance. Numbers are normalised to 8801XXXXXXXXX.
Credit use is per segment (see segments()). Secrets are read from env and never logged.
VENDOR FACTS (URLs, field names, response codes) ARE FROM MEMORY AND MUST BE CHECKED AGAINST THE VENDOR DOCS BEFORE GO-LIVE.
"""
from __future__ import annotations

import json
import os
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field

import httpx

from .http_util import ProviderError, send

# ------------------------------------------------------------------ numbers and segments
def normalize_msisdn(raw: str, fmt: str | None = None) -> str:
    """01712345678, +8801712345678, 8801712345678 and 880 1712-345678 all become 8801712345678. Raises ValueError for anything else."""
    d = re.sub(r"[\s\-().]", "", raw or "")
    d = d.removeprefix("+")
    if d.startswith("00880"):
        d = d[2:]
    if d.startswith("01") and len(d) == 11:
        d = "88" + d
    if not re.fullmatch(r"8801[3-9]\d{8}", d):
        raise ValueError("Not a Bangladesh mobile number")
    fmt = fmt or os.getenv("SMS_MSISDN_FORMAT", "intl")
    return {"local": "0" + d[3:], "plus": "+" + d}.get(fmt, d)


_GSM_BASIC = set("@£$¥èéùìòÇ\nØø\rÅåΔ_ΦΓΛΩΠΨΣΘΞÆæßÉ !\"#¤%&'()*+,-./0123456789:;<=>?¡ABCDEFGHIJKLMNOPQRSTUVWXYZÄÖÑÜ§¿abcdefghijklmnopqrstuvwxyzäöñüà")
_GSM_EXT = set("^{}\\[~]|€\f")


def encoding_of(text: str) -> str:
    return "gsm" if all(c in _GSM_BASIC or c in _GSM_EXT for c in text) else "unicode"


def _envint(name: str, default: int) -> int:
    try:
        return max(1, int(os.getenv(name, str(default))))
    except ValueError:
        return default


def segments(text: str) -> tuple[int, str]:
    """(segments, encoding). Bangla (any non-GSM character) is UCS-2: 70 characters in one SMS, 67 per part when joined.
    GSM-7: 160 / 153, extension characters count twice. Limits are env-configurable (SMS_GSM_SINGLE etc.)."""
    enc = encoding_of(text)
    if enc == "gsm":
        n, single, multi = sum(2 if c in _GSM_EXT else 1 for c in text), _envint("SMS_GSM_SINGLE", 160), _envint("SMS_GSM_MULTI", 153)
    else:
        n, single, multi = len(text), _envint("SMS_UNICODE_SINGLE", 70), _envint("SMS_UNICODE_MULTI", 67)
    if n <= single:
        return 1, enc
    return -(-n // multi), enc


def credits_for(text: str) -> tuple[int, int, str]:
    """(credits to charge, segments, encoding). SMS_BILL_BY_SEGMENT=0 charges one credit per message; SMS_CREDITS_PER_SEGMENT scales."""
    seg, enc = segments(text)
    per = _envint("SMS_CREDITS_PER_SEGMENT", 1)
    return (seg * per if os.getenv("SMS_BILL_BY_SEGMENT", "1") != "0" else per), seg, enc


# ------------------------------------------------------------------ interface
@dataclass
class SmsResult:
    ok: bool
    ref: str = ""                 # provider message id when it gives one
    error: str = ""               # short reason, safe to show
    code: str = ""                # provider's own code
    retryable: bool = False


@dataclass
class SmsItem:
    to: str
    text: str
    ref: str = ""                 # our idempotency reference


class SmsProvider(ABC):
    name = ""
    simulates = False

    @abstractmethod
    def send_one(self, to: str, text: str, ref: str = "") -> SmsResult: ...

    def send_many(self, items: list[SmsItem], chunk: int = 100) -> list[SmsResult]:
        """Default: one call per message. Providers with a bulk endpoint override it."""
        return [self.send_one(i.to, i.text, i.ref) for i in items]

    def balance(self) -> float | None:
        """Provider-side balance, or None when the provider has no such call."""
        return None


class SandboxSms(SmsProvider):
    name = "sandbox"
    simulates = True

    def send_one(self, to: str, text: str, ref: str = "") -> SmsResult:
        return SmsResult(True, ref=f"sbx-{ref or 'x'}"[:40])


# ------------------------------------------------------------------ BulkSMSBD
BULKSMSBD_CODES = {   # best recollection, VERIFY against the vendor documentation
    "202": "SMS submitted successfully", "1001": "Invalid number", "1002": "Sender ID not correct or disabled", "1003": "Required fields missing",
    "1005": "Internal error at the provider", "1006": "Balance validity not available", "1007": "Balance insufficient",
    "1011": "User ID not found", "1012": "Masking SMS must be sent in Bengali", "1013": "Sender ID not found", "1014": "Sender type name not found",
    "1015": "No valid sender ID found", "1016": "Sender type name active", "1017": "Sender type name not active", "1018": "Account disabled",
    "1019": "Sender type price disabled", "1020": "Parent account not found", "1021": "Parent active price", "1031": "Account not verified yet",
    "1032": "IP not whitelisted",
}
BULKSMSBD_RETRYABLE = {"1005"}            # everything else is a permanent or account-level fault; retrying the same call cannot fix it


def _code_of(body: str) -> str:
    try:
        j = json.loads(body)
        if isinstance(j, dict):
            return str(j.get("response_code", j.get("status_code", "")))
        if isinstance(j, int):
            return str(j)
    except ValueError:
        pass
    m = re.search(r"\b(\d{3,4})\b", body or "")
    return m.group(1) if m else ""


class BulkSmsBd(SmsProvider):
    """http://bulksmsbd.net/api/smsapi?api_key=&type=text|unicode&number=&senderid=&message=   (GET or POST)
    bulk: POST http://bulksmsbd.net/api/smsapimany  {api_key, senderid, messages:[{to, message}]}
    balance: GET http://bulksmsbd.net/api/getBalanceApi?api_key=
    Env: BULKSMSBD_API_KEY, BULKSMSBD_SENDER_ID, BULKSMSBD_BASE_URL (default http://bulksmsbd.net/api)."""
    name = "bulksmsbd"

    def __init__(self, transport: httpx.BaseTransport | None = None, api_key: str | None = None, sender_id: str | None = None, base_url: str | None = None, sleep=None):
        self.key = api_key if api_key is not None else os.getenv("BULKSMSBD_API_KEY", "")
        self.sender = sender_id if sender_id is not None else os.getenv("BULKSMSBD_SENDER_ID", "")
        self.base = (base_url or os.getenv("BULKSMSBD_BASE_URL", "http://bulksmsbd.net/api")).rstrip("/")
        self.transport = transport
        self.kw = {"sleep": sleep} if sleep else {}

    def _call(self, method: str, path: str, **kw) -> httpx.Response:
        if not self.key or not self.sender:
            raise ProviderError("BulkSMSBD is not configured (BULKSMSBD_API_KEY / BULKSMSBD_SENDER_ID)", code="config")
        return send(method, f"{self.base}/{path}", secrets=[self.key], transport=self.transport, timeout=float(os.getenv("SMS_TIMEOUT", "10")),
                    retries=_envint("SMS_RETRIES", 2), retry_on_read_timeout=False, **self.kw, **kw)

    @staticmethod
    def _result(r: httpx.Response) -> SmsResult:
        if r.status_code >= 400:
            return SmsResult(False, error=f"Provider answered HTTP {r.status_code}", code=str(r.status_code), retryable=r.status_code >= 500 or r.status_code == 429)
        body = r.text
        code = _code_of(body)
        if code == "202":
            return SmsResult(True, code=code, ref="")
        return SmsResult(False, code=code, error=BULKSMSBD_CODES.get(code, f"Provider answered {code or 'something unexpected'}")[:110], retryable=code in BULKSMSBD_RETRYABLE)

    def send_one(self, to: str, text: str, ref: str = "") -> SmsResult:
        try:
            number = normalize_msisdn(to, "intl")
        except ValueError:
            return SmsResult(False, error="Invalid number", code="1001")
        try:
            r = self._call("POST", "smsapi", data={"api_key": self.key, "type": "unicode" if encoding_of(text) == "unicode" else "text", "number": number, "senderid": self.sender, "message": text})
        except ProviderError as e:
            return SmsResult(False, error=str(e)[:110], retryable=e.retryable, code=e.code)
        res = self._result(r)
        if res.ok and ref:
            res.ref = ref          # BulkSMSBD returns no per-message id; our reference is the handle
        return res

    def send_many(self, items: list[SmsItem], chunk: int = 100) -> list[SmsResult]:
        out: list[SmsResult | None] = [None] * len(items)
        valid: list[tuple[int, str]] = []
        for i, it in enumerate(items):
            try:
                valid.append((i, normalize_msisdn(it.to, "intl")))
            except ValueError:
                out[i] = SmsResult(False, error="Invalid number", code="1001")
        for s in range(0, len(valid), chunk):
            part = valid[s:s + chunk]
            body = {"api_key": self.key, "senderid": self.sender, "messages": [{"to": n, "message": items[i].text} for i, n in part]}
            try:
                r = self._call("POST", "smsapimany", json=body)
                res = self._result(r)
            except ProviderError as e:
                res = SmsResult(False, error=str(e)[:110], retryable=e.retryable, code=e.code)
            for i, _ in part:
                out[i] = SmsResult(res.ok, ref=items[i].ref if res.ok else "", error=res.error, code=res.code, retryable=res.retryable)
        return [o or SmsResult(False, error="Not sent") for o in out]

    def balance(self) -> float | None:
        r = self._call("GET", "getBalanceApi", params={"api_key": self.key})
        try:
            j = r.json()
            return float(j["balance"] if isinstance(j, dict) else j)
        except (ValueError, KeyError, TypeError):
            m = re.search(r"-?\d+(\.\d+)?", r.text or "")
            if m:
                return float(m.group(0))
            raise ProviderError("Unreadable balance answer", code="parse")


# ------------------------------------------------------------------ generic HTTP gateway and presets
PRESETS = {   # all UNVERIFIED recollections; need the owner's credentials and a check against the vendor docs
    "sslwireless": {"url": "https://smsplus.sslwireless.com/api/v3/send-sms", "method": "POST", "format": "json",
                    "params": {"api_token": "{api_key}", "sid": "{sender}", "msisdn": "{to}", "sms": "{text}", "csms_id": "{ref}"},
                    "success_json": "status=SUCCESS", "id_path": "smsinfo.0.sms_info.0.reference_id"},
    "greenweb": {"url": "http://api.greenweb.com.bd/api.php", "method": "POST", "format": "form", "params": {"token": "{api_key}", "to": "{to}", "message": "{text}"}, "success_regex": r"^\s*Ok"},
    "alphasms": {"url": "https://api.sms.net.bd/sendsms", "method": "POST", "format": "form", "params": {"api_key": "{api_key}", "msg": "{text}", "to": "{to}"}, "success_json": "error=0", "id_path": "data.request_id"},
    "mimsms": {"url": "https://esms.mimsms.com/smsapi", "method": "POST", "format": "form",
               "params": {"api_key": "{api_key}", "type": "{type}", "contacts": "{to}", "senderid": "{sender}", "msg": "{text}"}, "success_regex": r"SMS SUBMITTED"},
}


def _dig(obj, path: str):
    for part in path.split("."):
        if isinstance(obj, list):
            obj = obj[int(part)]
        elif isinstance(obj, dict):
            obj = obj[part]
        else:
            return None
    return obj


class HttpSms(SmsProvider):
    """Generic gateway from env. SMS_HTTP_URL (may hold {to} {text} {ref} {sender} {api_key}), SMS_HTTP_METHOD, SMS_HTTP_FORMAT=query|form|json,
    SMS_HTTP_PARAMS (JSON object, same placeholders), SMS_HTTP_AUTH_HEADER ('Authorization: Bearer {api_key}'), SMS_API_KEY, SMS_SENDER_ID,
    SMS_HTTP_SUCCESS_JSON ('status=SUCCESS') or SMS_HTTP_SUCCESS_REGEX, SMS_HTTP_ID_PATH (dotted path in the JSON answer)."""

    def __init__(self, name: str = "http", conf: dict | None = None, transport: httpx.BaseTransport | None = None, api_key: str | None = None, sender_id: str | None = None, sleep=None):
        e = os.getenv
        self.name = name
        c = conf or {}
        self.url = c.get("url") or e("SMS_HTTP_URL", "")
        self.method = (c.get("method") or e("SMS_HTTP_METHOD", "POST")).upper()
        self.format = c.get("format") or e("SMS_HTTP_FORMAT", "form")
        self.params = c.get("params") or json.loads(e("SMS_HTTP_PARAMS", "{}") or "{}")
        self.auth = c.get("auth") or e("SMS_HTTP_AUTH_HEADER", "")
        self.ok_json = c.get("success_json") or e("SMS_HTTP_SUCCESS_JSON", "")
        self.ok_re = c.get("success_regex") or e("SMS_HTTP_SUCCESS_REGEX", "")
        self.id_path = c.get("id_path") or e("SMS_HTTP_ID_PATH", "")
        self.key = api_key if api_key is not None else e("SMS_API_KEY", "")
        self.sender = sender_id if sender_id is not None else e("SMS_SENDER_ID", "")
        self.transport = transport
        self.kw = {"sleep": sleep} if sleep else {}

    def _fill(self, s: str, v: dict) -> str:
        for k, val in v.items():
            s = s.replace("{" + k + "}", val)
        return s

    def send_one(self, to: str, text: str, ref: str = "") -> SmsResult:
        if not self.url:
            return SmsResult(False, error="SMS gateway is not configured", code="config")
        try:
            number = normalize_msisdn(to)
        except ValueError:
            return SmsResult(False, error="Invalid number", code="1001")
        v = {"to": number, "text": text, "ref": ref, "sender": self.sender, "api_key": self.key, "type": "unicode" if encoding_of(text) == "unicode" else "text"}
        from urllib.parse import quote
        url = self._fill(self.url, {k: quote(str(x), safe="") for k, x in v.items()})
        params = {k: self._fill(str(x), v) for k, x in self.params.items()}
        headers = {}
        if self.auth and ":" in self.auth:
            hk, hv = self.auth.split(":", 1)
            headers[hk.strip()] = self._fill(hv.strip(), v)
        kw: dict = {"headers": headers}
        kw["params" if self.format == "query" or self.method == "GET" else "json" if self.format == "json" else "data"] = params
        try:
            r = send(self.method, url, secrets=[self.key], transport=self.transport, timeout=float(os.getenv("SMS_TIMEOUT", "10")), retries=_envint("SMS_RETRIES", 2),
                     retry_on_read_timeout=False, **self.kw, **kw)
        except ProviderError as e:
            return SmsResult(False, error=str(e)[:110], retryable=e.retryable, code=e.code)
        return self._judge(r)

    def _judge(self, r: httpx.Response) -> SmsResult:
        if r.status_code >= 400:
            return SmsResult(False, error=f"Provider answered HTTP {r.status_code}", code=str(r.status_code), retryable=r.status_code >= 500)
        ok, ref = r.status_code < 300 and not (self.ok_json or self.ok_re), ""
        if self.ok_json:
            try:
                j = r.json()
                k, want = self.ok_json.split("=", 1)
                ok = str(_dig(j, k)).lower() == want.lower()
                if self.id_path:
                    ref = str(_dig(j, self.id_path) or "")
            except (ValueError, KeyError, IndexError, TypeError):
                ok = False
        elif self.ok_re:
            ok = bool(re.search(self.ok_re, r.text or "", re.I))
        return SmsResult(ok, ref=ref[:80], error="" if ok else "Provider did not accept the message", code="" if ok else "rejected")


def get_provider() -> SmsProvider:
    kind = os.getenv("SMS_PROVIDER", "sandbox").strip().lower()
    if kind == "bulksmsbd":
        return BulkSmsBd()
    if kind == "http":
        return HttpSms()
    if kind in PRESETS:
        return HttpSms(kind, PRESETS[kind])
    return SandboxSms()
