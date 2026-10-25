"""Cleaner OpenAPI for /docs and docs/API.md.

Adds tag descriptions, the two security schemes (bearer token and X-Property-Id), a description for every operation that has none,
the usual error responses, and documentation-only response models for a few public endpoints that return plain dicts.
Nothing here changes what the API does. /docs and /openapi.json do not exist when ENV=production (see main.py).
"""
from fastapi import FastAPI
from fastapi.openapi.utils import get_openapi
from pydantic import BaseModel

TAGS = [
    ("public", "Website endpoints that need no sign-in: plans and prices, leads, trial signup, form token."),
    ("auth", "Sign in and who am I."),
    ("account", "Sessions, refresh tokens, password change and reset, e-mail verification."),
    ("core", "Activity log and the current building."),
    ("saas", "SaaS console: buildings, subscriptions, plans, leads and team. FlatWise staff only."),
    ("saas-invoice-docs", "FlatWise invoices, credit notes and company settings. FlatWise staff only."),
    ("saas-reports", "SaaS revenue and subscription reports. FlatWise staff only."),
    ("credits", "SMS and email credits for a building: balance, packs, purchases."),
    ("credits-console", "Credit sales console for FlatWise staff."),
    ("mail", "Email campaigns, templates, audiences and unsubscribe. FlatWise staff only, plus the public unsubscribe link."),
    ("plan", "The current building's plan and feature switches."),
    ("property", "Flats, owners, tenants, building details and the agency portfolio."),
    ("billing", "Service charge: rules, invoices, payments, dues, receipts and reminders. Money is integer paisa."),
    ("cash", "Cash desk: cash taken with payer confirmation, custody and hand-over to the treasurer."),
    ("finance", "Expenses, vendors, assets, budget, ledger and trial balance."),
    ("budget", "Month-by-month budget and month locks."),
    ("gateway", "Online payment settings and sessions for a building."),
    ("staff", "Staff register, the National ID vault and salary sheets."),
    ("notices", "Notices with read proof."),
    ("policies", "Versioned policies and acceptance."),
    ("onboarding", "Tenant onboarding cases, documents and the DMP pack."),
    ("requests", "Service requests with service levels."),
    ("committee", "Committee members, meetings and votes."),
    ("profiles", "Profile photos and optional personal details."),
    ("rental", "Private rental records between an owner and a tenant."),
    ("visitors", "Visitor log, passes and regular visitors."),
    ("parking", "Parking slots, vehicles and visitor bays."),
    ("amenities", "Community hall and amenity booking."),
    ("agency", "Security and cleaning agencies, duty roster, attendance and agency bills."),
    ("contracts", "Agency contracts and documents."),
    ("jobs", "Scheduled jobs: status and manual runs."),
    ("webhooks", "Inbound provider callbacks (SMS delivery reports, payment gateway)."),
    ("setup", "New-customer setup wizard progress."),
    ("export", "CSV exports and the whole-building ZIP."),
    ("privacy", "Account-deletion requests."),
    ("retention", "SaaS console: data retention settings, purge, and deletion requests."),
]
HTTP = {"get", "put", "post", "patch", "delete"}
PUBLIC_PREFIXES = ("/api/public", "/api/health", "/healthz", "/readyz", "/api/auth/login", "/api/auth/refresh", "/api/auth/forgot-password",
                   "/api/auth/reset-password", "/api/auth/verify-email", "/api/auth/resend-verification", "/api/auth/demo-accounts", "/api/webhooks")


class Health(BaseModel):
    ok: bool
    app: str


class PlansDoc(BaseModel):
    bands: list[dict]
    trial_days: int
    yearly_months_paid: int
    sms_pack: dict
    plans: list[dict]


class LeadDoc(BaseModel):
    ok: bool
    id: int


# (method, path) -> documented 200/201 response. Documentation only.
RESPONSE_DOCS = {("get", "/api/health"): Health, ("get", "/api/public/plans"): PlansDoc, ("post", "/api/public/leads"): LeadDoc}


def _polish(app: FastAPI, schema: dict) -> dict:
    schema["info"]["description"] = (
        "FlatWise API: property and facility management for buildings in Bangladesh.\n\n"
        "- Every call except the public ones needs `Authorization: Bearer <token>` from `POST /api/auth/login`.\n"
        "- Building-scoped calls also need `X-Property-Id: <building id>`; the caller's roles in that building decide what is allowed.\n"
        "- Money is always an integer number of paisa (100 paisa = 1 BDT). Exports write decimal taka.\n"
        "- Errors are `{\"detail\": \"...\"}`. 402 means the building's plan does not include the feature.")
    comps = schema.setdefault("components", {})
    comps.setdefault("securitySchemes", {}).update({
        "BearerAuth": {"type": "http", "scheme": "bearer", "description": "Access token from POST /api/auth/login or /api/auth/refresh."},
        "PropertyId": {"type": "apiKey", "in": "header", "name": "X-Property-Id", "description": "Id of the building you are working in."},
    })
    for model in (Health, PlansDoc, LeadDoc):
        comps.setdefault("schemas", {})[model.__name__] = model.model_json_schema(ref_template="#/components/schemas/{model}")
    for path, item in schema["paths"].items():
        public = path.startswith(PUBLIC_PREFIXES)
        for method, op in item.items():
            if method not in HTTP:
                continue
            params = op.get("parameters", [])
            scoped = False
            kept = []
            for p in params:
                if p.get("in") == "header" and p["name"].lower() == "authorization":
                    continue                      # described by the security scheme instead
                if p.get("in") == "header" and p["name"].lower() == "x-property-id":
                    scoped = True
                    continue
                kept.append(p)
            if kept:
                op["parameters"] = kept
            else:
                op.pop("parameters", None)
            op["security"] = [] if public else ([{"BearerAuth": [], "PropertyId": []}] if scoped else [{"BearerAuth": []}])
            sm = op.get("summary", "")
            if sm and sm == sm.title() and " " in sm or sm.istitle():   # FastAPI's name-derived "Create Lead" reads better as "Create lead"
                op["summary"] = sm[:1] + sm[1:].lower()
            if not op.get("description"):
                who = "No sign-in needed." if public else ("Needs sign-in and the `X-Property-Id` header. " if scoped else "Needs sign-in. ") + "What you can do depends on your role in the building."
                op["description"] = f"{op.get('summary', '')}. {who}".strip()
            resp = op.setdefault("responses", {})
            if not public:
                resp.setdefault("401", {"description": "Not signed in, or the token expired."})
                resp.setdefault("403", {"description": "Your role cannot do this."})
            if scoped:
                resp.setdefault("400", {"description": "No building chosen (missing or unknown X-Property-Id)."})
            doc = RESPONSE_DOCS.get((method, path))
            if doc:
                for code in ("200", "201"):
                    if code in resp:
                        resp[code]["content"] = {"application/json": {"schema": {"$ref": f"#/components/schemas/{doc.__name__}"}}}
    return schema


def install(app: FastAPI) -> None:
    app.openapi_tags = [{"name": n, "description": d} for n, d in TAGS]

    def custom():
        if app.openapi_schema:
            return app.openapi_schema
        schema = get_openapi(title=app.title, version=app.version, routes=app.routes, tags=app.openapi_tags, description=app.description)
        app.openapi_schema = _polish(app, schema)
        return app.openapi_schema

    app.openapi = custom  # type: ignore[method-assign]
