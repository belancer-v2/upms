"""Demo data for M18: two supplier agencies, their staff, posts, shifts, two rostered weeks with attendance, one substitute and one pending bill."""
from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from .models.agency import Agency, AgencyBill, AgencySetting, Post, Replacement, RosterSlot, ShiftDef, StaffPosting
from .models.billing import Message
from .models.core import User
from .models.finance import Expense, Vendor
from .models.staff import Staff
from .routers.agency import DUAL_ABOVE, _today, week_start
from .services import vault


def seed_agency(db, ctx):
    sun = ctx["sunrise"]
    today = _today()
    tr = db.scalar(select(User).where(User.email == "treasurer@flatwise.demo"))
    sec = db.scalar(select(User).where(User.email == "secretary@flatwise.demo"))
    P = 100

    def agency(name, bn, kind, **kw):
        a = Agency(property_id=sun.id, name=name, name_bn=bn, kind=kind, **kw)
        db.add(a)
        db.flush()
        v = Vendor(property_id=sun.id, name=name, name_bn=bn, phone=kw.get("contact_phone", ""), category="services")
        db.add(v)
        db.flush()
        a.vendor_id = v.id
        return a

    shield = agency("Shield Guard Services Ltd", "শিল্ড গার্ড সার্ভিসেস লিমিটেড", "security", trade_licence="TL-DNCC-2019-004512", reg_no="TIN 123456789012 / BIN 000123456-0101", psc_licence="PSC-BD-0457/2023",
                    address="House 14, Road 3, Mohammadpur, Dhaka", contact_name="Maj. (Retd) Anwar Hossain", contact_phone="01711223344", emergency_phone="01711223300",
                    contract_start=today - timedelta(days=305), contract_end=today + timedelta(days=45), fee_mode="flat", monthly_fee=120_000 * P, notice_days=30,
                    sla_notes="Four guards on the Main gate across three shifts. Replacement within 2 hours of a call-out. Police verification for every guard.")
    clean = agency("CleanPro Facility Services", "ক্লিনপ্রো ফ্যাসিলিটি সার্ভিসেস", "cleaning", trade_licence="TL-DNCC-2021-017733", reg_no="TIN 987654321098",
                   address="Plot 8, Tejgaon Industrial Area, Dhaka", contact_name="Mizanur Rahman", contact_phone="01811334455", emergency_phone="01811334400",
                   contract_start=today - timedelta(days=120), contract_end=today + timedelta(days=245), fee_mode="per_post", monthly_fee=14_000 * P, notice_days=15,
                   sla_notes="Two cleaners, daily 06:00 to 14:00. Cleaning materials supplied by the agency.")
    db.add(AgencySetting(property_id=sun.id, shortfall_rate=400 * P))

    sh = {}
    for key, n, bn, a, b in (("day", "Day", "দিন", "06:00", "14:00"), ("eve", "Evening", "সন্ধ্যা", "14:00", "22:00"), ("night", "Night", "রাত", "22:00", "06:00")):
        sh[key] = ShiftDef(property_id=sun.id, name=n, name_bn=bn, start=a, end=b)
        db.add(sh[key])
    db.flush()
    allsh = [sh["day"].id, sh["eve"].id, sh["night"].id]
    posts = {}
    for key, n, bn, kind, hc, shifts, ag in (("main", "Main gate", "মূল ফটক", "security", 1, allsh, shield), ("lobby", "Lobby / CCTV", "লবি / সিসিটিভি", "security", 1, [sh["day"].id, sh["night"].id], None),
                                             ("blockA", "Block A cleaning", "ব্লক এ পরিচ্ছন্নতা", "cleaning", 1, [sh["day"].id], clean), ("common", "Common-area cleaning", "কমন এলাকা পরিচ্ছন্নতা", "cleaning", 1, [sh["day"].id], clean)):
        posts[key] = Post(property_id=sun.id, name=n, name_bn=bn, kind=kind, headcount=hc, shift_ids=shifts, agency_id=ag.id if ag else None)
        db.add(posts[key])
    db.flush()

    def person(name, bn, role, phone, nid, ag, emp, days_ago):
        s = Staff(property_id=sun.id, name=name, name_bn=bn, role=role, phone=phone, joined=today - timedelta(days=days_ago), salary=0, nid_enc=vault.seal(nid), nid_last4=nid[-4:])
        db.add(s)
        db.flush()
        db.add(StaffPosting(staff_id=s.id, agency_id=ag.id, emp_no=emp, deployed_on=today - timedelta(days=days_ago)))
        return s

    g = [person("Rubel Mia", "রুবেল মিয়া", "guard", "01911500001", "1992345678901", shield, "SG-1041", 300), person("Sohel Rana", "সোহেল রানা", "guard", "01911500002", "1989456789012", shield, "SG-1042", 290),
         person("Abul Kashem", "আবুল কাশেম", "guard", "01911500003", "1987567890123", shield, "SG-1057", 200), person("Nur Islam", "নূর ইসলাম", "guard", "01911500004", "1994678901234", shield, "SG-1063", 150)]
    c = [person("Rina Khatun", "রিনা খাতুন", "cleaner", "01911500005", "1995789012345", clean, "CP-207", 110), person("Moyna Begum", "ময়না বেগম", "cleaner", "01911500006", "1991890123456", clean, "CP-208", 110)]
    direct = {s.name: s for s in db.scalars(select(Staff).where(Staff.property_id == sun.id, Staff.name.in_(["Rahim Mia", "Karim Uddin", "Jabbar Ali"])))}
    rahim, karim, jabbar = direct["Rahim Mia"], direct["Karim Uddin"], direct["Jabbar Ali"]

    this_start = week_start(today)
    plan = []   # (date, post, shift, staff)
    for wk in (this_start - timedelta(days=7), this_start):
        for i in range(7):
            d = wk + timedelta(days=i)
            for k, shk in enumerate(("day", "eve", "night")):
                plan.append((d, "main", shk, g[(i + k) % 4]))                      # 3 of 4 guards each day, one rests
            plan.append((d, "lobby", "day", rahim if i < 6 else karim))
            plan.append((d, "lobby", "night", karim if i < 4 else jabbar))
            if i != 5:
                plan.append((d, "blockA", "day", c[0]))                           # Block A cleaner rests on the 6th day of the week
            if i != 6:
                plan.append((d, "common", "day", c[1]))                           # common-area cleaner rests on the 7th
    slots = []
    for d, pk, shk, s in plan:
        sl = RosterSlot(property_id=sun.id, day=d, post_id=posts[pk].id, shift_id=sh[shk].id, staff_id=s.id)
        if d < today:
            sl.status, sl.marked_by, sl.marked_at = "present", sec.id, datetime.now(timezone.utc) - timedelta(days=(today - d).days)
        db.add(sl)
        slots.append(sl)
    db.flush()
    # last week: two late arrivals, two absences (one covered by a substitute, one not) and one leave day
    lastwk = [s for s in slots if s.day < this_start and s.post_id == posts["main"].id]
    lastwk[2].status = "late"
    lastwk[9].status = "late"
    ab1, ab2, lv = lastwk[4], lastwk[13], lastwk[16]
    ab1.status, ab1.note = "absent", "Sick, called in"
    ab2.status, ab2.note = "absent", "No call"
    lv.status, lv.note = "leave", "Approved leave"
    sub = Staff(property_id=sun.id, name="Hasan Ali (substitute)", name_bn="হাসান আলী (বদলি)", role="guard", phone="01911500009", joined=ab1.day, salary=0)
    db.add(sub)
    db.flush()
    db.add(StaffPosting(staff_id=sub.id, agency_id=shield.id, emp_no="SG-TEMP-9", deployed_on=ab1.day, substitute=True))
    db.add(RosterSlot(property_id=sun.id, day=ab1.day, post_id=ab1.post_id, shift_id=ab1.shift_id, staff_id=sub.id, status="present", substitute=True, note="substitute", marked_by=sec.id, marked_at=datetime.now(timezone.utc)))
    db.flush()
    for slot, filled in ((ab1, True), (ab2, False)):
        r = Replacement(property_id=sun.id, slot_id=slot.id, agency_id=shield.id, day=slot.day, post_id=slot.post_id, shift_id=slot.shift_id, absent_staff_id=slot.staff_id, requested_by=sec.id,
                        status="fulfilled" if filled else "requested", sub_staff_id=sub.id if filled else None, sms_status="sent")
        db.add(r)
        db.flush()
        db.add(Message(property_id=sun.id, to_name=shield.contact_name, to_phone=shield.contact_phone, template="roster_replacement", lang="bn", idem_key=f"rosterrepl{r.id}", status="sent",
                       sent_at=datetime.now(timezone.utc), body=f"{sun.name_bn}: {slot.day.isoformat()} বদলি কর্মী পাঠান।"))
    # one monthly bill record (previous month, flat fee, no deductions) that went through the normal expense flow
    first = today.replace(day=1)
    prev = (first - timedelta(days=1)).strftime("%Y-%m")
    amount = shield.monthly_fee
    e = Expense(property_id=sun.id, category="services", vendor_id=shield.vendor_id, title=f"{shield.name} invoice SGS/{prev}/118 ({prev})", amount=amount, spent_on=first, needs_two=amount > DUAL_ABOVE, requested_by=tr.id)
    db.add(e)
    db.flush()
    db.add(AgencyBill(property_id=sun.id, agency_id=shield.id, period=prev, number=f"SGS/{prev}/118", amount=amount, expected=amount, shortfall_units=0, deduction=0, expense_id=e.id, created_by=tr.id))
    db.flush()
