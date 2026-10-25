"""Mail to the people who run an organization, using the existing transactional templates (created if a database lacks them)."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models.core import Membership, Organization, User
from ..models.mail import MailTemplate
from ..services import mailer as M

ADMIN_ROLES = ("PROPERTY_ADMIN", "AGENCY_MANAGER", "PRESIDENT")

H = lambda t: {"type": "heading", "text": t}      # noqa: E731
P = lambda t: {"type": "paragraph", "text": t}    # noqa: E731
B = lambda label: {"type": "button", "label": label, "url": "{{link}}"}   # noqa: E731
SIGN_EN, SIGN_BN = {"type": "footer", "text": "The FlatWise team"}, {"type": "footer", "text": "ফ্ল্যাটওয়াইজ টিম"}

# key -> (name, subject en, subject bn, blocks en, blocks bn). Only used when seed_mail did not create the template.
FALLBACK = {
    "credits_low": ("SMS credits low", "Your SMS credits for {{building}} are running low", "{{building}}-এর SMS ক্রেডিট কমে যাচ্ছে",
                    [H("SMS credits are running low"), P("Hello {{name}},\n\nThe SMS balance of {{building}} is almost used up. Add credits so reminders and notices keep going out."), B("Add SMS credits"), SIGN_EN],
                    [H("SMS ক্রেডিট কমে যাচ্ছে"), P("{{name}}, {{building}}-এর SMS ব্যালেন্স প্রায় শেষ। ক্রেডিট যোগ করুন।"), B("SMS ক্রেডিট যোগ করুন"), SIGN_BN]),
    "credits_low_email": ("Email credits low", "Your email credits for {{building}} are running low", "{{building}}-এর ইমেইল ক্রেডিট কমে যাচ্ছে",
                          [H("Email credits are running low"), P("Hello {{name}},\n\nThe email balance of {{building}} is almost used up. Add credits so messages keep going out."), B("Add email credits"), SIGN_EN],
                          [H("ইমেইল ক্রেডিট কমে যাচ্ছে"), P("{{name}}, {{building}}-এর ইমেইল ব্যালেন্স প্রায় শেষ। ক্রেডিট যোগ করুন।"), B("ইমেইল ক্রেডিট যোগ করুন"), SIGN_BN]),
    "invoice_overdue": ("Invoice overdue", "Your FlatWise invoice for {{building}} is overdue", "{{building}}-এর ফ্ল্যাটওয়াইজ ইনভয়েস বকেয়া",
                        [H("An invoice is overdue"), P("Hello {{name}},\n\nThe {{plan}} invoice for {{building}} is past its due date. Please pay it to keep the service running without interruption."), B("View invoice"), SIGN_EN],
                        [H("ইনভয়েস বকেয়া"), P("{{name}}, {{building}}-এর {{plan}} ইনভয়েসের তারিখ পেরিয়ে গেছে। সেবা চালু রাখতে পরিশোধ করুন।"), B("ইনভয়েস দেখুন"), SIGN_BN]),
    "invoice_issued": ("Invoice issued", "Your FlatWise invoice for {{building}}", "{{building}}-এর ফ্ল্যাটওয়াইজ ইনভয়েস",
                       [H("A new invoice is ready"), P("Hello {{name}},\n\nThe {{plan}} plan invoice for {{building}} has been issued."), B("View invoice"), SIGN_EN],
                       [H("নতুন ইনভয়েস তৈরি হয়েছে"), P("{{name}}, {{building}}-এর {{plan}} প্ল্যানের ইনভয়েস ইস্যু হয়েছে।"), B("ইনভয়েস দেখুন"), SIGN_BN]),
}
for _n, _t in (("trial_7", "7 days"), ("trial_3", "3 days"), ("trial_1", "1 day")):
    FALLBACK[_n] = (f"Trial ending in {_t}", f"Your FlatWise trial ends in {_t}, {{{{name}}}}", f"আপনার ফ্ল্যাটওয়াইজ ট্রায়াল শেষ হচ্ছে, {{{{name}}}}",
                    [H(f"{_t} left on your trial"), P(f"Hello {{{{name}}}},\n\nThe trial for {{{{building}}}} ends in {_t}. Choose a plan to keep your data."), B("Choose a plan"), SIGN_EN],
                    [H("ট্রায়াল শেষ হয়ে আসছে"), P("{{name}}, আপনার ট্রায়াল শেষ হয়ে আসছে। প্ল্যান নিন।"), B("প্ল্যান বেছে নিন"), SIGN_BN])


def ensure_template(db: Session, key: str) -> None:
    if db.scalar(select(MailTemplate.id).where(MailTemplate.key == key)):
        return
    name, se, sb, be, bb = FALLBACK[key]
    db.add(MailTemplate(key=key, name=name, name_bn=name, kind="transactional", subject_en=se, subject_bn=sb, blocks_en=be, blocks_bn=bb))
    db.flush()


def org_admins(db: Session, org_id: int) -> list[User]:
    ids = {m.user_id for m in db.scalars(select(Membership).where(Membership.org_id == org_id, Membership.role.in_(ADMIN_ROLES)))}
    return [u for u in db.scalars(select(User).where(User.id.in_(ids or {-1}), User.is_active)) if u.email]


def mail_org_admins(db: Session, org: Organization, template: str, vars: dict, at: datetime) -> int:
    """Sends one transactional email per admin of the organization. Returns how many were handed to the mail provider."""
    ensure_template(db, template)
    n = 0
    for u in org_admins(db, org.id):
        row = M.send_template(db, template, u.email, u.name, u.lang if u.lang in ("en", "bn") else "bn",
                              {"building": org.name_bn if u.lang == "bn" and org.name_bn else org.name, **vars}, org_id=org.id, at=at)
        n += row.status == "sent"
    return n
