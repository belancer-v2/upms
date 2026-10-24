"""M21 SaaS reports console and FlatWise tax invoices.

/api/saas/reports/*       money reports for finance and admins, the lead funnel also for sales
/api/saas/invoices-doc/*  tax-invoice documents, credit notes, statements and the invoice settings
All money is integer paisa. CSV files are UTF-8 with a BOM so Excel shows Bangla correctly.
"""
import csv
import importlib
import importlib.util
import io
import re
from datetime import date, datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..audit import audit
from ..db import get_db
from ..deps import current_user, require_saas
from ..models.core import AuditLog, Membership, Organization, Property, User, now
from ..models.saas import BANDS, Lead, Plan, SaasInvoice, SmsLedger, Subscription, band_for
from ..models.saas_reports import LeadStageEvent, SaasCreditNote, SaasInvoiceDoc, SaasSettings, SubscriptionEvent
from ..services import saas_docs as docs
from ..services.entitlements import org_features, sms_balance

MONEY = ("SUPER_ADMIN", "SAAS_ADMIN", "SAAS_FINANCE")
ADMINISH = ("SUPER_ADMIN", "SAAS_ADMIN")
LEADERS = ("SUPER_ADMIN", "SAAS_ADMIN", "SAAS_SALES")
REPORTS = ["revenue", "mrr", "customers", "collections", "credits", "funnel", "health"]
STAGES = ["new", "contacted", "demo", "trial", "won"]

router = APIRouter(prefix="/api/saas/reports", tags=["saas-reports"], dependencies=[Depends(require_saas())])
doc_router = APIRouter(prefix="/api/saas/invoices-doc", tags=["saas-invoice-docs"], dependencies=[Depends(require_saas())])


def _aware(dt):
    return dt.replace(tzinfo=timezone.utc) if dt is not None and dt.tzinfo is None else dt


def _month_start(d: date) -> date:
    return d.replace(day=1)


def _add_month(d: date, n: int = 1) -> date:
    y, m = divmod(d.year * 12 + d.month - 1 + n, 12)
    return date(y, m + 1, 1)


def _dt(d: date) -> datetime:
    return datetime(d.year, d.month, d.day, tzinfo=timezone.utc)


class Flt:
    """Date range and plan / band / city filters shared by every report."""
    def __init__(self, start: date, end: date, plan: str = "", band: str = "", city: str = "", source: str = ""):
        self.start, self.end, self.plan, self.band, self.city, self.source = start, end, plan, band, city, source
        self.t0 = _dt(start)
        self.t1 = _dt(end + timedelta(days=1))
        self.months = []
        m = _month_start(start)
        while m <= end:
            self.months.append(m)
            m = _add_month(m)

    def key(self, m: date) -> str:
        return f"{m:%Y-%m}"


def _filters(from_: str, to: str, plan: str, band: str, city: str, source: str = "") -> Flt:
    today = now().date()
    try:
        end = date.fromisoformat(to) if to else today
        start = date.fromisoformat(from_) if from_ else _add_month(_month_start(end), -11)
    except ValueError:
        raise HTTPException(422, "Dates must look like 2026-10-24")
    if start > end or (end - start).days > 1830:
        raise HTTPException(422, "Pick a valid date range of up to 5 years")
    return Flt(start, end, plan, band, city, source)


def _orgs(db: Session, f: Flt) -> dict[int, tuple[Organization, Subscription | None]]:
    out = {}
    subs = {}
    for s in db.scalars(select(Subscription).order_by(Subscription.id)):
        subs[s.org_id] = s
    for o in db.scalars(select(Organization).order_by(Organization.id)):
        s = subs.get(o.id)
        if f.city and o.city != f.city:
            continue
        if f.plan and (not s or s.plan_key != f.plan):
            continue
        if f.band and (not s or s.band != f.band):
            continue
        out[o.id] = (o, s)
    return out


def _events(db: Session, org_ids, orgs) -> dict[int, list[SubscriptionEvent]]:
    """Per organization history, oldest first. An organization without history gets one synthetic row from its current subscription."""
    ev: dict[int, list] = {i: [] for i in org_ids}
    for e in db.scalars(select(SubscriptionEvent).where(SubscriptionEvent.org_id.in_(list(org_ids)) if org_ids else False).order_by(SubscriptionEvent.at, SubscriptionEvent.id)):
        ev[e.org_id].append(e)
    for i in org_ids:
        s = orgs[i][1]
        if not ev[i] and s:
            live = s.status in ("active", "past_due")
            ev[i].append(SubscriptionEvent(org_id=i, at=s.started_at, kind="activate" if live else "trial_start", plan_key=s.plan_key, band=s.band, cycle=s.cycle,
                                           status=s.status, mrr=docs.monthly_price_of(db, s) if live else 0))
    return ev


def _state_at(evs: list, t: datetime):
    last = None
    for e in evs:
        if _aware(e.at) <= t:
            last = e
        else:
            break
    return last


def _mrr_at(evs: list, t: datetime) -> int:
    e = _state_at(evs, t)
    return e.mrr if e else 0


