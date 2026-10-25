# FlatWise runbook

For the person who runs the server. Hosting guides: `docs/CPANEL_DEPLOY.md` (interim), `docs/VPS_DEPLOY.md` (target).
Commands assume you are in `backend/` with the virtualenv active (cPanel: the `source …/activate` line on the Python App screen; Docker: prefix with `docker compose run --rm api`).

## 1. Production settings (what the app checks at startup)
With `ENV=production` the API **refuses to start**, prints every problem, and exits when:

| Check | Fix |
|---|---|
| `SECRET_KEY`, `NID_KEY`, `DATABASE_URL`, `APP_URL` not set | set them (the four required variables) |
| `SECRET_KEY` is the built-in default or shorter than 32 characters | `python -c "import secrets; print(secrets.token_urlsafe(48))"` |
| `NID_KEY` empty or not a Fernet key | `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"` |
| `DEMO=1` | set `DEMO=0` (the default in production). Demo accounts, seeding and the demo cash/OTP codes are off; `app.seed` raises an error in production |
| `CORS_ORIGINS` contains `*` | list exact origins, or leave empty (same-origin; the website proxies `/api`) |
| `DATABASE_URL` is SQLite | use `mysql://…` (MariaDB 10.5+/MySQL 8) or `postgresql://…` |
| `APP_URL` is not `https://` | use the public https address |

`GET /healthz` is liveness (process up, no database). `GET /readyz` is readiness (runs `SELECT 1`; 503 if the database is down).
API docs (`/docs`) are disabled in production. Errors return `{"detail": "...", "request_id": "..."}` with no stack trace; the trace is in the log under the same request id.
`.env.example` files: `backend/.env.example`, `frontend/.env.example`, `deploy/.env.example` (compose).

## 2. Deploy
1. Backup (section 5). 2. Put the new code in place. 3. `pip install -r requirements.txt`. 4. `python -m app.bootstrap` (applies only new migrations, idempotent). 5. Restart the app. 6. Check `/readyz`, sign in, open one building.
Never run `python -m app.seed` on a real database (it drops all tables in development; in production it refuses).

## 3. Rollback
* Code only: put the previous release back and restart. Migrations are written to be backward compatible (add first, remove later), so the previous code normally still runs.
* Code and schema: `alembic downgrade <revision before the release>` if that revision's `downgrade()` is safe, otherwise restore the pre-deploy backup (section 4). Restoring loses everything entered after the backup, so announce it.

## 4. Restore drill (do it monthly; a backup you never restored is a guess)
1. Pick the latest `flatwise-<stamp>.sql.gz` and `…-uploads.tar.gz` from your off-server copy.
2. Create an **empty scratch database** (never the production one), e.g. `cpuser_flatwise_drill` / `flatwise_drill`.
3. `DATABASE_URL=mysql://user:pw@localhost/cpuser_flatwise_drill UPLOAD_DIR=$HOME/drill/uploads scripts/restore.sh backups/flatwise-<stamp>.sql.gz backups/flatwise-<stamp>-uploads.tar.gz` (type the database name when asked).
4. Start a copy of the API against it (or `DATABASE_URL=… python -m app.bootstrap --no-migrate --check`), sign in as the administrator, open a building's invoices and a tenant document.
5. Record the date, backup age, time it took, and problems in your log. Drop the scratch database.

## 5. Backups
`scripts/backup.sh` (database dump with `mysqldump` or `pg_dump`, gzip-tested, plus a tar of `UPLOAD_DIR`, 14 days retention by default, `RETENTION_DAYS=30` for 30). It always keeps the newest 3 dumps. Copy the folder off the server daily. **The encryption keys are not in the backup**: store `SECRET_KEY` and `NID_KEY` in a password manager; without `NID_KEY` the encrypted NID numbers and payment-gateway credentials are unreadable.

## 6. Monitoring checklist
Daily (or automatic): `/healthz` and `/readyz` from an outside uptime monitor (UptimeRobot, Better Stack…) every minute, alert by SMS/e-mail; disk free above 20%; last backup younger than 26 hours; `jobs.log` has a line from the last 5 minutes.
Weekly: grep the log for `"level": "ERROR"` and 5xx statuses (`"status": 5`); check the SaaS console job page for failed jobs; look at slow requests (`"ms"` above 2000).
Monthly: restore drill, apply OS/Python/Node security updates, `pip list --outdated` for security fixes, review SaaS-team accounts.
Alert thresholds: `/readyz` failing 2 minutes; error rate above 2% for 10 minutes; any `FlatWise refuses to start` after a deploy.

## 7. Secrets rotation
| Secret | Effect of changing it | Procedure |
|---|---|---|
| Database password | none, if done in order | create the new password in the database, update `DATABASE_URL`, restart, confirm `/readyz`, remove the old password |
| `SECRET_KEY` | everybody is signed out; unused links in sent e-mails/SMS, pending cash-confirmation codes, visitor pass codes and in-flight payment callbacks stop working | do it outside business hours, set the new value, restart. Keep the old value in the password manager for a week in case of rollback |
| `NID_KEY` | all stored NID numbers (and gateway credentials) must be re-encrypted **before** the new key is used | see below |
| Mail/SMS/gateway provider keys | per provider | change in the provider portal, then in the environment, restart |
| First administrator's password | | sign in and use the password change screen |

### NID_KEY rotation
1. Announce a short maintenance window. Stop the API (cPanel: Stop in Setup Python App; Docker: `docker compose stop api jobs`) and disable the cron line.
2. Backup: `scripts/backup.sh`. Keep the dump.
3. Generate the new key: `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"` and store it in the password manager now.
4. Dry run (decrypts everything, changes nothing, rolls back):
   `OLD_NID_KEY=<current NID_KEY> NEW_NID_KEY=<new key> python -m app.rekey_nid --dry-run`
   It prints a count per column (`staff.nid_enc`, `tenant_cases.nid_enc`, `gateway_configs.credentials_enc`, …) and stops with an error naming the first row it cannot decrypt.
5. Real run (one transaction, all or nothing): the same command without `--dry-run`.
6. Set `NID_KEY` to the new key, start the API, re-enable cron. Check: reveal one staff NID in the app (it writes an audit line) and see the number is correct.
7. Keep the old key and the pre-rotation dump for 30 days, then destroy both.
If the old key was lost, the NID numbers cannot be recovered; staff and tenants must re-enter them (the `last4` display is stored separately).
(If data was written with no `NID_KEY` set in development, leave `OLD_NID_KEY` empty and set `SECRET_KEY` to the value used then. Production never does this.)

## 8. Incident basics
1. Find the request id in the error screen or the response header `X-Request-ID`; `grep` it in the log.
2. Site down: check `/healthz`; if ok and `/readyz` 503, the database; if neither answers, the app process / hosting panel; then the web server / DNS / certificate expiry.
3. Bad deploy: roll back (section 3).
4. Suspected data leak: change `SECRET_KEY` (signs everyone out), rotate provider keys, export the audit log (`/api/audit`), then follow the security notes in `backend/SECURITY.md` if present.

## 9. VPS
The long-term setup (Docker Compose, Caddy, hardening, off-server backups) is in `docs/VPS_DEPLOY.md`.
