# FlatWise (UPMS)

Property and facility management SaaS for buildings in Bangladesh. Bangla and English, day and night, built per building.

- `backend/` FastAPI + SQLAlchemy (SQLite for dev, Postgres-ready). Money is integer paisa. Every building-scoped call carries `X-Property-Id`.
- `frontend/` Next.js (App Router, TypeScript). Red identity design system in `src/app/globals.css`.
- `docs/` PRD v1.1, brand guideline PDF, and module screenshots in `docs/screenshots/<module>/`.
- `scripts/` `dev.sh` (run everything), `shots.cjs` (capture screenshots per module).

## Run it
```bash
cd backend && uv venv .venv && uv pip install -r requirements.txt --python .venv/bin/python
cd ../frontend && npm install && npm run build
cd .. && scripts/dev.sh seed     # API :8000, web :3000
```
Demo logins (password `demo1234`) are listed on the sign-in page when `DEMO=1`.

## Modules
| Module | Status |
|---|---|
| M0 Foundation: design system, BN/EN, day/night, login, roles, tenancy, audit | done |
| M1 Landing website | next |
| M2 SaaS console | planned |
| M3 Property setup | planned |
| M4 Service charge | planned |
| M5 Cash collection | planned |
| M6 Finance and assets | planned |
| M7 Staff and payroll | planned |
| M8 Notices and policies | planned |
| M9 Tenant onboarding and DMP | planned |
| M10 Complaints and committee | planned |

## User types
SaaS team: Super Admin, SaaS Admin, SaaS Finance, SaaS Sales, SaaS User.
Customer side: Agency Manager, Property Admin, Flat Owner, Tenant, Caretaker, Committee President, Secretary, Treasurer, Member, Auditor, Guard, Owner's Representative. One person can hold several roles (for example a flat owner who is also a committee member).
