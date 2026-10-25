# Deploying FlatWise on cPanel

This is the primary, interim hosting path: a cPanel account (shared or VPS) with **Setup Python App**, **Setup Node.js App**,
**MySQL Databases**, **Cron Jobs** and **Terminal or SSH**. For the long-term VPS plan see `docs/VPS_DEPLOY.md`.

Layout used below (replace `cpuser` and `example.com`):

| What | Where |
|---|---|
| Website (Next.js, Node.js App) | `https://example.com` , code in `~/flatwise/web` |
| API (FastAPI, Python App) | `https://api.example.com` , code in `~/flatwise/backend` |
| Uploads (NID photos, agreements) | `~/flatwise-data/uploads` (outside every web root) |
| Backups | `~/flatwise-data/backups` |

Why a separate API sub-domain: Passenger mounts a Python app at the root of its (sub)domain, which is simple and avoids URL-prefix
problems. Visitors only ever use `example.com`; the website forwards `/api/*` to `api.example.com` on the server (a Next.js rewrite),
so there is no CORS and no extra setup in the browser.

## 0. What you need before starting
* A cPanel plan that shows **Setup Python App** (CloudLinux, Python 3.11 or newer) and **Setup Node.js App** (Node 20 or newer). If either is missing, ask the host to enable it.
* Two DNS names pointing to the account: `example.com` and `api.example.com` (create the sub-domain in **Domains**).
* A computer with Node 20+, `npm`, `zip` and `bash` to build the upload bundles (cPanel shared hosting is too small to build Next.js).
* Three secrets, generated once and kept in your password manager (never in git, never in chat):
  ```bash
  python3 -c "import secrets; print(secrets.token_urlsafe(48))"                                   # SECRET_KEY
  python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"       # NID_KEY (losing it makes stored NID numbers unreadable)
  ```

## 1. Build the two zips (on your computer)
```bash
API_ORIGIN=https://api.example.com scripts/build_cpanel_bundle.sh
# -> dist/flatwise-backend-<stamp>.zip and dist/flatwise-web-<stamp>.zip
```
`API_ORIGIN` is baked into the website at build time: it is where the website forwards `/api` to.

## 2. MySQL database
cPanel > **MySQL Databases** (or **MySQL Database Wizard**):
1. Create database `cpuser_flatwise` (the `cpuser_` prefix is added by cPanel).
2. Create user `cpuser_fw` with a long random password.
3. Add the user to the database with **ALL PRIVILEGES**.
4. Charset: new cPanel databases are usually `utf8mb4`. Verify in phpMyAdmin > Operations: collation `utf8mb4_unicode_ci` (or `utf8mb4_general_ci`). If it shows `latin1`, change it before creating tables, because Bangla text needs utf8mb4.
5. Your URL is `mysql://cpuser_fw:PASSWORD@localhost/cpuser_flatwise`. A password with special characters must be URL-encoded (`@` is `%40`, `#` is `%23`, `/` is `%2F`).

## 3. Upload the API and create the Python app
1. File Manager > create `~/flatwise` and `~/flatwise-data/uploads` (mode 750; **not** under `public_html`).
2. Upload `flatwise-backend-<stamp>.zip` to `~/flatwise` and **Extract** into `~/flatwise/backend`.
3. cPanel > **Setup Python App** > **Create Application**:
   * Python version: highest available, **3.11 or newer** (3.12/3.13 preferred).
   * Application root: `flatwise/backend`
   * Application URL: choose `api.example.com` (empty path).
   * Application startup file: `passenger_wsgi.py`
   * Application Entry point: `application`
