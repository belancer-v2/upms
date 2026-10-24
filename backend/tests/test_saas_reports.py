import csv
import io

from conftest import login

from app.db import SessionLocal
from app.models.saas_reports import SaasNumberSeq
from app.services import saas_docs as docs


def H(client, who):
    return login(client, who)[0]


def test_amount_in_words_english_and_bangla():
    assert docs.amount_in_words(0, "en") == "Zero Taka Only"
    assert docs.amount_in_words(100, "en") == "One Taka Only"
    assert docs.amount_in_words(12_000_000, "en") == "One Lakh Twenty Thousand Taka Only"
    assert docs.amount_in_words(125_050, "en") == "One Thousand Two Hundred Fifty Taka and Fifty Paisa Only"
    assert docs.amount_in_words(1_234_567_800, "en") == "One Crore Twenty Three Lakh Forty Five Thousand Six Hundred Seventy Eight Taka Only"
    assert docs.amount_in_words(50, "en") == "Fifty Paisa Only"
    assert docs.amount_in_words(12_000_000, "bn") == "এক লাখ বিশ হাজার টাকা মাত্র"
    assert docs.amount_in_words(125_050, "bn") == "এক হাজার দুইশ পঞ্চাশ টাকা পঞ্চাশ পয়সা মাত্র"
    assert docs.amount_in_words(450_000, "bn") == "চার হাজার পাঁচশ টাকা মাত্র"
    assert docs.amount_in_words(1_234_567_800, "bn") == "এক কোটি তেইশ লাখ পঁয়তাল্লিশ হাজার ছয়শ আটাত্তর টাকা মাত্র"
    assert docs.amount_in_words(2_100, "bn") == "একুশ টাকা মাত্র"


def test_vat_split_adds_up():
    for total in (1, 99, 150_000, 345_678, 7_500_000):
        net, vat = docs.split_vat(total, 15)
        assert net + vat == total and abs(vat - total * 15 / 115) <= 0.5


def test_mrr_equals_sum_of_active_monthly_prices(client):
    h = H(client, "finance")
    live = client.get("/api/saas/overview", headers=h).json()["mrr"]
    r = client.get("/api/saas/reports/mrr", headers=h).json()
    assert live > 0 and r["current_mrr"] == live and r["current_arr"] == live * 12
    assert r["series"][-1]["end"] == live  # history ends where the live subscriptions are
    assert sum(p["amount"] for p in r["by_plan"]) == live


def test_mrr_movement_categories_add_up(client):
    series = client.get("/api/saas/reports/mrr", headers=H(client, "finance")).json()["series"]
    assert len(series) == 12
    for a, b in zip(series, series[1:]):
        assert a["end"] == b["start"]
    for row in series:
        assert row["start"] + row["new"] + row["expansion"] - row["contraction"] - row["churn"] == row["end"]
        assert row["net"] == row["end"] - row["start"]
    assert sum(r["new"] for r in series) > 0 and sum(r["churn"] for r in series) > 0
    assert sum(r["expansion"] for r in series) > 0 and sum(r["contraction"] for r in series) > 0


def test_filters_narrow_the_numbers(client):
    h = H(client, "finance")
    all_ = client.get("/api/saas/reports/mrr", headers=h).json()["current_mrr"]
    only = client.get("/api/saas/reports/mrr?plan=pro", headers=h).json()["current_mrr"]
    city = client.get("/api/saas/reports/mrr?city=Chattogram", headers=h).json()["current_mrr"]
    assert 0 < only < all_ and 0 < city < all_
    assert client.get("/api/saas/reports/revenue?from=2026-10-01&to=2026-01-01", headers=h).status_code == 422


def test_revenue_collections_customers_credits_shapes(client):
    h = H(client, "finance")
    rev = client.get("/api/saas/reports/revenue", headers=h).json()
    assert len(rev["series"]) == 12 and rev["totals"]["billed"] > rev["totals"]["collected"] > 0
    assert rev["totals"]["billed"] == rev["totals"]["subscription"] + rev["totals"]["credits"] + rev["totals"]["setup"]
    assert sum(p["amount"] for p in rev["by_plan"]) == rev["totals"]["billed"]
    col = client.get("/api/saas/reports/collections", headers=h).json()
    assert sum(b["amount"] for b in col["buckets"]) == col["outstanding"] and col["top_overdue"]
    cu = client.get("/api/saas/reports/customers", headers=h).json()
    assert cu["counts"]["churned"] >= 3 and cu["counts"]["trial"] >= 3 and cu["conversion_pct"] is not None and cu["arpb"] > 0 and cu["arpf"] > 0
    cr = client.get("/api/saas/reports/credits", headers=h).json()
    assert cr["sms"]["totals"]["consumed"] > 0 and "email" in cr


