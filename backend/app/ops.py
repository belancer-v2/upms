"""Operations plumbing: JSON logs, request ids, access log, gzip, CORS, safe 500s, health probes.

`install(app)` is called once from main.py. Nothing here knows about business modules.
"""
import contextvars
import json
import logging
import re
import sys
import time
import uuid

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from sqlalchemy import text
from starlette.middleware.cors import CORSMiddleware
from starlette.middleware.gzip import GZipMiddleware

from . import config
from .secure import redact_path
from .db import engine

request_id_var: contextvars.ContextVar[str] = contextvars.ContextVar("request_id", default="-")
log = logging.getLogger("flatwise")
access_log = logging.getLogger("flatwise.access")
_SAFE_ID = re.compile(r"^[A-Za-z0-9._\-]{8,64}$")
_SKIP_ACCESS = {"/healthz", "/readyz", "/api/health"}


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        data = {"ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"), "level": record.levelname,
                "logger": record.name, "msg": record.getMessage(), "request_id": request_id_var.get()}
        extra = getattr(record, "fields", None)
        if extra:
            data.update(extra)
        if record.exc_info:
            data["exc"] = self.formatException(record.exc_info)
        return json.dumps(data, ensure_ascii=False, default=str)


def setup_logging() -> None:
    root = logging.getLogger()
    if getattr(root, "_flatwise", False):
        return
    handler = logging.StreamHandler(sys.stdout)
    if config.PRODUCTION or config.LOG_FORMAT == "json":
        handler.setFormatter(JsonFormatter())
    else:
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s"))
    root.handlers[:] = [handler]
    root.setLevel(config.LOG_LEVEL)
    root._flatwise = True  # type: ignore[attr-defined]
    logging.getLogger("uvicorn.access").disabled = True  # replaced by flatwise.access


class RequestContextMiddleware:
    """Pure ASGI: assigns a request id (honouring a sane inbound X-Request-ID), adds it to the response, logs one access line."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        headers = dict(scope.get("headers") or [])
        inbound = headers.get(b"x-request-id", b"").decode("latin-1")
        rid = inbound if _SAFE_ID.match(inbound) else uuid.uuid4().hex
        token = request_id_var.set(rid)
        scope["flatwise_request_id"] = rid
        started = time.perf_counter()
        status = {"code": 500}

        async def send_wrapper(message):
            if message["type"] == "http.response.start":
                status["code"] = message["status"]
                message.setdefault("headers", []).append((b"x-request-id", rid.encode()))
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            path = redact_path(scope.get("path", ""))   # link tokens never reach the logs (P2)
            if path not in _SKIP_ACCESS:
                client = scope.get("client")
                access_log.info("%s %s %s", scope.get("method"), path, status["code"], extra={"fields": {
                    "method": scope.get("method"), "path": path, "status": status["code"],
                    "ms": round((time.perf_counter() - started) * 1000, 1), "client": client[0] if client else "",
                    "property_id": headers.get(b"x-property-id", b"").decode("latin-1")[:12]}})
            request_id_var.reset(token)


def install(app: FastAPI) -> None:
    setup_logging()
    # Order matters: the last added runs first. Context (request id) must wrap everything.
    app.add_middleware(GZipMiddleware, minimum_size=1024)
    if config.CORS_ORIGINS:
        app.add_middleware(CORSMiddleware, allow_origins=config.CORS_ORIGINS, allow_credentials=False,
                           allow_methods=["*"], allow_headers=["*"], expose_headers=["X-Request-ID"])
    app.add_middleware(RequestContextMiddleware)

    @app.exception_handler(Exception)
    async def unhandled(request: Request, exc: Exception):
        log.error("unhandled error on %s %s", request.method, redact_path(request.url.path), exc_info=exc, extra={"fields": {"request_id": request.scope.get("flatwise_request_id", "-")}})
        rid = request.scope.get("flatwise_request_id", request_id_var.get())
        body = {"detail": "Something went wrong on our side. Please try again.", "request_id": rid}
        if not config.PRODUCTION:
            body["error"] = f"{type(exc).__name__}: {exc}"
        return JSONResponse(body, status_code=500, headers={"X-Request-ID": rid})

    @app.get("/healthz", include_in_schema=False)
    def healthz():
        """Liveness: the process is up. Does not touch the database."""
        return {"status": "ok"}

    @app.get("/readyz", include_in_schema=False)
    def readyz():
        """Readiness: the database answers. Load balancers stop sending traffic on 503."""
        try:
            with engine.connect() as c:
                c.execute(text("SELECT 1"))
        except Exception:
            log.error("readiness check failed", exc_info=True)
            return JSONResponse({"status": "unavailable", "db": False}, status_code=503)
        return {"status": "ready", "db": True}
