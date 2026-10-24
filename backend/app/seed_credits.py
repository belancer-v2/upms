"""Demo data for M19: credit packs, plan email allowances, email balances and a few purchases."""
from datetime import timedelta

from sqlalchemy import select

from .models.core import User, now
from .models.credits import CreditPack, CreditPurchase, EmailLedger, PlatformSetting
from .models.saas import Plan, SaasInvoice, Subscription

P = 100
EMAIL_INCLUDED = {"basic": {"S": 500, "M": 1000, "L": 2000}, "standard": {"S": 2000, "M": 5000, "L": 10000}, "pro": {"S": 5000, "M": 10000, "L": 20000}}
PACKS = [  # kind, name, bn, credits, price (paisa)
    ("sms", "SMS 1,000", "এসএমএস ১,০০০", 1000, 800 * P), ("sms", "SMS 5,000", "এসএমএস ৫,০০০", 5000, 3500 * P), ("sms", "SMS 20,000", "এসএমএস ২০,০০০", 20000, 12000 * P),
    ("email", "Email 5,000", "ইমেইল ৫,০০০", 5000, 500 * P), ("email", "Email 20,000", "ইমেইল ২০,০০০", 20000, 1600 * P),
]


def seed_credits(db, ctx):
    for key, per in EMAIL_INCLUDED.items():
        plan = db.get(Plan, key)
        if plan:
            plan.email_included = per
    for n, (kind, name, bn, credits, price) in enumerate(PACKS):
        db.add(CreditPack(kind=kind, name=name, name_bn=bn, credits=credits, price=price, sort=n))
    db.add_all([PlatformSetting(key="vat_bps", value="0"), PlatformSetting(key="pay_bkash", value="01700-000000 (Personal)"), PlatformSetting(key="pay_nagad", value="01800-000000 (Personal)"),
                PlatformSetting(key="pay_bank", value="FlatWise Ltd, A/C 1234567890, Example Bank, Gulshan branch")])
    db.flush()
    # every live subscription starts with its monthly email allowance
    for sub in db.scalars(select(Subscription).where(Subscription.status.in_(("active", "past_due", "trial")))):
        plan = db.get(Plan, sub.plan_key)
        n = (plan.email_included or {}).get(sub.band, 0) if plan else 0
        if n:
            db.add(EmailLedger(org_id=sub.org_id, delta=n, reason="Monthly allowance"))
    # demo history for the agency (Sunrise Tower): one paid pack and one manual payment waiting for SaaS finance
    org = ctx["agency"]
    padmin = db.scalar(select(User).where(User.email == "padmin@flatwise.demo"))
    uid = padmin.id if padmin else 0
    pack = db.scalar(select(CreditPack).where(CreditPack.kind == "sms", CreditPack.credits == 1000))

    def inv(n, status, desc, total, trx, method):
        return SaasInvoice(number=f"FW-{now():%Y%m}-9{n:03d}", org_id=org.id, kind="credits", description=desc, amount=total, status=status, issued_at=now() - timedelta(days=6), due_at=now() + timedelta(days=1),
                           paid_at=now() - timedelta(days=6) if status == "paid" else None, method=method, trx_id=trx,
                           items=[{"kind": pack.kind, "name": pack.name, "name_bn": pack.name_bn, "credits": pack.credits, "amount": pack.price}], vat_bps=0, vat_amount=0)
    if pack:
        i1, i2 = inv(1, "paid", "1000 SMS credits, SMS 1,000", pack.price, "SBX1A2B3C4D", "bkash"), inv(2, "pending", "1000 SMS credits, SMS 1,000", pack.price, "BK9X77Q2LM", "bkash")
        db.add_all([i1, i2])
        db.flush()
        from .models.saas import SmsLedger
        db.add(SmsLedger(org_id=org.id, delta=pack.credits, reason=f"Pack {pack.credits} · {i1.number}", by_user_id=uid, invoice_id=i1.id))
        base = dict(org_id=org.id, user_id=uid, pack_id=pack.id, kind="sms", pack_name=pack.name, pack_name_bn=pack.name_bn, credits=pack.credits, price=pack.price, vat_bps=0, vat=0, total=pack.price)
        db.add(CreditPurchase(token="seed-credits-paid", mode="gateway", method="bkash", status="paid", trx_id="SBX1A2B3C4D", invoice_id=i1.id, idem_key="cr:seed-paid", completed_at=now() - timedelta(days=6),
                              created_at=now() - timedelta(days=6), **base))
        db.add(CreditPurchase(token="seed-credits-manual", mode="manual", method="bkash", status="pending", trx_id="BK9X77Q2LM", claimed_amount=pack.price, invoice_id=i2.id, idem_key="cr:seed-manual",
                              created_at=now() - timedelta(days=1), **base))
    db.flush()
