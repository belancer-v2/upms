#!/usr/bin/env bash
# Starts API (8000) and web (3000) for local use. Usage: scripts/dev.sh [seed]
set -e
cd "$(dirname "$0")/.."
if [ "$1" = "seed" ] || [ ! -f backend/flatwise.db ]; then (cd backend && .venv/bin/python -m app.seed); fi
(cd backend && .venv/bin/uvicorn app.main:app --port 8000 > /tmp/fw-api.log 2>&1 &)
(cd frontend && npm run start > /tmp/fw-web.log 2>&1 &)
echo "API http://127.0.0.1:8000  Web http://127.0.0.1:3000"