# ================================================================= report builders
def rep_revenue(db: Session, f: Flt):
    orgs = _orgs(db, f)
    ev = _events(db, orgs.keys(), orgs)
    rows = {f.key(m): {"month": f.key(m), "billed": 0, "collected": 0, "subscription": 0, "credits": 0, "setup": 0, "refunds": 0} for m in f.months}
    by_plan: dict[str, int] = {}
    by_city: dict[str, int] = {}
    for i in db.scalars(select(SaasInvoice).where(SaasInvoice.org_id.in_(list(orgs)) if orgs else False)):
        issued = _aware(i.issued_at)
        bucket = i.kind if i.kind in ("subscription", "setup") else "credits"
        if i.status != "void" and f.t0 <= issued < f.t1:
            r = rows.get(f"{issued:%Y-%m}")
            if r:
                r["billed"] += i.amount
                r[bucket] += i.amount
            st = _state_at(ev.get(i.org_id, []), issued)
            pk = (st.plan_key if st and st.plan_key else (orgs[i.org_id][1].plan_key if orgs[i.org_id][1] else "none")) or "none"
            by_plan[pk] = by_plan.get(pk, 0) + i.amount
            c = orgs[i.org_id][0].city
            by_city[c] = by_city.get(c, 0) + i.amount
        if i.status == "paid" and i.paid_at and f.t0 <= _aware(i.paid_at) < f.t1:
            r = rows.get(f"{_aware(i.paid_at):%Y-%m}")
            if r:
                r["collected"] += i.amount
    for cn in db.scalars(select(SaasCreditNote).where(SaasCreditNote.kind == "refund", SaasCreditNote.org_id.in_(list(orgs)) if orgs else False)):
        r = rows.get(f"{_aware(cn.issued_at):%Y-%m}")
        if r:
            r["refunds"] += cn.amount
            r["collected"] -= cn.amount
    series = list(rows.values())
    tot = {k: sum(r[k] for r in series) for k in ("billed", "collected", "subscription", "credits", "setup", "refunds")}
    data = {"series": series, "totals": tot, "by_plan": [{"key": k, "amount": v} for k, v in sorted(by_plan.items(), key=lambda x: -x[1])],
            "by_city": [{"key": k, "amount": v} for k, v in sorted(by_city.items(), key=lambda x: -x[1])]}
    cols = ["month", "billed_bdt", "collected_bdt", "subscription_bdt", "credit_sales_bdt", "setup_bdt", "refunds_bdt"]
    csv_rows = [[r["month"], *[_bdt(r[k]) for k in ("billed", "collected", "subscription", "credits", "setup", "refunds")]] for r in series]
    csv_rows += [["TOTAL", *[_bdt(tot[k]) for k in ("billed", "collected", "subscription", "credits", "setup", "refunds")]]]
    csv_rows += [[f"plan:{p['key']}", _bdt(p["amount"]), "", "", "", "", ""] for p in data["by_plan"]]
    csv_rows += [[f"city:{c['key']}", _bdt(c["amount"]), "", "", "", "", ""] for c in data["by_city"]]
    return data, cols, csv_rows


def mrr_series(db: Session, f: Flt, orgs=None):
    orgs = orgs if orgs is not None else _orgs(db, f)
    ev = _events(db, orgs.keys(), orgs)
    out = []
    clock = now()
    for m in f.months:
        a, b = _dt(m), min(_dt(_add_month(m)), clock)
        row = {"month": f.key(m), "start": 0, "new": 0, "expansion": 0, "contraction": 0, "churn": 0, "end": 0,
               "customers_end": 0, "new_n": 0, "churn_n": 0}
        for i in orgs:
            s, e = _mrr_at(ev[i], a), _mrr_at(ev[i], b)
            row["start"] += s
            row["end"] += e
            row["customers_end"] += 1 if e else 0
            if s == 0 and e > 0:
                row["new"] += e
                row["new_n"] += 1
            elif s > 0 and e == 0:
                row["churn"] += s
                row["churn_n"] += 1
            elif e > s > 0:
                row["expansion"] += e - s
            elif 0 < e < s:
                row["contraction"] += s - e
        row["arr"] = row["end"] * 12
        row["net"] = row["new"] + row["expansion"] - row["contraction"] - row["churn"]
        out.append(row)
    return out


def rep_mrr(db: Session, f: Flt):
    orgs = _orgs(db, f)
    series = mrr_series(db, f, orgs)
    by_plan: dict[str, int] = {}
    for o, s in orgs.values():
        if s and s.status in ("active", "past_due"):
            by_plan[s.plan_key] = by_plan.get(s.plan_key, 0) + docs.monthly_price_of(db, s)
    cur = sum(by_plan.values())
    data = {"series": series, "current_mrr": cur, "current_arr": cur * 12, "by_plan": [{"key": k, "amount": v} for k, v in sorted(by_plan.items())],
            "totals": {k: sum(r[k] for r in series) for k in ("new", "expansion", "contraction", "churn")}}
    cols = ["month", "opening_mrr_bdt", "new_bdt", "expansion_bdt", "contraction_bdt", "churn_bdt", "closing_mrr_bdt", "arr_bdt", "customers_end"]
    csv_rows = [[r["month"], _bdt(r["start"]), _bdt(r["new"]), _bdt(r["expansion"]), _bdt(r["contraction"]), _bdt(r["churn"]), _bdt(r["end"]), _bdt(r["arr"]), r["customers_end"]] for r in series]
    return data, cols, csv_rows


