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


EXTRA_SEEDS: list = [seed_plans]  # later modules append their seed functions here

if __name__ == "__main__":
    run()
