"""Public endpoints used by the website. No sign-in needed."""
from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..audit import audit
from ..db import get_db
from ..models.core import Membership, Organization, Property, User, now
from ..models.saas import BANDS, Lead, Plan, Subscription, band_for
from ..security import hash_password, make_token
from .auth import me_payload

router = APIRouter(prefix="/api/public", tags=["public"])
TRIAL_DAYS = 30


@router.get("/plans")
def plans(db: Session = Depends(get_db)):
    rows = db.scalars(select(Plan).order_by(Plan.sort)).all()
    return {
        "bands": [{"key": k, "label": l, "max": m} for k, l, m in BANDS],
        "trial_days": TRIAL_DAYS,
        "yearly_months_paid": 10,
        "sms_pack": {"count": 1000, "price": 80000},
        "plans": [{"key": p.key, "name": p.name, "name_bn": p.name_bn, "monthly": p.monthly, "setup": p.setup,
                   "sms_included": p.sms_included, "features": p.features} for p in rows],
    }


class LeadIn(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    phone: str = Field(min_length=6, max_length=32)
    email: str = ""
    building: str = ""
    flats: int = Field(default=0, ge=0, le=5000)
    city: str = ""
    message: str = Field(default="", max_length=2000)
    source: str = "website"


@router.post("/leads", status_code=201)
def create_lead(body: LeadIn, db: Session = Depends(get_db)):
    lead = Lead(**body.model_dump())
    db.add(lead)
    db.flush()
    audit(db, action="lead.created", entity="lead", entity_id=lead.id, meta={"source": body.source})
    db.commit()
    return {"ok": True, "id": lead.id}


class SignupIn(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    email: str = Field(min_length=5, max_length=160)
    phone: str = Field(default="", max_length=32)
    password: str = Field(min_length=8, max_length=100)
    building: str = Field(min_length=2, max_length=160)
    address: str = ""
    city: str = "Dhaka"
    flats: int = Field(ge=1, le=5000)
    plan: str = "standard"
    lang: str = "en"


@router.post("/signup", status_code=201)
def signup(body: SignupIn, db: Session = Depends(get_db)):
    email = body.email.strip().lower()
    if "@" not in email:
        raise HTTPException(422, "Enter a valid email")
    if db.scalar(select(User).where(User.email == email)):
        raise HTTPException(409, "This email already has an account. Sign in instead.")
    plan = db.get(Plan, body.plan)
    if not plan:
        raise HTTPException(422, "Unknown plan")
    band = band_for(body.flats)
    org = Organization(name=body.building, kind="committee", status="trial", city=body.city)
    db.add(org)
    db.flush()
    prop = Property(org_id=org.id, name=body.building, address=body.address, city=body.city)
    user = User(email=email, name=body.name, phone=body.phone, password_hash=hash_password(body.password),
                lang="bn" if body.lang == "bn" else "en")
    db.add_all([prop, user])
    db.flush()
    db.add(Membership(user_id=user.id, org_id=org.id, property_id=prop.id, role="PROPERTY_ADMIN"))
    db.add(Subscription(org_id=org.id, plan_key=plan.key, band=band, flats=body.flats, status="trial",
                        trial_ends=now() + timedelta(days=TRIAL_DAYS)))
    from ..services.saas_docs import record_event  # M21 history
    db.flush()
    record_event(db, db.scalar(select(Subscription).where(Subscription.org_id == org.id)), "trial_start", user.id)
    audit(db, user_id=user.id, org_id=org.id, property_id=prop.id, action="signup", entity="organization",
          entity_id=org.id, meta={"plan": plan.key, "band": band})
    db.commit()
    return {"token": make_token(user.id), **me_payload(db, user)}
