#!/usr/bin/env bash
# Local regressions and three actual cold starts. Business gates are recorded separately.
set -euo pipefail
cd "$(dirname "$0")/.."
python -m unittest discover -s tests -p 'test_*.py' -v
python scripts/cold_start.py
bash scripts/check-no-secrets.sh
