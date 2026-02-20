#!/usr/bin/env bash
# Smoke tests for the AI Contract Analyzer API.
# Requires the server to be running (make dev or make docker-up).
set -euo pipefail

BASE_URL="${API_URL:-http://localhost:3000}"
PASS=0
FAIL=0
CONTRACT_ID=""

green() { printf '\033[0;32m✓ %s\033[0m\n' "$1"; }
red()   { printf '\033[0;31m✗ %s\033[0m\n' "$1"; }

check() {
  local name="$1"
  local actual="$2"
  local expected="$3"
  if [[ "$actual" == "$expected" ]]; then
    green "$name"
    PASS=$((PASS + 1))
  else
    red "$name (expected '$expected', got '$actual')"
    FAIL=$((FAIL + 1))
  fi
}

echo "=== AI Contract Analyzer — API Smoke Tests ==="
echo "Target: $BASE_URL"
echo ""

# ── health ─────────────────────────────────────────────────────────────────────
STATUS=$(curl -s -o /dev/null -w "%{http_code}" "$BASE_URL/health")
check "GET /health returns 200" "$STATUS" "200"

BODY=$(curl -s "$BASE_URL/health")
DB_STATUS=$(echo "$BODY" | python3 -c "import sys,json; print(json.load(sys.stdin)['db'])" 2>/dev/null || echo "error")
check "GET /health db=connected" "$DB_STATUS" "connected"

# ── contract upload ────────────────────────────────────────────────────────────
UPLOAD_RESPONSE=$(curl -s -w "\n%{http_code}" -X POST "$BASE_URL/api/contracts" \
  -F "file=@data/contracts/sample-nda.txt;type=text/plain")

UPLOAD_STATUS=$(echo "$UPLOAD_RESPONSE" | tail -1)
UPLOAD_BODY=$(echo "$UPLOAD_RESPONSE" | head -n -1)

check "POST /api/contracts returns 201" "$UPLOAD_STATUS" "201"

CONTRACT_ID=$(echo "$UPLOAD_BODY" | python3 -c "import sys,json; print(json.load(sys.stdin).get('contract_id',''))" 2>/dev/null || echo "")
if [[ -n "$CONTRACT_ID" ]]; then
  green "POST /api/contracts returns contract_id"
  PASS=$((PASS + 1))
else
  red "POST /api/contracts missing contract_id"
  FAIL=$((FAIL + 1))
fi

RISK=$(echo "$UPLOAD_BODY" | python3 -c "import sys,json; print(json.load(sys.stdin).get('overall_risk',''))" 2>/dev/null || echo "")
if [[ -n "$RISK" ]]; then
  green "POST /api/contracts returns overall_risk ($RISK)"
  PASS=$((PASS + 1))
else
  red "POST /api/contracts missing overall_risk"
  FAIL=$((FAIL + 1))
fi

# ── list contracts ─────────────────────────────────────────────────────────────
LIST_STATUS=$(curl -s -o /dev/null -w "%{http_code}" "$BASE_URL/api/contracts")
check "GET /api/contracts returns 200" "$LIST_STATUS" "200"

# ── get contract ───────────────────────────────────────────────────────────────
if [[ -n "$CONTRACT_ID" ]]; then
  GET_STATUS=$(curl -s -o /dev/null -w "%{http_code}" "$BASE_URL/api/contracts/$CONTRACT_ID")
  check "GET /api/contracts/:id returns 200" "$GET_STATUS" "200"

  GET_BODY=$(curl -s "$BASE_URL/api/contracts/$CONTRACT_ID")
  CONTRACT_STATUS=$(echo "$GET_BODY" | python3 -c "import sys,json; print(json.load(sys.stdin)['contract']['status'])" 2>/dev/null || echo "")
  check "GET /api/contracts/:id status=complete" "$CONTRACT_STATUS" "complete"
fi

# ── 404 for unknown contract ───────────────────────────────────────────────────
NOT_FOUND=$(curl -s -o /dev/null -w "%{http_code}" "$BASE_URL/api/contracts/00000000-0000-0000-0000-000000000000")
check "GET /api/contracts/:id returns 404 for unknown id" "$NOT_FOUND" "404"

# ── semantic search ────────────────────────────────────────────────────────────
SEARCH_STATUS=$(curl -s -o /dev/null -w "%{http_code}" -X POST "$BASE_URL/api/search" \
  -H "Content-Type: application/json" \
  -d '{"query":"confidentiality obligations","limit":5}')
check "POST /api/search returns 200" "$SEARCH_STATUS" "200"

# ── bad request: missing file ──────────────────────────────────────────────────
BAD_STATUS=$(curl -s -o /dev/null -w "%{http_code}" -X POST "$BASE_URL/api/contracts" \
  -F "not_a_file=hello")
check "POST /api/contracts without file returns 400" "$BAD_STATUS" "400"

# ── unsupported file type ──────────────────────────────────────────────────────
UNS_STATUS=$(curl -s -o /dev/null -w "%{http_code}" -X POST "$BASE_URL/api/contracts" \
  -F "file=@package.json;type=application/json")
check "POST /api/contracts with unsupported type returns 415" "$UNS_STATUS" "415"

# ── summary ────────────────────────────────────────────────────────────────────
echo ""
echo "─────────────────────────────"
echo "Results: $PASS passed, $FAIL failed"
if [[ $FAIL -gt 0 ]]; then
  exit 1
fi
