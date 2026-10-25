# FlatWise on a VPS (Docker Compose)

Target: Ubuntu 24.04 LTS, Docker Compose, Caddy (automatic HTTPS), PostgreSQL in a container, a worker container for scheduled jobs,
uploads on a volume (S3-compatible storage later). The owner or a technician runs it; nothing here needs access from the assistant.
The cPanel guide (`docs/CPANEL_DEPLOY.md`) stays valid until you move.

## 1. Server size
| Stage | Size | Notes |
|---|---|---|
| Pilot, up to ~10 buildings | 2 vCPU, 4 GB RAM, 60 GB SSD | one API container with 2 workers, PostgreSQL ~512 MB |
| 10-50 buildings | 4 vCPU, 8 GB RAM, 100 GB SSD | raise `WEB_CONCURRENCY` to 4; add a daily off-server copy of uploads |
| Beyond | managed PostgreSQL, S3 storage, second API node | |
Pick a data centre close to Bangladesh users (Singapore or Mumbai). Enable the provider's snapshots as an extra, not the only backup.

## 2. Prepare the server (once)
```bash
# as root on the new machine
adduser deploy && usermod -aG sudo deploy
mkdir -p /home/deploy/.ssh && cp ~/.ssh/authorized_keys /home/deploy/.ssh/ && chown -R deploy:deploy /home/deploy/.ssh
# /etc/ssh/sshd_config: PermitRootLogin no, PasswordAuthentication no   -> systemctl restart ssh   (test a second session first!)
apt update && apt -y upgrade
apt -y install ufw fail2ban unattended-upgrades ca-certificates curl
ufw default deny incoming && ufw default allow outgoing
ufw allow 22/tcp && ufw allow 80/tcp && ufw allow 443/tcp && ufw enable
systemctl enable --now fail2ban
dpkg-reconfigure -plow unattended-upgrades          # security updates automatically
curl -fsSL https://get.docker.com | sh && usermod -aG docker deploy
timedatectl set-timezone UTC
```
Do not publish PostgreSQL's port (the compose file does not). Docker can bypass ufw for published ports, which is why only the proxy publishes 80/443.

