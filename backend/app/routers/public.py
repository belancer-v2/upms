"""Public endpoints used by the website. No sign-in needed."""
from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import config
from ..audit import audit
from ..db import get_db
from ..models.core import Membership, Organization, Property, User, now
from ..models.saas import BANDS, Lead, Plan, Subscription, band_for
from ..netutil import client_ip
from ..security import hash_password
from ..services import antispam, authmail, passwords, ratelimit, sessions
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
    email: str = Field(default="", max_length=160)
    building: str = Field(default="", max_length=160)
    flats: int = Field(default=0, ge=0, le=5000)
    city: str = Field(default="", max_length=80)
    message: str = Field(default="", max_length=2000)
    source: str = Field(default="website", max_length=40)
    hp: str = Field(default="", max_length=200)    # honeypot: a hidden field real visitors leave empty
    ft: str = Field(default="", max_length=300)    # signed form token from GET /api/public/form-token


@router.post("/leads", status_code=201, dependencies=[Depends(ratelimit.limit("lead", 10, 3600))])
def create_lead(body: LeadIn, db: Session = Depends(get_db)):
    if not antispam.looks_human(body.hp, body.ft):
        return {"ok": True, "id": 0}               # answered like a success; nothing is stored
    lead = Lead(**body.model_dump(exclude={"hp", "ft"}))
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
    address: str = Field(default="", max_length=240)
    city: str = Field(default="Dhaka", max_length=80)
    flats: int = Field(ge=1, le=5000)
    plan: str = Field(default="standard", max_length=24)
    lang: str = Field(default="en", max_length=4)
    hp: str = Field(default="", max_length=200)
    ft: str = Field(default="", max_length=300)


@router.post("/signup", status_code=201, dependencies=[Depends(ratelimit.limit("signup", 10, 3600))])
def signup(body: SignupIn, request: Request, response: Response, db: Session = Depends(get_db)):
    email = body.email.strip().lower()
    decoy = {"verification_required": True, "email": email}     # what a bot, or a repeat sign-up in verified mode, is told: no account is revealed
    if not antispam.looks_human(body.hp, body.ft):
        return decoy
    if "@" not in email:
        raise HTTPException(422, "Enter a valid email")
    bad = passwords.check(body.password, email=email, name=body.name, phone=body.phone)
    if bad:
        raise HTTPException(422, bad)
    if db.scalar(select(User).where(User.email == email)):
        if config.REQUIRE_EMAIL_VERIFICATION:
            return decoy                                       # do not reveal that the address is registered
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
                lang="bn" if body.lang == "bn" else "en", email_verified=not config.REQUIRE_EMAIL_VERIFICATION)
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
    if config.REQUIRE_EMAIL_VERIFICATION:      # the trial clock restarts when the address is confirmed (routers/account.py verify_email)
        raw = authmail.issue(db, user, "verify", client_ip(request))
        authmail.send_email(db, user, "verify", raw)
        db.commit()
        return {**decoy, **({"demo_link": authmail.link("verify", raw)} if config.DEMO else {})}
    toks = sessions.login_tokens(db, user, request, response)
    db.commit()
    return {**toks, **me_payload(db, user)}
