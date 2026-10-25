#!/usr/bin/env bash
# Rebuilds alembic/versions/*_0001_baseline.py from the current models. ONLY while no real database exists yet
# (before the first production install). After that, add revisions with `alembic revision --autogenerate` instead.
set -euo pipefail
cd "$(dirname "$0")/../backend"
TMP="$(mktemp -d)"; trap 'rm -rf "$TMP"' EXIT
rm -f alembic/versions/*.py
ALEMBIC_BATCH=0 FLATWISE_NO_DOTENV=1 DATABASE_URL="sqlite:///$TMP/empty.db" ${PYTHON:-.venv/bin/python} -m alembic revision --autogenerate -m baseline --rev-id 0001
${PYTHON:-.venv/bin/python} -m pytest -q tests/test_migrations.py
