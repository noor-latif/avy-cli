#!/usr/bin/env bash
# Scan tracked files for common credential / personal-data patterns.
set -euo pipefail
cd "$(dirname "$0")/.."

patterns=(
  'eyJhbGci'                         # JWT
  '[0-9]{12}'                        # Swedish personal number
  'AVY_TOKEN_FILE *= *["'"'"'][^"'"'"']+/token\.json'
  'noor\.crystal|Kryddvägen|Latif'
  '/tmp/opencode'
)

status=0
printf '%s\n' "${patterns[@]}" |
  git grep --quiet -I -E -f - -- . ':!scripts/check-secrets.sh' || status=$?
case "$status" in
  0) echo "ERROR: possible secret/personal data in tracked files." >&2; exit 1 ;;
  1) ;;
  *) exit "$status" ;;
esac
echo "Secret scan clean."
