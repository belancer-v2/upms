#!/usr/bin/env bash
# Restore a dump (and optionally uploads) made by backup.sh. DESTRUCTIVE: it replaces the database contents.
#   DATABASE_URL=... scripts/restore.sh backups/flatwise-20261025T020000Z.sql.gz [backups/flatwise-...-uploads.tar.gz]
# Restore drill: point DATABASE_URL at an EMPTY scratch database first (see docs/RUNBOOK.md), never at production by mistake:
# the script prints the target and waits for you to type the database name.
set -euo pipefail
DUMP="${1:?usage: restore.sh <dump.sql.gz> [uploads.tar.gz]}"; UPL="${2:-}"
: "${DATABASE_URL:?DATABASE_URL is required}"
rest="${DATABASE_URL#*://}"; scheme="${DATABASE_URL%%://*}"; scheme="${scheme%%+*}"
cred="${rest%%@*}"; hostpart="${rest#*@}"; user="${cred%%:*}"; pass="${cred#*:}"
hostport="${hostpart%%/*}"; db="${hostpart#*/}"; db="${db%%\?*}"; host="${hostport%%:*}"; port=""; [[ "$hostport" == *:* ]] && port="${hostport##*:}"
pass="$(printf '%b' "${pass//%/\\x}")"
gzip -t "$DUMP"
echo "This will REPLACE the contents of database '$db' on '$host'."
if [ "${ASSUME_YES:-}" != "$db" ]; then read -r -p "Type the database name to continue: " ans; [ "$ans" = "$db" ] || { echo aborted; exit 1; }; fi
case "$scheme" in
  mysql|mariadb)
    cnf="$(mktemp)"; trap 'rm -f "$cnf"' EXIT
    printf '[client]\nuser=%s\npassword=%s\nhost=%s\n%s\n' "$user" "$pass" "$host" "${port:+port=$port}" > "$cnf"
    gunzip -c "$DUMP" | mysql --defaults-extra-file="$cnf" --default-character-set=utf8mb4 "$db" ;;
  postgres|postgresql)
    export PGPASSWORD="$pass"
    psql -h "$host" ${port:+-p "$port"} -U "$user" -d "$db" -v ON_ERROR_STOP=1 -c "DROP SCHEMA public CASCADE; CREATE SCHEMA public;"
    gunzip -c "$DUMP" | psql -h "$host" ${port:+-p "$port"} -U "$user" -d "$db" -v ON_ERROR_STOP=1 -q ;;
  *) echo "unsupported scheme $scheme" >&2; exit 2 ;;
esac
if [ -n "$UPL" ] && [ -n "${UPLOAD_DIR:-}" ]; then
  mkdir -p "$(dirname "$UPLOAD_DIR")"; tar -C "$(dirname "$UPLOAD_DIR")" -xzf "$UPL"
fi
echo "restore ok. Next: run 'python -m app.bootstrap --no-migrate --check' and open /readyz."
