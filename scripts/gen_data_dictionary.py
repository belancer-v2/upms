"""Writes docs/DATA_DICTIONARY.md from the SQLAlchemy models. Run from the repo root:

    backend/.venv/bin/python scripts/gen_data_dictionary.py

Column notes come from the trailing "# comment" on each column line in backend/app/models/*.py, table notes from the class docstring.
"""
import ast
import os
import re
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))
os.environ.setdefault("DATABASE_URL", f"sqlite:///{tempfile.mkdtemp()}/dd.db")

from app import models  # noqa: E402,F401
from app.db import Base  # noqa: E402

MODELS = ROOT / "backend" / "app" / "models"
MODULE_TITLES = {
    "core": "Identity and tenancy", "saas": "Plans, subscriptions, leads", "property": "Flats and people", "billing": "Service charge and messages", "cash": "Cash collection",
    "finance": "Ledger, expenses, assets", "staff": "Staff and payroll", "notice": "Notices and policies", "onboarding": "Tenant onboarding", "requests": "Requests, committee, votes",
    "gateway": "Online payments", "budget": "Monthly budget", "profile": "Profiles", "parking": "Parking", "amenities": "Hall and amenity booking", "rental": "Owner rental records",
    "credits": "SMS and email credits", "agency": "Agencies and duty roster", "visitors": "Visitors", "saas_reports": "FlatWise invoices and reports", "mail": "Email campaigns",
    "jobs": "Scheduled jobs and SMS dispatch", "security": "Sessions and tokens", "contracts": "Agency contracts", "setup": "Setup wizard and deletion requests",
}


def parse(path: Path) -> dict[str, dict]:
    """table name -> {doc, cols: {col: comment}} read from the source of one models file."""
    tree = ast.parse(path.read_text())
    lines = path.read_text().splitlines()
    out = {}
    for node in tree.body:
        if not isinstance(node, ast.ClassDef):
            continue
        table = None
        for b in node.body:
            if isinstance(b, ast.Assign) and any(getattr(t, "id", "") == "__tablename__" for t in b.targets):
                table = b.value.value
        if not table:
            continue
        cols = {}
        for b in node.body:
            if isinstance(b, ast.AnnAssign) and isinstance(b.target, ast.Name):
                m = re.search(r"#\s*(.+)$", lines[b.end_lineno - 1])
                if m:
                    cols[b.target.id] = m.group(1).strip()
        out[table] = {"doc": (ast.get_docstring(node) or "").split("\n\n")[0].replace("\n", " "), "cols": cols}
    return out


def main():
    info, module_of = {}, {}
    for f in sorted(MODELS.glob("*.py")):
        if f.stem in ("__init__", "indexes"):
            continue
        for t, v in parse(f).items():
            info[t], module_of[t] = v, f.stem
    groups: dict[str, list] = {}
    for t in Base.metadata.sorted_tables:
        groups.setdefault(module_of.get(t.name, "other"), []).append(t)
    out = ["# Data dictionary", "",
           "Generated from the models by `scripts/gen_data_dictionary.py`. Do not edit by hand; change the model comment and run the script again.", "",
           "Conventions: money columns are **integer paisa** (100 paisa = 1 BDT); dates are UTC; every building-scoped table has `property_id` (the tenant boundary); "
           "ledger tables (`journals`, `journal_lines`) and `audit_log` are append-only.", "",
           f"{len(Base.metadata.sorted_tables)} tables.", ""]
    for mod, tables in sorted(groups.items(), key=lambda x: list(MODULE_TITLES).index(x[0]) if x[0] in MODULE_TITLES else 99):
        out += [f"## {MODULE_TITLES.get(mod, mod.title())}", ""]
        for t in tables:
            meta = info.get(t.name, {"doc": "", "cols": {}})
            out += [f"### `{t.name}`", ""]
            if meta["doc"]:
                out += [meta["doc"], ""]
            out += ["| Column | Type | Null | Key | Notes |", "|---|---|---|---|---|"]
            for c in t.columns:
                key = "PK" if c.primary_key else ("FK " + ", ".join(sorted({fk.target_fullname for fk in c.foreign_keys}))) if c.foreign_keys else ("unique" if c.unique else ("index" if c.index else ""))
                note = meta["cols"].get(c.name, "")
                if c.name.endswith(("_paisa",)) or (not note and c.name in ("amount", "total", "paid", "balance", "fee", "deposit", "cost", "salary", "rent", "advance", "debit", "credit", "price", "base", "bonus", "deduction") and "INT" in str(c.type).upper()):
                    note = (note + " " if note else "") + "(paisa)"
                out.append(f"| `{c.name}` | {str(c.type).replace('|', '/')} | {'yes' if c.nullable else 'no'} | {key} | {note.replace('|', '/')} |")
            uq = [u for u in t.constraints if u.__class__.__name__ == "UniqueConstraint" and len(u.columns) > 1]
            if uq:
                out += ["", "Unique together: " + "; ".join("(" + ", ".join(c.name for c in u.columns) + ")" for u in uq)]
            out.append("")
    (ROOT / "docs" / "DATA_DICTIONARY.md").write_text("\n".join(out))
    print("wrote docs/DATA_DICTIONARY.md,", len(Base.metadata.sorted_tables), "tables")


main()
