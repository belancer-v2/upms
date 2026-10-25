from dataclasses import dataclass, field

from fastapi import Depends, Header, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from .db import get_db
from .models.core import Membership, Organization, Property, User
from .services.entitlements import cancel_state, org_features
from .models.core import now
from .models.security import AuthSession
from .security import read_access_token

SAAS_ALL_ACCESS = {"SUPER_ADMIN", "SAAS_ADMIN"}


def _utc(d):
    from datetime import timezone
    return d.replace(tzinfo=timezone.utc) if d is not None and d.tzinfo is None else d


def current_auth(authorization: str = Header(default=""), db: Session = Depends(get_db)) -> tuple[User, AuthSession]:
    """The signed-in user and the sign-in session the bearer token belongs to. 401 if the token is forged, expired, revoked or out of date."""
    scheme, _, token = authorization.partition(" ")
    claims = read_access_token(token.strip()) if scheme.lower() == "bearer" and token.strip() else None
    user = db.get(User, claims["uid"]) if claims else None
    sess = db.get(AuthSession, claims["sid"]) if claims else None
    if (not claims or not user or not user.is_active or user.token_version != claims["tv"] or not sess or sess.user_id != user.id
            or sess.revoked_at is not None or _utc(sess.expires_at) < now()):
        raise HTTPException(401, "Not signed in")
    if (now() - _utc(sess.last_used_at)).total_seconds() > 300:  # a write at most every 5 minutes per device
        sess.last_used_at = now()
        db.commit()
    return user, sess


def current_user_any(auth: tuple[User, AuthSession] = Depends(current_auth)) -> User:
    """Signed in, even if a password change is still pending. Only the change-password, profile and sign-out endpoints use this."""
    return auth[0]


def current_user(user: User = Depends(current_user_any)) -> User:
    if user.must_change_password:
        raise HTTPException(403, "You must set a new password before you continue.", headers={"X-Error-Code": "password_change_required"})
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
    features: set[str] = field(default_factory=set)

    def has(self, *roles: str) -> bool:
        return self.saas_staff or bool(self.roles & set(roles))

    def need(self, *roles: str) -> None:
        if not self.has(*roles):
            raise HTTPException(403, "Your role cannot do this")

    def feature(self, key: str) -> None:
        """Plan gate. Raises 402 so the app can show an upgrade message."""
        if key not in self.features:
            raise HTTPException(402, f"Your plan does not include '{key}'")


def property_ctx(request: Request = None, x_property_id: int = Header(default=0), user: User = Depends(current_user),
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
    org = db.get(Organization, prop.org_id)
    if org and org.status == "suspended" and not user.saas_role:
        raise HTTPException(403, "This building's account is suspended. Please contact FlatWise.")
    if request is not None and request.method not in ("GET", "HEAD", "OPTIONS") and not user.saas_role:
        cs = cancel_state(db, prop.org_id)
        if cs and cs["readonly"]:
            raise HTTPException(403, "This building's subscription has ended. Your data is read-only; you can still view and export it.")
    return Ctx(user=user, property=prop, roles=roles, unit_ids=units, saas_staff=staff, features=org_features(db, prop.org_id))