def rep_customers(db: Session, f: Flt):
    orgs = _orgs(db, f)
    ev = _events(db, orgs.keys(), orgs)
    counts = {"active": 0, "past_due": 0, "trial": 0, "suspended": 0, "churned": 0}
    mrr = flats = buildings = 0
    by_plan: dict[str, dict] = {}
    for oid, (o, s) in orgs.items():
        if not s:
            continue
        key = "churned" if s.status == "cancelled" else s.status
        counts[key] = counts.get(key, 0) + 1
        if s.status in ("active", "past_due"):
            p = docs.monthly_price_of(db, s)
            props = db.scalar(select(func.count()).select_from(Property).where(Property.org_id == oid)) or 1
            mrr, flats, buildings = mrr + p, flats + s.flats, buildings + props
            d = by_plan.setdefault(s.plan_key, {"key": s.plan_key, "customers": 0, "mrr": 0})
            d["customers"] += 1
            d["mrr"] += p
    started = converted = churned_in = 0
    for oid in orgs:
        evs = ev[oid]
        trial = next((e for e in evs if e.kind == "trial_start" and f.t0 <= _aware(e.at) < f.t1), None)
        if trial:
            started += 1
            if any(e.kind == "activate" and _aware(e.at) >= _aware(trial.at) for e in evs):
                converted += 1
        churned_in += sum(1 for e in evs if e.kind in ("suspend", "cancel") and f.t0 <= _aware(e.at) < f.t1)
    data = {"counts": counts, "total": len(orgs), "trials_started": started, "trials_converted": converted,
            "conversion_pct": round(converted * 100 / started, 1) if started else None, "churn_events": churned_in,
            "mrr": mrr, "buildings_paying": buildings, "flats_paying": flats,
            "arpb": round(mrr / buildings) if buildings else 0, "arpf": round(mrr / flats) if flats else 0,
            "by_plan": sorted(by_plan.values(), key=lambda x: x["key"])}
    cols = ["metric", "value"]
    csv_rows = [[k, v] for k, v in counts.items()] + [["trials_started", started], ["trials_converted", converted], ["trial_to_paid_pct", data["conversion_pct"] if started else ""],
                                                      ["mrr_bdt", _bdt(mrr)], ["avg_revenue_per_building_bdt", _bdt(data["arpb"])], ["avg_revenue_per_flat_bdt", _bdt(data["arpf"])]]
    csv_rows += [[f"plan:{p['key']}:customers", p["customers"]] for p in data["by_plan"]]
    return data, cols, csv_rows


BUCKETS = [("current", None, 0), ("d1_30", 1, 30), ("d31_60", 31, 60), ("d61_90", 61, 90), ("d90p", 91, None)]


def rep_collections(db: Session, f: Flt):
    orgs = _orgs(db, f)
    clock = now()
    buckets = {k: {"key": k, "count": 0, "amount": 0} for k, _, _ in BUCKETS}
    per: dict[int, dict] = {}
    for i in db.scalars(select(SaasInvoice).where(SaasInvoice.status.in_(("issued", "pending")), SaasInvoice.org_id.in_(list(orgs)) if orgs else False)):
        days = (clock - _aware(i.due_at)).days
        k = "current" if days <= 0 else "d1_30" if days <= 30 else "d31_60" if days <= 60 else "d61_90" if days <= 90 else "d90p"
        buckets[k]["count"] += 1
        buckets[k]["amount"] += i.amount
        if days > 0:
            d = per.setdefault(i.org_id, {"org_id": i.org_id, "name": orgs[i.org_id][0].name, "city": orgs[i.org_id][0].city, "invoices": 0, "amount": 0, "oldest_days": 0})
            d["invoices"] += 1
            d["amount"] += i.amount
            d["oldest_days"] = max(d["oldest_days"], days)
    top = sorted(per.values(), key=lambda x: (-x["amount"], x["org_id"]))[:10]
    out_total = sum(b["amount"] for b in buckets.values())
    data = {"outstanding": out_total, "overdue": out_total - buckets["current"]["amount"], "count": sum(b["count"] for b in buckets.values()),
            "buckets": list(buckets.values()), "top_overdue": top}
    cols = ["bucket", "invoices", "amount_bdt"]
    csv_rows = [[b["key"], b["count"], _bdt(b["amount"])] for b in data["buckets"]] + [["TOTAL", data["count"], _bdt(out_total)]]
    csv_rows += [[f"overdue:{t['name']}", t["invoices"], _bdt(t["amount"])] for t in top]
    return data, cols, csv_rows


def _email_rows(db: Session, org_ids):
    """EmailLedger belongs to another module. Used only if it exists with the columns we need."""
    try:
        mod = importlib.import_module("app.models.credits")
        L = getattr(mod, "EmailLedger", None)
        if L is None or not all(hasattr(L, c) for c in ("org_id", "delta", "reason", "at")):
            return None
        return [(r.org_id, r.delta, r.reason, _aware(r.at)) for r in db.scalars(select(L)) if r.org_id in org_ids]
    except Exception:
        return None


def _split_ledger(rows, f: Flt):
    series = {f.key(m): {"month": f.key(m), "purchased": 0, "allowance": 0, "consumed": 0} for m in f.months}
    per: dict[int, int] = {}
    for org_id, delta, reason, at in rows:
        if not (f.t0 <= at < f.t1):
            continue
        r = series.get(f"{at:%Y-%m}")
        if not r:
            continue
        low = (reason or "").lower()
        if delta < 0:
            r["consumed"] += -delta
            per[org_id] = per.get(org_id, 0) - delta
        elif low.startswith("opening"):
            pass
        elif low.startswith("monthly allowance"):
            r["allowance"] += delta
        else:
            r["purchased"] += delta
    return list(series.values()), per


