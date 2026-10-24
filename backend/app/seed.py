"""Demo data. Run: python -m app.seed  (safe to run again; it resets the demo database)."""
from sqlalchemy import select

from .db import Base, SessionLocal, engine
from . import models  # noqa: F401
from .models.core import Membership, Organization, Property, User, now
from .security import hash_password

PASSWORD = "demo1234"


def mk_user(db, email, name, name_bn, phone="", saas_role=None, lang="en"):
    u = User(email=f"{email}@flatwise.demo", name=name, name_bn=name_bn, phone=phone,
             password_hash=hash_password(PASSWORD), saas_role=saas_role, lang=lang)
    db.add(u)
    db.flush()
    return u


def seed_core(db):
    # --- SaaS staff
    mk_user(db, "super", "Rafiq Hasan", "রফিক হাসান", "01711000001", "SUPER_ADMIN")
    mk_user(db, "admin", "Nusrat Jahan", "নুসরাত জাহান", "01711000002", "SAAS_ADMIN")
    mk_user(db, "finance", "Tanvir Ahmed", "তানভীর আহমেদ", "01711000003", "SAAS_FINANCE")
    mk_user(db, "sales", "Mehedi Hasan", "মেহেদী হাসান", "01711000004", "SAAS_SALES")
    mk_user(db, "support", "Sadia Rahman", "সাদিয়া রহমান", "01711000005", "SAAS_USER")

    # --- Agency with three buildings
    agency = Organization(name="Metro Property Care Ltd", name_bn="মেট্রো প্রপার্টি কেয়ার লিমিটেড", kind="agency", status="active")
    db.add(agency)
    db.flush()
    sunrise = Property(org_id=agency.id, name="Sunrise Tower", name_bn="সানরাইজ টাওয়ার", address="Road 5, Dhanmondi", city="Dhaka", floors=8)
    lake = Property(org_id=agency.id, name="Lakeview Heights", name_bn="লেকভিউ হাইটস", address="Road 12, Gulshan 2", city="Dhaka", floors=10)
    green = Property(org_id=agency.id, name="Green Court", name_bn="গ্রিন কোর্ট", address="Sector 7, Uttara", city="Dhaka", floors=6)
    db.add_all([sunrise, lake, green])
    db.flush()

    agency_mgr = mk_user(db, "agency", "Farhana Karim", "ফারহানা করিম", "01811000001")
    db.add(Membership(user_id=agency_mgr.id, org_id=agency.id, property_id=None, role="AGENCY_MANAGER"))

    def add(email, name, name_bn, role, phone="", prop=sunrise):
        u = mk_user(db, email, name, name_bn, phone)
        db.add(Membership(user_id=u.id, org_id=agency.id, property_id=prop.id, role=role))
        return u

    padmin = add("padmin", "Imran Hossain", "ইমরান হোসেন", "PROPERTY_ADMIN", "01911000001")
    pres = add("president", "Dr. Kamal Uddin", "ডা. কামাল উদ্দিন", "PRESIDENT", "01911000002")
    add("secretary", "Shirin Akter", "শিরীন আক্তার", "SECRETARY", "01911000003")
    add("treasurer", "Abdul Karim", "আব্দুল করিম", "TREASURER", "01911000004")
    add("member", "Jahangir Alam", "জাহাঙ্গীর আলম", "MEMBER", "01911000005")
    add("caretaker", "Rahim Mia", "রহিম মিয়া", "CARETAKER", "01911000006")
    add("auditor", "Salma Khatun", "সালমা খাতুন", "AUDITOR", "01911000007")
    add("guard", "Babul Sheikh", "বাবুল শেখ", "GUARD", "01911000008")
    # Flat owner who is ALSO a committee member (two roles, one login)
    owner = add("owner", "Mahmud Hasan", "মাহমুদ হাসান", "FLAT_OWNER", "01911000009")
    db.add(Membership(user_id=owner.id, org_id=agency.id, property_id=sunrise.id, role="MEMBER"))
    add("owner2", "Rokeya Begum", "রোকেয়া বেগম", "FLAT_OWNER", "01911000010")
    add("tenant", "Tasnim Ferdous", "তাসনিম ফেরদৌস", "TENANT", "01911000011")
    add("ownerrep", "Nazmul Islam", "নাজমুল ইসলাম", "OWNER_REP", "01911000012")
    return {"agency": agency, "sunrise": sunrise, "lake": lake, "green": green, "owner": owner}


def reset():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)


def run():
    reset()
    with SessionLocal() as db:
        ctx = seed_core(db)
        for fn in EXTRA_SEEDS:
            fn(db, ctx)
        db.commit()
    print("Seeded. Demo password:", PASSWORD)


def seed_plans(db, ctx):
    from .models.saas import Plan, Subscription
    P = 100  # paisa per taka
    base = {"S": 1, "M": 1, "L": 1}
    db.add_all([
        Plan(key="basic", name="Basic", name_bn="বেসিক", sort=1,
             monthly={"S": 1500 * P, "M": 2500 * P, "L": 4000 * P}, setup={"S": 3000 * P, "M": 5000 * P, "L": 8000 * P},
             sms_included={"S": 200, "M": 500, "L": 1000},
             features=["billing", "expenses", "notices", "resident_web", "reports"]),
        Plan(key="standard", name="Standard", name_bn="স্ট্যান্ডার্ড", sort=2,
             monthly={"S": 3000 * P, "M": 4500 * P, "L": 7000 * P}, setup={"S": 3000 * P, "M": 5000 * P, "L": 8000 * P},
             sms_included={"S": 200, "M": 500, "L": 1000},
             features=["billing", "expenses", "notices", "resident_web", "reports", "staff", "assets", "tenant_dmp", "reminders", "caretaker_app", "cash_confirm", "policies", "committee", "rental_records", "amenities"]),
        Plan(key="pro", name="Pro", name_bn="প্রো", sort=3,
             monthly={"S": 5000 * P, "M": 7500 * P, "L": 11000 * P}, setup={"S": 3000 * P, "M": 5000 * P, "L": 8000 * P},
             sms_included={"S": 200, "M": 500, "L": 1000},
             features=["billing", "expenses", "notices", "resident_web", "reports", "staff", "assets", "tenant_dmp", "reminders", "caretaker_app", "cash_confirm", "policies",
                       "resident_portal", "visitor", "amenities", "parking", "maintenance", "cash_otp", "priority_support", "gateway", "committee", "rental_records"]),
    ])
    db.flush()
    # the demo agency and its three buildings run on Pro
    db.add(Subscription(org_id=ctx["agency"].id, plan_key="pro", band="M", flats=96, status="active"))


