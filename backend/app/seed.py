"""Demo data. Run: python -m app.seed  (safe to run again; it resets the demo database)."""
from sqlalchemy import select

from .db import Base, SessionLocal, engine
from . import models  # noqa: F401
from .models.core import Membership, Organization, Property, User
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


EXTRA_SEEDS: list = [seed_plans, seed_saas_demo]  # later modules append their seed functions here

if __name__ == "__main__":
    run()
