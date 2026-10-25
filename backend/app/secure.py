"""HTTP hardening for the API: security headers, request size limits, optional host allow-list.

Pure ASGI middleware (no buffering, works with streaming and file downloads). `install(app)` is called once from main.py.
The API only ever returns JSON, images, PDFs and one 1x1 gif, so its Content-Security-Policy forbids everything: a response that somehow
rendered in a browser could load no script, style, frame or form target. `sandbox` additionally stops uploaded files from running.
"""
import logging
import os
import re

from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException
from starlette.middleware.trustedhost import TrustedHostMiddleware

from . import config

API_CSP = "default-src 'none'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'; sandbox"
DOCS_PATHS = ("/docs", "/openapi.json", "/redoc")      # only exist outside production; Swagger UI needs scripts, so it gets no CSP
PERMISSIONS = "accelerometer=(), ambient-light-sensor=(), autoplay=(), camera=(), display-capture=(), geolocation=(), gyroscope=(), microphone=(), midi=(), payment=(), usb=(), interest-cohort=()"


_SECRET_SEGMENT = re.compile(r"/(link|callback|unsubscribe|click|open|sandbox|return|verify|reset)/[^/?]+")


def redact_path(path: str) -> str:
    """URLs that carry a secret in the path (SMS links, payment callbacks, e-mail links) are logged without it."""
    return _SECRET_SEGMENT.sub(r"/\1/[redacted]", path or "")


class SecurityHeadersMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        path = scope.get("path", "")
        is_docs = path.startswith(DOCS_PATHS)
        is_mail_asset = path.startswith("/api/public/mail/")      # tracking pixel is embedded in other people's mail clients

        async def wrapped(message):
            if message["type"] == "http.response.start":
                h = [(k, v) for k, v in message.get("headers", []) if k.lower() not in (b"server", b"x-powered-by")]
                names = {k.lower() for k, _ in h}

                def put(name: bytes, value: str, only_if_missing: bool = True):
                    if name in names and only_if_missing:
                        return
                    h.append((name, value.encode()))
                put(b"x-content-type-options", "nosniff", False)
                put(b"x-frame-options", "DENY")
                put(b"referrer-policy", "no-referrer")
                put(b"permissions-policy", PERMISSIONS)
                put(b"cross-origin-resource-policy", "cross-origin" if is_mail_asset else "same-origin")
                put(b"cross-origin-opener-policy", "same-origin")
                if not is_docs:
                    put(b"content-security-policy", API_CSP)
                if path.startswith("/api/") and b"cache-control" not in names:
                    h.append((b"cache-control", b"no-store"))
                if config.PRODUCTION:
                    put(b"strict-transport-security", "max-age=31536000; includeSubDomains")
                message["headers"] = h
            await send(message)
        await self.app(scope, receive, wrapped)


class BodyLimitMiddleware:
    """413 for oversized requests: by the Content-Length header up front, and by counting bytes for chunked bodies."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or scope["method"] in ("GET", "HEAD", "OPTIONS"):
            await self.app(scope, receive, send)
            return
        headers = {k.lower(): v for k, v in scope.get("headers", [])}
        multipart = headers.get(b"content-type", b"").lower().startswith(b"multipart/form-data")
        limit = config.MAX_UPLOAD_BYTES + 1024 * 1024 if multipart else config.MAX_BODY_BYTES
        declared = headers.get(b"content-length", b"")
        if declared.isdigit() and int(declared) > limit:
            await self._reject(send, limit)
            return
        seen = 0

        async def counted():
            nonlocal seen
            msg = await receive()
            if msg["type"] == "http.request":
                seen += len(msg.get("body", b""))
                if seen > limit:
                    raise HTTPException(413, "The request is too large.")
            return msg
        await self.app(scope, counted, send)

    @staticmethod
    async def _reject(send, limit: int):
        body = b'{"detail":"The request is too large."}'
        await send({"type": "http.response.start", "status": 413, "headers": [(b"content-type", b"application/json"), (b"content-length", str(len(body)).encode()), (b"connection", b"close")]})
        await send({"type": "http.response.body", "body": body})


async def _validation_error(request, exc: RequestValidationError):
    """The default 422 echoes the rejected value back ("input"), which for a password field would put the password in a response body. Keep where and why, drop what."""
    return JSONResponse({"detail": [{"loc": [str(x) for x in e.get("loc", ())], "msg": str(e.get("msg", "")), "type": str(e.get("type", ""))} for e in exc.errors()]}, status_code=422)


def install(app) -> None:
    """Call before ops.install(app): the last middleware added is the outermost, and these should sit next to the router."""
    if config.PRODUCTION and not config.TRUSTED_PROXIES:
        logging.getLogger("flatwise.security").warning(
            "TRUSTED_PROXIES is empty: every request will look like it comes from the proxy, so per-address rate limits and sign-in lockouts "
            "are shared by all visitors. Set TRUSTED_PROXIES to the proxy addresses (see SECURITY.md) unless the API is exposed directly.")
    app.add_exception_handler(RequestValidationError, _validation_error)
    app.add_middleware(BodyLimitMiddleware)
    app.add_middleware(SecurityHeadersMiddleware)
    hosts = [h.strip() for h in os.getenv("ALLOWED_HOSTS", "").split(",") if h.strip()]
    if hosts:
        app.add_middleware(TrustedHostMiddleware, allowed_hosts=hosts)