def rep_credits(db: Session, f: Flt):
    orgs = _orgs(db, f)
    ids = set(orgs)
    sms_rows = [(l.org_id, l.delta, l.reason, _aware(l.at)) for l in db.scalars(select(SmsLedger)) if l.org_id in ids]
    sms, per = _split_ledger(sms_rows, f)
    sales = {f.key(m): 0 for m in f.months}
    for i in db.scalars(select(SaasInvoice).where(SaasInvoice.kind.notin_(("subscription", "setup")), SaasInvoice.status != "void", SaasInvoice.org_id.in_(list(ids)) if ids else False)):
        if f.t0 <= _aware(i.issued_at) < f.t1:
            sales[f"{_aware(i.issued_at):%Y-%m}"] += i.amount
    for r in sms:
        r["sales"] = sales[r["month"]]
    top = sorted(({"org_id": k, "name": orgs[k][0].name, "consumed": v, "balance": sms_balance(db, k)} for k, v in per.items()), key=lambda x: (-x["consumed"], x["org_id"]))[:10]
    low = sorted(({"org_id": k, "name": orgs[k][0].name, "balance": sms_balance(db, k)} for k in ids if orgs[k][1] and orgs[k][1].status in ("active", "past_due", "trial")), key=lambda x: x["balance"])[:5]
    email = None
    er = _email_rows(db, ids)
    if er is not None:
        es, _ = _split_ledger(er, f)
        email = {"series": es}
    data = {"sms": {"series": sms, "totals": {k: sum(r[k] for r in sms) for k in ("purchased", "allowance", "consumed", "sales")}}, "email": email,
            "top_consumers": top, "lowest_balance": low}
    cols = ["month", "channel", "credits_sold", "allowance_granted", "consumed", "credit_sales_bdt"]
    csv_rows = [[r["month"], "sms", r["purchased"], r["allowance"], r["consumed"], _bdt(r["sales"])] for r in sms]
    if email:
        csv_rows += [[r["month"], "email", r["purchased"], r["allowance"], r["consumed"], ""] for r in email["series"]]
    return data, cols, csv_rows


def _lead_events(db: Session, leads) -> dict[int, list]:
    ev: dict[int, list] = {l.id: [] for l in leads}
    if leads:
        for e in db.scalars(select(LeadStageEvent).where(LeadStageEvent.lead_id.in_(list(ev))).order_by(LeadStageEvent.at, LeadStageEvent.id)):
            ev[e.lead_id].append((e.status, _aware(e.at)))
    for l in leads:
        if not ev[l.id]:
            ev[l.id] = [("new", _aware(l.created_at))] + ([(l.status, _aware(l.created_at))] if l.status != "new" else [])
    return ev


def rep_funnel(db: Session, f: Flt):
    leads = [l for l in db.scalars(select(Lead).order_by(Lead.id))
             if f.t0 <= _aware(l.created_at) < f.t1 and (not f.city or l.city == f.city) and (not f.band or band_for(l.flats) == f.band) and (not f.source or l.source == f.source)]
    ev = _lead_events(db, leads)
    now_count = {s: 0 for s in STAGES + ["lost"]}
    reached = {s: 0 for s in STAGES}
    spent: dict[str, list[float]] = {s: [] for s in STAGES}
    by_source: dict[str, dict] = {}
    for l in leads:
        now_count[l.status] = now_count.get(l.status, 0) + 1
        evs = ev[l.id]
        top = max([STAGES.index(s) for s, _ in evs if s in STAGES] + [STAGES.index(l.status) if l.status in STAGES else 0])
        for s in STAGES[: top + 1]:
            reached[s] += 1
        for (s, a), (_, b) in zip(evs, evs[1:]):
            if s in spent:
                spent[s].append(max(0.0, (b - a).total_seconds() / 86400))
        d = by_source.setdefault(l.source, {"source": l.source, "total": 0, "won": 0, "lost": 0, "open": 0})
        d["total"] += 1
        d["won" if l.status == "won" else "lost" if l.status == "lost" else "open"] += 1
    stages = []
    prev = None
    for s in STAGES:
        stages.append({"stage": s, "now": now_count.get(s, 0), "reached": reached[s],
                       "conv_pct": round(reached[s] * 100 / prev, 1) if prev else None,
                       "avg_days": round(sum(spent[s]) / len(spent[s]), 1) if spent[s] else None})
        prev = reached[s] or None
    for d in by_source.values():
        d["win_pct"] = round(d["won"] * 100 / d["total"], 1) if d["total"] else 0
    total = len(leads)
    data = {"total": total, "stages": stages, "lost": now_count.get("lost", 0), "win_pct": round(now_count.get("won", 0) * 100 / total, 1) if total else None,
            "by_source": sorted(by_source.values(), key=lambda x: (-x["total"], x["source"])), "sources": sorted({l.source for l in db.scalars(select(Lead))})}
    cols = ["stage", "leads_now", "leads_reached", "conversion_from_previous_pct", "avg_days_in_stage"]
    csv_rows = [[s["stage"], s["now"], s["reached"], "" if s["conv_pct"] is None else s["conv_pct"], "" if s["avg_days"] is None else s["avg_days"]] for s in stages]
    csv_rows.append(["lost", data["lost"], "", "", ""])
    csv_rows += [[f"source:{d['source']}", d["total"], d["won"], d["win_pct"], ""] for d in data["by_source"]]
    return data, cols, csv_rows


