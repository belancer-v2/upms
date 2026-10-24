from sqlalchemy.orm import Session

from .models.core import AuditLog


def audit(db: Session, *, user_id=None, org_id=None, property_id=None, action: str,
          entity: str = "", entity_id="", meta: dict | None = None, note: str = "") -> None:
    db.add(AuditLog(user_id=user_id, org_id=org_id, property_id=property_id, action=action,
                    entity=entity, entity_id=str(entity_id), meta=meta or {}, note=note))
