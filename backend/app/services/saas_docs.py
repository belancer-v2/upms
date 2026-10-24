"""Tax-invoice helpers for M21: numbers, VAT split, amount in words, credit notes, history events.

SaasInvoice.amount is the VAT-inclusive total. VAT is split out when the invoice is issued, so every report
that reads SaasInvoice.amount stays correct.
"""
from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from ..audit import audit
from ..models.core import Membership, Organization, User, now
from ..models.saas import Plan, SaasInvoice, Subscription
from ..models.saas_reports import (LeadStageEvent, SaasCreditNote, SaasInvoiceDoc, SaasNumberSeq, SaasSettings, SubscriptionEvent)

# ---------------------------------------------------------------- amount in words
_EN_UNITS = ["", "One", "Two", "Three", "Four", "Five", "Six", "Seven", "Eight", "Nine", "Ten", "Eleven", "Twelve", "Thirteen", "Fourteen",
             "Fifteen", "Sixteen", "Seventeen", "Eighteen", "Nineteen"]
_EN_TENS = ["", "", "Twenty", "Thirty", "Forty", "Fifty", "Sixty", "Seventy", "Eighty", "Ninety"]
_BN_0_99 = ("শূন্য এক দুই তিন চার পাঁচ ছয় সাত আট নয় দশ এগার বার তের চৌদ্দ পনের ষোল সতের আঠার ঊনিশ "
            "বিশ একুশ বাইশ তেইশ চব্বিশ পঁচিশ ছাব্বিশ সাতাশ আটাশ ঊনত্রিশ ত্রিশ একত্রিশ বত্রিশ তেত্রিশ চৌত্রিশ পঁয়ত্রিশ ছত্রিশ সাঁইত্রিশ আটত্রিশ ঊনচল্লিশ "
            "চল্লিশ একচল্লিশ বিয়াল্লিশ তেতাল্লিশ চুয়াল্লিশ পঁয়তাল্লিশ ছেচল্লিশ সাতচল্লিশ আটচল্লিশ ঊনপঞ্চাশ "
            "পঞ্চাশ একান্ন বায়ান্ন তিপ্পান্ন চুয়ান্ন পঞ্চান্ন ছাপ্পান্ন সাতান্ন আটান্ন ঊনষাট "
            "ষাট একষট্টি বাষট্টি তেষট্টি চৌষট্টি পঁয়ষট্টি ছেষট্টি সাতষট্টি আটষট্টি ঊনসত্তর "
            "সত্তর একাত্তর বাহাত্তর তিয়াত্তর চুয়াত্তর পঁচাত্তর ছিয়াত্তর সাতাত্তর আটাত্তর ঊনআশি "
            "আশি একাশি বিরাশি তিরাশি চুরাশি পঁচাশি ছিয়াশি সাতাশি আটাশি ঊননব্বই "
            "নব্বই একানব্বই বিরানব্বই তিরানব্বই চুরানব্বই পঁচানব্বই ছিয়ানব্বই সাতানব্বই আটানব্বই নিরানব্বই").split()
_BN_HUNDRED = ["", "একশ", "দুইশ", "তিনশ", "চারশ", "পাঁচশ", "ছয়শ", "সাতশ", "আটশ", "নয়শ"]
assert len(_BN_0_99) == 100