## 3. DNS and e-mail authentication
* `A` record `app.example.com` (and `AAAA` if the server has IPv6) -> the server. Lower the TTL to 300 s a day before a move.
* Send e-mail through a provider (Amazon SES, Mailgun, Postmark, Brevo) rather than from the VPS; the VPS IP has no reputation and port 25 is often blocked.
* **SPF**: one TXT on the sending domain, e.g. `v=spf1 include:amazonses.com ~all` (use the provider's include; only one SPF record per domain).
* **DKIM**: add the provider's CNAME/TXT records (selector names come from the provider) and wait for "verified".
* **DMARC**: TXT `_dmarc.example.com` = `v=DMARC1; p=none; rua=mailto:dmarc@example.com` for the first month, read the reports, then `p=quarantine`, later `p=reject`.
* Use a sub-domain for newsletters/promotions (`mail.example.com`) so a spam complaint does not hurt invoices and password resets. Add a reverse-DNS (PTR) record only if you send directly.
* Test with mail-tester.com or Gmail "Show original" (SPF/DKIM/DMARC must say PASS).

## 4. Get the code and settings
```bash
sudo -iu deploy
git clone <repository> ~/flatwise && cd ~/flatwise        # or unpack a release tarball
cp deploy/.env.example .env && chmod 600 .env && nano .env
```
`.env` (never committed; keep a copy in the password manager): `POSTGRES_PASSWORD`, `SECRET_KEY`, `NID_KEY`, `APP_URL=https://app.example.com`, `SITE_ADDRESS=app.example.com`, optional `BOOTSTRAP_ADMIN_*`, `TRUSTED_PROXIES` (the compose network address of the proxy, so client IPs in logs and rate limits are right). Generate secrets as in `docs/RUNBOOK.md`.

## 5. First start
```bash
docker compose build
docker compose up -d db
docker compose run --rm api python -m app.bootstrap     # migrations, plans, first SUPER_ADMIN
docker compose up -d
docker compose ps                                       # all "healthy"/running
curl -fsS https://app.example.com/healthz
```
Caddy obtains and renews the certificate by itself once DNS points to the server and ports 80/443 are open. Remove `BOOTSTRAP_ADMIN_PASSWORD` from `.env` afterwards.
Services: `db` (PostgreSQL 16, volume `dbdata`), `api` (uvicorn, workers = `WEB_CONCURRENCY`, health check `/healthz`, non-root), `jobs` (runs `python -m app.jobs.cli run-due` every minute), `web` (Next.js standalone), `proxy` (Caddy, `deploy/Caddyfile`). Uploads are the `uploads` volume mounted by `api` and `jobs`.
To use MariaDB instead: replace the `db` service with `mariadb:10.11`, set `DATABASE_URL=mysql://…`; everything else is the same.

## 6. Staging, then production
Keep a second, smaller server (or the same compose project name on another machine) called staging with its own domain `staging.example.com`, its own `.env` and secrets, and a copy of production data only if it is anonymised.
Flow: merge -> CI is green (SQLite, PostgreSQL and MariaDB suites, type check, build) -> deploy to staging -> run the checks below -> deploy to production in a quiet hour.
```bash
# on either server, as deploy
cd ~/flatwise && git fetch && git checkout <tag>
./scripts/backup.sh                     # production only, before changing anything
docker compose build
docker compose run --rm api python -m app.bootstrap       # applies new migrations
docker compose up -d
curl -fsS https://app.example.com/readyz
```
Staging checks: sign in, open invoices, create and cancel a visitor pass, upload a document, trigger `docker compose run --rm api python -m app.jobs.cli list`.

## 7. Rollback
`git checkout <previous tag> && docker compose build && docker compose up -d`. If the release included a migration that is not backward compatible, restore the pre-deploy dump (`scripts/restore.sh`, see `docs/RUNBOOK.md`) after stopping `api` and `jobs`. Tag images with the release (`docker compose build` after checkout is enough) and keep the previous two.

## 8. Backups (nightly, off-server, 30 days) and the monthly drill
```
# crontab -e   (as deploy)
15 2 * * * cd ~/flatwise && docker compose exec -T db true && BACKUP_DIR=$HOME/backups RETENTION_DAYS=30 DATABASE_URL=postgresql://flatwise:$(grep ^POSTGRES_PASSWORD .env | cut -d= -f2-)@127.0.0.1:5432/flatwise UPLOAD_DIR=/var/lib/docker/volumes/flatwise_uploads/_data scripts/backup.sh >> ~/backup.log 2>&1
45 2 * * * rclone sync ~/backups remote:flatwise-backups --min-age 5m >> ~/backup.log 2>&1
```
(The database port must be reachable for `pg_dump` from the host: either publish it on `127.0.0.1` only by adding `ports: ["127.0.0.1:5432:5432"]` to `db`, or run `docker compose exec -T db pg_dump -U flatwise flatwise | gzip > …` instead. Check the upload volume path with `docker volume inspect flatwise_uploads`.)
The off-server copy goes to a different provider/region (Backblaze B2, S3, Wasabi, a second VPS) with versioning; the remote side keeps 30 days (lifecycle rule). Restore drill monthly: `docs/RUNBOOK.md` section 4, on a scratch database, never on production.

## 9. Monitoring
* Uptime monitor on `https://app.example.com/healthz` (and `/readyz`) every minute with SMS/e-mail alert (UptimeRobot, Better Stack).
* Disk: `df -h` alert at 80%; `docker system prune -f` monthly (not volumes).
* Logs: `docker compose logs -f api` (JSON lines). Ship them to a log service if you grow; docker keeps them rotated if you add `logging: {driver: json-file, options: {max-size: "10m", max-file: "5"}}` to services.
* Certificates: Caddy renews automatically; the uptime monitor also warns before expiry.

## 10. Later: S3-compatible uploads
Files are written under `UPLOAD_DIR` today (every access goes through `config.UPLOAD_DIR`). Moving to object storage needs a small storage layer in the backend (planned work); until then the volume is backed up with the database.
