#!/bin/sh
# Starts the API. WEB_CONCURRENCY = uvicorn workers. Migrations are NOT run here: use `docker compose run --rm api python -m app.bootstrap`.
set -e
exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}" \
  --workers "${WEB_CONCURRENCY:-2}" \
  --proxy-headers --forwarded-allow-ips "${FORWARDED_ALLOW_IPS:-*}" \
  --no-access-log \
  --timeout-keep-alive "${KEEPALIVE_SECONDS:-5}" \
  --timeout-graceful-shutdown "${GRACEFUL_SECONDS:-20}"
