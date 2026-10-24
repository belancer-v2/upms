"""Demo data for M20: the template library, audiences, three sent campaigns with stats, outbox rows for the demo leads, a few suppressed addresses."""
import re
from datetime import timedelta
from random import Random

from sqlalchemy import select

from .models.core import User, now
from .models.mail import MailAudience, MailCampaign, MailConsent, MailProspect, MailTemplate
from .models.saas import Lead

H = lambda t: {"type": "heading", "text": t}
P = lambda t: {"type": "paragraph", "text": t}
B = lambda label, url="{{link}}": {"type": "button", "label": label, "url": url}
D = {"type": "divider"}
F = lambda t: {"type": "footer", "text": t}
IMG = lambda url, alt: {"type": "image", "url": url, "alt": alt}

SIGN_EN, SIGN_BN = F("The FlatWise team"), F("ফ্ল্যাটওয়াইজ টিম")


def _trial(days_en, days_bn, line_en, line_bn):
    return (f"Your FlatWise trial ends in {days_en}, {{{{name}}}}", f"আপনার ফ্ল্যাটওয়াইজ ট্রায়াল {days_bn} পর শেষ হবে, {{{{name}}}}",
            [H(f"{days_en.capitalize()} left on your trial"), P(f"Hello {{{{name}}}},\n\nThe trial for {{{{building}}}} ends in {days_en}. {line_en}"), B("Choose a plan"), D, SIGN_EN],
            [H(f"ট্রায়ালের আর {days_bn} বাকি"), P(f"{{{{name}}}}, আসসালামু আলাইকুম।\n\n{{{{building}}}}-এর ট্রায়াল {days_bn} পর শেষ হবে। {line_bn}"), B("প্ল্যান বেছে নিন"), D, SIGN_BN])


