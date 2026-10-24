from fastapi import APIRouter, Depends, Header
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import current_user
from ..models.core import AuditLog, Membership, Property, User

router = APIRouter(prefix="/api", tags=["core"])
SEE_PROPERTY_LOG = {"PROPERTY_ADMIN", "AGENCY_MANAGER", "PRESIDENT", "AUDITOR"}


@router.get("/audit")
def audit_list(limit: int = 50, user: User = Depends(current_user), db: Session = Depends(get_db),
               x_property_id: int = Header(default=0)):
    """SaaS admins see everything. Building managers and the president see their building. Everyone else sees their own actions."""
    q = select(AuditLog).order_by(AuditLog.at.desc()).limit(min(limit, 500))
    if user.saas_role in ("SUPER_ADMIN", "SAAS_ADMIN"):
        pass
    else:
        prop = db.get(Property, x_property_id) if x_property_id else None
        roles = {m.role for m in db.scalars(select(Membership).where(
            Membership.user_id == user.id, Membership.org_id == (prop.org_id if prop else -1),
            or_(Membership.property_id == x_property_id, Membership.property_id.is_(None))))}
        if prop and roles & SEE_PROPERTY_LOG:
            q = q.where(or_(AuditLog.property_id == prop.id, AuditLog.user_id == user.id))
        else:
            q = q.where(AuditLog.user_id == user.id)
    names = {u.id: u.name for u in db.scalars(select(User))}
    return [{"id": a.id, "at": a.at.isoformat(), "who": names.get(a.user_id, "system"), "action": a.action,
             "entity": a.entity, "entity_id": a.entity_id} for a in db.scalars(q)]
