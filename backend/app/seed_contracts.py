"""Demo data for vendor contracts: Sunrise Tower has five maintenance contracts: three due for renewal inside 60 days, one already expired, one with a service visit overdue."""
from datetime import date, timedelta

from sqlalchemy import select

from .models.contracts import Contract, ContractVisit
from .models.core import User
from .models.finance import Vendor

P = 100


def seed_contracts(db, ctx):
    sun = ctx["sunrise"]
    today = date.today()
    ct = db.scalar(select(User).where(User.email == "caretaker@flatwise.demo"))
    pa = db.scalar(select(User).where(User.email == "padmin@flatwise.demo"))

    def vendor(en, bn, cat="services"):
        v = db.scalar(select(Vendor).where(Vendor.property_id == sun.id, Vendor.name == en))
        if not v:
            v = Vendor(property_id=sun.id, name=en, name_bn=bn, category=cat, phone="01711000000")
            db.add(v)
            db.flush()
        return v

    rows = [  # kind, title, vendor, start offset (days), end offset (days), annual BDT, interval, visits [(days ago, technician, notes, cost BDT)]
        ("lift", "Lift AMC, Blocks A and B", vendor("Metro Lift Service", "মেট্রো লিফট সার্ভিস", "repairs"), -250, 115, 180000, 30,
         [(95, "Habib", "Greased guide rails, replaced door sensor on lift A2.", 0), (62, "Habib", "Monthly service. Brake pads checked.", 0), (31, "Sohel", "Monthly service. No faults.", 0), (4, "Habib", "Monthly service. Cabin fan replaced.", 3500)]),
        ("generator", "Generator AMC, 250 kVA", vendor("Power Care Engineering", "পাওয়ার কেয়ার ইঞ্জিনিয়ারিং"), -320, 45, 96000, 90,
         [(200, "Rafiq", "Oil and filter change.", 4200), (110, "Rafiq", "Battery test and load run.", 0), (20, "Rafiq", "Quarterly service. Coolant topped up.", 0)]),
        ("cctv", "CCTV and access control AMC", vendor("SecureView Systems", "সিকিউরভিউ সিস্টেমস"), -340, 25, 48000, 90,
         [(150, "Imran", "Cleaned cameras, moved NVR disk.", 0), (60, "Imran", "Camera 7 and 11 realigned.", 1800)]),
        ("fire", "Fire extinguisher and alarm service", vendor("Fire Safe Bangladesh", "ফায়ার সেফ বাংলাদেশ"), -300, 58, 36000, 120,
         [(170, "Mizan", "Refilled 14 extinguishers, tested alarm panel.", 0)]),
        ("pest", "Pest control, quarterly", vendor("Clean Home Pest Control", "ক্লিন হোম পেস্ট কন্ট্রোল"), -400, -12, 24000, 90,
         [(130, "Jahid", "Spray in basement, garbage room and stairwells.", 0), (40, "Jahid", "Rodent bait stations refreshed.", 0)]),
    ]
    for kind, title, v, s, e, cost, every, visits in rows:
        c = Contract(property_id=sun.id, kind=kind, title=title, vendor_id=v.id, start_date=today + timedelta(days=s), end_date=today + timedelta(days=e),
                     annual_cost=cost * P, interval_days=every, status="active", created_by=pa.id if pa else None)
        db.add(c)
        db.flush()
        for ago, tech, note, vc in visits:
            db.add(ContractVisit(contract_id=c.id, visited_on=today - timedelta(days=ago), technician=tech, notes=note, cost=vc * P, created_by=ct.id if ct else None))
    db.flush()
