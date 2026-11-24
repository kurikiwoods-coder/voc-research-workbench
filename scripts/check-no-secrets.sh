#!/usr/bin/env bash
# Inspect Git-bound content. Report file names only, never matched values.
set -eu
cd "$(dirname "$0")/.."
python - <<'PY'
from pathlib import Path
import re
import subprocess
import sys
paths = subprocess.check_output(["git","ls-files","-z"]).decode().split("\0")
rules = [r"sk-[A-Za-z0-9]{16,}",r"AKIA[0-9A-Z]{16}",r"xox[baprs]-[A-Za-z0-9-]{10,}",r"ghp_[A-Za-z0-9]{20,}",r"github_pat_[A-Za-z0-9_]{20,}",r"[\w.%+-]+@[\w.-]+\.[A-Za-z]{2,}",r"(?m)^[ \t]*(?:TYPESAFE|JEVMODEL|TAVILY|BRAVE|YOUTUBE)_API_KEY[ \t]*=[ \t]*[^\s#]+",r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"]
bad = set()
for name in filter(None, paths):
    path = Path(name)
    if ((path.name.startswith(".env") and path.name!=".env.example")
            or name.startswith(("data/raw/","data/private/","data/cx/","runtime/"))
            or {"credentials", "api-diagnostics"}.intersection(path.parts)):
        bad.add(name)
    if name == "scripts/check-no-secrets.sh":
        continue
    blobs = [subprocess.check_output(["git","show",":"+name])]
    if path.is_file():
        blobs.append(path.read_bytes())
    for blob in blobs:
        if b"\0" not in blob[:8192] and any(re.search(r,blob.decode("utf-8","replace")) for r in rules):
            bad.add(name)
if bad:
    print("Review before push:",", ".join(sorted(bad)))
    sys.exit(1)
print("OK: Git-bound content and staged files checked")
PY
