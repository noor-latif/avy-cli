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

failed=0
for pattern in "${patterns[@]}"; do
  if git ls-files -z | grep -zv '^scripts/check-secrets.sh$' | xargs -0 -r grep -nE "$pattern" 2>/dev/null; then
    echo "ERROR: possible secret/personal data matched: $pattern" >&2
    failed=1
  fi
done

if [ "$failed" -ne 0 ]; then
  exit 1
fi
echo "Secret scan clean."