def test_funnel_conversion_and_sales_access(client):
    d = client.get("/api/saas/reports/funnel", headers=H(client, "sales")).json()
    reached = [s["reached"] for s in d["stages"]]
    assert reached == sorted(reached, reverse=True) and reached[0] <= d["total"]
    assert d["by_source"] and any(s["avg_days"] is not None for s in d["stages"])
    assert sum(x["total"] for x in d["by_source"]) == d["total"]


def test_building_health_is_paged_and_searchable(client):
    h = H(client, "finance")
    p1 = client.get("/api/saas/reports/health?size=5&page=1", headers=h).json()
    p2 = client.get("/api/saas/reports/health?size=5&page=2", headers=h).json()
    assert p1["total"] >= 12 and len(p1["rows"]) == 5 and p1["rows"][0]["id"] != p2["rows"][0]["id"]
    q = client.get("/api/saas/reports/health?q=rupayan", headers=h).json()
    assert q["total"] == 1 and q["rows"][0]["last_login"] and q["rows"][0]["last_paid"]


def test_csv_has_bom_and_columns(client):
    h = H(client, "finance")
    r = client.get("/api/saas/reports/revenue/csv", headers=h)
    assert r.status_code == 200 and r.content.startswith(b"\xef\xbb\xbf") and "text/csv" in r.headers["content-type"]
    rows = list(csv.reader(io.StringIO(r.content.decode("utf-8-sig"))))
    assert rows[0] == ["month", "billed_bdt", "collected_bdt", "subscription_bdt", "credit_sales_bdt", "setup_bdt", "refunds_bdt"]
    assert len(rows) > 13
    mrr = client.get("/api/saas/reports/mrr/csv", headers=h).content.decode("utf-8-sig").splitlines()[0]
    assert mrr.startswith("month,opening_mrr_bdt,new_bdt")
    health = client.get("/api/saas/reports/health/csv", headers=h)
    assert health.content.startswith(b"\xef\xbb\xbf") and len(health.content.decode("utf-8-sig").splitlines()) > 12  # every row, not one page


def test_role_matrix(client):
    money = ["revenue", "mrr", "customers", "collections", "credits", "health"]
    expect = {"super": (True, True), "admin": (True, True), "finance": (True, False), "sales": (False, True), "support": (False, False)}
    for who, (m, f) in expect.items():
        h = H(client, who)
        for name in money:
            assert client.get(f"/api/saas/reports/{name}", headers=h).status_code == (200 if m else 403), (who, name)
        assert client.get("/api/saas/reports/funnel", headers=h).status_code == (200 if f else 403), who
        assert client.get("/api/saas/reports/revenue/csv", headers=h).status_code == (200 if m else 403)
        assert client.get("/api/saas/invoices-doc/settings", headers=h).status_code == (200 if m else 403), who
    assert client.get("/api/saas/reports/revenue").status_code == 401
    assert client.get("/api/saas/reports/revenue", headers=H(client, "owner")).status_code == 403
    assert client.get("/api/saas/reports/meta", headers=H(client, "sales")).json()["reports"] == ["funnel"]


def test_numbering_is_sequential_and_gap_free(client):
    h = H(client, "finance")
    for n in (300, 400, 500):
        org = client.get("/api/saas/orgs", headers=h).json()[1]["id"]
        client.post(f"/api/saas/orgs/{org}/sms", headers=h, json={"count": n, "reason": "SMS pack"})
    client.post("/api/saas/invoices/run", headers=h, json={"period": "2027-03"})
    first = client.post("/api/saas/invoices-doc/issue-pending", headers=h).json()
    assert first["issued"] >= 5
    again = client.post("/api/saas/invoices-doc/issue-pending", headers=h).json()
    assert again["issued"] == 0  # repeated calls never burn a number
    nums = [int(x.rsplit("-", 1)[1]) for x in first["numbers"]]
    assert nums == list(range(nums[0], nums[0] + len(nums)))
    assert all(x.startswith("INV-2026-") and len(x.rsplit("-", 1)[1]) == 6 for x in first["numbers"])
    inv = client.get("/api/saas/invoices", headers=h).json()[0]
    a = client.post(f"/api/saas/invoices-doc/{inv['id']}/issue", headers=h).json()
    b = client.post(f"/api/saas/invoices-doc/{inv['id']}/issue", headers=h).json()
    assert a["doc_no"] == b["doc_no"] and a["issued"]
    with SessionLocal() as db:  # every number from 1 to the counter exists exactly once
        last = db.get(SaasNumberSeq, ("INV", 2026)).last
        from sqlalchemy import select
        from app.models.saas_reports import SaasInvoiceDoc
        seqs = sorted(db.scalars(select(SaasInvoiceDoc.seq).where(SaasInvoiceDoc.fy == 2026)))
        assert seqs == list(range(1, last + 1))


