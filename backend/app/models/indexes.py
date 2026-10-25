"""Extra indexes for the hot filters, attached to the tables after every model is loaded.

Kept in one place so that the model files stay about columns. Two parts:
1. composite indexes for the filters the list screens and dashboards use (building + status/date/period);
2. a safety net: every foreign key column that has no index starting with it gets one (PostgreSQL does not
   index foreign keys by itself; joins and cascades would scan the table).
Add a migration (alembic revision --autogenerate) whenever this file changes.
"""
from sqlalchemy import Index, event

from ..db import Base

COMPOSITE: dict[str, list[tuple[str, ...]]] = {
    "invoices": [("property_id", "period"), ("property_id", "status", "due_date")],
    "payments": [("property_id", "status", "paid_on"), ("invoice_id", "status")],
    "service_requests": [("property_id", "status", "created_at"), ("property_id", "status", "due_at")],
    "notices": [("property_id", "status", "created_at")],
    "notice_receipts": [("notice_id", "read_at")],
    "cash_entries": [("property_id", "collector_id", "status")],
    "journals": [("property_id", "date")],
    "visits": [("property_id", "status", "created_at")],
    "amenity_bookings": [("property_id", "on_date", "status"), ("amenity_id", "on_date")],
    "messages": [("property_id", "status", "created_at")],
    "expenses": [("property_id", "status", "spent_on")],
    "mail_outbox": [("campaign_id", "status")],
    "units": [("property_id", "number")],
    "staff": [("property_id", "status")],
    "occupancies": [("unit_id", "active", "kind")],
    "memberships": [("user_id", "org_id", "property_id")],
    "audit_log": [("property_id", "at"), ("user_id", "at")],
    "proposals": [("property_id", "status")],
    "gateway_sessions": [("property_id", "status")],
    "credit_purchases": [("org_id", "status")],
    "saas_invoices": [("org_id", "status")],
}


def _stable(table: str, cols: tuple[str, ...]) -> str:
    name = f"ix_{table}_{'_'.join(cols)}"
    if len(name) <= 60:
        return name
    import zlib
    return f"ix_{table[:24]}_{zlib.crc32(name.encode()):08x}"


def attach() -> None:
    tables = Base.metadata.tables
    for t in tables.values():   # MySQL/MariaDB: InnoDB + utf8mb4 on every table (ignored by other databases)
        opts = t.dialect_options["mysql"]
        opts["engine"], opts["charset"], opts["collate"] = "InnoDB", "utf8mb4", "utf8mb4_unicode_ci"
    for tname, groups in COMPOSITE.items():
        t = tables.get(tname)
        if t is None:
            continue
        for cols in groups:
            if all(c in t.c for c in cols) and not any(ix.name == _stable(tname, cols) for ix in t.indexes):
                Index(_stable(tname, cols), *[t.c[c] for c in cols])
    for t in tables.values():
        led = {tuple(c.name for c in ix.columns)[:1] for ix in t.indexes}
        led |= {tuple(c.name for c in uc.columns)[:1] for uc in t.constraints if uc.__class__.__name__ in ("UniqueConstraint", "PrimaryKeyConstraint")}
        for fk in t.foreign_key_constraints:
            first = tuple(c.name for c in fk.columns)[:1]
            if first not in led and len(fk.columns) == 1:
                Index(_stable(t.name, tuple(c.name for c in fk.columns)), *fk.columns)
                led.add(first)


attach()
# models imported after this module (other modules append to models/__init__.py) are covered right before create_all
event.listen(Base.metadata, "before_create", lambda *a, **k: attach())
