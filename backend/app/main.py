from contextlib import asynccontextmanager

from fastapi import FastAPI

from .db import Base, engine
from . import models  # noqa: F401  (registers tables)
from .routers import gateway as gateway_router, budget as budget_router, auth, billing, cash, core, finance, notices, onboarding, profiles, staff as staff_router, property as property_router, public, rental, saas


@asynccontextmanager
async def lifespan(_: FastAPI):
    Base.metadata.create_all(engine)
    yield


app = FastAPI(title="FlatWise API", version="0.1.0", lifespan=lifespan)
app.include_router(auth.router)
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


@app.get("/api/health")
def health():
    return {"ok": True, "app": "flatwise"}
