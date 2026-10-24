"""Demo data for M15: Sunrise Tower visitor log (about 60 visitors over 10 days), a pass, two frequent visitors."""
from datetime import datetime, timedelta, timezone
from random import Random

from sqlalchemy import select

from .models.core import Membership, User
from .models.property import Unit
from .models.visitors import FrequentVisitor, Visit, VisitorNotice, VisitorPass
from .permissions import RESIDENT
from .routers.visitors import BD, _hash

DEMO_PASS_CODE = "482913"        # demo only: the real flow shows a code once and never stores it
NAMES = [("Rashed Khan", "guest"), ("Mitu Akter", "guest"), ("Foodpanda rider", "courier"), ("Pathao rider", "courier"), ("Sumon (plumber)", "service"), ("Electrician Alamgir", "service"),
         ("Uber driver", "cab"), ("Courier, Sundarban", "courier"), ("Dr. Hasina", "guest"), ("Tax officer", "official"), ("Gas cylinder man", "delivery"), ("Water jar, Pran", "delivery"),
         ("Nasir Uddin", "guest"), ("Sharmin Sultana", "guest"), ("Painter Kalam", "service"), ("Internet technician", "service"), ("Meter reader, DESCO", "official"), ("Rafi (cousin)", "guest")]


def seed_visitors(db, ctx):
    sun = ctx["sunrise"]
    r = Random(15)
    usr = lambda k: db.scalar(select(User).where(User.email == f"{k}@flatwise.demo"))
    guard, owner, owner2 = usr("guard"), usr("owner"), usr("owner2")
    units = {u.number: u for u in db.scalars(select(Unit).where(Unit.property_id == sun.id))}
    numbers = sorted(units)
    login_flats = ["A-501", "B-302", "A-801"]
    now = datetime.now(timezone.utc)
    ago = lambda h: now - timedelta(hours=h)
    visits: list[Visit] = []

    def add(unit, name, purpose, created, status="out", kind="walkin", via="resident", people=1, vehicle="", dur=1.0, phone="", note=""):
        v = Visit(property_id=sun.id, unit_id=units[unit].id, name=name, phone=phone, purpose=purpose, people=people, vehicle=vehicle, kind=kind, status=status, decision_via=via if status != "waiting" else "",
                  created_by=guard.id, created_at=created, note=note)
        if status != "waiting":
            v.decided_at = created + timedelta(minutes=2)
            v.decided_by = owner.id if via == "resident" else None
        if status in ("in", "out"):
            v.in_at = created + timedelta(minutes=3)
        if status == "out":
            v.out_at = v.in_at + timedelta(hours=dur)
        db.add(v)
        visits.append(v)
        return v

    # about 55 finished visits spread over the last 10 days
    for i in range(55):
        name, purpose = NAMES[r.randrange(len(NAMES))]
        unit = login_flats[r.randrange(3)] if i % 3 == 0 else numbers[r.randrange(len(numbers))]
        created = now - timedelta(days=r.randrange(0, 10), hours=r.randrange(1, 14), minutes=r.randrange(60))
        if created > ago(3):
            created = ago(r.randrange(4, 20))
        roll = r.random()
        vehicle = f"DHAKA-METRO-HA-{r.randrange(10, 99)}-{r.randrange(1000, 9999)}" if purpose in ("cab", "guest") and r.random() < 0.4 else ""
        phone = f"017{r.randrange(10000000, 99999999)}" if purpose in ("guest", "service") else ""
        if roll < 0.08:
            add(unit, name, purpose, created, "denied", people=1, phone=phone)
        elif purpose == "delivery":
            add(unit, name, purpose, created, "out", kind="delivery", via="delivery", dur=0.2)
        else:
            add(unit, name, purpose, created, "out", people=r.randrange(1, 4), vehicle=vehicle, phone=phone, dur=r.choice([0.3, 0.8, 1.5, 3, 5]))
    add("A-102", "Guest of Mr. Haque", "guest", ago(30), "out", via="override", note="Resident phone not answering, known family guest", dur=2)
    # 3 currently inside (one has stayed too long, with a vehicle)
    add("A-501", "Rafi (cousin)", "guest", ago(1.5), "in", people=2, phone="01712000111")
    add("B-302", "Electrician Alamgir", "service", ago(0.8), "in", phone="01712000222")
    add("A-203", "Rented van, movers", "service", ago(14), "in", people=3, vehicle="DHAKA-METRO-U-11-2345", via="override", note="Resident away, owner called the guard")
    # 2 waiting for the resident
    add("A-501", "Sharmin Sultana", "guest", ago(0.05), "waiting", people=2, phone="01713000333")
    add("B-302", "Foodpanda rider", "courier", ago(0.02), "waiting")
    db.flush()
    # notifications for the flats that have a login
    members = db.scalars(select(Membership).where(Membership.org_id == sun.org_id, Membership.role.in_(list(RESIDENT)))).all()
    by_unit: dict[int, set[int]] = {}
    for m in members:
        if m.unit_id:
            by_unit.setdefault(m.unit_id, set()).add(m.user_id)
    for v in visits:
        for uid in sorted(by_unit.get(v.unit_id, ())):
            fresh = v.status == "waiting" or v.created_at > ago(2)
            db.add(VisitorNotice(property_id=sun.id, user_id=uid, unit_id=v.unit_id, visit_id=v.id, kind="ask" if v.kind == "walkin" else "info", created_at=v.created_at,
                                 read_at=None if fresh else v.created_at + timedelta(minutes=2)))
    # one pre-approved pass (valid for tonight), one frequent maid and one driver
    db.add(VisitorPass(property_id=sun.id, unit_id=units["A-501"].id, name="Dr. Hasina (family doctor)", purpose="guest", people=1, valid_from=now - timedelta(hours=1), valid_to=now + timedelta(hours=10),
                       code_hash=_hash(sun.id, DEMO_PASS_CODE), created_by=owner.id))
    today = datetime.now(BD).date()
    db.add(FrequentVisitor(property_id=sun.id, unit_id=units["B-302"].id, name="Rina Begum", phone="01714000444", role="maid", valid_from=today - timedelta(days=60), valid_to=today + timedelta(days=120), created_by=owner2.id))
    db.add(FrequentVisitor(property_id=sun.id, unit_id=units["A-501"].id, name="Driver Moksed", phone="01714000555", role="driver", valid_from=today - timedelta(days=30), valid_to=today + timedelta(days=60), created_by=owner.id))
    db.flush()