def test_rolled_back_issue_gives_the_number_back():
    with SessionLocal() as db:
        n1 = docs.next_number(db, "XT", 2026)
        db.rollback()
        n2 = docs.next_number(db, "XT", 2026)
        db.commit()
        assert n1 == n2 == 1
        assert docs.next_number(db, "XT", 2026) == 2
        db.commit()


def test_doc_content_totals_and_stamp(client):
    h = H(client, "finance")
    inv = client.get("/api/saas/invoices?status=paid", headers=h).json()[0]
    d = client.post(f"/api/saas/invoices-doc/{inv['id']}/issue", headers=h).json()
    assert d["stamp"] == "paid" and d["subtotal"] + d["vat"] == d["total"] == inv["amount"] and d["vat_pct"] == 15
    assert sum(i["net"] for i in d["items"]) == d["subtotal"]
    assert d["words_en"].endswith("Only") and d["words_bn"].endswith("মাত্র")
    assert d["company"]["bin_no"] and d["payment"]["reference"] == inv["number"] and d["customer"]["name"]
    r = client.put(f"/api/saas/invoices-doc/{inv['id']}/lang", headers=h, json={"lang": "bn"}).json()
    assert r["lang"] == "bn"


def test_void_creates_credit_note_and_keeps_invoice_row(client):
    h = H(client, "finance")
    org = client.get("/api/saas/orgs", headers=h).json()[2]["id"]
    client.post(f"/api/saas/orgs/{org}/sms", headers=h, json={"count": 1000, "reason": "SMS pack"})
    inv = [i for i in client.get("/api/saas/invoices?status=issued", headers=h).json() if i["org_id"] == org and i["kind"] == "sms"][0]
    before = len(client.get("/api/saas/invoices", headers=h).json())
    assert client.post(f"/api/saas/invoices/{inv['id']}/void", headers=h, json={}).status_code == 200  # the existing console button
    rows = client.get("/api/saas/invoices", headers=h).json()
    assert len(rows) == before and [r for r in rows if r["id"] == inv["id"]][0]["status"] == "void"
    d = client.get(f"/api/saas/invoices-doc/{inv['id']}", headers=h).json()
    assert d["stamp"] == "void" and d["issued"] and len(d["credit_notes"]) == 1
    cn = d["credit_notes"][0]
    assert cn["doc_no"].startswith("CN-2026-") and len(cn["doc_no"].rsplit("-", 1)[1]) == 4 and cn["amount"] == inv["amount"]
    page = client.get(f"/api/saas/invoices-doc/credit-note/{cn['id']}", headers=h).json()
    assert page["invoice_no"] == d["doc_no"] and page["net"] + page["vat"] == page["amount"]
    assert client.post(f"/api/saas/invoices/{inv['id']}/void", headers=h, json={}).status_code == 422
    st = client.get(f"/api/saas/invoices-doc/statement/{org}", headers=h).json()
    assert any(r["type"] == "credit_note" and r["ref"] == cn["doc_no"] for r in st["rows"])
    assert any(r["type"] == "invoice" and r["ref"] == d["doc_no"] for r in st["rows"])


