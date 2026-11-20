#!/usr/bin/env bash
# Fail if this repository contains anything that looks like machine-specific data.
set -euo pipefail

cd "$(dirname "$0")/.."

patterns=(
  '/Users/[A-Za-z0-9._-]+'
  '/home/[A-Za-z0-9._-]+'
  'C:\\\\Users\\\\'
  'mt16'
  'sk-[A-Za-z0-9]{16,}'
  'ghp_[A-Za-z0-9]{20,}'
  'github_pat_[A-Za-z0-9_]{20,}'
  'AKIA[0-9A-Z]{16}'
  'xox[bp]-[A-Za-z0-9-]{10,}'
)

status=0
for pattern in "${patterns[@]}"; do
  if rg --hidden --line-number --no-heading \
      --glob '!.git/**' --glob '!**/.venv/**' --glob '!scripts/check_pii.sh' \
      -e "$pattern" . >/tmp/chor-pii-hit 2>/dev/null; then
    echo "PII pattern matched: $pattern"
    cat /tmp/chor-pii-hit
    status=1
  fi
done
rm -f /tmp/chor-pii-hit

if [ "$status" -eq 0 ]; then
  echo "check_pii: clean"
fi
exit "$status"