def seed_saas_demo(db, ctx):
    from datetime import timedelta
    from random import Random
    from .models.core import now
    from .models.saas import Lead, LeadNote, Plan, SaasInvoice, SmsLedger, Subscription
    from .services.entitlements import current_subscription
    rnd = Random(7)
    sales = db.scalar(select(User).where(User.email == "sales@flatwise.demo"))
    plans = {p.key: p for p in db.scalars(select(Plan))}
    seq = [0]

    def invoice(org, kind, period, desc, amount, issued_days_ago, paid, method="bkash", due_days=10):
        seq[0] += 1
        issued = now() - timedelta(days=issued_days_ago)
        inv = SaasInvoice(number=f"FW-{issued:%Y%m}-{seq[0]:04d}", org_id=org.id, kind=kind, period=period, description=desc, amount=amount,
                          issued_at=issued, due_at=issued + timedelta(days=due_days), status="paid" if paid else "issued")
        if paid:
            inv.paid_at, inv.method, inv.trx_id = issued + timedelta(days=3), method, f"TX{rnd.randint(10**7, 10**8)}"
        db.add(inv)

    customers = [  # name, bn, city, plan, band, flats, state, cycle, trial_days_left, discount, sms
        ("Rupayan Tower Owners Association", "রূপায়ণ টাওয়ার মালিক সমিতি", "Dhaka", "standard", "M", 62, "active", "monthly", 0, 0, 420),
        ("Green Valley Flat Owners", "গ্রিন ভ্যালি ফ্ল্যাট মালিক", "Dhaka", "basic", "S", 24, "active", "monthly", 0, 0, 42),
        ("Shapla Residential Committee", "শাপলা আবাসিক কমিটি", "Dhaka", "standard", "M", 54, "active", "monthly", 0, 0, 380),
        ("Palm Garden Apartments", "পাম গার্ডেন অ্যাপার্টমেন্টস", "Dhaka", "pro", "L", 120, "active", "yearly", 0, 10, 1650),
        ("Lake Breeze Owners", "লেক ব্রিজ মালিক সমিতি", "Dhaka", "pro", "M", 70, "active", "monthly", 0, 0, 910),
        ("Nirala Heights", "নিরালা হাইটস", "Chattogram", "standard", "S", 28, "active", "monthly", 0, 0, 260),
        ("Moon View Tower", "মুন ভিউ টাওয়ার", "Dhaka", "standard", "L", 96, "past_due", "monthly", 0, 0, 120),
        ("Sonar Bangla Housing", "সোনার বাংলা হাউজিং", "Dhaka", "basic", "S", 18, "trial", "monthly", 6, 0, 200),
        ("Dream Nest Apartments", "ড্রিম নেস্ট অ্যাপার্টমেন্টস", "Narayanganj", "standard", "M", 40, "trial", "monthly", 19, 0, 200),
        ("City Garden Tower", "সিটি গার্ডেন টাওয়ার", "Sylhet", "pro", "M", 64, "trial", "monthly", 2, 0, 200),
        ("Old Dhaka Heritage Flats", "পুরান ঢাকা হেরিটেজ ফ্ল্যাটস", "Dhaka", "basic", "S", 22, "suspended", "monthly", 0, 0, 0),
        ("Bijoy Sarani Residency", "বিজয় সরণি রেসিডেন্সি", "Dhaka", "standard", "M", 58, "active", "monthly", 0, 0, 300),
    ]
    for i, (name, bn, city, plan, band, flats, state, cycle, tdays, disc, sms) in enumerate(customers, start=1):
        org = Organization(name=name, name_bn=bn, kind="committee", status="active" if state == "past_due" else state, city=city,
                           created_at=now() - timedelta(days=(30 - tdays) if state == "trial" else 120 + i * 9))
        db.add(org)
        db.flush()
        db.add(Property(org_id=org.id, name=name, name_bn=bn, city=city, floors=max(4, flats // 8)))
        adm = User(email=f"admin{i}@customers.demo", name=f"Admin {i}", password_hash=hash_password(PASSWORD))
        db.add(adm)
        db.flush()
        db.add(Membership(user_id=adm.id, org_id=org.id, role="PROPERTY_ADMIN"))
        sub = Subscription(org_id=org.id, plan_key=plan, band=band, cycle=cycle, flats=flats, status=state, discount_pct=disc,
                           started_at=org.created_at, trial_ends=(now() + timedelta(days=tdays)) if state == "trial" else None)
        db.add(sub)
        db.add(SmsLedger(org_id=org.id, delta=sms + (350 if sms and state != "trial" else 0), reason="Opening balance"))
        if sms and state != "trial":
            db.add(SmsLedger(org_id=org.id, delta=-350, reason="SMS sent"))
        if state in ("active", "past_due"):
            price = int(plans[plan].monthly[band] * (100 - disc) / 100)
            amt = price * 10 if cycle == "yearly" else price
            invoice(org, "setup", "", f"One-time setup, {plans[plan].name}", plans[plan].setup[band], 80, True)
            if cycle == "yearly":
                invoice(org, "subscription", "2026", f"{plans[plan].name} · {band} · 2026", amt, 40, True, "bank")
            else:
                invoice(org, "subscription", "2026-09", f"{plans[plan].name} · {band} · 2026-09", amt, 38, state != "past_due")
                invoice(org, "subscription", "2026-10", f"{plans[plan].name} · {band} · 2026-10", amt, 8, i % 3 != 0 and state != "past_due")
    # the demo agency
    ag = ctx["agency"]
    for period, ago in (("2026-09", 36), ("2026-10", 6)):
        invoice(ag, "subscription", period, f"Pro · M · {period}", plans["pro"].monthly["M"], ago, True, "bank")
    db.add(SmsLedger(org_id=ag.id, delta=1500, reason="Opening balance"))

    leads = [  # name, phone, building, flats, city, source, status, note
        ("Mizanur Rahman", "01715000011", "Eden Court", 36, "Dhaka", "website", "new", ""),
        ("Parveen Sultana", "01715000012", "Rose Valley Tower", 72, "Dhaka", "demo", "new", ""),
        ("Anisul Haque", "01715000013", "Padma Residency", 30, "Rajshahi", "website", "contacted", "Called. Wants a demo on Friday."),
        ("Shahana Yesmin", "01715000014", "Meghna Heights", 90, "Dhaka", "demo", "demo", "Demo booked for Sunday 4pm. Treasurer will join."),
        ("Golam Mostafa", "01715000015", "Kaliganj Tower", 48, "Gazipur", "referral", "trial", "Started trial. Needs Excel import help."),
        ("Rezaul Karim", "01715000016", "Blue Sky Apartments", 120, "Dhaka", "website", "won", "Signed Pro, yearly."),
        ("Nasrin Akter", "01715000017", "Shanti Nibash", 16, "Khulna", "website", "lost", "Too small for now. Follow up in 6 months."),
        ("Habibur Rahman", "01715000018", "Sunflower Court", 55, "Dhaka", "demo", "contacted", "Asked about bKash TrxID flow."),
        ("Tahmina Khan", "01715000019", "Orchid Plaza", 210, "Dhaka", "website", "demo", "Large complex. Needs custom quote."),
        ("Abu Taher", "01715000020", "Jamuna View", 44, "Mymensingh", "website", "new", ""),
        ("Farida Parvin", "01715000021", "Kadamtali Residence", 26, "Dhaka", "referral", "trial", "On Basic trial."),
        ("Shamim Ahmed", "01715000022", "Hill Top Flats", 38, "Chattogram", "website", "contacted", "")]
    for n, ph, b, f, c, src, st, note in leads:
        l = Lead(name=n, phone=ph, building=b, flats=f, city=c, source=src, status=st, owner_id=sales.id if st != "new" else None,
                 created_at=now() - timedelta(days=rnd.randint(1, 25)))
        db.add(l)
        db.flush()
        if note:
            db.add(LeadNote(lead_id=l.id, user_id=sales.id, text=note))


NAMES = [("Abdur Rahman", "আব্দুর রহমান"), ("Shamsul Haque", "শামসুল হক"), ("Nurul Islam", "নূরুল ইসলাম"), ("Fatema Begum", "ফাতেমা বেগম"), ("Kamrul Hasan", "কামরুল হাসান"),
         ("Sultana Razia", "সুলতানা রাজিয়া"), ("Monir Hossain", "মনির হোসেন"), ("Rina Akter", "রিনা আক্তার"), ("Habib Ullah", "হাবিব উল্লাহ"), ("Shirin Sultana", "শিরীন সুলতানা"),
         ("Anwar Hossain", "আনোয়ার হোসেন"), ("Mahfuza Khatun", "মাহফুজা খাতুন"), ("Jashim Uddin", "জসিম উদ্দিন"), ("Nasima Begum", "নাসিমা বেগম"), ("Rafiqul Alam", "রফিকুল আলম"),
         ("Dilruba Yasmin", "দিলরুবা ইয়াসমিন"), ("Sohel Rana", "সোহেল রানা"), ("Mitu Rahman", "মিতু রহমান"), ("Faruk Ahmed", "ফারুক আহমেদ"), ("Lipi Akter", "লিপি আক্তার"),
         ("Alamgir Kabir", "আলমগীর কবির"), ("Rehana Parvin", "রেহানা পারভীন"), ("Tarek Aziz", "তারেক আজিজ"), ("Sharmin Nahar", "শারমিন নাহার"), ("Mostafa Kamal", "মোস্তফা কামাল"),
         ("Joynab Bibi", "জয়নব বিবি"), ("Zahid Hasan", "জাহিদ হাসান"), ("Parul Akter", "পারুল আক্তার"), ("Belal Hossain", "বেলাল হোসেন"), ("Suraiya Begum", "সুরাইয়া বেগম"),
         ("Imtiaz Ahmed", "ইমতিয়াজ আহমেদ"), ("Ferdousi Islam", "ফেরদৌসী ইসলাম"), ("Golam Kibria", "গোলাম কিবরিয়া"), ("Hosne Ara", "হোসনে আরা"), ("Saiful Islam", "সাইফুল ইসলাম"),
         ("Nazma Khanam", "নাজমা খানম"), ("Masud Rana", "মাসুদ রানা"), ("Jesmin Akter", "জেসমিন আক্তার"), ("Tofazzal Hossain", "তোফাজ্জল হোসেন"), ("Kohinur Begum", "কোহিনূর বেগম")]


def seed_units(db, ctx):
    from datetime import date, timedelta
    from random import Random
    from .models.property import Occupancy, Unit
    rnd = Random(11)
    areas = [1100, 1250, 1380, 1450, 1600, 1650]

    def build(prop, floors, blocks, per_block, density):
        units = []
        for f in range(1, floors + 1):
            for b in blocks:
                for n in range(1, per_block + 1):
                    u = Unit(property_id=prop.id, block=b, floor=f, number=f"{b}-{f}{n:02d}", area_sqft=rnd.choice(areas), bedrooms=3 if rnd.random() > .2 else 2)
                    db.add(u)
                    units.append(u)
        db.flush()
        for i, u in enumerate(units):
            en, bn = NAMES[(i * 7 + prop.id) % len(NAMES)]
            phone = f"0171{rnd.randint(1000000, 9999999)}"
            start = date(2021, 1, 1) + timedelta(days=rnd.randint(0, 1400))
            slot = i % 8
            if slot in density["owner"]:
                db.add(Occupancy(unit_id=u.id, kind="owner", name=en, name_bn=bn, phone=phone, resides=True, start_date=start))
                u.status = "occupied"
            elif slot in density["tenant"]:
                db.add(Occupancy(unit_id=u.id, kind="owner", name=en, name_bn=bn, phone=phone, resides=False, start_date=start))
                ten = NAMES[(i * 5 + 3) % len(NAMES)]
                db.add(Occupancy(unit_id=u.id, kind="tenant", name=ten[0], name_bn=ten[1], phone=f"0181{rnd.randint(1000000, 9999999)}", start_date=date(2025, 1, 1) + timedelta(days=rnd.randint(0, 600))))
                u.status = "occupied"
            else:
                db.add(Occupancy(unit_id=u.id, kind="owner", name=en, name_bn=bn, phone=phone, resides=False, start_date=start))
                u.status = "vacant"
        db.flush()
        return units

    sun = build(ctx["sunrise"], 8, ["A", "B"], 2, {"owner": {0, 1, 2, 3, 4}, "tenant": {5, 6}})
    build(ctx["lake"], 10, ["A", "B"], 2, {"owner": {0, 1, 2, 3}, "tenant": {4, 5, 6}})
    build(ctx["green"], 6, ["A", "B"], 2, {"owner": {0, 1, 2}, "tenant": {3, 4, 5}})
    by = {u.number: u for u in sun}

    def person(email):
        return db.scalar(select(User).where(User.email == f"{email}@flatwise.demo"))

    def set_owner(unit, user, resides):
        for o in db.scalars(select(Occupancy).where(Occupancy.unit_id == unit.id, Occupancy.kind == "owner")):
            db.delete(o)
        db.add(Occupancy(unit_id=unit.id, kind="owner", user_id=user.id, name=user.name, name_bn=user.name_bn, phone=user.phone, email=user.email, resides=resides, start_date=date(2020, 3, 1)))

    # demo people who can sign in, each tied to a unit
    mahmud, rokeya, tasnim, rep = person("owner"), person("owner2"), person("tenant"), person("ownerrep")
    a501, b302, a801 = by["A-501"], by["B-302"], by["A-801"]
    set_owner(a501, mahmud, True); a501.status = "occupied"
    for o in db.scalars(select(Occupancy).where(Occupancy.unit_id == a501.id, Occupancy.kind == "tenant")):
        db.delete(o)
    set_owner(by["B-302"], rokeya, False)
    for o in db.scalars(select(Occupancy).where(Occupancy.unit_id == b302.id, Occupancy.kind == "tenant")):
        db.delete(o)
    db.add(Occupancy(unit_id=b302.id, kind="tenant", user_id=tasnim.id, name=tasnim.name, name_bn=tasnim.name_bn, phone=tasnim.phone, email=tasnim.email, start_date=date(2025, 7, 1)))
    b302.status = "occupied"
    for o in db.scalars(select(Occupancy).where(Occupancy.unit_id == a801.id, Occupancy.kind == "tenant")):
        db.delete(o)
    for o in db.scalars(select(Occupancy).where(Occupancy.unit_id == a801.id, Occupancy.kind == "owner")):
        o.name, o.name_bn, o.resides = "Kabir Chowdhury (abroad)", "কবির চৌধুরী (প্রবাসে)", False
    a801.status = "to_let_pending"
    vacants = [u for u in sun if u.status == "vacant"]
    for u in vacants[:2]:
        u.status = "to_let"
    for m in db.scalars(select(Membership).where(Membership.user_id == mahmud.id)):
        m.unit_id = a501.id
    for m in db.scalars(select(Membership).where(Membership.user_id == rokeya.id)):
        m.unit_id = b302.id
    for m in db.scalars(select(Membership).where(Membership.user_id == tasnim.id)):
        m.unit_id = b302.id
    for m in db.scalars(select(Membership).where(Membership.user_id == rep.id)):
        m.unit_id = a801.id


def seed_billing(db, ctx):
    from datetime import date
    from random import Random
    from .models.billing import ChargeRule, Invoice, InvoiceLine, Message, Payment
    from .models.property import Occupancy, Unit
    rnd = Random(21)
    periods = ["2026-05", "2026-06", "2026-07", "2026-08", "2026-09", "2026-10"]
    methods = ["bkash"] * 9 + ["nagad"] * 3 + ["bank"] * 3 + ["cash"] * 5
    trs = db.scalar(select(User).where(User.email == "treasurer@flatwise.demo"))
    for key in ("sunrise", "lake", "green"):
        prop = ctx[key]
        rules = [(ChargeRule(property_id=prop.id, name="Service charge", name_bn="সার্ভিস চার্জ", kind="per_sqft", amount=200), "sq"),
                 (ChargeRule(property_id=prop.id, name="Generator", name_bn="জেনারেটর", kind="flat", amount=40000), "f"),
                 (ChargeRule(property_id=prop.id, name="Lift", name_bn="লিফট", kind="flat", amount=30000), "f"),
                 (ChargeRule(property_id=prop.id, name="Water", name_bn="পানি", kind="flat", amount=25000), "f")]
        for r, _ in rules:
            db.add(r)
        db.flush()
        units = db.scalars(select(Unit).where(Unit.property_id == prop.id).order_by(Unit.id)).all()
        chronic = {units[i].id for i in range(3, len(units), 11)}
        n_rc = 0
        for per in periods:
            y, m = int(per[:4]), int(per[5:])
            current = per == periods[-1]
            for u in units:
                total, lines = 0, []
                for r, _ in rules:
                    a = int(round(r.amount * u.area_sqft)) if r.kind == "per_sqft" else r.amount
                    lines.append((r, a)); total += a
                inv = Invoice(property_id=prop.id, unit_id=u.id, period=per, number=f"INV-{prop.id}-{per}-{u.number}", issue_date=date(y, m, 1), due_date=date(y, m, 10), total=total)
                db.add(inv); db.flush()
                for r, a in lines:
                    db.add(InvoiceLine(invoice_id=inv.id, description=r.name, description_bn=r.name_bn, amount=a))
                chance = 0.62 if current else 0.93
                if u.id in chronic and per >= "2026-07":
                    chance = 0
                x = rnd.random()
                if x < chance:
                    amt = total
                elif x < chance + 0.05 and chance > 0:
                    amt = total // 2
                else:
                    continue
                n_rc += 1
                meth = rnd.choice(methods)
                day = min(rnd.randint(2, 22 if current else 14), 24 if current else 28)
                db.add(Payment(property_id=prop.id, invoice_id=inv.id, unit_id=u.id, amount=amt, method=meth,
                               trx_id=f"{'BK' if meth == 'bkash' else 'NG' if meth == 'nagad' else 'TR'}{rnd.randint(10**8, 10**9 - 1)}" if meth != "cash" else "",
                               paid_on=date(y, m, day), status="verified", verified_by=trs.id if trs else None, verified_at=now(), receipt_no=f"RC-{prop.id}-{n_rc:05d}"))
                inv.paid = amt
                inv.status = "paid" if amt >= total else "partial"
        db.flush()
    # pending payments waiting for the treasurer (Sunrise)
    sun = ctx["sunrise"]
    tasnim = db.scalar(select(User).where(User.email == "tenant@flatwise.demo"))
    for number, meth, who in (("B-302", "bkash", tasnim.id if tasnim else None), ("A-203", "nagad", None), ("B-105", "bkash", None)):
        u = db.scalar(select(Unit).where(Unit.property_id == sun.id, Unit.number == number))
        if not u:
            continue
        inv = db.scalar(select(Invoice).where(Invoice.unit_id == u.id, Invoice.period == "2026-10"))
        if not inv:
            continue
        for old in db.scalars(select(Payment).where(Payment.invoice_id == inv.id)):
            db.delete(old)
        inv.paid, inv.status = 0, "open"
        db.flush()
        db.add(Payment(property_id=sun.id, invoice_id=inv.id, unit_id=u.id, amount=inv.total - inv.paid, method=meth, trx_id=f"{'BK' if meth == 'bkash' else 'NG'}{rnd.randint(10**8, 10**9 - 1)}",
                       paid_on=date(2026, 10, 23), status="pending", submitted_by=who))
    # a few reminders already sent, in Bangla
    od = db.scalars(select(Invoice).where(Invoice.property_id == sun.id, Invoice.period == "2026-09", Invoice.status != "paid").limit(6)).all()
    for inv in od:
        o = db.scalar(select(Occupancy).where(Occupancy.unit_id == inv.unit_id, Occupancy.active).order_by(Occupancy.kind.desc()))
        if not o:
            continue
        db.add(Message(property_id=sun.id, unit_id=inv.unit_id, to_name=o.name_bn or o.name, to_phone=o.phone, template="due_o7", lang="bn",
                       body=f"সানরাইজ টাওয়ার: {inv.period} মাসের সার্ভিস চার্জ BDT {inv.total // 100:,} বকেয়া। অনুগ্রহ করে পরিশোধ করুন।",
                       status="sent", idem_key=f"seed-{inv.id}-o7", sent_at=now()))
    db.flush()


def seed_cash(db, ctx):
    from datetime import timedelta
    from .models.billing import Invoice, Payment
    from .models.cash import CashEntry, Remittance
    from .models.property import Unit
    sun = ctx["sunrise"]
    ct = db.scalar(select(User).where(User.email == "caretaker@flatwise.demo"))
    trs = db.scalar(select(User).where(User.email == "treasurer@flatwise.demo"))
    cash = db.scalars(select(Payment).join(Invoice, Invoice.id == Payment.invoice_id).where(Payment.property_id == sun.id, Payment.method == "cash", Payment.status == "verified").order_by(Payment.paid_on.desc())).all()
    if not ct or len(cash) < 12:
        return
    older, recent = cash[6:12], cash[:4]
    rem = Remittance(property_id=sun.id, collector_id=ct.id, amount=sum(p.amount for p in older), status="accepted", decided_by=trs.id if trs else None, decided_at=now() - timedelta(days=9))
    db.add(rem); db.flush()
    for p in older:
        db.add(CashEntry(property_id=sun.id, invoice_id=p.invoice_id, unit_id=p.unit_id, amount=p.amount, collector_id=ct.id, mode="otp", status="remitted", payment_id=p.id, remittance_id=rem.id, confirmed_at=now() - timedelta(days=12)))
    sub = Remittance(property_id=sun.id, collector_id=ct.id, amount=sum(p.amount for p in recent[2:]), status="submitted")
    db.add(sub); db.flush()
    for k, p in enumerate(recent):
        db.add(CashEntry(property_id=sun.id, invoice_id=p.invoice_id, unit_id=p.unit_id, amount=p.amount, collector_id=ct.id, mode="otp", status="held" if k < 2 else "handover", payment_id=p.id,
                         remittance_id=None if k < 2 else sub.id, confirmed_at=now() - timedelta(days=2)))
    # one open entry waiting for the payer, and one waiting for the treasurer
    b302 = db.scalar(select(Unit).where(Unit.property_id == sun.id, Unit.number == "B-302"))
    inv = db.scalar(select(Invoice).where(Invoice.unit_id == b302.id, Invoice.period == "2026-10")) if b302 else None
    if inv:
        db.add(CashEntry(property_id=sun.id, invoice_id=inv.id, unit_id=inv.unit_id, amount=100000, collector_id=ct.id, mode="otp", status="pending", code_hash="x", code_expires=now() + timedelta(minutes=4)))
    db.flush()


def seed_finance(db, ctx):
    from datetime import date
    from random import Random
    from .models.billing import Payment
    from .models.finance import Asset, Budget, Expense, Vendor
    from .services import ledger
    rnd = Random(31)
    P = 100
    for key in ("sunrise", "lake", "green"):
        prop = ctx[key]
        ledger.post(db, prop.id, date(2026, 4, 30), "Opening bank balance", [("1020", 400000 * P, 0), ("3010", 0, 400000 * P)], "opening", prop.id)
        for p in db.scalars(select(Payment).where(Payment.property_id == prop.id, Payment.status == "verified").order_by(Payment.id)):
            ledger.post(db, prop.id, p.paid_on, f"Service charge receipt {p.receipt_no}", [(ledger.METHOD_ACCOUNT[p.method], p.amount, 0), ("4010", 0, p.amount)], "payment", p.id)
    sun = ctx["sunrise"]
    tr = db.scalar(select(User).where(User.email == "treasurer@flatwise.demo"))
    pres = db.scalar(select(User).where(User.email == "president@flatwise.demo"))
    sec = db.scalar(select(User).where(User.email == "secretary@flatwise.demo"))
    pa = db.scalar(select(User).where(User.email == "padmin@flatwise.demo"))
    vend = {}
    for key, en, bn, cat in (("desco", "DESCO (electricity)", "ডেসকো (বিদ্যুৎ)", "utilities"), ("wasa", "Dhaka WASA", "ঢাকা ওয়াসা", "utilities"), ("fuel", "Jamuna Fuel Station", "যমুনা ফিউয়েল স্টেশন", "fuel"),
                              ("lift", "Metro Lift Service", "মেট্রো লিফট সার্ভিস", "repairs"), ("guard", "SafeGuard Security", "সেফগার্ড সিকিউরিটি", "services"), ("elec", "Rahman Electric Works", "রহমান ইলেকট্রিক", "repairs")):
        v = Vendor(property_id=sun.id, name=en, name_bn=bn, category=cat, phone=f"01{rnd.randint(300000000, 999999999)}")
        db.add(v); db.flush(); vend[key] = v
    months = [(2026, m) for m in range(5, 11)]
    methods = ["bank", "bkash", "cash", "bank"]

    def expense(cat, title, amount, on, vendor, status="paid", approvers=(), requester=None, method="bank"):
        e = Expense(property_id=sun.id, category=cat, vendor_id=vendor.id if vendor else None, title=title, amount=amount * P, spent_on=on, status=status, needs_two=amount * P > 5_000_000,
                    requested_by=(requester or tr).id, approvals=[{"user_id": u.id, "name": u.name, "at": on.isoformat()} for u in approvers])
        if status == "paid":
            e.method, e.paid_on = method, on
        db.add(e); db.flush()
        if status == "paid":
            ledger.post(db, sun.id, on, title, [(ledger.CATEGORY_ACCOUNT[cat], e.amount, 0), (ledger.METHOD_ACCOUNT[method], 0, e.amount)], "expense", e.id)
        return e
    for y, m in months:
        mn = date(y, m, 1).strftime("%B")
        expense("utilities", f"Electricity, common areas ({mn})", rnd.randint(16000, 21000), date(y, m, 14), vend["desco"], approvers=[pres], method="bank")
        expense("utilities", f"Water bill ({mn})", rnd.randint(5500, 7500), date(y, m, 16), vend["wasa"], approvers=[pres], method="bank")
        expense("fuel", f"Generator diesel ({mn})", rnd.randint(9000, 15000), date(y, m, rnd.randint(5, 25)), vend["fuel"], approvers=[pres], method=rnd.choice(["cash", "bkash"]))
        if m <= 8:   # from September salaries run through the payroll module
            expense("salary", f"Caretaker, guard and cleaner salary ({mn})", 38000, date(y, m, 28), None, approvers=[pres], method="bank")
        expense("services", f"Security service ({mn})", 14000, date(y, m, 5), vend["guard"], approvers=[pres], method="bank")
        if m in (6, 8, 9):
            expense("repairs", rnd.choice(["Corridor light replacement", "Pump motor repair", "Gate repair", "Intercom fix"]), rnd.randint(3500, 18000), date(y, m, rnd.randint(8, 22)), vend["elec"], approvers=[pa], method=rnd.choice(methods))
    # waiting for decisions, to show the approval flow
    expense("repairs", "Lift motor overhaul (Block A)", 120000, date(2026, 10, 20), vend["lift"], status="pending", approvers=[pres], requester=tr)
    expense("repairs", "Roof waterproofing, tower top", 85000, date(2026, 10, 18), vend["elec"], status="pending", requester=sec)
    expense("utilities", "Electricity, common areas (October)", 19400, date(2026, 10, 14), vend["desco"], status="approved", approvers=[pres])
    expense("services", "Pest control, all floors", 6500, date(2026, 10, 22), None, status="pending", requester=tr)
    # yearly budget
    for cat, amt in {"utilities": 330000, "repairs": 220000, "salary": 480000, "fuel": 170000, "services": 190000, "other": 50000}.items():
        db.add(Budget(property_id=sun.id, year=2026, category=cat, amount=amt * P))
    # fixed assets
    for name, bn, cat, cost, on, life in (("Diesel generator 125 kVA", "ডিজেল জেনারেটর ১২৫ কেভিএ", "equipment", 850000, date(2022, 3, 12), 10), ("Passenger lifts (2)", "যাত্রী লিফট (২টি)", "building", 2400000, date(2020, 8, 1), 20),
                                          ("CCTV system, 16 cameras", "সিসিটিভি সিস্টেম, ১৬ ক্যামেরা", "equipment", 180000, date(2024, 2, 20), 6), ("Water pump set", "পানির পাম্প সেট", "equipment", 65000, date(2023, 5, 9), 8),
                                          ("Office furniture", "অফিস আসবাব", "furniture", 38000, date(2025, 1, 15), 8)):
        a = Asset(property_id=sun.id, name=name, name_bn=bn, category=cat, cost=cost * P, bought_on=on, life_years=life, capitalised=True)
        db.add(a); db.flush()
        # bought before the books start: carried in with the opening balance, not paid from today's bank
        ledger.post(db, sun.id, on, f"Bought {name}", [("1500", a.cost, 0), ("3010", 0, a.cost)], "asset", a.id)
    ch = Asset(property_id=sun.id, name="Office chair", name_bn="অফিস চেয়ার", category="furniture", cost=8000 * P, bought_on=date(2026, 7, 3), life_years=5, capitalised=False, note="Below the BDT 20,000 asset line, booked as an expense")
    db.add(ch); db.flush()
    ledger.post(db, sun.id, ch.bought_on, "Bought Office chair (below asset threshold)", [("5020", ch.cost, 0), ("1010", 0, ch.cost)], "asset", ch.id)
    db.flush()


def seed_payroll(db, ctx):
    from datetime import date
    from .models.staff import SalaryLine, SalarySheet, Staff
    from .services import ledger, vault
    sun = ctx["sunrise"]
    tr = db.scalar(select(User).where(User.email == "treasurer@flatwise.demo"))
    pres = db.scalar(select(User).where(User.email == "president@flatwise.demo"))
    P = 100
    people = [("Rahim Mia", "রহিম মিয়া", "caretaker", "01711000111", 14000, date(2021, 2, 1), "1985123456789"), ("Karim Uddin", "করিম উদ্দিন", "guard", "01711000222", 9000, date(2022, 6, 15), "1990654321098"),
              ("Jabbar Ali", "জব্বার আলী", "guard", "01711000333", 9000, date(2023, 1, 10), "1988112233445"), ("Shefali Begum", "শেফালী বেগম", "cleaner", "01711000444", 6000, date(2024, 4, 1), "1993778899001")]
    st = []
    for n, bn, role, ph, sal, j, nid in people:
        s = Staff(property_id=sun.id, name=n, name_bn=bn, role=role, phone=ph, joined=j, salary=sal * P, nid_enc=vault.seal(nid), nid_last4=nid[-4:])
        db.add(s); st.append(s)
    db.flush()
    sep = SalarySheet(property_id=sun.id, period="2026-09", status="paid", created_by=tr.id, approved_by=pres.id, paid_on=date(2026, 9, 28), method="bank")
    db.add(sep); db.flush()
    for s in st:
        db.add(SalaryLine(sheet_id=sep.id, staff_id=s.id, base=s.salary))
    ledger.post(db, sun.id, sep.paid_on, "Salaries 2026-09", [("5030", sum(s.salary for s in st), 0), ("1020", 0, sum(s.salary for s in st))], "payroll", sep.id)
    octo = SalarySheet(property_id=sun.id, period="2026-10", status="draft", created_by=tr.id)
    db.add(octo); db.flush()
    for s in st:
        db.add(SalaryLine(sheet_id=octo.id, staff_id=s.id, base=s.salary))
    db.flush()


def seed_notices(db, ctx):
    import secrets
    from datetime import datetime, timedelta, timezone
    from random import Random
    from .models.notice import Notice, Policy, PolicyAcceptance, PolicyVersion, Receipt
    from .models.property import Occupancy, Unit
    rnd = Random(41)
    sun = ctx["sunrise"]
    sec = db.scalar(select(User).where(User.email == "secretary@flatwise.demo"))
    pres = db.scalar(select(User).where(User.email == "president@flatwise.demo"))
    pa = db.scalar(select(User).where(User.email == "padmin@flatwise.demo"))
    units = {u.id: u.number for u in db.scalars(select(Unit).where(Unit.property_id == sun.id))}
    people = {"owners": [], "tenants": []}
    for o in db.scalars(select(Occupancy).where(Occupancy.unit_id.in_(list(units)), Occupancy.active)):
        people["owners" if o.kind == "owner" else "tenants"].append((o.name, units[o.unit_id], o.phone, o.user_id))
    committee = [(u.name, "", u.phone, u.id) for u in db.scalars(select(User).where(User.email.in_([f"{k}@flatwise.demo" for k in ("president", "secretary", "treasurer", "member")])))]
    items = [
        ("Water supply off tomorrow, 9 am to 1 pm", "আগামীকাল সকাল ৯টা থেকে দুপুর ১টা পানি বন্ধ থাকবে", "The overhead tank will be cleaned. Please store water tonight. Supply returns by 1 pm.", "ওভারহেড ট্যাংক পরিষ্কার করা হবে। অনুগ্রহ করে আজ রাতে পানি জমিয়ে রাখুন। দুপুর ১টার মধ্যে সরবরাহ ফিরবে।", "all", "urgent", True, 1, 0.82),
        ("Annual general meeting, Friday 7 Nov, 5 pm", "বার্ষিক সাধারণ সভা, শুক্রবার ৭ নভেম্বর, বিকাল ৫টা", "All flat owners are invited to the AGM in the ground floor hall. Agenda: yearly accounts, budget 2027, lift replacement.", "সকল ফ্ল্যাট মালিককে নিচতলার হলরুমে বার্ষিক সাধারণ সভায় আমন্ত্রণ। আলোচ্যসূচি: বার্ষিক হিসাব, ২০২৭ বাজেট, লিফট প্রতিস্থাপন।", "owners", "normal", True, 3, 0.64),
        ("Lift maintenance, Block A, Saturday", "শনিবার ব্লক এ লিফটের রক্ষণাবেক্ষণ", "Block A lifts will be off from 10 am to 2 pm. Please use Block B lifts.", "ব্লক এ লিফট সকাল ১০টা থেকে দুপুর ২টা বন্ধ থাকবে। অনুগ্রহ করে ব্লক বি লিফট ব্যবহার করুন।", "all", "normal", False, 5, 0.9),
        ("Reminder for tenants: guest and parking rules", "ভাড়াটিয়াদের জন্য স্মরণ: অতিথি ও পার্কিং নিয়ম", "Guests must be registered with the guard. Please park only in your flat's marked space.", "অতিথিদের গার্ডের কাছে নিবন্ধন করতে হবে। শুধু আপনার ফ্ল্যাটের নির্দিষ্ট জায়গায় গাড়ি রাখুন।", "tenants", "normal", False, 8, 0.55),
        ("Committee meeting notes, October", "কমিটি সভার কার্যবিবরণী, অক্টোবর", "Approved: lift motor overhaul quotation review, generator service schedule, security vendor renewal.", "অনুমোদিত: লিফট মোটর ওভারহলের কোটেশন পর্যালোচনা, জেনারেটর সার্ভিসের সময়সূচি, নিরাপত্তা সংস্থার নবায়ন।", "committee", "normal", False, 12, 1.0),
    ]
    for title, tbn, body, bbn, aud, pri, pin, days, rate in items:
        n = Notice(property_id=sun.id, title=title, title_bn=tbn, body=body, body_bn=bbn, audience=aud, priority=pri, pinned=pin, created_by=(sec if aud != "committee" else pres).id, created_at=datetime.now(timezone.utc) - timedelta(days=days))
        db.add(n); db.flush()
        rec = {"all": people["owners"] + people["tenants"] + committee, "owners": people["owners"], "tenants": people["tenants"], "committee": committee}[aud]
        seen = set()
        for name, unit, phone, uid in rec:
            if uid and uid in seen:
                continue
            seen.add(uid)
            r = Receipt(notice_id=n.id, name=name, unit=unit, phone=phone, user_id=uid, token=secrets.token_urlsafe(12), sms_at=n.created_at if phone and aud != "committee" else None)
            if rnd.random() < rate:
                r.read_at, r.read_via = n.created_at + timedelta(hours=rnd.randint(1, 60)), ("app" if uid and rnd.random() < .5 else "link")
            db.add(r)
        db.flush()
    # leave a few demo residents unread so their inbox shows what is new
    for r in db.scalars(select(Receipt).join(User, User.id == Receipt.user_id).where(User.email.in_(["owner@flatwise.demo", "tenant@flatwise.demo", "owner2@flatwise.demo"]), Receipt.notice_id.in_(select(Notice.id).where(Notice.title.like("Water%"))))):
        r.read_at, r.read_via = None, ""
    # policies
    def policy(title, bn, versions):
        p = Policy(property_id=sun.id, title=title, title_bn=bn)
        db.add(p); db.flush()
        out = []
        for i, (body, bbn, note) in enumerate(versions, 1):
            v = PolicyVersion(policy_id=p.id, version=i, body=body, body_bn=bbn, change_note=note, published_by=pres.id, published_at=datetime.now(timezone.utc) - timedelta(days=200 - i * 90))
            db.add(v); db.flush(); out.append(v)
        return out
    house = policy("House rules", "ভবনের নিয়মাবলী", [
        ("1. Quiet hours are 10 pm to 7 am.\n2. Garbage goes in the bins on each floor landing.\n3. No storage in stairwells.\n4. Pets must be leashed in common areas.", "১. রাত ১০টা থেকে সকাল ৭টা শান্ত থাকার সময়।\n২. প্রতি তলার ল্যান্ডিংয়ের বিনে ময়লা ফেলুন।\n৩. সিঁড়িতে মালপত্র রাখা যাবে না।\n৪. সাধারণ এলাকায় পোষা প্রাণী বেঁধে রাখুন।", "First version"),
        ("1. Quiet hours are 10 pm to 7 am.\n2. Garbage goes in the bins on each floor landing, wet and dry apart.\n3. No storage in stairwells.\n4. Pets must be leashed in common areas.\n5. Renovation work only 9 am to 5 pm, never on Fridays.", "১. রাত ১০টা থেকে সকাল ৭টা শান্ত থাকার সময়।\n২. ময়লা ভেজা ও শুকনো আলাদা করে ল্যান্ডিংয়ের বিনে ফেলুন।\n৩. সিঁড়িতে মালপত্র রাখা যাবে না।\n৪. সাধারণ এলাকায় পোষা প্রাণী বেঁধে রাখুন।\n৫. সংস্কারের কাজ সকাল ৯টা থেকে বিকাল ৫টা, শুক্রবার নয়।", "Added renovation hours and waste sorting")])
    guest = policy("Guest and parking policy", "অতিথি ও পার্কিং নীতি", [("Guests register at the gate. Parking only in the marked space of your flat. Visitor cars may stay up to 4 hours.", "অতিথিরা গেটে নিবন্ধন করবেন। শুধু নিজের ফ্ল্যাটের নির্দিষ্ট জায়গায় গাড়ি রাখুন। অতিথির গাড়ি সর্বোচ্চ ৪ ঘণ্টা থাকতে পারবে।", "First version")])
    accepters = [db.scalar(select(User).where(User.email == f"{k}@flatwise.demo")) for k in ("owner", "owner2", "ownerrep", "president", "secretary", "treasurer", "member")]
    for u in accepters:
        db.add(PolicyAcceptance(version_id=house[0].id, user_id=u.id))
        db.add(PolicyAcceptance(version_id=guest[0].id, user_id=u.id))
    for u in accepters[:4]:
        db.add(PolicyAcceptance(version_id=house[1].id, user_id=u.id))
    tenant = db.scalar(select(User).where(User.email == "tenant@flatwise.demo"))
    db.add(PolicyAcceptance(version_id=house[0].id, user_id=tenant.id))
    db.flush()


def seed_onboarding(db, ctx):
    import secrets
    from datetime import date, datetime, timedelta, timezone
    from . import config
    from .models.onboarding import TenantCase, TenantDoc
    from .models.property import Occupancy, Unit
    from .services import vault
    sun = ctx["sunrise"]
    png = bytes.fromhex("89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4890000000d49444154789c6360000002000001e221bc330000000049454e44ae426082")
    units = {u.number: u for u in db.scalars(select(Unit).where(Unit.property_id == sun.id))}
    to_let = [u for u in units.values() if u.status == "to_let"]
    vacant = [u for u in units.values() if u.status == "vacant"]
    rented = [o for o in db.scalars(select(Occupancy).where(Occupancy.kind == "tenant", Occupancy.active, Occupancy.unit_id.in_([u.id for u in units.values()]))) if o.user_id is None]
    ago = lambda d: datetime.now(timezone.utc) - timedelta(days=d)
    DET = {"father_name": "Abdul Mannan", "mother_name": "Rahela Khatun", "permanent_address": "Village Charmajlishpur, Upazila Sadar, Noakhali", "previous_address": "House 12, Road 3, Mirpur 10, Dhaka", "profession": "Software engineer", "employer": "Brightpath Technologies Ltd",
           "family": [{"name": "Sharmin Akter", "relation": "Wife", "age": "29"}, {"name": "Rayan", "relation": "Son", "age": "4"}], "emergency_name": "Abdul Mannan", "emergency_phone": "01711223344", "reference_name": "Kamrul Hasan", "reference_phone": "01819887766"}

    def mk(unit, name, phone, status, rent, start, details=True, docs=("nid_front", "nid_back", "photo"), doc_status="accepted", nid="1992456789012", ref="", on=None, receipt="", occ=None, ev=()):
        c = TenantCase(property_id=sun.id, unit_id=unit.id, token=secrets.token_urlsafe(14), status=status, name=name, phone=phone, rent=rent * 100, advance=rent * 200, start_date=start, lease_months=12,
                       details=DET if details else {}, nid_enc=vault.seal(nid) if nid else "", nid_last4=nid[-4:] if nid else "", police_ref=ref, police_on=on, receipt_no=receipt, occupancy_id=occ,
                       created_by=1, submitted_at=ago(6) if status != "invited" else None, events=[{"at": ago(d).isoformat(), "by": by, "key": k, "note": n} for d, by, k, n in ev])
        db.add(c); db.flush()
        for k in docs:
            stored = f"{secrets.token_hex(8)}.png"
            folder = config.UPLOAD_DIR / str(c.id); folder.mkdir(parents=True, exist_ok=True); (folder / stored).write_bytes(png)
            db.add(TenantDoc(case_id=c.id, kind=k, filename=f"{k}.png", stored=stored, content_type="image/png", size=len(png), status=doc_status))
        return c
    b302 = units["B-302"]
    occ302 = db.scalar(select(Occupancy).where(Occupancy.unit_id == b302.id, Occupancy.kind == "tenant", Occupancy.active))
    mk(b302, "Tasnim Ferdous", "01811000003", "done", 30000, date(2025, 7, 1), ref="DMP/TEN/2025/04412", on=date(2025, 7, 9), receipt="DMP-RCPT-88231", occ=occ302.id if occ302 else None,
       ev=[(470, "Abdul Karim", "invited", ""), (466, "Tasnim Ferdous", "submitted", ""), (462, "Abdul Karim", "verified", ""), (460, "Abdul Karim", "police", "DMP/TEN/2025/04412"), (455, "Abdul Karim", "done", "DMP-RCPT-88231")])
    if len(to_let) >= 1:
        mk(to_let[0], "Mizanur Rahman", "01912345678", "review", 28000, date(2026, 11, 5), doc_status="pending", ev=[(8, "Mahmud Hasan", "invited", ""), (6, "Mizanur Rahman", "submitted", "")])
    if len(to_let) >= 2:
        mk(to_let[1], "Nusrat Jahan", "01712121212", "invited", 26000, date(2026, 11, 15), details=False, docs=(), nid="", ev=[(2, "Abdul Karim", "invited", "")])
    if vacant:
        u = vacant[0]; u.status = "occupied"
        occ = Occupancy(unit_id=u.id, kind="tenant", name="Rubel Ahmed", name_bn="রুবেল আহমেদ", phone="01555000111", start_date=date(2026, 10, 12)); db.add(occ); db.flush()
        mk(u, "Rubel Ahmed", "01555000111", "verified", 24000, date(2026, 10, 12), occ=occ.id, ev=[(14, "Abdul Karim", "invited", ""), (12, "Rubel Ahmed", "submitted", ""), (10, "Abdul Karim", "verified", "")])
    for o in rented[:1]:
        u = db.get(Unit, o.unit_id)
        mk(u, o.name, o.phone or "01700000000", "police", 27000, o.start_date, ref="DMP/TEN/2026/10977", on=date(2026, 10, 20), occ=o.id, ev=[(30, "Abdul Karim", "invited", ""), (24, o.name, "submitted", ""), (20, "Abdul Karim", "verified", ""), (4, "Abdul Karim", "police", "DMP/TEN/2026/10977")])
    db.flush()


def seed_budget_months(db, ctx):
    """2026 month-by-month budget for Sunrise. Seasonal: electricity and generator fuel peak in the hot months."""
    from .models.budget import BudgetMonth
    P = 100
    # (Jan..Dec) in thousand taka
    plan = {
        "utilities": [22, 22, 24, 28, 32, 34, 34, 34, 32, 28, 23, 22],
        "fuel": [8, 8, 10, 13, 16, 17, 17, 17, 15, 12, 9, 8],
        "salary": [40] * 12, "services": [14] * 12,
        "repairs": [14, 14, 16, 18, 20, 22, 20, 20, 20, 18, 16, 14],
        "other": [4, 4, 4, 4, 4, 5, 4, 4, 4, 4, 5, 4],
    }
    for cat, vals in plan.items():
        for m, v in enumerate(vals, 1):
            db.add(BudgetMonth(property_id=ctx["sunrise"].id, year=2026, month=m, category=cat, amount=v * 1000 * P))
    db.flush()


def _placeholder_png(seed: int, size: int = 96) -> bytes:
    """A small valid PNG: coloured square with a lighter head-and-shoulders silhouette. No imaging library needed."""
    import colorsys, struct, zlib
    r, g, b = [int(c * 255) for c in colorsys.hsv_to_rgb((seed * 0.137) % 1, 0.45, 0.78)]
    lr, lg, lb = min(255, r + 70), min(255, g + 70), min(255, b + 70)
    rows = bytearray()
    for y in range(size):
        rows.append(0)
        for x in range(size):
            head = (x - size / 2) ** 2 + (y - size * 0.38) ** 2 <= (size * 0.19) ** 2
            body = y > size * 0.66 and (x - size / 2) ** 2 / (size * 0.36) ** 2 + (y - size * 0.98) ** 2 / (size * 0.34) ** 2 <= 1
            rows += bytes((lr, lg, lb) if head or body else (r, g, b))
    def chunk(tag, data):
        c = struct.pack(">I", len(data)) + tag + data
        return c + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", size, size, 8, 2, 0, 0, 0)) + chunk(b"IDAT", zlib.compress(bytes(rows))) + chunk(b"IEND", b"")


def seed_profiles(db, ctx):
    """Placeholder photos and a few optional details for about ten people (owners, committee, tenant, 4 staff)."""
    from datetime import date as _d
    from . import config
    from .models.profile import Profile
    from .models.property import Occupancy
    from .models.staff import Staff
    folder = config.UPLOAD_DIR / "avatars"
    folder.mkdir(parents=True, exist_ok=True)
    n = 0

    def put(kind, rid, **d):
        nonlocal n
        n += 1
        name = f"{kind}_{rid}_seed{n}.png"
        (folder / name).write_bytes(_placeholder_png(n * 3 + rid))
        db.add(Profile(kind=kind, ref_id=rid, photo_file=name, photo_type="image/png", photo_ver=1, languages=d.pop("languages", ["Bangla", "English"]), **d))
    info = {
        "president": dict(about="Retired physician. Chairs the committee.", dob=_d(1960, 3, 14), blood_group="B+", profession="Physician", emergency_name="Nasrin Uddin", emergency_phone="01711555001", address="A-801, Sunrise Tower, Dhanmondi"),
        "secretary": dict(about="Keeps the minutes and the notices.", dob=_d(1975, 9, 2), blood_group="O+", profession="Bank officer", emergency_name="Hasan Akter", emergency_phone="01711555002"),
        "treasurer": dict(about="Looks after collections and payroll.", dob=_d(1968, 1, 20), blood_group="A+", profession="Accountant"),
        "owner": dict(about="Flat owner and committee member.", dob=_d(1982, 6, 8), blood_group="AB+", profession="Engineer", emergency_name="Mina Hasan", emergency_phone="01711555003", languages=["Bangla", "English", "Hindi"]),
        "owner2": dict(blood_group="O-", profession="Teacher"),
    }
    for email, d in info.items():
        u = db.scalar(select(User).where(User.email == f"{email}@flatwise.demo"))
        if u:
            put("user", u.id, **d)
    t = db.scalar(select(User).where(User.email == "tenant@flatwise.demo"))
    occ = db.scalar(select(Occupancy).where(Occupancy.user_id == t.id)) if t else None
    if occ:
        put("occupant", occ.id, about="Tenant of B-302.", profession="Software developer", blood_group="A-", emergency_name="Ferdous Alam", emergency_phone="01711555004")
    for s in db.scalars(select(Staff).order_by(Staff.id).limit(4)):
        put("staff", s.id, blood_group=["O+", "B+", "A+", "AB+"][s.id % 4], address="Dhaka", emergency_name="Family member", emergency_phone="01700555000", languages=["Bangla"])
    db.flush()


def _seed_gateway(db, ctx):
    from .services.gateway import seed_gateway
    seed_gateway(db, ctx)


def seed_rental(db, ctx):
    """M14: B-302 (owner Rokeya, tenant Tasnim) has Rental records ON; A-501 has it OFF (it has no tenant)."""
    from datetime import date, datetime, timedelta, timezone
    from . import config
    from .models.property import Unit
    from .models.rental import RentalAgreement, RentalComment, RentalFollowup, RentalIssue, RentalNote, RentalPayment, RentalSetting
    sun = ctx["sunrise"]
    units = {u.number: u for u in db.scalars(select(Unit).where(Unit.property_id == sun.id))}
    owner = db.scalar(select(User).where(User.email == "owner2@flatwise.demo"))
    tenant = db.scalar(select(User).where(User.email == "tenant@flatwise.demo"))
    b302, a501 = units["B-302"], units["A-501"]
    db.add(RentalSetting(unit_id=a501.id, property_id=sun.id, enabled=False))
    st = RentalSetting(unit_id=b302.id, property_id=sun.id, enabled=True, receipt_seq=0, updated_by=owner.id)
    db.add(st)
    today = date.today()
    shift = lambda k: date(today.year + (today.month - 1 + k) // 12, (today.month - 1 + k) % 12 + 1, 1)
    ago = lambda d: datetime.now(timezone.utc) - timedelta(days=d)
    pdf = b"%PDF-1.4\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n3 0 obj<</Type/Page/Parent 2 0 R/MediaBox[0 0 200 200]>>endobj\ntrailer<</Root 1 0 R>>\n%%EOF\n"
    png = bytes.fromhex("89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4890000000d49444154789c6360000002000001e221bc330000000049454e44ae426082")
    folder = config.UPLOAD_DIR / "rental" / str(b302.id)
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "seedagreement.pdf").write_bytes(pdf)
    (folder / "seedtap.png").write_bytes(png)
    db.add(RentalAgreement(unit_id=b302.id, title="Rental agreement, B-302", start_date=shift(-6), end_date=today + timedelta(days=40), rent=30000 * 100, advance=60000 * 100,
                           filename="rental-agreement-b302.pdf", stored="seedagreement.pdf", content_type="application/pdf", size=len(pdf), created_by=owner.id))
    seq = 0
    for k in range(-6, 0):
        if k == -3:
            continue                      # the overdue month
        d = shift(k)
        bank = k % 2 == 0
        pay = RentalPayment(unit_id=b302.id, period=d.strftime("%Y-%m"), amount=30000 * 100, method="bank" if bank else "cash", paid_on=d.replace(day=5 + (k % 3)),
                            bank_ref=f"DBBL-TRX-{880000 + k * 7}" if bank else "", note="Paid in full", status="confirmed", source="owner", created_by=owner.id, decided_at=ago(-k * 30))
        if k <= -4:                       # the oldest months already have a money receipt
            seq += 1
            pay.receipt_seq, pay.receipt_no = seq, f"MR-B-302-{seq:04d}"
        db.add(pay)
    st.receipt_seq = seq
    db.add(RentalNote(unit_id=b302.id, kind="reminder", period=shift(-3).strftime("%Y-%m"), body="SMS rent reminder sent", sms_status="sent", created_by=owner.id, created_at=ago(60)))
    i1 = RentalIssue(unit_id=b302.id, title="Kitchen tap is leaking", body="The mixer tap under the sink drips all night.", status="in_progress", cost=250000, cost_note="Plumber, new cartridge",
                     raised_by=tenant.id, raised_side="tenant", created_at=ago(9), updated_at=ago(2))
    i2 = RentalIssue(unit_id=b302.id, title="Bedroom light flickers", body="Tube light flickers when the fan is on.", status="open", photo_name="light.png", photo_stored="seedtap.png", photo_type="image/png",
                     raised_by=tenant.id, raised_side="tenant", created_at=ago(3), updated_at=ago(3))
    db.add_all([i1, i2])
    db.flush()
    db.add_all([RentalComment(issue_id=i1.id, user_id=owner.id, side="owner", body="I have asked a plumber to come on Saturday.", created_at=ago(7)),
                RentalComment(issue_id=i1.id, user_id=tenant.id, side="tenant", body="Thank you. I will be home after 10 am.", created_at=ago(6))])
    db.add_all([RentalFollowup(unit_id=b302.id, text=f"Ask about the {shift(-3).strftime('%Y-%m')} rent", due_date=today + timedelta(days=2), ref_kind="rent", ref=shift(-3).strftime("%Y-%m"), created_by=owner.id),
                RentalFollowup(unit_id=b302.id, text="Check the tap after the plumber's visit", due_date=today + timedelta(days=5), ref_kind="issue", ref=str(i1.id), created_by=owner.id)])
    db.flush()


EXTRA_SEEDS: list = [seed_plans, seed_saas_demo, seed_units, seed_billing, _seed_gateway, seed_cash, seed_finance, seed_payroll, seed_notices, seed_onboarding, seed_budget_months, seed_profiles, seed_rental]

from .seed_requests import seed_requests  # noqa: E402
EXTRA_SEEDS.append(seed_requests)
from .seed_amenities import seed_amenities  # noqa: E402
EXTRA_SEEDS.append(seed_amenities)

if __name__ == "__main__":
    run()