4. Press **Create**. The screen shows the command to enter the virtualenv, like `source /home/cpuser/virtualenv/flatwise/backend/3.12/bin/activate && cd /home/cpuser/flatwise/backend`.
5. In the same screen: **Configuration files** > add `requirements.txt` > **Run Pip Install**. Or from Terminal: run the command from step 4, then `pip install -r requirements.txt`.
6. **Environment variables** (same screen, **Add Variable**). These are the required ones; the app refuses to start in production without them and prints the list of what is wrong into the log.

   | Name | Value |
   |---|---|
   | `ENV` | `production` |
   | `SECRET_KEY` | generated above |
   | `NID_KEY` | generated above |
   | `DATABASE_URL` | `mysql://cpuser_fw:PASSWORD@localhost/cpuser_flatwise` |
   | `APP_URL` | `https://example.com` (links in e-mails; must be https) |
   | `UPLOAD_DIR` | `/home/cpuser/flatwise-data/uploads` |
   | `DB_POOL_SIZE` / `DB_MAX_OVERFLOW` | `3` / `2` (shared hosts cap MySQL connections) |
   | `DEMO` | `0` (the default in production; never `1`) |

   Cron jobs and SSH shells do **not** see these variables. For them (and as a backup) create `~/flatwise/backend/.env` with the same `NAME=value` lines (copy `.env.example`), then `chmod 600 .env`. Variables set in the cPanel screen win over `.env`.
7. Press **Restart**.

## 4. Create the tables and the first administrator
Terminal (or SSH), after entering the virtualenv (step 3.4):
```bash
export BOOTSTRAP_ADMIN_EMAIL=you@example.com BOOTSTRAP_ADMIN_NAME="Your Name" BOOTSTRAP_ADMIN_PASSWORD='a-long-passphrase-12+'
python -m app.bootstrap
unset BOOTSTRAP_ADMIN_PASSWORD
```
It runs `alembic upgrade head`, loads the plans / credit packs / settings (no demo data, ever) and creates the first SUPER_ADMIN. It can be run again safely. If you have no Terminal: ask the host to enable it, or run the same command locally against the remote MySQL if the host allows remote connections.

Check: open `https://api.example.com/healthz` (`{"status":"ok"}`) and `https://api.example.com/readyz` (`{"status":"ready","db":true}`).
A `503` on `/readyz` means the database URL or permissions are wrong. If the page shows "Incomplete response" or Passenger's error page, read the log (section 9).

## 5. Upload the website (Node.js App)
1. Upload `flatwise-web-<stamp>.zip` to `~/flatwise` and **Extract** into `~/flatwise/web`.
2. cPanel > **Setup Node.js App** > **Create Application**:
   * Node.js version: 20 or newer
   * Application mode: **Production**
   * Application root: `flatwise/web`
   * Application URL: `example.com`
   * Application startup file: `server.js`
3. **Add Variable**: `API_ORIGIN` = `https://api.example.com` (the rewrite was baked in at build time; the variable keeps the setting visible), `NODE_ENV` = `production`.
4. **Do not** press "Run NPM Install": the standalone bundle already contains what it needs. Press **Restart**.
5. Open `https://example.com`. The sign-in page must load and a login must work. If `/api/...` gives 404/502, `API_ORIGIN` was wrong at build time: rebuild with the right value and upload again.

If your host cannot run Node.js apps, the alternative is to put Next.js on a small separate server or on Vercel-style hosting and point it at `API_ORIGIN`; the Python side does not change.

## 6. HTTPS
cPanel > **SSL/TLS Status** > select `example.com`, `www.example.com`, `api.example.com` > **Run AutoSSL**. Then force https: in **Domains** switch **Force HTTPS Redirect** on for each domain.

## 7. Scheduler (cron)
The scheduled work (reminders, trial and subscription checks, mail queue) is a command, not a background thread, because shared hosting kills long-running processes.
cPanel > **Cron Jobs** > add (every minute):
```
* * * * * cd ~/flatwise/backend && /home/cpuser/virtualenv/flatwise/backend/3.12/bin/python -m app.jobs.cli run-due >> ~/flatwise-data/jobs.log 2>&1
```
(use the python path shown on the Setup Python App screen; `~/app` in some notes means this backend folder). Overlapping runs are safe: a database lock lets exactly one run each job. If your host limits cron to every 5 minutes, use `*/5 * * * *`; reminders will be up to 5 minutes late. Check with `python -m app.jobs.cli list` and by reading `jobs.log` (one JSON line per job). Rotate the log monthly or add `&& : > ~/flatwise-data/jobs.log` to a monthly cron.

