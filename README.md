# FlatWise (UPMS)

Property and facility management software for buildings in Bangladesh. Service charge bills and receipts, cash with proof, expenses and a balanced ledger, notices with read proof, staff and payroll, tenant onboarding, visitors, parking, hall booking and more. Bangla and English, day and night, one building at a time or an agency with many.

- `backend/` FastAPI + SQLAlchemy. SQLite for development and tests, PostgreSQL or MySQL in production (schema by Alembic). **Money is integer paisa.** Every building-scoped call carries `X-Property-Id`.
- `frontend/` Next.js (App Router, TypeScript). Red identity design system in `src/app/globals.css`. Every string lives in `src/lib/i18n/*.ts` in English and Bangla.
- `docs/` guides, architecture, API, data dictionary, launch checklist, PRD and module screenshots (`docs/screenshots/<module>/`).
- `SECURITY.md` threat model, controls, incident steps and disclosure contact; `docs/PERMISSIONS.md` role-by-module matrix (generated: `python -m app.permmatrix`); `docs/DEPENDENCY_AUDIT.md`.
- `scripts/` `dev.sh` (run both servers), `backup.sh` / `restore.sh`, `shots.cjs` (screenshots per module), `gen_api_doc.py` and `gen_data_dictionary.py` (regenerate the two reference docs), `build_cpanel_bundle.sh`.
  Quality checks: `npm run i18n:audit` (in `frontend/`: BN/EN keys, hard-coded English, Latin digits, en-GB dates; runs in CI) and `scripts/sweep.cjs` (logs in as every demo role, opens every menu item in EN light, BN dark and phone width, writes `docs/SWEEP_REPORT.md`; point it at your own instance, for example `WEB=http://127.0.0.1:3100 API=http://127.0.0.1:8100 node scripts/sweep.cjs`).
- `deploy/`, `docker-compose.yml`, `backend/Dockerfile`, `frontend/Dockerfile` for a VPS.

## Run it locally
```bash
cd backend && python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
cd ../frontend && npm install && npm run build
cd .. && scripts/dev.sh seed     # demo data, API :8000, web :3000
```
Demo logins (password `demo1234`) are listed on the sign-in page when `DEMO=1` (the default outside production). Examples: `padmin@flatwise.demo` (building admin), `treasurer@`, `president@`, `tenant@`, `caretaker@`, `super@` (FlatWise super admin).

For development without a production build: `npm run dev` in `frontend/` and `.venv/bin/uvicorn app.main:app --reload --port 8000` in `backend/`. `/docs` shows the API (switched off when `ENV=production`).

## Check it
```bash
cd backend && .venv/bin/python -m pytest -q        # about 3 minutes; password hashing is the slow part
cd frontend && npx tsc --noEmit                    # type check
```
A single file: `.venv/bin/python -m pytest tests/test_setup.py -q`.

## Modules
| Module | Status |
|---|---|
| M0 Foundation: design system, BN/EN, day/night, sign-in, roles, tenancy, audit | done |
| M1 Website: home, features, pricing (live from the API), demo, signup + trial, FAQ, contact, legal pages | done (legal text and company details are placeholders) |
| M2 SaaS console: buildings, plans, subscriptions, SaaS invoices, SMS credits, leads, team, feature flags | done |
| M3 Property setup: flats map, owners, tenants, to-let approval, agency portfolio | done |
| M4 Service charge | done |
| M5 Cash collection with OTP | done |
| M6 Finance and assets, ledger | done |
| M7 Staff and payroll | done |
| M8 Notices and policies | done |
| M9 Tenant onboarding and DMP pack | done |
| M10 Complaints and committee | done |
| M11 Profiles with photo and optional details | done |
| M12 Monthly budget setting | done |
| M13 Payment gateway (bKash, SSLCommerz; sandbox until certified) | built, not live |
| M14 Owner rental records add-on | done |
| M15 Visitor log | done |
| M16 Community hall and amenity booking | done |
| M17 Parking allocated with the flat | done |
| M18 Security and cleaner agency, duty roster | done |
| M19 SMS and email credit top-up | done |
| M20 SaaS email campaigns and templates | done |
| M21 SaaS reports and FlatWise invoices | done |
| Jobs, providers, storage | done (SMS and email providers need your accounts) |
| Security: sessions, refresh tokens, password rules, rate limits, audit chain | done |
| Help center (50 articles, EN and BN), setup wizard, data export, retention, account deletion | done |

## User types
FlatWise team: Super Admin, SaaS Admin, SaaS Finance, SaaS Sales, SaaS User.
Customer side: Agency Manager, Property Admin, Flat Owner, Tenant, Caretaker, Committee President, Secretary, Treasurer, Member, Auditor, Guard, Owner's Representative. One person can hold several roles (for example a flat owner who is also the treasurer).

## Documentation
| Read | For |
|---|---|
| `docs/PRD_v1.1.md` | what the product is meant to do |
| `docs/ARCHITECTURE.md` | modules, tenancy, money, ledger, feature gating, diagrams |
| `docs/API.md` | every endpoint, conventions, errors |
| `docs/DATA_DICTIONARY.md` | every table and column |
| `docs/ADMIN_GUIDE.md` | FlatWise staff: onboarding a building, plans, credits, gateway, email, jobs, retention |
| `docs/USER_GUIDE_building_admin.md`, `_committee_treasurer`, `_resident`, `_caretaker_guard`, `_agency_manager`, `_saas_team` | plain-English guides per audience |
| In the app: **Help** (menu) and the **?** next to each page title | 50 short articles in English and Bangla; also public at `/help` |
| `docs/LAUNCH_CHECKLIST.md` | what the owner must register, sign and fill before launch |
| `docs/CPANEL_DEPLOY.md`, `docs/VPS_DEPLOY.md`, `docs/RUNBOOK.md` | deploy, backups, rollback, incidents |
| `docs/ENV_VARS.md`, `backend/.env.example` | every setting |
| `docs/JOBS.md`, `docs/SMS_SETUP.md`, `docs/EMAIL_SETUP.md`, `docs/PAYMENTS_SETUP.md`, `docs/STORAGE.md` | scheduled jobs and providers |
| `backend/MIGRATIONS.md` | database changes with Alembic |

The API reference and the data dictionary are generated; after changing routers or models run
`backend/.venv/bin/python scripts/gen_api_doc.py` and `backend/.venv/bin/python scripts/gen_data_dictionary.py`.

## Data, privacy and retention
- Any list has **Export CSV**; the property admin, agency manager or president can download the whole building as a ZIP (`/app/data`, 3 per building per day, audited). Staff National ID is never exported.
- Retention (SaaS console > Data retention): visitor logs 24 months, sent email and SMS logs 12, former residents' contact details and onboarding files 36 by default; the audit log is never deleted. **The purge is not scheduled by itself**: call `app.services.retention.run_purge(db)` from a job, or press Run purge.
- Anyone can ask to erase their personal details (Profile > Delete my account). Staff process it; invoices and the ledger stay without the name.
- No advertising or tracking cookies, so no cookie banner.

## Before you go live
Read `docs/LAUNCH_CHECKLIST.md`. The legal texts (`frontend/src/lib/legal.ts`) are drafts for a lawyer, and company details (`frontend/src/lib/company.ts`) are placeholders shown highlighted in `[BRACKETS]` until you fill them.
