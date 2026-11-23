#!/usr/bin/env bash
# smoke-test.sh — G0–G7 smoke test (PDT v1.2 Appendix C)
# Runs the workbench end to end on SYNTHETIC examples only.
# No real API calls are made unless the corresponding key is set;
# without keys the Jev steps are skipped with a clear message, never faked.
set -euo pipefail
cd "$(dirname "$0")/.."

echo "== G0 cold start =="
test -f README.md || { echo "FAIL: README.md missing"; exit 1; }
test -f .env.example || { echo "FAIL: .env.example missing"; exit 1; }
test -f schemas/unified-table.schema.json || { echo "FAIL: schema missing"; exit 1; }
echo "OK: README, .env.example, schemas present"

echo "== G1 data intake =="
test -f examples/sample-unified-table.csv || { echo "FAIL: sample CSV missing"; exit 1; }
rows=$(($(wc -l < examples/sample-unified-table.csv) - 1))
echo "OK: sample CSV has $rows data rows (synthetic)"
test "$rows" -ge 20 || { echo "FAIL: expected >= 20 rows"; exit 1; }

echo "== G2 sampling audit (30/30 traceable) =="
# Every data row must carry a source URL and a batch id.
python3 - <<'PY'
import csv, sys
with open("examples/sample-unified-table.csv", newline="", encoding="utf-8") as f:
    rows = list(csv.DictReader(f))
missing = [r["record_id"] for r in rows if not r.get("source_url") or not r.get("batch_id")]
if missing:
    print("FAIL: rows without source_url/batch_id:", missing); sys.exit(1)
print(f"OK: {len(rows)}/{len(rows)} sample rows traceable to source + batch")
PY

echo "== G3 discovery =="
test -f examples/sample-intent-registry.json || { echo "FAIL: sample registry missing"; exit 1; }
echo "OK: sample intent registry present (synthetic)"

echo "== G4 Jev coding =="
if [ -z "${TYPESAFE_API_KEY:-}" ]; then
  echo "SKIP: TYPESAFE_API_KEY not set — Jev steps skipped, not faked"
else
  echo "TYPESAFE_API_KEY set — Jev calibration would run here (not implemented in this scaffold)"
fi

echo "== G5 Token Center =="
echo "SKIP: Token Center not implemented in this scaffold (design only, PDT v1.2 §6.7)"

echo "== G6 questionnaire loop =="
test -f examples/sample-questionnaire.md || { echo "FAIL: sample questionnaire missing"; exit 1; }
echo "OK: sample questionnaire present (synthetic)"

echo "== G7 fault & security =="
./scripts/check-no-secrets.sh

echo "SMOKE TEST DONE (synthetic data only; Jev/Token Center steps skipped as designed)"
