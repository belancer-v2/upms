#!/usr/bin/env bash
# Verifies the Help center content and the P5 dictionary keys. Run from the repo root: scripts/check-help.sh
set -euo pipefail
cd "$(dirname "$0")/.."
OUT="$(mktemp -d)"; trap 'rm -rf "$OUT"' EXIT
(cd frontend && npx tsc src/lib/help/index.ts src/lib/help/search.ts src/lib/dict.ts src/lib/legal.ts src/lib/company.ts src/lib/setupDefaults.ts \
  --outDir "$OUT" --module commonjs --target es2022 --skipLibCheck --moduleResolution node --esModuleInterop)
node scripts/check-help.cjs "$OUT"
