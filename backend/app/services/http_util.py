"""Outbound HTTP for provider adapters: timeouts, retries with backoff, and secret redaction in anything that gets logged.

Tests pass an httpx.MockTransport as `transport`; production leaves it None.
"""
from __future__ import annotations

import logging
import time

import httpx

log = logging.getLogger("flatwise.http")


class ProviderError(Exception):
    """A provider call failed. `retryable` tells the caller whether trying again later could help. The message never contains secrets."""

    def __init__(self, message: str, retryable: bool = False, code: str = ""):
        super().__init__(message)
        self.retryable, self.code = retryable, code


def redact(text: str, secrets: list[str]) -> str:
    for s in secrets:
        if s and len(s) >= 4:
            text = text.replace(s, "***")
    return text


def send(method: str, url: str, *, secrets: list[str] = (), transport: httpx.BaseTransport | None = None, timeout: float = 10.0, retries: int = 2,
         backoff: float = 0.5, retry_on_read_timeout: bool = True, sleep=time.sleep, **kw) -> httpx.Response:
    """One logical request. Retries connection errors, 5xx and 429 with exponential backoff. A read timeout is only retried when
    `retry_on_read_timeout` is true (set it False for calls that are not safe to repeat). Raises ProviderError, never leaks secrets."""
    last = ""
    for attempt in range(retries + 1):
        try:
            with httpx.Client(transport=transport, timeout=timeout) as c:
                r = c.request(method, url, **kw)
            if r.status_code in (429, 500, 502, 503, 504) and attempt < retries:
                last = f"HTTP {r.status_code}"
            else:
                return r
        except httpx.ReadTimeout:
            last = "read timeout"
            if not retry_on_read_timeout:
                raise ProviderError("The provider did not answer in time", retryable=False, code="timeout")
        except httpx.TransportError as e:
            last = type(e).__name__
        if attempt < retries:
            sleep(backoff * (2 ** attempt))
    log.warning("provider call failed after %d tries: %s", retries + 1, redact(last, list(secrets)))
    raise ProviderError(f"Provider unreachable ({last})", retryable=True, code="unreachable")
