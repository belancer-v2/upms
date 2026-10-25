"""A building's own view of its FlatWise plan: what it is on, asking to cancel, and taking its data out.
Only the building admin / agency manager can ask. FlatWise staff approve in the SaaS console (routers/saas.py)."""
import csv
import io
import zipfile
from datetime import date, datetime

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy import inspect, select
from sqlalchemy.orm import Session

from ..audit import audit
from ..db import get_db
from ..deps import Ctx, property_ctx
from ..models.billing import Invoice, Payment
from ..models.core import now
from ..models.finance import Asset, Expense, Vendor
from ..models.property import Occupancy, Unit
from ..models.saas import CancellationRequest, Plan
from ..models.staff import Staff
from ..permissions import MANAGE
from ..services.entitlements import GRACE_DAYS, cancel_state, current_subscription

router = APIRouter(prefix="/api/plan", tags=["plan"])


def _req(r: CancellationRequest | None) -> dict | None:
    if not r:
        return None
    return {"id": r.id, "status": r.status, "reason": r.reason, "created_at": r.created_at.isoformat(), "decision_note": r.decision_note,
            "decided_at": r.decided_at.isoformat() if r.decided_at else None}


@router.get("")
def my_plan(ctx: Ctx = Depends(property_ctx), db: Session = Depends(get_db)):
    ctx.need(*MANAGE)
    org_id = ctx.property.org_id
    sub = current_subscription(db, org_id)
    plan = db.get(Plan, sub.plan_key) if sub else None
    last = db.scalar(select(CancellationRequest).where(CancellationRequest.org_id == org_id).order_by(CancellationRequest.id.desc()))
    cs = cancel_state(db, org_id)
    return {"plan": sub.plan_key if sub else "", "plan_name": plan.name if plan else "", "plan_name_bn": plan.name_bn if plan else "", "band": sub.band if sub else "",
            "cycle": sub.cycle if sub else "", "status": sub.status if sub else "", "flats": sub.flats if sub else 0,
            "trial_ends": sub.trial_ends.isoformat() if sub and sub.trial_ends else None, "features": sorted(ctx.features),
            "request": _req(last), "grace_days": GRACE_DAYS,
            "cancelled": {"ended_at": cs["ended_at"].isoformat(), "readonly_from": cs["readonly_from"].isoformat(), "readonly": cs["readonly"], "days_left": cs["days_left"]} if cs else None}


class CancelIn(BaseModel):
    reason: str = Field(min_length=3, max_length=1000)


@router.post("/cancel-request", status_code=201)
def request_cancel(body: CancelIn, ctx: Ctx = Depends(property_ctx), db: Session = Depends(get_db)):
    ctx.need(*MANAGE)
    org_id = ctx.property.org_id
    sub = current_subscription(db, org_id)
    if not sub or sub.status == "cancelled":
        raise HTTPException(409, "This subscription is not active")
    if db.scalar(select(CancellationRequest.id).where(CancellationRequest.org_id == org_id, CancellationRequest.status == "pending")):
        raise HTTPException(409, "A cancellation request is already waiting for FlatWise")
    r = CancellationRequest(org_id=org_id, requested_by=ctx.user.id, reason=body.reason.strip())
    db.add(r)
    db.flush()
    audit(db, user_id=ctx.user.id, org_id=org_id, property_id=ctx.property.id, action="plan.cancel.request", entity="subscription", entity_id=sub.id)
    db.commit()
    return _req(r)


@router.delete("/cancel-request")
def withdraw_cancel(ctx: Ctx = Depends(property_ctx), db: Session = Depends(get_db)):
    ctx.need(*MANAGE)
    r = db.scalar(select(CancellationRequest).where(CancellationRequest.org_id == ctx.property.org_id, CancellationRequest.status == "pending"))
    if not r:
        raise HTTPException(404, "No request is waiting")
    r.status, r.decided_at, r.decided_by = "withdrawn", now(), ctx.user.id
    audit(db, user_id=ctx.user.id, org_id=r.org_id, property_id=ctx.property.id, action="plan.cancel.withdraw", entity="subscription", entity_id=r.id)
    db.commit()
    return _req(r)


# ---------------------------------------------------------------- data export (works for the whole life of the building, and after it ends)
SKIP = {"nid_enc", "nid_last4", "password_hash", "photo_stored", "stored", "token"}


def _csv(db: Session, model, rows) -> str:
    cols = [c.key for c in inspect(model).mapper.column_attrs if c.key not in SKIP]
    out = io.StringIO()
    w = csv.writer(out)
    w.writerow(cols)
    for r in rows:
        w.writerow([("" if getattr(r, c) is None else (getattr(r, c).isoformat() if isinstance(getattr(r, c), (date, datetime)) else getattr(r, c))) for c in cols])
    return out.getvalue()


@router.get("/export")
def export_data(ctx: Ctx = Depends(property_ctx), db: Session = Depends(get_db)):
    """A zip of CSV files: flats, people, invoices, payments, expenses, vendors, assets, staff. Money columns are integer paisa."""
    ctx.need(*MANAGE)
    pid = ctx.property.id
    units = db.scalars(select(Unit).where(Unit.property_id == pid).order_by(Unit.id)).all()
    uids = [u.id for u in units]
    parts = {
        "flats.csv": _csv(db, Unit, units),
        "people.csv": _csv(db, Occupancy, db.scalars(select(Occupancy).where(Occupancy.unit_id.in_(uids or [0])).order_by(Occupancy.id))),
        "invoices.csv": _csv(db, Invoice, db.scalars(select(Invoice).where(Invoice.property_id == pid).order_by(Invoice.id))),
        "payments.csv": _csv(db, Payment, db.scalars(select(Payment).where(Payment.property_id == pid).order_by(Payment.id))),
        "expenses.csv": _csv(db, Expense, db.scalars(select(Expense).where(Expense.property_id == pid).order_by(Expense.id))),
        "vendors.csv": _csv(db, Vendor, db.scalars(select(Vendor).where(Vendor.property_id == pid).order_by(Vendor.id))),
        "assets.csv": _csv(db, Asset, db.scalars(select(Asset).where(Asset.property_id == pid).order_by(Asset.id))),
        "staff.csv": _csv(db, Staff, db.scalars(select(Staff).where(Staff.property_id == pid).order_by(Staff.id))),
    }
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for name, text in parts.items():
            z.writestr(name, "﻿" + text)
    audit(db, user_id=ctx.user.id, org_id=ctx.property.org_id, property_id=pid, action="plan.export", entity="property", entity_id=pid)
    db.commit()
    return Response(buf.getvalue(), media_type="application/zip", headers={"Content-Disposition": f'attachment; filename="flatwise-export-{pid}-{date.today().isoformat()}.zip"'})