TEMPLATES = [  # key, name, bn, kind, subject en, subject bn, blocks en, blocks bn
    ("welcome", "Welcome", "স্বাগত", "transactional", "Welcome to FlatWise, {{name}}", "ফ্ল্যাটওয়াইজে স্বাগতম, {{name}}",
     [H("Welcome to FlatWise"), P("Hello {{name}},\n\nThank you for your interest in {{building}}. FlatWise keeps service charges, cash, expenses and notices of your building in order, in Bangla and English."), B("See how it works"), D, SIGN_EN],
     [H("ফ্ল্যাটওয়াইজে স্বাগতম"), P("{{name}}, আসসালামু আলাইকুম।\n\n{{building}}-এর প্রতি আপনার আগ্রহের জন্য ধন্যবাদ। ফ্ল্যাটওয়াইজে আপনার ভবনের সার্ভিস চার্জ, নগদ, খরচ ও নোটিশ বাংলা ও ইংরেজিতে গুছিয়ে রাখা যায়।"), B("কীভাবে কাজ করে দেখুন"), D, SIGN_BN]),
    ("trial_7", "Trial ending in 7 days", "ট্রায়াল ৭ দিন পর শেষ", "transactional", *_trial("7 days", "৭ দিন", "Pick a plan now and keep all your data.", "এখনই প্ল্যান নিন, আপনার সব তথ্য থাকবে।")),
    ("trial_3", "Trial ending in 3 days", "ট্রায়াল ৩ দিন পর শেষ", "transactional", *_trial("3 days", "৩ দিন", "Choose a plan so nothing is interrupted.", "প্ল্যান নিন, যাতে কোনো কাজ থেমে না যায়।")),
    ("trial_1", "Trial ending tomorrow", "ট্রায়াল আগামীকাল শেষ", "transactional", *_trial("1 day", "১ দিন", "After that the building switches to read-only.", "এরপর ভবনটি শুধু দেখার মোডে চলে যাবে।")),
    ("demo_followup", "Demo follow-up", "ডেমোর পর যোগাযোগ", "promotional", "Thank you for the FlatWise demo, {{name}}", "ফ্ল্যাটওয়াইজ ডেমোর জন্য ধন্যবাদ, {{name}}",
     [H("Thank you for your time"), P("Hello {{name}},\n\nIt was good to show FlatWise for {{building}}. If your committee has questions about pricing or moving your records, reply to this email and we will help."), B("See pricing"), D, SIGN_EN],
     [H("সময় দেওয়ার জন্য ধন্যবাদ"), P("{{name}}, আসসালামু আলাইকুম।\n\n{{building}}-এর জন্য ফ্ল্যাটওয়াইজ দেখাতে পেরে ভালো লেগেছে। মূল্য বা পুরোনো তথ্য আনা নিয়ে কমিটির প্রশ্ন থাকলে এই ইমেইলের উত্তর দিন, আমরা সাহায্য করব।"), B("মূল্য দেখুন"), D, SIGN_BN]),
    ("invoice_issued", "Invoice issued", "ইনভয়েস ইস্যু হয়েছে", "transactional", "Your FlatWise invoice for {{building}}", "{{building}}-এর ফ্ল্যাটওয়াইজ ইনভয়েস",
     [H("A new invoice is ready"), P("Hello {{name}},\n\nThe {{plan}} plan invoice for {{building}} has been issued. You can pay by bKash, Nagad or bank transfer."), B("View invoice"), D, SIGN_EN],
     [H("নতুন ইনভয়েস তৈরি হয়েছে"), P("{{name}}, আসসালামু আলাইকুম।\n\n{{building}}-এর {{plan}} প্ল্যানের ইনভয়েস ইস্যু হয়েছে। বিকাশ, নগদ বা ব্যাংক ট্রান্সফারে পরিশোধ করা যাবে।"), B("ইনভয়েস দেখুন"), D, SIGN_BN]),
    ("payment_received", "Payment received", "পেমেন্ট পাওয়া গেছে", "transactional", "We received your payment, {{name}}", "আপনার পেমেন্ট পেয়েছি, {{name}}",
     [H("Payment received"), P("Hello {{name}},\n\nThank you. We have received the payment for {{building}} ({{plan}}). Your receipt is in the app."), B("Open receipts"), D, SIGN_EN],
     [H("পেমেন্ট পাওয়া গেছে"), P("{{name}}, ধন্যবাদ। {{building}} ({{plan}})-এর পেমেন্ট আমরা পেয়েছি। রসিদ অ্যাপে আছে।"), B("রসিদ দেখুন"), D, SIGN_BN]),
    ("credits_low", "SMS credits low", "SMS ক্রেডিট কমে গেছে", "transactional", "Your SMS credits for {{building}} are running low", "{{building}}-এর SMS ক্রেডিট কমে যাচ্ছে",
     [H("SMS credits are running low"), P("Hello {{name}},\n\nThe SMS balance of {{building}} is almost used up. Add credits so dues reminders and notices keep going out."), B("Add SMS credits"), D, SIGN_EN],
     [H("SMS ক্রেডিট কমে যাচ্ছে"), P("{{name}}, {{building}}-এর SMS ব্যালেন্স প্রায় শেষ। ক্রেডিট যোগ করুন, যাতে বকেয়ার তাগিদ ও নোটিশ যেতে থাকে।"), B("ক্রেডিট যোগ করুন"), D, SIGN_BN]),
    ("feature_announcement", "Feature announcement", "নতুন ফিচারের ঘোষণা", "promotional", "New in FlatWise: smarter dues reminders", "ফ্ল্যাটওয়াইজে নতুন: আরও স্মার্ট বকেয়া তাগিদ",
     [H("Dues reminders that work"), IMG("https://placehold.co/536x200/691542/FFFFFF?text=FlatWise", "FlatWise dues reminders"),
      P("Hello {{name}},\n\nCommittees using FlatWise can now send SMS and email reminders to owners and tenants on the day a charge falls due, in their own language, and see who paid."), B("See what is new"), D, SIGN_EN],
     [H("যে তাগিদ কাজ করে"), IMG("https://placehold.co/536x200/691542/FFFFFF?text=FlatWise", "ফ্ল্যাটওয়াইজ বকেয়া তাগিদ"),
      P("{{name}}, আসসালামু আলাইকুম।\n\nফ্ল্যাটওয়াইজ ব্যবহারকারী কমিটি এখন চার্জের তারিখে মালিক ও ভাড়াটিয়াকে তাদের ভাষায় SMS ও ইমেইলে তাগিদ পাঠাতে এবং কে দিয়েছে দেখতে পারে।"), B("নতুন কী আছে দেখুন"), D, SIGN_BN]),
    ("eid_offer", "Eid greetings and offer", "ঈদ শুভেচ্ছা ও অফার", "promotional", "Eid Mubarak from FlatWise, {{name}}", "ফ্ল্যাটওয়াইজের পক্ষ থেকে ঈদ মোবারক, {{name}}",
     [H("Eid Mubarak"), P("Dear {{name}},\n\nWishing you and the residents of {{building}} a joyful Eid. As our Eid gift, set up FlatWise this month and get your first month free."), B("Claim the Eid offer"), D, SIGN_EN],
     [H("ঈদ মোবারক"), P("প্রিয় {{name}},\n\nআপনাকে এবং {{building}}-এর সব বাসিন্দাকে ঈদের শুভেচ্ছা। ঈদ উপহার হিসেবে এই মাসে ফ্ল্যাটওয়াইজ চালু করলে প্রথম মাস বিনামূল্যে।"), B("ঈদ অফার নিন"), D, SIGN_BN]),
    ("winback", "Win-back", "ফিরে আসার আমন্ত্রণ", "promotional", "We would love to have {{building}} back", "{{building}}-কে আবার পেলে খুশি হব",
     [H("Come back to FlatWise"), P("Hello {{name}},\n\nWe have added a lot since {{building}} left: mobile payments, dues reminders and a simpler budget. Your records are safe and can be restored in a day."), B("Reactivate my building"), D, SIGN_EN],
     [H("ফ্ল্যাটওয়াইজে ফিরে আসুন"), P("{{name}}, আসসালামু আলাইকুম।\n\n{{building}} চলে যাওয়ার পর আমরা অনেক কিছু যোগ করেছি: মোবাইল পেমেন্ট, বকেয়া তাগিদ, সহজ বাজেট। আপনার তথ্য নিরাপদ আছে, এক দিনে ফিরিয়ে আনা যাবে।"), B("আমার ভবন আবার চালু করুন"), D, SIGN_BN]),
    ("referral_invite", "Referral invite", "রেফারেল আমন্ত্রণ", "promotional", "Refer a building, get a free month", "একটি ভবন রেফার করুন, একটি মাস ফ্রি পান",
     [H("Know another building?"), P("Hello {{name}},\n\nIf a friend's building joins FlatWise because of you, both buildings get one month free on the {{plan}} plan."), B("Invite a building"), D, SIGN_EN],
     [H("অন্য কোনো ভবন চেনেন?"), P("{{name}}, আপনার মাধ্যমে কোনো বন্ধুর ভবন ফ্ল্যাটওয়াইজে যোগ দিলে {{plan}} প্ল্যানে দুই ভবনই এক মাস ফ্রি পাবে।"), B("ভবনকে আমন্ত্রণ জানান"), D, SIGN_BN]),
]

