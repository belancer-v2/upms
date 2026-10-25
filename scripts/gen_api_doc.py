"""Writes docs/API.md from the live OpenAPI schema. Run from the repo root:

    backend/.venv/bin/python scripts/gen_api_doc.py

/docs and /openapi.json are switched off when ENV=production, so this script builds the schema in-process instead.
"""
import os
import re
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))
os.environ.setdefault("DATABASE_URL", f"sqlite:///{tempfile.mkdtemp()}/api.db")
os.environ.pop("ENV", None)

import warnings  # noqa: E402
warnings.filterwarnings("ignore")
from app.main import app  # noqa: E402

HEAD = """# FlatWise API

The API is a FastAPI application (`backend/app`). This page is generated from its OpenAPI schema by `scripts/gen_api_doc.py`; the same schema is
served at `/docs` (Swagger UI) and `/openapi.json` when `ENV` is not `production`. In production both are switched off on purpose; use this file or run
the script against a staging copy.

## Conventions

| Topic | Rule |
|---|---|
| Base path | Everything is under `/api`. The web app proxies `/api/*` to the API, so the browser sees one origin. |
| Sign in | `POST /api/auth/login` returns an access token. Send it as `Authorization: Bearer <token>`. Access tokens are short-lived; `POST /api/auth/refresh` rotates the refresh token (also kept as an HttpOnly cookie). A person with a temporary password must call `POST /api/auth/change-password` before anything else (403 with `X-Error-Code: password_change_required`). |
| Building scope | Calls about a building also need `X-Property-Id: <id>`. The caller's roles *in that building* decide what is allowed. An agency manager's role covers every building of the agency. Missing or unknown id: 400. No access: 403. |
| Roles | 5 FlatWise staff roles (`saas_role` on the user) and 12 customer roles (memberships). See `backend/app/permissions.py` for the groups used by every router. |
| Plan gate | A feature the building's plan does not include answers **402** `Your plan does not include '<feature>'`. The web app shows an upgrade message. |
| Money | Always **integer paisa** (100 paisa = 1 BDT) in JSON. CSV exports are decimal taka in columns ending `_bdt`. Never floats. |
| Dates | ISO 8601. Dates are `YYYY-MM-DD`, times are UTC. Billing periods are `YYYY-MM`. |
| Errors | `{"detail": "message"}`. 401 not signed in, 403 role cannot do this, 404 not found (also used to hide other buildings' records), 409 conflict (duplicate), 422 validation, 429 rate limited. Unexpected failures answer 500 with a `request_id`; quote it to support. |
| Request id | Every response carries `X-Request-ID`. A sane inbound value is kept. |
| Rate limits | Sign-in, password reset, public forms and the whole-building export are limited. 429 carries `Retry-After`. |
| Lists | Long lists take `q` (search) and `page` / `size` and return `total` where the screen has a pager. Some older lists return a plain array capped at a few hundred rows. |
| Idempotency | Generating invoices twice creates nothing new. A ledger entry is unique per source. Reminder SMS use a message key. A repeated payment transaction id is refused (409). |
| Audit | Every write that matters adds an `audit_log` row (append-only, hash-chained). `GET /api/audit` reads it; `GET /api/audit/verify` checks the chain (FlatWise admins). |
| Files | Uploads are multipart, limited in size and type; downloads go through the API so the sign-in applies. |
| Public endpoints | `/api/public/*`, `/api/auth/login`, password reset, e-mail verification, `/api/health`, `/healthz`, `/readyz`, and token links (`/api/notices/link/...`, tenant form, unsubscribe). Everything else needs sign-in. |

## Endpoints by area

Columns: method, path, summary and, where the code has one, the first sentence of its description. All except those in the public list above need `Authorization`; paths marked with `*` also need `X-Property-Id`.
"""


def first_sentence(op: dict) -> str:
    """The first sentence of a written docstring; empty when the description is only the generated fallback line."""
    text = re.sub(r"\s+", " ", (op.get("description") or "").strip())
    if not text or text.endswith(("What you can do depends on your role in the building.", "No sign-in needed.")):
        return ""
    m = re.match(r"(.+?[.!?])(\s|$)", text)
    return (m.group(1) if m else text).replace("|", "/")[:240]


def main():
    schema = app.openapi()
    tags = {t["name"]: t["description"] for t in schema.get("tags", [])}
    by_tag: dict[str, list] = {}
    for path, item in sorted(schema["paths"].items()):
        for method, op in item.items():
            if method not in ("get", "post", "put", "patch", "delete"):
                continue
            scoped = any("PropertyId" in s for s in op.get("security", []))
            by_tag.setdefault((op.get("tags") or ["other"])[0], []).append((method.upper(), path, scoped, op.get("summary", ""), first_sentence(op)))
    out = [HEAD]
    total = 0
    for tag in list(tags) + [t for t in by_tag if t not in tags]:
        rows = by_tag.get(tag)
        if not rows:
            continue
        total += len(rows)
        out += [f"### {tag}", "", tags.get(tag, ""), "", "| Method | Path | Summary | Notes |", "|---|---|---|---|"]
        out += [f"| {m} | `{p}`{' *' if s else ''} | {sm} | {d} |" for m, p, s, sm, d in rows]
        out.append("")
    out.insert(1, f"{total} operations in {len([t for t in by_tag])} areas.\n")
    (ROOT / "docs" / "API.md").write_text("\n".join(out))
    print("wrote docs/API.md,", total, "operations")


main()