def health_rows(db: Session, f: Flt) -> list[dict]:
    orgs = _orgs(db, f)
    clock = now()
    since30, since90 = clock - timedelta(days=30), clock - timedelta(days=90)
    members: dict[int, set[int]] = {}
    for oid, uid in db.execute(select(Membership.org_id, Membership.user_id)):
        members.setdefault(oid, set()).add(uid)
    logins = {uid: _aware(at) for uid, at in db.execute(select(AuditLog.user_id, func.max(AuditLog.at)).where(AuditLog.action == "auth.login").group_by(AuditLog.user_id))}
    props: dict[int, list[int]] = {}
    for pid, oid in db.execute(select(Property.id, Property.org_id)):
        props.setdefault(oid, []).append(pid)
    out = []
    for oid, (o, s) in orgs.items():
        mem = members.get(oid, set())
        last = max([logins[u] for u in mem if u in logins], default=None)
        active = sum(1 for u in mem if u in logins and logins[u] >= since30)
        paid = db.scalar(select(func.max(SaasInvoice.paid_at)).where(SaasInvoice.org_id == oid, SaasInvoice.status == "paid"))
        acts = db.scalars(select(AuditLog.action).where(AuditLog.at >= since90, (AuditLog.org_id == oid) | (AuditLog.property_id.in_(props.get(oid, [0]))))).all()
        areas = {a.split(".")[0] for a in acts if a.split(".")[0] not in ("auth", "saas")}
        out.append({"id": oid, "name": o.name, "city": o.city, "plan": s.plan_key if s else "", "band": s.band if s else "", "status": s.status if s else "",
                    "users": len(mem), "active_users": active, "last_login": last.isoformat() if last else None,
                    "last_paid": _aware(paid).isoformat() if paid else None, "features_on": len(org_features(db, oid)), "adopted": len(areas)})
    return out


def rep_health(db: Session, f: Flt, q: str = "", page: int = 1, size: int = 10, everything: bool = False):
    rows = health_rows(db, f)
    if q:
        rows = [r for r in rows if q.lower() in f"{r['name']} {r['city']} {r['plan']}".lower()]
    total = len(rows)
    size = max(1, min(size, 100))
    view = rows if everything else rows[(max(page, 1) - 1) * size: max(page, 1) * size]
    data = {"rows": view, "total": total, "page": page, "size": size}
    cols = ["building", "city", "plan", "status", "users", "active_users_30d", "last_login", "last_invoice_paid", "features_on", "areas_used_90d"]
    csv_rows = [[r["name"], r["city"], r["plan"], r["status"], r["users"], r["active_users"], r["last_login"] or "", r["last_paid"] or "", r["features_on"], r["adopted"]] for r in view]
    return data, cols, csv_rows


def _bdt(paisa) -> str:
    return f"{(paisa or 0) / 100:.2f}"


BUILDERS = {"revenue": rep_revenue, "mrr": rep_mrr, "customers": rep_customers, "collections": rep_collections, "credits": rep_credits, "funnel": rep_funnel}


def _allowed(user: User, name: str) -> bool:
    return user.saas_role in (LEADERS if name == "funnel" else MONEY)


def _run(name: str, user: User, db: Session, f: Flt, q="", page=1, size=10, everything=False):
    if name not in REPORTS:
        raise HTTPException(404, "Unknown report")
    if not _allowed(user, name):
        raise HTTPException(403, "Not allowed")
    if name == "health":
        return rep_health(db, f, q, page, size, everything)
    return BUILDERS[name](db, f)


@router.get("/meta")
def meta(user: User = Depends(current_user), db: Session = Depends(get_db)):
    plans = [p.key for p in db.scalars(select(Plan).order_by(Plan.sort))]
    cities = sorted({c for (c,) in db.execute(select(Organization.city))} | {c for (c,) in db.execute(select(Lead.city)) if c})
    return {"reports": [r for r in REPORTS if _allowed(user, r)], "plans": plans, "bands": [b[0] for b in BANDS], "cities": cities, "role": user.saas_role}


@router.get("/{name}")
def report(name: str, from_: str = Query("", alias="from"), to: str = "", plan: str = "", band: str = "", city: str = "", source: str = "",
           q: str = "", page: int = 1, size: int = 10, user: User = Depends(current_user), db: Session = Depends(get_db)):
    f = _filters(from_, to, plan, band, city, source)
    data, _, _ = _run(name, user, db, f, q, page, size)
    return {"report": name, "from": f.start.isoformat(), "to": f.end.isoformat(), **data}


@router.get("/{name}/csv")
def report_csv(name: str, from_: str = Query("", alias="from"), to: str = "", plan: str = "", band: str = "", city: str = "", source: str = "", q: str = "",
               user: User = Depends(current_user), db: Session = Depends(get_db)):
    f = _filters(from_, to, plan, band, city, source)
    _, cols, rows = _run(name, user, db, f, q, everything=True)
    return _csv_response(f"flatwise-{name}-{f.start}-{f.end}.csv", cols, rows)


def _csv_response(filename: str, cols, rows) -> Response:
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\r\n")
    w.writerow(cols)
    w.writerows(rows)
    return Response("﻿" + buf.getvalue(), media_type="text/csv; charset=utf-8", headers={"Content-Disposition": f'attachment; filename="{filename}"'})