FIRST = ["Abdul", "Rahim", "Karim", "Nasima", "Sabina", "Jahid", "Rubel", "Mitu", "Sohel", "Shirin", "Tanvir", "Farhana", "Imran", "Lutfa", "Monir", "Ayesha"]
LAST = ["Hossain", "Uddin", "Akter", "Islam", "Rahman", "Khan", "Sarker", "Chowdhury", "Mia", "Begum"]


def seed_mail(db, ctx):
    rnd = Random(2026)
    from .services import mailer as M
    sales = db.scalar(select(User).where(User.email == "sales@flatwise.demo"))
    t0 = now()

    tpls = {}
    for key, name, bn, kind, se, sb, be, bb in TEMPLATES:
        t = MailTemplate(key=key, name=name, name_bn=bn, kind=kind, subject_en=se, subject_bn=sb, blocks_en=be, blocks_bn=bb, updated_by=sales.id if sales else None)
        db.add(t)
        tpls[key] = t
    db.flush()

    # demo leads get an email address and a recorded consent source (the seeded leads had none)
    leads = db.scalars(select(Lead).order_by(Lead.id)).all()
    src_map = {"website": "website_form", "demo": "demo_request", "referral": "referral"}
    for i, l in enumerate(leads):
        if not l.email:
            l.email = re.sub(r"[^a-z]+", ".", l.name.lower()).strip(".") + "@example.bd"
        db.add(MailConsent(lead_id=l.id, source=src_map.get(l.source, "website_form"), lang="en" if i % 3 == 0 else "bn", at=l.created_at))
    db.flush()

    # CSV prospects
    aud_csv = MailAudience(name="Dhaka building committees (CSV)", kind="csv", params={"consent_source": "event_signup_sheet"}, created_by=sales.id)
    db.add(aud_csv)
    db.flush()
    seen = set()
    for i in range(80):
        f, l = rnd.choice(FIRST), rnd.choice(LAST)
        email = f"{f.lower()}.{l.lower()}{i}@prospects.example.bd"
        seen.add(email)
        db.add(MailProspect(audience_id=aud_csv.id, email=email, name=f"{f} {l}", company=f"{rnd.choice(['Green', 'Blue', 'Sunny', 'Lake', 'Palm'])} {rnd.choice(['Villa', 'Tower', 'Court', 'Heights'])}",
                            city=rnd.choice(["Dhaka", "Dhaka", "Chattogram", "Sylhet"]), lang=rnd.choice(["bn", "bn", "en", ""]), consent_source="event_signup_sheet"))
    db.flush()
    aud_leads = MailAudience(name="Open leads (new, contacted, demo, trial)", kind="stage", params={"stages": ["new", "contacted", "demo", "trial"]}, created_by=sales.id)
    aud_active = MailAudience(name="Active customers", kind="active", params={}, created_by=sales.id)
    aud_trial = MailAudience(name="Buildings on trial", kind="trial", params={}, created_by=sales.id)
    aud_churn = MailAudience(name="Suspended or cancelled", kind="churned", params={}, created_by=sales.id)
    aud_dhaka = MailAudience(name="Dhaka leads and buildings", kind="city", params={"city": "Dhaka"}, created_by=sales.id)
    db.add_all([aud_leads, aud_active, aud_trial, aud_churn, aud_dhaka])
    db.flush()

    # a few suppressed addresses: two unsubscribes, one hard bounce, one manual
    prospects = [e for e in sorted(seen)][:2]
    M.add_suppression(db, prospects[0], "unsubscribe", "link, seed")
    M.add_suppression(db, prospects[1], "unsubscribe", "link, seed")
    M.add_suppression(db, "old.address@bounced.example.bd", "bounce", "hard bounce, seed")
    M.add_suppression(db, "do.not.mail@example.bd", "manual", "asked by phone", sales.id)
    lost = next((l for l in leads if l.status == "lost"), None)
    if lost:
        M.add_suppression(db, lost.email, "unsubscribe", "link, seed")
    db.flush()

    # welcome mail to every demo lead, shortly after they arrived
    for l in leads:
        c = db.get(MailConsent, l.id)
        at = min(t0, M._aware(l.created_at) + timedelta(minutes=2))
        M.send_template(db, "welcome", l.email, l.name, c.lang or "bn", {"building": l.building, "link": f"{M.APP_URL}/demo"}, lead_id=l.id, at=at, simulate=True)

    def campaign(name, aud, key, days_ago, throttle=0, lang_rule="recipient"):
        c = MailCampaign(name=name, audience_id=aud.id, template_id=tpls[key].id, lang_rule=lang_rule, throttle_per_hour=throttle, simulate=True, created_by=sales.id,
                         created_at=t0 - timedelta(days=days_ago + 1))
        db.add(c)
        db.flush()
        at = t0 - timedelta(days=days_ago)
        M.queue_campaign(db, c, at)
        M.dispatch(db, c, at)
        db.flush()
        return c

    campaign("Launch: smarter dues reminders", aud_csv, "feature_announcement", 12)
    campaign("Demo follow-up, October", aud_leads, "demo_followup", 6)
    campaign("Refer a building, get a free month", aud_active, "referral_invite", 2)
    # one scheduled for later: no stats yet
    db.add(MailCampaign(name="Win back suspended buildings", audience_id=aud_churn.id, template_id=tpls["winback"].id, lang_rule="recipient", status="scheduled",
                        scheduled_at=t0 + timedelta(days=2), simulate=True, created_by=sales.id))
    db.add(MailCampaign(name="Eid greetings and offer (draft)", audience_id=aud_dhaka.id, template_id=tpls["eid_offer"].id, lang_rule="recipient", status="draft", simulate=True, created_by=sales.id))
    db.flush()
