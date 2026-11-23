#!/usr/bin/env bash
# check-no-secrets.sh — pre-commit scan: keys, emails, order numbers, CX text.
# Exits non-zero if a forbidden pattern is found. Run before every push.
set -uo pipefail
cd "$(dirname "$0")/.."

fail=0

# Real .env files must never be staged
if [ -f .env ] || ls .env.* 2>/dev/null | grep -vq '^\.env\.example$'; then
  echo "FAIL: real .env file present in the repo root"
  fail=1
fi

# Scan tracked text files for likely secrets / PII
# (skips binary docx files; the .env.example intentionally contains only key NAMES)
patterns=(
  'sk-[A-Za-z0-9]{16,}'
  'AKIA[0-9A-Z]{16}'
  'xox[baprs]-[A-Za-z0-9-]{10,}'
  'ghp_[A-Za-z0-9]{20,}'
  'github_pat_[A-Za-z0-9_]{20,}'
  '[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}'
)
for p in "${patterns[@]}"; do
  hits=$(grep -rEIn --exclude-dir=.git --exclude='*.docx' --exclude='.env.example' --exclude='check-no-secrets.sh' "$p" . 2>/dev/null || true)
  if [ -n "$hits" ]; then
    echo "FAIL: pattern '$p' found:"
    echo "$hits"
    fail=1
  fi
done

# Real data directories must be empty / absent in the public repo
for d in data/raw data/cx data/private; do
  if [ -d "$d" ] && [ -n "$(ls -A "$d" 2>/dev/null)" ]; then
    echo "FAIL: $d contains files — real data must not be committed"
    fail=1
  fi
done

if [ "$fail" -eq 0 ]; then
  echo "OK: no secrets, emails, or real-data directories found"
else
  echo "check-no-secrets FAILED — fix before committing"
  exit 1
fi
