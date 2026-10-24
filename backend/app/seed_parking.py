"""Demo data for M17: Sunrise Tower parking. Every flat has a car slot, ten have a second, four visitor bays, ~28 vehicles."""
from datetime import date, datetime, timedelta, timezone
from random import Random

from sqlalchemy import select

from .models.core import User
from .models.parking import ParkingAllocation, ParkingSlot, ParkingVisit, Vehicle
from .models.property import Unit
from .services.parking import clean_plate, provision_unit, set_entitlement

PREFIX = ["DHAKA METRO GA", "DHAKA METRO KHA", "DHAKA METRO HA", "DHAKA METRO CHA"]
MAKES = [("Toyota Axio", "White"), ("Toyota Allion", "Silver"), ("Honda Vezel", "Black"), ("Toyota Premio", "Grey"), ("Nissan X-Trail", "Pearl"), ("Suzuki Swift", "Red"), ("Honda Grace", "Blue")]
BIKES = [("Yamaha FZ", "Black"), ("Honda CB Hornet", "Red"), ("Suzuki Gixxer", "Blue"), ("Bajaj Pulsar", "Grey")]


def seed_parking(db, ctx):
    sun = ctx["sunrise"]
    units = {u.number: u for u in db.scalars(select(Unit).where(Unit.property_id == sun.id))}
    ordered = sorted(units.values(), key=lambda u: (u.floor, u.number))
    usr = lambda k: db.scalar(select(User).where(User.email == f"{k}@flatwise.demo"))
    since = date.today() - timedelta(days=400)
    for u in ordered:
        provision_unit(db, u, 1, 0)
    # ten flats get a second slot: a motorbike bay for six of them, a second car slot for four
    seconds = ["A-501", "B-302", "A-801"] + [u.number for u in ordered if u.number not in ("A-501", "B-302", "A-801")][:7]
    for i, n in enumerate(seconds):
        if i < 6:
            provision_unit(db, units[n], 1, 1)
        else:
            u = units[n]
            code = f"{n}-C2"
            s = ParkingSlot(property_id=sun.id, code=code, level="Ground", kind="car", cover="open")
            db.add(s)
            db.flush()
            db.add(ParkingAllocation(slot_id=s.id, unit_id=u.id, vehicle_kind="car", since=date.today()))
            db.flush()
            set_entitlement(db, u.id, "car", 2)
    # two flats are promised a second car slot that has not been handed over yet
    for n in ("A-802", "B-402"):
        db.flush()
        set_entitlement(db, units[n].id, "car", 2)
    # visitor bays and two free slots in the basement
    for i in range(1, 5):
        db.add(ParkingSlot(property_id=sun.id, code=f"V-{i:02d}", level="Ground", kind="car", cover="open", visitor=True, note="Visitor bay"))
    db.add(ParkingSlot(property_id=sun.id, code="P-B-01", level="Basement", kind="car", cover="covered"))
    db.add(ParkingSlot(property_id=sun.id, code="P-B-02", level="Basement", kind="car", cover="covered"))
    db.add(ParkingSlot(property_id=sun.id, code="P-B-03", level="Basement", kind="motorbike", cover="covered", status="blocked", note="Waterlogged, under repair"))
    db.flush()
    # vehicles
    rnd = Random(23)
    used: set[str] = set()

    def plate():
        while True:
            shown, norm = clean_plate(f"{rnd.choice(PREFIX)} {rnd.randint(11, 39)}-{rnd.randint(1000, 9999)}")
            if norm not in used:
                used.add(norm)
                return shown, norm

    def add(unit, kind, who, status="active", holder="owner", i=0):
        shown, norm = plate()
        mm, colour = (MAKES if kind == "car" else BIKES)[i % (len(MAKES) if kind == "car" else len(BIKES))]
        db.add(Vehicle(property_id=sun.id, unit_id=unit.id, reg_no=shown, reg_norm=norm, kind=kind, make_model=mm, colour=colour, sticker=f"S-{unit.id:03d}{kind[0].upper()}", holder_kind=holder,
                       status=status, registered_by=who.id if who else None))

    owner, tenant = usr("owner"), usr("tenant")
    n = 0
    for u in ordered[:24]:
        who = owner if u.number == "A-501" else tenant if u.number == "B-302" else None
        add(u, "car", who, holder="tenant" if u.number == "B-302" else "owner", i=n)
        n += 1
    for u in [units[k] for k in seconds[:4]]:
        add(u, "motorbike", owner if u.number == "A-501" else None, i=n)
        n += 1
    # two tenant vehicles left behind after a move-out, waiting for review
    for k in ("A-401", "B-401"):
        add(units[k], "car", None, status="to_review", holder="tenant", i=n)
        n += 1
    # visitor log: one car in, two gone
    bays = {s.code: s for s in db.scalars(select(ParkingSlot).where(ParkingSlot.property_id == sun.id, ParkingSlot.visitor))}
    guard = usr("guard")
    ago = lambda h: datetime.now(timezone.utc) - timedelta(hours=h)
    db.add(ParkingVisit(property_id=sun.id, slot_id=bays["V-01"].id, plate="DHAKA METRO GHA 11-2468", in_at=ago(1), logged_by=guard.id))
    db.add(ParkingVisit(property_id=sun.id, slot_id=bays["V-02"].id, plate="DHAKA METRO KA 15-9021", in_at=ago(30), out_at=ago(27), logged_by=guard.id))
    db.add(ParkingVisit(property_id=sun.id, slot_id=bays["V-01"].id, plate="DHAKA METRO LA 12-7765", in_at=ago(52), out_at=ago(50), logged_by=guard.id))
    db.flush()