# ================================================================= invoice documents
SETTING_FIELDS = ["legal_name", "legal_name_bn", "address", "address_bn", "phone", "email", "bin_no", "tin", "bank_details", "bkash_merchant", "nagad_merchant",
                  "logo_url", "footer_text", "footer_text_bn", "invoice_prefix", "credit_prefix", "default_vat_pct", "fy_start_month"]


def _settings_out(db: Session) -> dict:
    s = docs.get_settings(db)
    fy = docs.fiscal_year(now(), s.fy_start_month)
    return {**{k: getattr(s, k) for k in SETTING_FIELDS}, "fy": fy, "next_number": docs.peek_next(db, "INV", fy), "next_credit_number": docs.peek_next(db, "CN", fy),
            "next_invoice_preview": docs.fmt_number(s.invoice_prefix, fy, docs.peek_next(db, "INV", fy), 6)}


class SettingsIn(BaseModel):
    legal_name: str | None = Field(default=None, max_length=160)
    legal_name_bn: str | None = Field(default=None, max_length=160)
    address: str | None = Field(default=None, max_length=300)
    address_bn: str | None = Field(default=None, max_length=300)
    phone: str | None = Field(default=None, max_length=40)
    email: str | None = Field(default=None, max_length=120)
    bin_no: str | None = Field(default=None, max_length=40)
    tin: str | None = Field(default=None, max_length=40)
    bank_details: str | None = Field(default=None, max_length=1000)
    bkash_merchant: str | None = Field(default=None, max_length=40)
    nagad_merchant: str | None = Field(default=None, max_length=40)
    logo_url: str | None = Field(default=None, max_length=300000)
    footer_text: str | None = Field(default=None, max_length=500)
    footer_text_bn: str | None = Field(default=None, max_length=500)
    invoice_prefix: str | None = Field(default=None, pattern=r"^[A-Za-z0-9]{1,8}$")
    credit_prefix: str | None = Field(default=None, pattern=r"^[A-Za-z0-9]{1,8}$")
    default_vat_pct: float | None = Field(default=None, ge=0, le=100)
    fy_start_month: int | None = Field(default=None, ge=1, le=12)
    next_number: int | None = Field(default=None, ge=1, le=999999)


@doc_router.get("/settings")
def get_settings(user: User = Depends(require_saas(*MONEY)), db: Session = Depends(get_db)):
    out = _settings_out(db)
    db.commit()
    return out


@doc_router.put("/settings")
def put_settings(body: SettingsIn, user: User = Depends(require_saas(*ADMINISH)), db: Session = Depends(get_db)):
    s = docs.get_settings(db)
    changed = []
    for k in SETTING_FIELDS:
        v = getattr(body, k)
        if v is not None and getattr(s, k) != v:
            setattr(s, k, v.upper() if k.endswith("_prefix") else v)
            changed.append(k)
    if body.next_number is not None:
        fy = docs.fiscal_year(now(), s.fy_start_month)
        try:
            docs.set_next_number(db, "INV", fy, body.next_number)
        except ValueError:
            raise HTTPException(422, "The next number cannot be lower than a number already used")
        changed.append("next_number")
    s.updated_at = now()
    audit(db, user_id=user.id, action="saas.settings.edit", entity="saas_settings", entity_id=1, meta={"fields": changed, "vat": s.default_vat_pct, "prefix": s.invoice_prefix})
    db.commit()
    return _settings_out(db)


def _company(s: SaasSettings) -> dict:
    return {k: getattr(s, k) for k in ("legal_name", "legal_name_bn", "address", "address_bn", "phone", "email", "bin_no", "tin", "bank_details", "bkash_merchant",
                                          "nagad_merchant", "logo_url", "footer_text", "footer_text_bn")}


def _customer(db: Session, org_id: int) -> dict:
    o = db.get(Organization, org_id)
    p = db.scalar(select(Property).where(Property.org_id == org_id).order_by(Property.id))
    contacts = db.execute(select(User.name, User.email).join(Membership, Membership.user_id == User.id).where(Membership.org_id == org_id,
                          Membership.role.in_(("PROPERTY_ADMIN", "AGENCY_MANAGER", "PRESIDENT"))).order_by(Membership.id)).all()
    return {"id": org_id, "name": o.name if o else "", "name_bn": o.name_bn if o else "", "city": o.city if o else "", "address": p.address if p else "",
            "contacts": [{"name": n, "email": e} for n, e in contacts]}


def _stamp(inv: SaasInvoice) -> str:
    return "void" if inv.status == "void" else "paid" if inv.status == "paid" else "due"


def _cn_out(c: SaasCreditNote) -> dict:
    return {"id": c.id, "doc_no": c.doc_no, "kind": c.kind, "amount": c.amount, "vat": c.vat, "reason": c.reason, "issued_at": _aware(c.issued_at).isoformat()}


