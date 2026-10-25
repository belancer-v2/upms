#!/usr/bin/env bash
# Builds two upload-ready zips for cPanel in ./dist:
#   flatwise-backend-<stamp>.zip   Python app (app/, alembic/, passenger_wsgi.py, requirements.txt, MIGRATIONS notes, scripts)
#   flatwise-web-<stamp>.zip       Next.js standalone server (server.js, .next/, public/, node_modules subset)
# Usage: API_ORIGIN=https://example.com scripts/build_cpanel_bundle.sh [--backend-only|--web-only]
# API_ORIGIN is baked into the frontend's /api rewrite at build time: it is the public https address of this site.
# Run it on your computer (needs node 20+/npm and zip). Nothing secret goes into the zips: settings live in cPanel.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"; OUT="$ROOT/dist"; STAMP="$(date -u +%Y%m%d-%H%M)"
mkdir -p "$OUT"
command -v zip >/dev/null || { echo "zip is required (apt install zip)"; exit 1; }
want_backend=1; want_web=1
[ "${1:-}" = "--backend-only" ] && want_web=0
[ "${1:-}" = "--web-only" ] && want_backend=0

if [ $want_backend = 1 ]; then
  STAGE="$(mktemp -d)"; trap 'rm -rf "$STAGE"' EXIT
  B="$STAGE/backend"; mkdir -p "$B"
  cp -R "$ROOT/backend/app" "$ROOT/backend/alembic" "$B/"
  cp "$ROOT/backend/alembic.ini" "$ROOT/backend/passenger_wsgi.py" "$ROOT/backend/requirements.txt" "$ROOT/backend/.env.example" "$ROOT/backend/MIGRATIONS.md" "$B/" 2>/dev/null || true
  mkdir -p "$B/scripts" && cp "$ROOT/scripts/backup.sh" "$ROOT/scripts/restore.sh" "$B/scripts/"
  find "$B" \( -name __pycache__ -o -name '*.pyc' -o -name '*.db' \) -prune -exec rm -rf {} + 2>/dev/null || true
  rm -rf "$B/app/uploads"
  (cd "$STAGE/backend" && zip -qr "$OUT/flatwise-backend-$STAMP.zip" .)
  echo "built $OUT/flatwise-backend-$STAMP.zip"
fi

if [ $want_web = 1 ]; then
  : "${API_ORIGIN:?set API_ORIGIN to the public https address of the site, e.g. https://app.example.com}"
  export API_ORIGIN NEXT_TELEMETRY_DISABLED=1
  (cd "$ROOT/frontend" && npm ci && npm run build)
  S="$ROOT/frontend/.next/standalone"
  [ -f "$S/server.js" ] || { echo "standalone output missing: is output: 'standalone' set in next.config.mjs?"; exit 1; }
  W="$(mktemp -d)"; cp -R "$S/." "$W/"
  mkdir -p "$W/.next" && cp -R "$ROOT/frontend/.next/static" "$W/.next/static"
  [ -d "$ROOT/frontend/public" ] && cp -R "$ROOT/frontend/public" "$W/public"
  (cd "$W" && zip -qr "$OUT/flatwise-web-$STAMP.zip" .)
  rm -rf "$W"
  echo "built $OUT/flatwise-web-$STAMP.zip"
fi
echo "Next: docs/CPANEL_DEPLOY.md"
