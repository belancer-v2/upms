from contextlib import asynccontextmanager

from fastapi import FastAPI

from .db import Base, engine
from . import models  # noqa: F401  (registers tables)
from .routers import gateway as gateway_router, budget as budget_router, auth, billing, cash, core, finance, notices, onboarding, profiles, staff as staff_router, property as property_router, public, rental, saas


@asynccontextmanager
async def lifespan(_: FastAPI):
    if not config.PRODUCTION:  # production schema comes from `alembic upgrade head` only
        Base.metadata.create_all(engine)
        from .devschema import ensure_columns
        ensure_columns(engine)  # dev/test only: adds the P2 security columns to an existing local database
    from .jobs import scheduler_running  # P3: in-process scheduler, only when JOBS_ENABLED=1 (cPanel uses cron: python -m app.jobs.cli run-due)
    async with scheduler_running():
        yield


from . import config, ops, prodcheck, secure  # noqa: E402
prodcheck.enforce()  # ENV=production: refuse to start with unsafe settings
app = FastAPI(title="FlatWise API", version="0.1.0", lifespan=lifespan, docs_url=None if config.PRODUCTION else "/docs",
              redoc_url=None, openapi_url=None if config.PRODUCTION else "/openapi.json")
secure.install(app)   # security headers + request size limits (P2)
ops.install(app)
from . import openapi_polish  # noqa: E402  (P5)
openapi_polish.install(app)
app.include_router(auth.router)
from .routers import account as account_router  # noqa: E402
app.include_router(account_router.router)  # refresh, logout, passwords, sessions (P2)
app.include_router(core.router)
app.include_router(public.router)
app.include_router(saas.router)
app.include_router(property_router.router)
app.include_router(billing.router)
app.include_router(cash.router)
app.include_router(finance.router)
app.include_router(budget_router.router)
app.include_router(staff_router.router)
app.include_router(notices.router)
app.include_router(notices.pol)
app.include_router(onboarding.router)
app.include_router(rental.router)
from .routers import committee as committee_router, complaints as complaints_router  # noqa: E402
app.include_router(complaints_router.router)
app.include_router(committee_router.router)
app.include_router(gateway_router.router)
app.include_router(profiles.router)
from .routers import credits as credits_router  # noqa: E402
app.include_router(credits_router.router)
app.include_router(credits_router.console)
from .routers import visitors as visitors_router  # noqa: E402
app.include_router(visitors_router.router)
from .routers import parking as parking_router  # noqa: E402
app.include_router(parking_router.router)
from .routers import amenities as amenities_router  # noqa: E402
app.include_router(amenities_router.router)
from .routers import campaigns as campaigns_router  # noqa: E402
app.include_router(campaigns_router.router)
app.include_router(campaigns_router.public_router)


@app.get("/api/health")
def health():
    return {"ok": True, "app": "flatwise"}
from .routers import agency as agency_router  # noqa: E402
app.include_router(agency_router.router)
from .routers import saas_reports as saas_reports_router  # noqa: E402
app.include_router(saas_reports_router.router)
app.include_router(saas_reports_router.doc_router)
from .routers import setup as setup_router, exports as exports_router, privacy as privacy_router  # noqa: E402  (P5)
app.include_router(setup_router.router)
app.include_router(exports_router.router)
app.include_router(privacy_router.router)
app.include_router(privacy_router.console)
from .routers import plan as plan_router  # noqa: E402
app.include_router(plan_router.router)
from .routers import jobs as jobs_router, webhooks as webhooks_router  # noqa: E402  (P3)
app.include_router(jobs_router.router)
app.include_router(jobs_router.auto_router)
app.include_router(webhooks_router.router)
from .routers import contracts as contracts_router  # noqa: E402
app.include_router(contracts_router.router)
