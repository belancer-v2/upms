from dataclasses import dataclass, field

from fastapi import Depends, Header, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from .db import get_db
from .models.core import Membership, Property, User
from .security import read_token

SAAS_ALL_ACCESS = {"SUPER_ADMIN", "SAAS_ADMIN"}


def current_user(authorization: str = Header(default=""), db: Session = Depends(get_db)) -> User:
    token = authorization.removeprefix("Bearer ").strip()
    uid = read_token(token) if token else None
    user = db.get(User, uid) if uid else None
    if not user or not user.is_active:
        raise HTTPException(401, "Not signed in")
    return user


def require_saas(*roles: str):
    """SaaS staff only. No roles given means any SaaS staff role."""
    def dep(user: User = Depends(current_user)) -> User:
        if not user.saas_role or (roles and user.saas_role not in roles):
            raise HTTPException(403, "Not allowed")
        return user
    return dep


@dataclass
class Ctx:
    user: User
    property: Property
    roles: set[str] = field(default_factory=set)
    unit_ids: set[int] = field(default_factory=set)
    saas_staff: bool = False

    def has(self, *roles: str) -> bool:
        return self.saas_staff or bool(self.roles & set(roles))

    def need(self, *roles: str) -> None:
        if not self.has(*roles):
            raise HTTPException(403, "Your role cannot do this")


def property_ctx(x_property_id: int = Header(default=0), user: User = Depends(current_user),
                 db: Session = Depends(get_db)) -> Ctx:
    """Resolves which building the caller is working in and the union of their roles there."""
    prop = db.get(Property, x_property_id) if x_property_id else None
    if not prop:
        raise HTTPException(400, "Choose a building first")
    ms = db.scalars(select(Membership).where(Membership.user_id == user.id, Membership.org_id == prop.org_id)).all()
    roles, units = set(), set()
    for m in ms:
        if m.property_id in (prop.id, None):  # org-level membership (agency manager) covers every building
            roles.add(m.role)
            if m.unit_id:
                units.add(m.unit_id)
    staff = user.saas_role in SAAS_ALL_ACCESS
    if not roles and not staff:
        raise HTTPException(403, "No access to this building")
    return Ctx(user=user, property=prop, roles=roles, unit_ids=units, saas_staff=staff)
