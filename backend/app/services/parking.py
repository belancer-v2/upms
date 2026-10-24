"""Parking rules shared by the parking router and the flat-creation endpoints."""
import re
from datetime import date

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..audit import audit
from ..models.parking import ParkingAllocation, ParkingEntitlement, ParkingSlot, Vehicle
from ..models.property import Unit

KINDS = ("car", "motorbike", "bicycle")
_BN = str.maketrans("০১২৩৪৫৬৭৮৯", "0123456789")


def clean_plate(raw: str) -> tuple[str, str]:
    """Free text in, (shown, key) out. Upper case, one space between words, Bangla digits to Latin; the key keeps letters and digits only."""
    shown = re.sub(r"\s*-\s*", "-", re.sub(r"\s+", " ", raw.translate(_BN).strip().upper()))
    return shown, re.sub(r"[^0-9A-Zঀ-৿]", "", shown)


def entitlement(db: Session, unit_id: int) -> dict[str, int]:
    out = {k: 0 for k in KINDS}
    for e in db.scalars(select(ParkingEntitlement).where(ParkingEntitlement.unit_id == unit_id)):
        out[e.kind] = e.count
    return out


def held(db: Session, unit_id: int) -> dict[str, int]:
    out = {k: 0 for k in KINDS}
    rows = db.execute(select(ParkingAllocation.vehicle_kind, func.count()).where(ParkingAllocation.unit_id == unit_id, ParkingAllocation.until.is_(None)).group_by(ParkingAllocation.vehicle_kind))
    for k, n in rows:
        out[k] = n
    return out


def set_entitlement(db: Session, unit_id: int, kind: str, count: int) -> None:
    e = db.scalar(select(ParkingEntitlement).where(ParkingEntitlement.unit_id == unit_id, ParkingEntitlement.kind == kind))
    if e:
        e.count = count
    elif count:
        db.add(ParkingEntitlement(unit_id=unit_id, kind=kind, count=count))


def provision_unit(db: Session, unit: Unit, cars: int, bikes: int) -> int:
    """Gives a flat its entitlement and creates plus allocates the missing slots (A-501-C1, A-501-M1). Safe to repeat. Returns slots made."""
    made = 0
    for kind, n, tag in (("car", cars, "C"), ("motorbike", bikes, "M")):
        if n <= 0:
            continue
        have = held(db, unit.id)[kind]
        set_entitlement(db, unit.id, kind, max(entitlement(db, unit.id)[kind], n))
        i = 0
        while have < n:
            i += 1
            code = f"{unit.number}-{tag}{i}"
            if db.scalar(select(ParkingSlot.id).where(ParkingSlot.property_id == unit.property_id, ParkingSlot.code == code)):
                continue
            slot = ParkingSlot(property_id=unit.property_id, code=code, level="Ground", kind=kind, cover="open")
            db.add(slot)
            db.flush()
            db.add(ParkingAllocation(slot_id=slot.id, unit_id=unit.id, vehicle_kind=kind, since=date.today()))
            have += 1
            made += 1
    return made


def flag_tenant_vehicles(db: Session, unit: Unit, user_id: int, org_id: int) -> int:
    """A tenant moved out: their vehicles are marked 'to review', never deleted."""
    rows = db.scalars(select(Vehicle).where(Vehicle.unit_id == unit.id, Vehicle.holder_kind == "tenant", Vehicle.status == "active")).all()
    for v in rows:
        v.status = "to_review"
    if rows:
        audit(db, user_id=user_id, org_id=org_id, property_id=unit.property_id, action="parking.vehicles.to_review", entity="unit", entity_id=unit.id, meta={"count": len(rows)})
    return len(rows)
