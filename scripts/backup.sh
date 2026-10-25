#!/usr/bin/env bash
# Database dump + uploads archive with retention. Works for MySQL/MariaDB (cPanel) and PostgreSQL.
#   DATABASE_URL=mysql://user:pass@localhost/db UPLOAD_DIR=~/flatwise-data/uploads BACKUP_DIR=~/backups scripts/backup.sh
# Env: DATABASE_URL (required), UPLOAD_DIR, BACKUP_DIR (default ./backups), RETENTION_DAYS (default 14), BACKUP_KEEP_MIN (default 3)
# Reads DATABASE_URL/UPLOAD_DIR from backend/.env (repo) or ./.env (cPanel bundle) when not set. Output: flatwise-<stamp>.sql.gz and flatwise-<stamp>-uploads.tar.gz (chmod 600).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
ENVFILE=""; for f in "$ROOT/backend/.env" "$ROOT/.env"; do [ -f "$f" ] && ENVFILE="$f" && break; done
if [ -z "${DATABASE_URL:-}" ] && [ -n "$ENVFILE" ]; then
  DATABASE_URL="$(grep -E '^DATABASE_URL=' "$ENVFILE" | head -1 | cut -d= -f2- | sed 's/[[:space:]]*#.*//' | tr -d "\"'")"
  UPLOAD_DIR="${UPLOAD_DIR:-$(grep -E '^UPLOAD_DIR=' "$ENVFILE" | head -1 | cut -d= -f2- | sed 's/[[:space:]]*#.*//' | tr -d "\"'")}"
fi
: "${DATABASE_URL:?DATABASE_URL is required}"
BACKUP_DIR="${BACKUP_DIR:-$PWD/backups}"; RETENTION_DAYS="${RETENTION_DAYS:-14}"; KEEP_MIN="${BACKUP_KEEP_MIN:-3}"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
umask 077; mkdir -p "$BACKUP_DIR"

# split scheme://user:pass@host:port/db?query  (no python needed on the host)
rest="${DATABASE_URL#*://}"; scheme="${DATABASE_URL%%://*}"; scheme="${scheme%%+*}"
cred="${rest%%@*}"; hostpart="${rest#*@}"; user="${cred%%:*}"; pass="${cred#*:}"
hostport="${hostpart%%/*}"; db="${hostpart#*/}"; db="${db%%\?*}"; host="${hostport%%:*}"; port=""; [[ "$hostport" == *:* ]] && port="${hostport##*:}"
# URL-decoded password
pass="$(printf '%b' "${pass//%/\\x}")"

case "$scheme" in
  mysql|mariadb)
    cnf="$(mktemp)"; trap 'rm -f "$cnf"' EXIT
    printf '[client]\nuser=%s\npassword=%s\nhost=%s\n%s\n' "$user" "$pass" "$host" "${port:+port=$port}" > "$cnf"
    mysqldump --defaults-extra-file="$cnf" --single-transaction --quick --routines --default-character-set=utf8mb4 "$db" | gzip -9 > "$BACKUP_DIR/flatwise-$STAMP.sql.gz" ;;
  postgres|postgresql)
    PGPASSWORD="$pass" pg_dump -h "$host" ${port:+-p "$port"} -U "$user" --no-owner --format=plain "$db" | gzip -9 > "$BACKUP_DIR/flatwise-$STAMP.sql.gz" ;;
  *) echo "backup.sh: unsupported database scheme '$scheme' (SQLite: copy the file while the app is stopped)" >&2; exit 2 ;;
esac
gzip -t "$BACKUP_DIR/flatwise-$STAMP.sql.gz"

if [ -n "${UPLOAD_DIR:-}" ] && [ -d "$UPLOAD_DIR" ]; then
  tar -C "$(dirname "$UPLOAD_DIR")" -czf "$BACKUP_DIR/flatwise-$STAMP-uploads.tar.gz" "$(basename "$UPLOAD_DIR")"
fi

# retention: delete files older than RETENTION_DAYS, but always keep the newest KEEP_MIN dumps
ls -1t "$BACKUP_DIR"/flatwise-*.sql.gz 2>/dev/null | tail -n +$((KEEP_MIN + 1)) | while read -r f; do
  if [ -n "$(find "$f" -mtime +"$RETENTION_DAYS" -print 2>/dev/null)" ]; then rm -f "$f" "${f%.sql.gz}-uploads.tar.gz"; fi
done
echo "backup ok: $BACKUP_DIR/flatwise-$STAMP.sql.gz ($(du -h "$BACKUP_DIR/flatwise-$STAMP.sql.gz" | cut -f1))"
