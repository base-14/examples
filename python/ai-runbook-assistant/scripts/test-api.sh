#!/usr/bin/env bash
set -euo pipefail
BASE="${BASE_URL:-http://localhost:8000}"
curl -fsS --max-time 10 "$BASE/healthz" >/dev/null && echo "healthz ok"
curl -fsS --max-time 300 -X POST "$BASE/api/v1/diagnose" \
  -H 'content-type: application/json' \
  -d '{"question":"checkout pods are being OOMKilled, what do I do?"}' | tee /tmp/diagnose.json
echo
test -s /tmp/diagnose.json && echo "diagnose ok"
