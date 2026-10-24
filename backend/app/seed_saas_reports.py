"""M21 demo data: 12 months of subscription history for the 12 demo customers, three churned customers, historic invoices and payments,
tax-invoice numbers, a few credit notes, lead stage history, login and activity traces, and the FlatWise invoice settings."""
from datetime import timedelta
from random import Random

from sqlalchemy import select

from .models.core import AuditLog, Membership, Organization, Property, User, now
from .models.saas import Lead, Plan, SaasInvoice, SmsLedger, Subscription
from .models.saas_reports import LeadStageEvent, SubscriptionEvent
from .security import hash_password
from .services import saas_docs as docs

# customer number (admin<i>@customers.demo) -> days ago it became a paying customer
ACTIVATED = {1: 335, 2: 305, 3: 275, 4: 245, 5: 215, 6: 185, 7: 155, 11: 240, 12: 125}
# customer number -> [(days ago, plan, band)] plan changes after activation; the first tuple is the starting plan
HISTORY = {1: [(335, "basic", "M"), (150, "standard", "M")], 2: [(305, "standard", "S"), (90, "basic", "S")], 3: [(275, "standard", "S"), (120, "standard", "M")],
           4: [(245, "pro", "M"), (95, "pro", "L")], 5: [(215, "standard", "M"), (60, "pro", "M")]}
SUSPENDED_DAYS = {11: 55}
CHURNED = [  # name, bn, city, plan, band, flats, activated days ago, cancelled days ago, last invoice unpaid
    ("Hillview Residency", "হিলভিউ রেসিডেন্সি", "Dhaka", "basic", "S", 20, 340, 190, False),
    ("Padma Court Owners", "পদ্মা কোর্ট মালিক সমিতি", "Rajshahi", "standard", "S", 26, 300, 125, False),
    ("Mirpur Green Homes", "মিরপুর গ্রিন হোমস", "Dhaka", "standard", "M", 52, 270, 65, True),
]