def _doc_out(db: Session, inv: SaasInvoice) -> dict:
    s = docs.get_settings(db)
    doc = db.scalar(select(SaasInvoiceDoc).where(SaasInvoiceDoc.invoice_id == inv.id))
    if doc:
        net, vat, pct, items, lang, no = doc.net, doc.vat, doc.vat_pct, doc.items, doc.lang, doc.doc_no
        issued_at = _aware(doc.issued_at)
    else:  # preview of what issuing will produce
        net, vat, pct, own = docs.vat_facts(inv, s.default_vat_pct)
        items, lang, no, issued_at = docs.build_items(db, inv, net, pct, own), docs._customer_lang(db, inv.org_id), None, None
    cns = db.scalars(select(SaasCreditNote).where(SaasCreditNote.invoice_id == inv.id).order_by(SaasCreditNote.id)).all()
    credited = sum(c.amount for c in cns)
    paid = inv.amount if inv.status == "paid" else 0
    overdue = inv.status == "issued" and _aware(inv.due_at) < now()
    return {"id": inv.id, "issued": bool(doc), "doc_no": no, "number": no or inv.number, "quote_ref": inv.number, "lang": lang, "issued_at": issued_at.isoformat() if issued_at else None,
            "due_at": _aware(inv.due_at).isoformat(), "stamp": _stamp(inv), "overdue": overdue, "status": inv.status, "kind": inv.kind, "period": inv.period,
            "company": _company(s), "customer": _customer(db, inv.org_id), "items": items,
            "subtotal": net, "vat_pct": pct, "vat": vat, "total": inv.amount, "words_en": docs.amount_in_words(inv.amount, "en"), "words_bn": docs.amount_in_words(inv.amount, "bn"),
            "paid_at": _aware(inv.paid_at).isoformat() if inv.paid_at else None, "method": inv.method, "trx_id": inv.trx_id,
            "credited": credited, "balance": max(0, inv.amount - paid - credited) if inv.status != "void" else 0, "credit_notes": [_cn_out(c) for c in cns],
            "payment": {"bkash": s.bkash_merchant, "nagad": s.nagad_merchant, "bank": s.bank_details, "reference": inv.number},
            "emailed_at": _aware(doc.emailed_at).isoformat() if doc and doc.emailed_at else None}


def _need_inv(db: Session, invoice_id: int) -> SaasInvoice:
    inv = db.get(SaasInvoice, invoice_id)
    if not inv:
        raise HTTPException(404, "Not found")
    return inv


@doc_router.post("/issue-pending")
def issue_pending(user: User = Depends(require_saas(*MONEY)), db: Session = Depends(get_db)):
    have = set(db.scalars(select(SaasInvoiceDoc.invoice_id)))
    made = []
    for inv in db.scalars(select(SaasInvoice).order_by(SaasInvoice.id)):
        if inv.id not in have:
            made.append(docs.issue_doc(db, inv, user.id).doc_no)
    db.commit()
    return {"issued": len(made), "numbers": made}


@doc_router.get("/credit-note/{cn_id}")
def credit_note(cn_id: int, user: User = Depends(require_saas(*MONEY)), db: Session = Depends(get_db)):
    c = db.get(SaasCreditNote, cn_id)
    if not c:
        raise HTTPException(404, "Not found")
    inv = db.get(SaasInvoice, c.invoice_id)
    doc = db.scalar(select(SaasInvoiceDoc).where(SaasInvoiceDoc.invoice_id == c.invoice_id))
    s = docs.get_settings(db)
    return {**_cn_out(c), "net": c.amount - c.vat, "invoice_id": inv.id, "invoice_no": doc.doc_no if doc else inv.number, "lang": doc.lang if doc else "en",
            "company": _company(s), "customer": _customer(db, c.org_id), "vat_pct": doc.vat_pct if doc else s.default_vat_pct,
            "words_en": docs.amount_in_words(c.amount, "en"), "words_bn": docs.amount_in_words(c.amount, "bn")}


@doc_router.get("/statement/{org_id}")
def statement(org_id: int, user: User = Depends(require_saas(*MONEY)), db: Session = Depends(get_db)):
    return _statement(db, org_id)


def _statement(db: Session, org_id: int) -> dict:
    if not db.get(Organization, org_id):
        raise HTTPException(404, "Not found")
    ev = []
    for inv in db.scalars(select(SaasInvoice).where(SaasInvoice.org_id == org_id)):
        doc = db.scalar(select(SaasInvoiceDoc).where(SaasInvoiceDoc.invoice_id == inv.id))
        ref = doc.doc_no if doc else inv.number
        ev.append((_aware(inv.issued_at), 0, "invoice", ref, inv.description or inv.kind, inv.amount, 0, inv.id))
        if inv.paid_at:
            ev.append((_aware(inv.paid_at), 1, "payment", ref, f"{inv.method} {inv.trx_id}".strip(), 0, inv.amount, inv.id))
        cns = db.scalars(select(SaasCreditNote).where(SaasCreditNote.invoice_id == inv.id)).all()
        for c in cns:
            ev.append((_aware(c.issued_at), 2, "credit_note", c.doc_no, c.reason, 0, c.amount, inv.id))
        if inv.status == "void" and not cns:  # voided before credit notes existed
            ev.append((_aware(inv.issued_at), 2, "credit_note", ref, "Voided", 0, inv.amount, inv.id))
    ev.sort(key=lambda x: (x[0], x[1], x[7]))
    bal, rows = 0, []
    for at, _, typ, ref, desc, dr, cr, iid in ev:
        bal += dr - cr
        rows.append({"date": at.isoformat(), "type": typ, "ref": ref, "description": desc, "debit": dr, "credit": cr, "balance": bal, "invoice_id": iid})
    return {"customer": _customer(db, org_id), "company": _company(docs.get_settings(db)), "rows": rows, "balance": bal,
            "debit": sum(r["debit"] for r in rows), "credit": sum(r["credit"] for r in rows)}