## 8. File permissions
```bash
chmod 700 ~/flatwise-data ~/flatwise-data/uploads ~/flatwise-data/backups
chmod 600 ~/flatwise/backend/.env
chmod 750 ~/flatwise ~/flatwise/backend
```
Never put `.env`, the uploads or backups below `public_html`. The API serves uploaded files only after a permission check.

## 9. Logs
| Log | Where |
|---|---|
| API (JSON lines: request id, status, ms) | the Passenger log: Setup Python App shows the path, usually `~/logs/passenger.log` or `~/flatwise/backend/stderr.log` |
| Startup refusal ("refuses to start in ENV=production") | same file, first lines after Restart |
| Website | Setup Node.js App log link, or `~/logs/` |
| Cron / scheduler | `~/flatwise-data/jobs.log` |
| Web server errors | cPanel > **Metrics > Errors** |
Every API response has an `X-Request-ID` header; a user who reports an error can quote the `request_id` shown in the error and you grep it in the log.

## 10. Updating, rollback
1. Take a backup (section 11) **before** every update.
2. Build the new bundle, upload, extract over `~/flatwise/backend` (keep `.env`), `pip install -r requirements.txt`, `python -m app.bootstrap` (runs only new migrations), **Restart**.
3. Rollback: re-extract the previous zip, `alembic downgrade <previous revision>` only if the new migration was not backward compatible (see `backend/MIGRATIONS.md`), or restore the pre-update backup (`scripts/restore.sh`) if data must go back. Keep the last three zips.

## 11. Backups
* cPanel > **Backup** (or JetBackup) gives full-account backups; keep them on, but do not rely on them alone.
* Add a nightly database + uploads backup that you can copy off the server (`scripts/backup.sh` is in the backend zip):
  ```
  15 2 * * * cd ~/flatwise/backend && BACKUP_DIR=$HOME/flatwise-data/backups RETENTION_DAYS=30 bash scripts/backup.sh >> ~/flatwise-data/backup.log 2>&1
  ```
  It reads `DATABASE_URL` and `UPLOAD_DIR` from `.env`, uses `mysqldump`, and keeps 30 days.
* Copy `~/flatwise-data/backups` to another place every day (cPanel Backup destinations, rclone to cloud storage, or download weekly). Backups on the same server are not backups.
* Test the restore once a month: `docs/RUNBOOK.md`, "Restore drill".

## 12. Limits of shared hosting, and when to move
* No long-running workers: the scheduler is cron, e-mail/SMS are sent in the cron run or in the request. Large campaigns will be slow.
* Memory is limited (often 512 MB-1 GB for the account): keep `DB_POOL_SIZE` small; one Python process serves requests; Passenger may restart idle apps (first request after idle is slow).
* MySQL connections are limited (often 25-50 total): the pool settings above matter.
* The Python app cannot upload files bigger than the host's request limit (usually 128 MB; FlatWise allows 3 MB per file).
* No Docker, no custom ports, no Redis, no object storage.
* **Move to a VPS when a few buildings are live** (a good trigger: 3-5 paying buildings, or any day the cron or the site is slow). The VPS bundle is ready: `docker-compose.yml`, `docs/VPS_DEPLOY.md`. The data moves with `mysqldump`/`pg_dump` plus the uploads folder; moving from MariaDB to PostgreSQL needs a data migration (ask a technician), moving MariaDB to MariaDB in the compose file does not.

## 13. Troubleshooting
| Symptom | Likely cause |
|---|---|
| Passenger error page right after Restart | wrong Python version / missing `pip install`; open the log |
| Log says `FlatWise refuses to start` | a required variable is missing or unsafe; the message lists each one |
| `/readyz` 503 | `DATABASE_URL` wrong, password not URL-encoded, user not added to the database |
| Bangla text shows `????` | database or tables are not utf8mb4 |
| Login works but pages say "Not signed in" | `APP_URL`/https mismatch or the website was built with a wrong `API_ORIGIN` |
| Jobs never run | cron line has the wrong python path; run it by hand and read the output |
