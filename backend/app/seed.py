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
             features=["billing", "expenses", "notices", "resident_web", "reports", "staff", "assets", "tenant_dmp", "reminders", "caretaker_app", "cash_confirm", "policies"]),
        Plan(key="pro", name="Pro", name_bn="প্রো", sort=3,
             monthly={"S": 5000 * P, "M": 7500 * P, "L": 11000 * P}, setup={"S": 3000 * P, "M": 5000 * P, "L": 8000 * P},
             sms_included={"S": 200, "M": 500, "L": 1000},
             features=["billing", "expenses", "notices", "resident_web", "reports", "staff", "assets", "tenant_dmp", "reminders", "caretaker_app", "cash_confirm", "policies",
                       "resident_portal", "visitor", "amenities", "parking", "maintenance", "cash_otp", "priority_support"]),
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


EXTRA_SEEDS: list = [seed_plans, seed_saas_demo, seed_units, seed_billing]  # later modules append their seed functions here

if __name__ == "__main__":
    run()