def seed_saas_reports(db, ctx):
    rnd = Random(21)
    clock = now()
    ago = lambda d: clock - timedelta(days=d)
    plans = {p.key: p for p in db.scalars(select(Plan))}

    # ---- settings
    st = docs.get_settings(db)
    st.bin_no, st.tin = "000123456-0101", "123456789012"
    st.phone, st.email = "+880 1700 000000", "billing@flatwise.demo"
    st.bank_details = "Bank: Demo Bank Ltd., Dhanmondi branch\nAccount name: FlatWise Technologies Ltd.\nAccount no: 1234 5678 9012\nRouting: 090 261 234"
    st.bkash_merchant, st.nagad_merchant = "01700000000", "01700000001"
    st.footer_text = "Thank you for choosing FlatWise. This is a computer generated invoice and needs no signature."
    st.footer_text_bn = "ফ্ল্যাটওয়াইজ বেছে নেওয়ার জন্য ধন্যবাদ। এটি কম্পিউটার তৈরি ইনভয়েস, স্বাক্ষরের প্রয়োজন নেই।"

    def price(plan, band, disc=0):
        return int(plans[plan].monthly.get(band, 0) * (100 - disc) / 100)

    # ---- customers by number
    cust: dict[int, Organization] = {}
    for u in db.scalars(select(User).where(User.email.like("admin%@customers.demo"))):
        m = db.scalar(select(Membership).where(Membership.user_id == u.id))
        if m:
            cust[int(u.email[5:].split("@")[0])] = db.get(Organization, m.org_id)
    ag = ctx["agency"]

    # ---- churned customers
    churned_orgs = []
    for n, (name, bn, city, plan, band, flats, act, canc, unpaid) in enumerate(CHURNED, start=1):
        o = Organization(name=name, name_bn=bn, kind="committee", status="suspended", city=city, created_at=ago(act + 14))
        db.add(o)
        db.flush()
        db.add(Property(org_id=o.id, name=name, name_bn=bn, city=city, floors=max(4, flats // 8)))
        sub = Subscription(org_id=o.id, plan_key=plan, band=band, flats=flats, status="cancelled", started_at=ago(act))
        db.add(sub)
        churned_orgs.append((o, sub, act, canc, unpaid))
    db.flush()

    # ---- (org, subscription, activated days ago, [(days ago, plan, band)] timeline, end event (days ago, kind, status) or None, never paid)
    plan_of = {}
    for sub in db.scalars(select(Subscription)):
        plan_of[sub.org_id] = sub
    jobs = []
    for i, org in cust.items():
        sub = plan_of[org.id]
        if i in ACTIVATED:
            act = ACTIVATED[i]
            tl = HISTORY.get(i, [(act, sub.plan_key, sub.band)])
            end = (SUSPENDED_DAYS[i], "suspend", "suspended") if i in SUSPENDED_DAYS else None
            jobs.append((org, sub, act, tl, end, False))
        else:  # trial: a single trial_start event
            db.add(SubscriptionEvent(org_id=org.id, at=org.created_at, kind="trial_start", plan_key=sub.plan_key, band=sub.band, cycle=sub.cycle, status="trial", mrr=0))
    jobs.append((ag, plan_of[ag.id], 330, [(330, "pro", "M")], None, False))
    for o, sub, act, canc, unpaid in churned_orgs:
        jobs.append((o, sub, act, [(act, sub.plan_key, sub.band)], (canc, "cancel", "cancelled"), unpaid))

    def mrr_for(sub, plan, band, status):
        return price(plan, band, sub.discount_pct) if status in ("active", "past_due") else 0

    inv_seq = [0]

    def add_invoice(org, kind, period, desc, amount, issued, paid_after=None, method="bkash", status=None, due_days=10):
        inv_seq[0] += 1
        inv = SaasInvoice(number=f"FW-{issued:%Y%m}-H{inv_seq[0]:03d}", org_id=org.id, kind=kind, period=period, description=desc, amount=amount,
                          issued_at=issued, due_at=issued + timedelta(days=due_days), status=status or ("paid" if paid_after is not None else "issued"))
        if paid_after is not None:
            inv.paid_at, inv.method, inv.trx_id = issued + timedelta(days=paid_after), method, f"TX{rnd.randint(10**7, 10**8)}"
        db.add(inv)
        return inv

    for org, sub, act, tl, end, unpaid_last in jobs:
        # events: trial, activate, plan changes, end
        if org.id != ag.id:
            db.add(SubscriptionEvent(org_id=org.id, at=ago(act + 14), kind="trial_start", plan_key=tl[0][1], band=tl[0][2], cycle=sub.cycle, status="trial", mrr=0))
        db.add(SubscriptionEvent(org_id=org.id, at=ago(tl[0][0]), kind="activate", plan_key=tl[0][1], band=tl[0][2], cycle=sub.cycle, status="active", mrr=mrr_for(sub, tl[0][1], tl[0][2], "active")))
        for d, pk, bd in tl[1:]:
            db.add(SubscriptionEvent(org_id=org.id, at=ago(d), kind="plan_change", plan_key=pk, band=bd, cycle=sub.cycle, status="active", mrr=mrr_for(sub, pk, bd, "active")))
        last = tl[-1]
        if end:
            db.add(SubscriptionEvent(org_id=org.id, at=ago(end[0]), kind=end[1], plan_key=last[1], band=last[2], cycle=sub.cycle, status=end[2], mrr=0))
        # dates of the organization itself follow the story
        if org.id != ag.id:
            org.created_at = ago(act + 14)
        sub.started_at = ago(act)
        # re-date the setup / yearly invoice from the base seed to the activation day
        for inv in db.scalars(select(SaasInvoice).where(SaasInvoice.org_id == org.id)):
            if inv.kind == "setup" or (inv.kind == "subscription" and len(inv.period) == 4):
                inv.issued_at, inv.due_at = ago(act), ago(act) + timedelta(days=10)
                if inv.paid_at:
                    inv.paid_at = ago(act) + timedelta(days=3)
        if not db.scalar(select(SaasInvoice.id).where(SaasInvoice.org_id == org.id, SaasInvoice.kind == "setup")) and org.id != ag.id:
            add_invoice(org, "setup", "", f"One-time setup, {plans[tl[0][1]].name}", plans[tl[0][1]].setup[tl[0][2]], ago(act), 3)
        # historic monthly invoices, from the activation month up to August (September and October exist in the base seed)
        if sub.cycle == "monthly":
            first = ago(act).date().replace(day=1)
            stop_day = ago(end[0]).date() if end else None
            y, m = first.year, first.month
            periods = []
            while (y, m) < (2026, 9):
                periods.append((y, m))
                y, m = (y + 1, 1) if m == 12 else (y, m + 1)
            for k, (y, m) in enumerate(periods):
                issued = max(ago(act), ago(0).replace(year=y, month=m, day=5, hour=9, minute=0, second=0, microsecond=0))
                if stop_day and issued.date() > stop_day:
                    break
                cur = [t for t in tl if ago(t[0]) <= issued][-1] if any(ago(t[0]) <= issued for t in tl) else tl[0]
                amt = price(cur[1], cur[2], sub.discount_pct)
                last_one = (k == len(periods) - 1) or (stop_day and True and (y, m) == (stop_day.year, stop_day.month))
                is_unpaid = last_one and (unpaid_last or (org.id in [cust[11].id] if 11 in cust else False))
                add_invoice(org, "subscription", f"{y}-{m:02d}", f"{plans[cur[1]].name} · {cur[2]} · {y}-{m:02d}", amt, issued,
                            None if is_unpaid else rnd.randint(1, 12), rnd.choice(["bkash", "bkash", "nagad", "bank"]))
        # SMS ledger story that nets to zero, so balances stay what the base seed says
        pack = ago(act - 20) if act > 40 else None
        if pack and org.id != ag.id and sub.status != "cancelled":
            n = rnd.choice([500, 1000, 2000])
            db.add(SmsLedger(org_id=org.id, delta=n, reason="SMS pack", at=pack))
            add_invoice(org, "sms", "", f"{n} SMS credits", int(n / 1000 * 80000), pack, 2)
            months = max(2, act // 30)
            ws = [rnd.randint(5, 15) for _ in range(months)]
            left = n
            for j, w in enumerate(ws):
                use = left if j == months - 1 else min(left, n * w // sum(ws))
                left -= use
                if use:
                    db.add(SmsLedger(org_id=org.id, delta=-use, reason="SMS sent", at=ago(act - 30 * (j + 1) - 10 if act - 30 * (j + 1) - 10 > 0 else 1)))
    db.flush()

    # ---- allowance + usage spread for the whole year for charts: net zero per organization
    for org, sub, act, tl, end, _ in jobs:
        if sub.status == "cancelled":
            continue
        inc = plans[sub.plan_key].sms_included.get(sub.band, 0)
        if not inc or act < 40:
            continue
        for k in range(1, min(11, act // 30) + 1):
            use = int(inc * rnd.uniform(.5, .95))
            db.add(SmsLedger(org_id=org.id, delta=inc, reason=f"Monthly allowance", at=ago(act - 30 * k + 1 if act - 30 * k + 1 > 0 else 1)))
            db.add(SmsLedger(org_id=org.id, delta=-inc, reason="SMS sent", at=ago(act - 30 * k + 15 if act - 30 * k + 15 > 0 else 1)))
            _ = use

    # ---- a refund and two voided invoices with credit notes
    db.flush()
    refund_inv = db.scalar(select(SaasInvoice).where(SaasInvoice.org_id == cust[1].id, SaasInvoice.kind == "setup"))
    voids = []
    for org, period, desc in ((cust[2], "2026-08", "Basic · S · 2026-08 (issued twice by mistake)"), (cust[6], "", "500 SMS credits (duplicate)")):
        v = add_invoice(org, "subscription" if period else "sms", period, desc, price("basic", "S") if period else 40000, ago(70), None, status="void")
        voids.append(v)
    db.flush()
    # issue every invoice in date order, leave the two newest open ones without a number so the "Issue" action has something to do
    allinv = db.scalars(select(SaasInvoice).order_by(SaasInvoice.issued_at, SaasInvoice.id)).all()
    skip = {i.id for i in [x for x in allinv if x.status == "issued"][-2:]}
    for inv in allinv:
        if inv.id not in skip:
            docs.issue_doc(db, inv, None, at=inv.issued_at)
    if refund_inv:
        docs.issue_credit_note(db, refund_inv, "refund", "Goodwill refund, part of the setup fee", None, refund_inv.amount // 2, at=ago(150))
    for v in voids:
        docs.issue_credit_note(db, v, "void", "Issued by mistake", None, v.amount, at=ago(69))

    # ---- lead stage history; plus older leads so the funnel has a year behind it
    sales = db.scalar(select(User).where(User.email == "sales@flatwise.demo"))
    path = ["new", "contacted", "demo", "trial", "won"]
    srcs = ["website", "website", "demo", "referral", "facebook", "event"]
    cities = ["Dhaka", "Dhaka", "Dhaka", "Chattogram", "Sylhet", "Rajshahi", "Khulna", "Gazipur"]
    for k in range(22):
        status = rnd.choices(["won", "lost", "trial", "demo", "contacted"], [8, 8, 2, 2, 2])[0]
        db.add(Lead(name=f"Lead {k + 1:02d}", phone=f"017150001{k:02d}", building=f"Historic Tower {k + 1}", flats=rnd.choice([20, 28, 45, 60, 90, 140]), city=rnd.choice(cities),
                    source=rnd.choice(srcs), status=status, owner_id=sales.id if sales else None, created_at=ago(rnd.randint(30, 330))))
    db.flush()
    for l in db.scalars(select(Lead).order_by(Lead.id)):
        t = l.created_at if l.created_at.tzinfo else l.created_at.replace(tzinfo=clock.tzinfo)
        db.add(LeadStageEvent(lead_id=l.id, status="new", at=t))
        if l.status == "new":
            continue
        route = path[1: path.index(l.status) + 1] if l.status in path else (path[1: 1 + rnd.randint(1, 2)] + ["lost"])
        for s in route:
            t = min(t + timedelta(days=rnd.randint(1, 6), hours=rnd.randint(0, 8)), clock - timedelta(hours=1))
            db.add(LeadStageEvent(lead_id=l.id, status=s, at=t))

    # ---- logins and activity traces for the health table
    areas = ["billing", "cash", "expenses", "notices", "staff", "complaints", "budget", "assets", "policies", "gateway"]
    last_login_days = {7: 41, 11: 72, 8: 2, 9: 4, 10: 1}
    for i, org in cust.items():
        admin = db.scalar(select(User).where(User.email == f"admin{i}@customers.demo"))
        newest = last_login_days.get(i, rnd.randint(0, 6))
        for k in range(rnd.randint(3, 9)):
            db.add(AuditLog(at=ago(newest + k * rnd.randint(1, 4)), user_id=admin.id, org_id=org.id, action="auth.login", entity="user", entity_id=str(admin.id)))
        sub = plan_of[org.id]
        n_areas = {"basic": 3, "standard": 5, "pro": 8}.get(sub.plan_key, 3) if sub.status in ("active", "past_due") else 1
        if i in (7, 11):
            n_areas = 1
        for a in areas[:n_areas]:
            db.add(AuditLog(at=ago(newest + rnd.randint(0, 60)), user_id=admin.id, org_id=org.id, action=f"{a}.update", entity=a, entity_id="1"))
    ag_admin = db.scalar(select(User).where(User.email == "agency@flatwise.demo")) or db.scalar(select(User).join(Membership, Membership.user_id == User.id).where(Membership.org_id == ag.id))
    if ag_admin:
        db.add(AuditLog(at=ago(1), user_id=ag_admin.id, org_id=ag.id, action="auth.login", entity="user", entity_id=str(ag_admin.id)))
    db.flush()