def test_void_through_doc_endpoint_and_refund(client):
    h = H(client, "finance")
    org = client.get("/api/saas/orgs", headers=h).json()[3]["id"]
    client.post(f"/api/saas/orgs/{org}/sms", headers=h, json={"count": 200, "reason": "SMS pack"})
    inv = [i for i in client.get("/api/saas/invoices?status=issued", headers=h).json() if i["org_id"] == org and i["kind"] == "sms"][-1]
    d = client.post(f"/api/saas/invoices-doc/{inv['id']}/void", headers=h, json={"reason": "Wrong customer"}).json()
    assert d["stamp"] == "void" and d["credit_notes"][0]["reason"] == "Wrong customer"
    # refund needs a paid invoice and cannot exceed it
    client.post(f"/api/saas/orgs/{org}/sms", headers=h, json={"count": 100, "reason": "SMS pack"})
    inv2 = [i for i in client.get("/api/saas/invoices?status=issued", headers=h).json() if i["org_id"] == org and i["kind"] == "sms"][-1]
    assert client.post(f"/api/saas/invoices-doc/{inv2['id']}/refund", headers=h, json={}).status_code == 422
    client.post(f"/api/saas/invoices/{inv2['id']}/pay", headers=h, json={"method": "bkash", "trx_id": "TXR1"})
    r = client.post(f"/api/saas/invoices-doc/{inv2['id']}/refund", headers=h, json={"amount": inv2["amount"] // 2, "reason": "Half back"}).json()
    assert r["stamp"] == "paid" and r["credited"] == inv2["amount"] // 2 and r["credit_notes"][0]["kind"] == "refund"
    assert client.post(f"/api/saas/invoices-doc/{inv2['id']}/refund", headers=h, json={"amount": inv2["amount"]}).status_code == 422


def test_statement_running_balance(client):
    h = H(client, "finance")
    org = [o for o in client.get("/api/saas/orgs", headers=h).json() if o["name"].startswith("Moon View")][0]["id"]
    st = client.get(f"/api/saas/invoices-doc/statement/{org}", headers=h).json()
    bal = 0
    for r in st["rows"]:
        bal += r["debit"] - r["credit"]
        assert r["balance"] == bal
    unpaid = sum(i["amount"] for i in client.get("/api/saas/invoices", headers=h).json() if i["org_id"] == org and i["status"] in ("issued", "overdue"))
    assert st["balance"] == bal == unpaid > 0
    csv_ = client.get(f"/api/saas/invoices-doc/statement/{org}/csv", headers=h)
    assert csv_.content.startswith(b"\xef\xbb\xbf") and csv_.content.decode("utf-8-sig").startswith("date,type,reference")


def test_settings_admin_only_edit_and_audited(client):
    ha, hf = H(client, "admin"), H(client, "finance")
    cur = client.get("/api/saas/invoices-doc/settings", headers=hf).json()
    assert cur["default_vat_pct"] == 15 and cur["invoice_prefix"] == "INV" and cur["next_number"] >= 1
    assert client.put("/api/saas/invoices-doc/settings", headers=hf, json={"tin": "999"}).status_code == 403
    assert client.put("/api/saas/invoices-doc/settings", headers=H(client, "sales"), json={"tin": "999"}).status_code == 403
    r = client.put("/api/saas/invoices-doc/settings", headers=ha, json={"tin": "555000111", "footer_text": "Pay within 10 days."})
    assert r.status_code == 200 and r.json()["tin"] == "555000111"
    assert client.put("/api/saas/invoices-doc/settings", headers=ha, json={"default_vat_pct": 150}).status_code == 422
    assert client.put("/api/saas/invoices-doc/settings", headers=ha, json={"next_number": 1}).status_code == 422  # never backwards
    nxt = cur["next_number"] + 10
    assert client.put("/api/saas/invoices-doc/settings", headers=ha, json={"next_number": nxt}).json()["next_number"] == nxt
    audit = client.get("/api/audit", headers=ha)
    if audit.status_code == 200:
        body = audit.text
        assert "saas.settings.edit" in body


def test_issue_and_void_are_audited():
    from sqlalchemy import select
    from app.models.core import AuditLog
    with SessionLocal() as db:
        acts = set(db.scalars(select(AuditLog.action).where(AuditLog.action.like("saas.%"))))
    assert {"saas.settings.edit", "saas.invoice.issue", "saas.invoice.void", "saas.creditnote.void"} <= acts


def test_email_action_is_safe(client):
    h = H(client, "finance")
    inv = client.get("/api/saas/invoices", headers=h).json()[0]
    r = client.post(f"/api/saas/invoices-doc/{inv['id']}/email", headers=h)
    assert r.status_code == 200 and "sent" in r.json()


def test_history_events_written_on_plan_change_and_status(client):
    ha = H(client, "admin")
    org = [o for o in client.get("/api/saas/orgs", headers=ha).json() if o["name"].startswith("Dream Nest")][0]["id"]
    from app.models.saas_reports import SubscriptionEvent
    from sqlalchemy import select, func
    def count():
        with SessionLocal() as db:
            return db.scalar(select(func.count()).select_from(SubscriptionEvent).where(SubscriptionEvent.org_id == org))
    n = count()
    client.post(f"/api/saas/orgs/{org}/plan", headers=ha, json={"plan": "pro", "band": "M", "cycle": "monthly"})
    assert count() == n + 1
    client.post(f"/api/saas/orgs/{org}/status", headers=ha, json={"status": "active"})
    assert count() == n + 2
    client.post(f"/api/saas/orgs/{org}/status", headers=ha, json={"status": "suspended"})
    with SessionLocal() as db:
        last = db.scalars(select(SubscriptionEvent).where(SubscriptionEvent.org_id == org).order_by(SubscriptionEvent.id.desc())).first()
        assert last.kind == "suspend" and last.mrr == 0
