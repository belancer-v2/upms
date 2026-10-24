from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import config
from ..audit import audit
from ..db import get_db
from ..deps import current_user
from ..models.core import Membership, Organization, Property, User
from ..security import make_token, verify_password
from ..services.entitlements import current_subscription, org_features

router = APIRouter(prefix="/api", tags=["auth"])


class LoginIn(BaseModel):
    email: str
    password: str


def me_payload(db: Session, user: User) -> dict:
    ms = db.scalars(select(Membership).where(Membership.user_id == user.id)).all()
    org_ids = {m.org_id for m in ms}
    orgs = {o.id: o for o in db.scalars(select(Organization).where(Organization.id.in_(org_ids)))} if org_ids else {}
    props: dict[int, Property] = {}
    for m in ms:
        if m.property_id:
            props[m.property_id] = db.get(Property, m.property_id)
        else:  # org-level role (agency manager) -> every building in that org
            for p in db.scalars(select(Property).where(Property.org_id == m.org_id)):
                props[p.id] = p
    if user.saas_role in ("SUPER_ADMIN", "SAAS_ADMIN"):
        for p in db.scalars(select(Property)):
            props[p.id] = p
    missing = {p.org_id for p in props.values()} - set(orgs)
    if missing:
        orgs.update({o.id: o for o in db.scalars(select(Organization).where(Organization.id.in_(missing)))})
    roles_by_prop: dict[int, list[str]] = {}
    for m in ms:
        targets = [m.property_id] if m.property_id else [p.id for p in props.values() if p.org_id == m.org_id]
        for pid in targets:
            roles_by_prop.setdefault(pid, [])
            if m.role not in roles_by_prop[pid]:
                roles_by_prop[pid].append(m.role)
    return {
        "user": {"id": user.id, "name": user.name, "name_bn": user.name_bn, "email": user.email,
                 "phone": user.phone, "lang": user.lang, "saas_role": user.saas_role},
        "properties": [
            {"id": p.id, "name": p.name, "name_bn": p.name_bn, "city": p.city, "org_id": p.org_id,
             "org_name": orgs[p.org_id].name if p.org_id in orgs else "", "roles": roles_by_prop.get(p.id, []),
             "features": sorted(org_features(db, p.org_id)),
             "plan": (current_subscription(db, p.org_id).plan_key if current_subscription(db, p.org_id) else ""),
             "sub_status": (current_subscription(db, p.org_id).status if current_subscription(db, p.org_id) else ""),
             "org_status": orgs[p.org_id].status if p.org_id in orgs else ""}
            for p in sorted(props.values(), key=lambda x: x.id)
        ],
    }


@router.post("/auth/login")
def login(body: LoginIn, db: Session = Depends(get_db)):
    user = db.scalar(select(User).where(User.email == body.email.strip().lower()))
    if not user or not user.is_active or not verify_password(body.password, user.password_hash):
        raise HTTPException(401, "Wrong email or password")
    audit(db, user_id=user.id, action="auth.login", entity="user", entity_id=user.id)
    db.commit()
    return {"token": make_token(user.id), **me_payload(db, user)}


@router.get("/me")
def me(user: User = Depends(current_user), db: Session = Depends(get_db)):
    return me_payload(db, user)


class LangIn(BaseModel):
    lang: str


@router.post("/me/lang")
def set_lang(body: LangIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    if body.lang not in ("en", "bn"):
        raise HTTPException(422, "lang must be en or bn")
    user.lang = body.lang
    db.commit()
    return {"ok": True}


@router.get("/auth/demo-accounts")
def demo_accounts(db: Session = Depends(get_db)):
    if not config.DEMO:
        return {"enabled": False, "accounts": []}
    rows = db.scalars(select(User).where(User.email.like("%@flatwise.demo")).order_by(User.id)).all()
    out = []
    for u in rows:
        roles = [u.saas_role] if u.saas_role else sorted({m.role for m in u.memberships})
        out.append({"email": u.email, "name": u.name, "name_bn": u.name_bn, "roles": roles})
    return {"enabled": True, "password": "demo1234", "accounts": out}
