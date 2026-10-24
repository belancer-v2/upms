from contextlib import asynccontextmanager

from fastapi import FastAPI

from .db import Base, engine
from . import models  # noqa: F401  (registers tables)
from .routers import auth, billing, cash, core, finance, staff as staff_router, property as property_router, public, saas


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
app.include_router(staff_router.router)


@app.get("/api/health")
def health():
    return {"ok": True, "app": "flatwise"}
