"""Demo data for M16: Sunrise Tower community hall and rooftop, prices, two blackout dates and eight bookings in mixed states."""
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import select

from .models.amenities import Amenity, Blackout, Booking, SlotHold
from .models.billing import Invoice, InvoiceLine, Payment
from .models.core import User, now
from .models.property import Unit
from .routers import billing as B
from .routers.amenities import PARTS, SLOT_BN, SLOT_EN, price
from .services import ledger

P = 100  # paisa per taka


def seed_amenities(db, ctx):
    sun = ctx["sunrise"]
    usr = lambda k: db.scalar(select(User).where(User.email == f"{k}@flatwise.demo"))
    unit = lambda n: db.scalar(select(Unit).where(Unit.property_id == sun.id, Unit.number == n))
    today = date.today()
    day = lambda n: today + timedelta(days=n)
    padmin = usr("padmin")
    rules_en = "Music must stop by 11 pm. No fireworks or open flames. Decorations must not damage the walls. Caterers use the service lift only. The host is responsible for the guests."
    rules_bn = "রাত ১১টার মধ্যে গান-বাজনা বন্ধ করতে হবে। আতশবাজি বা খোলা আগুন নিষিদ্ধ। সাজসজ্জায় দেয়ালের ক্ষতি করা যাবে না। ক্যাটারার শুধু সার্ভিস লিফট ব্যবহার করবে। অতিথিদের দায়িত্ব আয়োজকের।"
    hall = Amenity(property_id=sun.id, kind="hall", name="Community Hall", name_bn="কমিউনিটি হল", capacity=150, rules=rules_en, rules_bn=rules_bn, active=True,
                   slots={"morning": {"on": True, "owner": 9000 * P, "tenant": 11000 * P}, "evening": {"on": True, "owner": 12000 * P, "tenant": 15000 * P},
                          "night": {"on": True, "owner": 12000 * P, "tenant": 15000 * P}, "full": {"on": True, "owner": 25000 * P, "tenant": 30000 * P}},
                   ext_hour_fee=1500 * P, max_ext_hours=2, deposit=10000 * P, cleaning_fee=1500 * P, generator_fee=3000 * P, free_quota=0,
                   min_notice_days=3, max_advance_days=90, hold_days=3, cancel_rules=[{"days": 14, "pct": 100}, {"days": 7, "pct": 50}, {"days": 0, "pct": 0}])
    roof = Amenity(property_id=sun.id, kind="rooftop", name="Rooftop Garden", name_bn="ছাদ বাগান", capacity=40, rules="Gatherings end by 10 pm. No loud music.", rules_bn="অনুষ্ঠান রাত ১০টায় শেষ করতে হবে। উচ্চস্বরে গান নয়।", active=True,
                   slots={"morning": {"on": False, "owner": 0, "tenant": 0}, "evening": {"on": True, "owner": 3000 * P, "tenant": 4000 * P}, "night": {"on": True, "owner": 3000 * P, "tenant": 4000 * P}, "full": {"on": False, "owner": 0, "tenant": 0}},
                   ext_hour_fee=0, max_ext_hours=0, deposit=2000 * P, cleaning_fee=500 * P, generator_fee=0, free_quota=1,
                   min_notice_days=2, max_advance_days=60, hold_days=3, cancel_rules=[{"days": 7, "pct": 100}, {"days": 2, "pct": 50}, {"days": 0, "pct": 0}])
    db.add_all([hall, roof])
    db.flush()
    db.add_all([Blackout(property_id=sun.id, amenity_id=hall.id, on_date=day(21), reason="Hall floor polishing", reason_bn="হলের মেঝে পালিশ", created_by=padmin.id),
                Blackout(property_id=sun.id, amenity_id=None, on_date=max(date(2026, 12, 16), day(50)), reason="Victory Day building programme", reason_bn="বিজয় দিবসের ভবন অনুষ্ঠান", created_by=padmin.id)])
    # (amenity, flat, who, party, day offset, slot, purpose, guests, catering, status, ext, generator, paid method, damage, reason)
    rows = [
        (hall, "A-501", "owner", "owner", -40, "evening", "wedding_reception", 140, True, "completed", 1, True, "bank", 0, ""),
        (hall, "B-302", "tenant", "tenant", -20, "night", "birthday", 60, True, "completed", 0, False, "bkash", 2000 * P, ""),
        (hall, "A-801", "ownerrep", "owner", -12, "morning", "milad", 80, False, "rejected", 0, False, "", 0, "The hall is reserved for a committee event that day."),
        (hall, "A-501", "owner", "owner", 9, "evening", "aqeeqah", 70, True, "confirmed", 0, False, "bkash", 0, ""),
        (hall, "B-302", "tenant", "tenant", 16, "full", "birthday", 100, True, "approved", 0, True, "", 0, ""),
        (hall, "A-801", "ownerrep", "owner", 25, "morning", "meeting", 30, False, "pending", 0, False, "", 0, ""),
        (roof, "B-302", "owner2", "owner", 12, "evening", "birthday", 25, False, "confirmed", 0, False, "cash", 0, ""),
        (hall, "A-501", "owner", "owner", 40, "night", "wedding_reception", 120, True, "pending", 0, False, "", 0, ""),
    ]
    for a, flat, who, party, off, slot, purpose, guests, cat, status, ext, gen, method, damage, reason in rows:
        u, user = unit(flat), usr(who)
        b = Booking(property_id=sun.id, amenity_id=a.id, unit_id=u.id, user_id=user.id, party=party, on_date=day(off), slot=slot, purpose=purpose, guests=guests, catering=cat,
                    contact=user.phone or "01911000000", ext_hours=ext, use_generator=gen, status=status, reason=reason,
                    created_at=datetime.now(timezone.utc) - timedelta(days=max(2, 8 - off if off < 0 else 3)))
        db.add(b)
        db.flush()
        if status in ("pending", "rejected"):
            if status == "rejected":
                b.decided_by, b.decided_at = padmin.id, now() - timedelta(days=15)
            continue
        p = price(db, a, slot, party, u.id, b.on_date, ext, gen)
        b.fee, b.ext_fee, b.cleaning, b.generator, b.deposit, b.total, b.free_used = p["fee"], p["ext_fee"], p["cleaning"], p["generator"], p["deposit"], p["total"], p["free"]
        b.decided_by, b.decided_at = padmin.id, now() - timedelta(days=max(1, -off + 3 if off < 0 else 2))
        for part in PARTS[slot]:
            db.add(SlotHold(amenity_id=a.id, on_date=b.on_date, part=part, booking_id=b.id))
        period = f"HALL-{b.id}"
        inv = Invoice(property_id=sun.id, unit_id=u.id, period=period, number=f"INV-{sun.id}-{period}", issue_date=b.decided_at.date(), due_date=b.decided_at.date() + timedelta(days=a.hold_days), total=b.total)
        db.add(inv)
        db.flush()
        sn, sb = SLOT_EN[slot], SLOT_BN[slot]
        for en, bn, amt in ((f"{a.name}: {sn}", f"{a.name_bn}: {sb}", b.fee), (f"{a.name}: extra {ext} hour(s)", f"{a.name_bn}: অতিরিক্ত {ext} ঘণ্টা", b.ext_fee), (f"{a.name}: cleaning fee", f"{a.name_bn}: পরিচ্ছন্নতা ফি", b.cleaning),
                            (f"{a.name}: generator", f"{a.name_bn}: জেনারেটর", b.generator), (f"{a.name}: refundable deposit", f"{a.name_bn}: ফেরতযোগ্য জামানত", b.deposit)):
            if amt > 0 or (b.free_used and amt == 0 and en.endswith(sn)):
                db.add(InvoiceLine(invoice_id=inv.id, description=en, description_bn=bn, amount=amt))
        b.invoice_id = inv.id
        if status == "approved":
            b.expires_at = datetime.combine(today + timedelta(days=2), datetime.max.time().replace(microsecond=0), tzinfo=timezone.utc)
            continue
        pay = Payment(property_id=sun.id, invoice_id=inv.id, unit_id=u.id, amount=b.total, method=method, trx_id=f"HALL{b.id:04d}" if method in ("bkash", "nagad") else "",
                      paid_on=b.decided_at.date() + timedelta(days=1), status="verified", submitted_by=user.id, verified_by=padmin.id, verified_at=now(), note=f"Hall booking {b.id}")
        db.add(pay)
        db.flush()
        pay.receipt_no = B._receipt_no(db, sun.id)
        inv.paid, inv.status = b.total, "paid"
        ledger.post(db, sun.id, pay.paid_on, f"Hall booking receipt {pay.receipt_no}", [(ledger.METHOD_ACCOUNT[method], pay.amount, 0), *_credits(b, pay.amount)], "payment", pay.id, padmin.id)
        b.confirmed_at = pay.verified_at
        if status == "completed":
            b.damage_amount, b.damage_note = damage, "Broken chairs and a stained curtain" if damage else ""
            b.refund_amount, b.refund_method, b.refunded_at = b.deposit - damage, "bank", now() - timedelta(days=max(1, -off - 1))
            b.handover_by, b.handover_at = usr("caretaker").id, now() - timedelta(days=max(1, -off - 1))
    db.flush()


def _credits(b, amount):
    dep = amount * b.deposit // b.total if b.total and b.deposit else 0
    return [("4020", 0, amount - dep), ("2010", 0, dep)]