@doc_router.get("/statement/{org_id}/csv")
def statement_csv(org_id: int, user: User = Depends(require_saas(*MONEY)), db: Session = Depends(get_db)):
    st = _statement(db, org_id)
    return _csv_response(f"flatwise-statement-{org_id}.csv", ["date", "type", "reference", "description", "debit_bdt", "credit_bdt", "balance_bdt"],
                         [[r["date"][:10], r["type"], r["ref"], r["description"], _bdt(r["debit"]), _bdt(r["credit"]), _bdt(r["balance"])] for r in st["rows"]])


@doc_router.get("/{invoice_id}")
def get_doc(invoice_id: int, user: User = Depends(require_saas(*MONEY)), db: Session = Depends(get_db)):
    return _doc_out(db, _need_inv(db, invoice_id))


@doc_router.post("/{invoice_id}/issue")
def issue(invoice_id: int, user: User = Depends(require_saas(*MONEY)), db: Session = Depends(get_db)):
    inv = _need_inv(db, invoice_id)
    docs.issue_doc(db, inv, user.id)
    db.commit()
    return _doc_out(db, inv)


class LangIn(BaseModel):
    lang: str = Field(pattern="^(en|bn)$")


@doc_router.put("/{invoice_id}/lang")
def set_lang(invoice_id: int, body: LangIn, user: User = Depends(require_saas(*MONEY)), db: Session = Depends(get_db)):
    inv = _need_inv(db, invoice_id)
    doc = docs.issue_doc(db, inv, user.id)
    doc.lang = body.lang
    db.commit()
    return _doc_out(db, inv)


class VoidIn(BaseModel):
    reason: str = Field(default="Invoice voided", max_length=200)


@doc_router.post("/{invoice_id}/void")
def void(invoice_id: int, body: VoidIn, user: User = Depends(require_saas(*MONEY)), db: Session = Depends(get_db)):
    inv = _need_inv(db, invoice_id)
    if inv.status != "issued":
        raise HTTPException(422, "Only open invoices can be voided")
    inv.status = "void"
    docs.void_with_credit_note(db, inv, user.id, body.reason)
    audit(db, user_id=user.id, org_id=inv.org_id, action="saas.invoice.void", entity="invoice", entity_id=inv.id)
    db.commit()
    return _doc_out(db, inv)


class RefundIn(BaseModel):
    amount: int | None = Field(default=None, ge=1)  # paisa; empty means the whole invoice
    reason: str = Field(default="Refund", max_length=200)


@doc_router.post("/{invoice_id}/refund")
def refund(invoice_id: int, body: RefundIn, user: User = Depends(require_saas(*MONEY)), db: Session = Depends(get_db)):
    inv = _need_inv(db, invoice_id)
    if inv.status != "paid":
        raise HTTPException(422, "Only paid invoices can be refunded")
    try:
        docs.issue_credit_note(db, inv, "refund", body.reason, user.id, body.amount)
    except ValueError as e:
        raise HTTPException(422, str(e))
    db.commit()
    return _doc_out(db, inv)


def _mail_html(d: dict) -> str:
    rows = "".join(f"<tr><td>{i['desc_bn'] if d['lang'] == 'bn' else i['desc']}</td><td align='right'>BDT {i['net'] / 100:,.2f}</td></tr>" for i in d["items"])
    return (f"<h2>{d['company']['legal_name']}</h2><p>Tax invoice {d['number']} (ref {d['quote_ref']})</p><table>{rows}</table>"
            f"<p>VAT {d['vat_pct']}%: BDT {d['vat'] / 100:,.2f}<br><b>Total: BDT {d['total'] / 100:,.2f}</b></p><p>{d['words_bn'] if d['lang'] == 'bn' else d['words_en']}</p>")


@doc_router.post("/{invoice_id}/email")
def email(invoice_id: int, user: User = Depends(require_saas(*MONEY)), db: Session = Depends(get_db)):
    """Renders the invoice into the sandbox outbox (services/mailer.py, M20). If that module is missing, nothing happens and that is not an error."""
    inv = _need_inv(db, invoice_id)
    doc = docs.issue_doc(db, inv, user.id)
    db.commit()
    sent = False
    if importlib.util.find_spec("app.services.mailer") is not None:
        try:
            mailer = importlib.import_module("app.services.mailer")
            outbox = importlib.import_module("app.models.mail").MailOutbox
            d = _doc_out(db, inv)
            to = next((c["email"] for c in d["customer"]["contacts"] if c["email"]), "")
            if to and not mailer.block_reason(db, to.lower(), "transactional", now()):
                subject = f"{d['company']['legal_name']} - {'ট্যাক্স ইনভয়েস' if d['lang'] == 'bn' else 'Tax invoice'} {d['number']}"
                html = _mail_html(d)
                prov = mailer.get_provider()
                prov.send(mailer.Mail(to, subject, html, re.sub(r"<[^>]+>", " ", html)))
                db.add(outbox(template_key="tax_invoice", kind="transactional", to_email=to.lower(), to_name="", lang=d["lang"], org_id=inv.org_id, subject=subject,
                              html=html, text=re.sub(r"<[^>]+>", " ", html), status="sent", provider=prov.name, sent_at=now(), delivered_at=now()))
                doc.emailed_at = now()
                audit(db, user_id=user.id, org_id=inv.org_id, action="saas.invoice.email", entity="invoice", entity_id=inv.id, meta={"to": to})
                sent = True
        except Exception:
            db.rollback()
            sent = False
    db.commit()
    return {"sent": sent}
