"""Double-entry ledger. Every money event posts one balanced entry; nothing is ever edited."""
from datetime import date

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..models.finance import Account, Journal, JournalLine

CHART = [
    ("1010", "Cash in hand", "হাতে নগদ", "asset"), ("1020", "Bank account", "ব্যাংক হিসাব", "asset"), ("1030", "bKash / Nagad wallet", "বিকাশ / নগদ ওয়ালেট", "asset"), ("1500", "Fixed assets", "স্থায়ী সম্পদ", "asset"),
    ("3010", "Opening balance equity", "প্রারম্ভিক জের", "equity"),
    ("4010", "Service charge income", "সার্ভিস চার্জ আয়", "income"), ("4090", "Other income", "অন্যান্য আয়", "income"),
    ("5010", "Utilities", "ইউটিলিটি", "expense"), ("5020", "Repairs and maintenance", "মেরামত ও রক্ষণাবেক্ষণ", "expense"), ("5030", "Salaries", "বেতন", "expense"),
    ("5040", "Generator fuel", "জেনারেটর জ্বালানি", "expense"), ("5050", "Security and cleaning", "নিরাপত্তা ও পরিচ্ছন্নতা", "expense"), ("5090", "Other expenses", "অন্যান্য ব্যয়", "expense"),
]
METHOD_ACCOUNT = {"cash": "1010", "bank": "1020", "bkash": "1030", "nagad": "1030", "card": "1020"}
CATEGORY_ACCOUNT = {"utilities": "5010", "repairs": "5020", "salary": "5030", "fuel": "5040", "services": "5050", "other": "5090"}
CAPITALISE_FROM = 2_000_000   # paisa: items of BDT 20,000 or more are assets, cheaper ones are expenses


def ensure_chart(db: Session, property_id: int) -> dict[str, Account]:
    have = {a.code: a for a in db.scalars(select(Account).where(Account.property_id == property_id))}
    for code, name, bn, typ in CHART:
        if code not in have:
            a = Account(property_id=property_id, code=code, name=name, name_bn=bn, type=typ)
            db.add(a)
            have[code] = a
    db.flush()
    return have


def post(db: Session, property_id: int, on: date, memo: str, lines: list[tuple[str, int, int]], source: str, source_id, user_id: int | None = None) -> Journal | None:
    """lines are (account code, debit, credit). Refuses an unbalanced entry. A second post for the same source does nothing."""
    if sum(d for _, d, _ in lines) != sum(c for _, _, c in lines) or not any(d or c for _, d, c in lines):
        raise ValueError("Journal entry does not balance")
    sid = str(source_id)
    if db.scalar(select(Journal.id).where(Journal.property_id == property_id, Journal.source == source, Journal.source_id == sid)):
        return None
    acc = ensure_chart(db, property_id)
    j = Journal(property_id=property_id, date=on, memo=memo[:200], source=source, source_id=sid, created_by=user_id)
    db.add(j)
    db.flush()
    for code, d, c in lines:
        if d or c:
            db.add(JournalLine(journal_id=j.id, account_id=acc[code].id, debit=d, credit=c))
    db.flush()
    return j


def balances(db: Session, property_id: int, start: date | None = None, end: date | None = None) -> dict[str, dict]:
    """Per account: debit total, credit total. Optional date range."""
    stmt = (select(Account.code, Account.name, Account.name_bn, Account.type, func.coalesce(func.sum(JournalLine.debit), 0), func.coalesce(func.sum(JournalLine.credit), 0))
            .select_from(Account).outerjoin(JournalLine, JournalLine.account_id == Account.id).outerjoin(Journal, Journal.id == JournalLine.journal_id)
            .where(Account.property_id == property_id).group_by(Account.id))
    if start:
        stmt = stmt.where((Journal.id.is_(None)) | (Journal.date >= start))
    if end:
        stmt = stmt.where((Journal.id.is_(None)) | (Journal.date <= end))
    return {code: {"code": code, "name": n, "name_bn": nb, "type": t, "debit": int(d), "credit": int(c)} for code, n, nb, t, d, c in db.execute(stmt)}
