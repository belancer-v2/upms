# Dependency audit

Audited 2026-10-25 (P2).

## Backend (Python)

- `backend/requirements.txt` pins every direct dependency to an exact version (the set the full test suite passes on). Transitive packages are resolved from those pins; for fully reproducible builds generate a hashed lock with `uv pip compile backend/requirements.txt --generate-hashes -o backend/requirements.lock` in CI.
- Tool: `pip-audit`. Run it in a throw-away environment so it is not added to the application:

```bash
python3 -m venv /tmp/audit && /tmp/audit/bin/pip install pip-audit
cd backend && .venv/bin/python - > /tmp/freeze.txt <<'PY'
import importlib.metadata as m
for d in sorted(m.distributions(), key=lambda d: d.metadata["Name"].lower()): print(f'{d.metadata["Name"]}=={d.version}')
PY
/tmp/audit/bin/pip-audit -r /tmp/freeze.txt --no-deps --disable-pip
```

- Result on 2026-10-25 (42 installed packages): **No known vulnerabilities found.**
- Re-run before every release and monthly. To upgrade: bump the pin, run `pytest`, run `pip-audit`, commit both.

## Frontend (npm)

`cd frontend && npm audit --omit=dev` on 2026-10-25 reports **2 findings, both from the same cause**: the copy of PostCSS (<= 8.5.22) that ships inside `next@15.5.x` (XSS in `</style>` stringify output, and `sourceMappingURL` file reads in PostCSS source-map auto-loading). PostCSS is used by Next.js only while building CSS from our own source files; nothing user-supplied is parsed at runtime, so the practical exposure is low. The advisory's fix is a jump to Next 16 (`npm audit fix --force`, a breaking change). **Decision for the owner:** plan the Next 16 upgrade as its own task, test the pages and the CSP middleware afterwards. Until then do not accept untrusted CSS in builds.

## Process

1. CI: run `pip-audit` and `npm audit --omit=dev` on every pull request and weekly; fail on high or critical findings that have a fix.
2. Update pins deliberately, never with `>=` ranges in `requirements.txt`.
3. Review new dependencies before adding them (maintainers, downloads, licence, install scripts).
4. Keep the base images (`backend/Dockerfile`, Node image) on supported releases and rebuild monthly.