def _en_below_1000(n: int) -> str:
    parts = []
    if n >= 100:
        parts.append(_EN_UNITS[n // 100] + " Hundred")
        n %= 100
    if n >= 20:
        parts.append(_EN_TENS[n // 10] + (" " + _EN_UNITS[n % 10] if n % 10 else ""))
    elif n:
        parts.append(_EN_UNITS[n])
    return " ".join(parts)


def _en_int(n: int) -> str:
    """Indian/Bangladeshi grouping: crore, lakh, thousand."""
    if n == 0:
        return "Zero"
    parts = []
    for size, name in ((10_000_000, "Crore"), (100_000, "Lakh"), (1000, "Thousand")):
        if n >= size:
            parts.append(f"{_en_int(n // size)} {name}")
            n %= size
    if n:
        parts.append(_en_below_1000(n))
    return " ".join(parts)


def _bn_int(n: int) -> str:
    if n == 0:
        return _BN_0_99[0]
    parts = []
    for size, name in ((10_000_000, "কোটি"), (100_000, "লাখ"), (1000, "হাজার")):
        if n >= size:
            parts.append(f"{_bn_int(n // size)} {name}")
            n %= size
    if n >= 100:
        h = _BN_HUNDRED[n // 100]
        n %= 100
        parts.append(h + (" " + _BN_0_99[n] if n else ""))
    elif n:
        parts.append(_BN_0_99[n])
    return " ".join(parts)


def amount_in_words(paisa: int, lang: str = "en") -> str:
    taka, ps = divmod(abs(int(paisa)), 100)
    if lang == "bn":
        s = f"{_bn_int(taka)} টাকা" if taka or not ps else ""
        if ps:
            s = (s + " " if s else "") + f"{_bn_int(ps)} পয়সা"
        return s + " মাত্র"
    s = f"{_en_int(taka)} Taka" if taka or not ps else ""
    if ps:
        s = (s + " and " if s else "") + f"{_en_int(ps)} Paisa"
    return s + " Only"


# ---------------------------------------------------------------- settings, fiscal year, numbering
def get_settings(db: Session) -> SaasSettings:
    s = db.get(SaasSettings, 1)
    if not s:
        s = SaasSettings(id=1)
        db.add(s)
        db.flush()
    return s


def fiscal_year(dt: datetime, start_month: int = 1) -> int:
    """Fiscal year is named after the calendar year in which it starts."""
    return dt.year if dt.month >= start_month else dt.year - 1


def next_number(db: Session, series: str, fy: int) -> int:
    """Gap-free: the counter row is bumped inside the caller's transaction, so a rollback gives the number back."""
    if not db.get(SaasNumberSeq, (series, fy)):
        db.add(SaasNumberSeq(series=series, fy=fy, last=0))
        db.flush()
    db.execute(update(SaasNumberSeq).where(SaasNumberSeq.series == series, SaasNumberSeq.fy == fy).values(last=SaasNumberSeq.last + 1))
    return int(db.scalar(select(SaasNumberSeq.last).where(SaasNumberSeq.series == series, SaasNumberSeq.fy == fy)))


def peek_next(db: Session, series: str, fy: int) -> int:
    return int(db.scalar(select(SaasNumberSeq.last).where(SaasNumberSeq.series == series, SaasNumberSeq.fy == fy)) or 0) + 1


def set_next_number(db: Session, series: str, fy: int, nxt: int) -> None:
    """Only moves the counter forward, so a number is never reused."""
    cur = peek_next(db, series, fy)
    if nxt < cur:
        raise ValueError("next number cannot go backwards")
    if not db.get(SaasNumberSeq, (series, fy)):
        db.add(SaasNumberSeq(series=series, fy=fy, last=0))
        db.flush()
    db.execute(update(SaasNumberSeq).where(SaasNumberSeq.series == series, SaasNumberSeq.fy == fy).values(last=nxt - 1))


def fmt_number(prefix: str, fy: int, seq: int, width: int) -> str:
    return f"{prefix}-{fy}-{seq:0{width}d}"


# ---------------------------------------------------------------- VAT and items
def split_vat(total: int, pct: float) -> tuple[int, int]:
    """Total is VAT-inclusive. Returns (net, vat) in paisa."""
    net = int((Decimal(total) * 100 / (Decimal(str(pct)) + 100)).quantize(Decimal(1), rounding=ROUND_HALF_UP))
    return net, total - net


def _customer_lang(db: Session, org_id: int) -> str:
    u = db.scalar(select(User).join(Membership, Membership.user_id == User.id).where(Membership.org_id == org_id).order_by(Membership.id))
    return u.lang if u and u.lang in ("en", "bn") else "en"


def build_items(db: Session, inv: SaasInvoice, net_total: int, pct: float) -> list[dict]:
    custom = getattr(inv, "items", None)
    if isinstance(custom, list) and custom and all(isinstance(x, dict) for x in custom):
        items, left = [], net_total
        for n, x in enumerate(custom):
            gross = int(x.get("amount", x.get("total", 0)) or 0)
            net = left if n == len(custom) - 1 else split_vat(gross, pct)[0]
            left -= net
            d = str(x.get("description") or x.get("desc") or inv.description)
            items.append({"desc": d, "desc_bn": str(x.get("description_bn") or d), "qty": int(x.get("qty", 1) or 1), "net": net})
        return items
    sub = db.scalar(select(Subscription).where(Subscription.org_id == inv.org_id).order_by(Subscription.id.desc()))
    plan = db.get(Plan, sub.plan_key) if sub else None
    pn, pb = (plan.name, plan.name_bn or plan.name) if plan else ("", "")
    band = sub.band if sub else ""
    if inv.kind == "subscription":
        en = f"FlatWise {pn} plan, size band {band}, {'year' if len(inv.period) == 4 else 'month'} {inv.period}"
        bn = f"ফ্ল্যাটওয়াইজ {pb} প্ল্যান, আকারের ধাপ {band}, {'বছর' if len(inv.period) == 4 else 'মাস'} {inv.period}"
    elif inv.kind == "setup":
        en, bn = f"One-time setup fee, {pn} plan", f"এককালীন সেটআপ ফি, {pb} প্ল্যান"
    elif inv.kind == "sms":
        en, bn = inv.description or "SMS credits", f"এসএমএস ক্রেডিট ({inv.description})" if inv.description else "এসএমএস ক্রেডিট"
    else:
        en = bn = inv.description or inv.kind
    return [{"desc": en, "desc_bn": bn, "qty": 1, "net": net_total}]


def issue_doc(db: Session, inv: SaasInvoice, user_id: int | None = None, lang: str | None = None) -> SaasInvoiceDoc:
    """Gives the invoice its tax-invoice number. Safe to call twice: the same document comes back."""
    doc = db.scalar(select(SaasInvoiceDoc).where(SaasInvoiceDoc.invoice_id == inv.id))
    if doc:
        return doc
    st = get_settings(db)
    at = now()
    fy = fiscal_year(at, st.fy_start_month)
    seq = next_number(db, "INV", fy)
    net, vat = split_vat(inv.amount, st.default_vat_pct)
    doc = SaasInvoiceDoc(invoice_id=inv.id, doc_no=fmt_number(st.invoice_prefix, fy, seq, 6), fy=fy, seq=seq, issued_at=at, vat_pct=st.default_vat_pct,
                         net=net, vat=vat, total=inv.amount, items=build_items(db, inv, net, st.default_vat_pct),
                         lang=lang or _customer_lang(db, inv.org_id), quote_ref=inv.number, issued_by=user_id)
    db.add(doc)
    db.flush()
    audit(db, user_id=user_id, org_id=inv.org_id, action="saas.invoice.issue", entity="invoice", entity_id=inv.id, meta={"doc_no": doc.doc_no, "total": inv.amount})
    return doc


def credit_total(db: Session, invoice_id: int) -> int:
    return int(db.scalar(select(func.coalesce(func.sum(SaasCreditNote.amount), 0)).where(SaasCreditNote.invoice_id == invoice_id)) or 0)


def issue_credit_note(db: Session, inv: SaasInvoice, kind: str, reason: str, user_id: int | None, amount: int | None = None) -> SaasCreditNote:
    doc = issue_doc(db, inv, user_id)
    room = inv.amount - credit_total(db, inv.id)
    amt = room if amount is None else amount
    if amt <= 0 or amt > room:
        raise ValueError("Credit note amount is more than what is left on the invoice")
    st = get_settings(db)
    at = now()
    fy = fiscal_year(at, st.fy_start_month)
    seq = next_number(db, "CN", fy)
    vat = split_vat(amt, doc.vat_pct)[1]
    cn = SaasCreditNote(doc_no=fmt_number(st.credit_prefix, fy, seq, 4), fy=fy, seq=seq, invoice_id=inv.id, org_id=inv.org_id, kind=kind, amount=amt, vat=vat,
                        reason=reason[:200], issued_at=at, issued_by=user_id)
    db.add(cn)
    db.flush()
    audit(db, user_id=user_id, org_id=inv.org_id, action=f"saas.creditnote.{kind}", entity="invoice", entity_id=inv.id, meta={"cn": cn.doc_no, "amount": amt, "invoice": doc.doc_no})
    return cn


def void_with_credit_note(db: Session, inv: SaasInvoice, user_id: int | None, reason: str = "Invoice voided") -> SaasCreditNote | None:
    """The invoice row stays; a credit note for the full open amount is issued. Called by the existing void route."""
    left = inv.amount - credit_total(db, inv.id)
    if left <= 0:
        return None
    return issue_credit_note(db, inv, "void", reason, user_id, left)


# ---------------------------------------------------------------- history events
def monthly_price_of(db: Session, sub: Subscription) -> int:
    plan = db.get(Plan, sub.plan_key)
    base = plan.monthly.get(sub.band, 0) if plan else 0
    return int(base * (100 - sub.discount_pct) / 100)


def record_event(db: Session, sub: Subscription | None, kind: str, user_id: int | None = None, at: datetime | None = None) -> None:
    """Called after a plan change, activate, suspend, cancel or trial start. Never raises into the caller."""
    if not sub:
        return
    live = sub.status in ("active", "past_due")
    db.add(SubscriptionEvent(org_id=sub.org_id, at=at or now(), kind=kind, plan_key=sub.plan_key, band=sub.band, cycle=sub.cycle, status=sub.status,
                             mrr=monthly_price_of(db, sub) if live else 0, by_user_id=user_id))


def record_lead_stage(db: Session, lead_id: int, status: str, at: datetime | None = None) -> None:
    db.add(LeadStageEvent(lead_id=lead_id, status=status, at=at or now()))
