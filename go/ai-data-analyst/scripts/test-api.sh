#!/usr/bin/env bash
set -euo pipefail

BASE_URL="${API_URL:-http://localhost:8080}"
PASS=0
FAIL=0

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

echo "=== AI Data Analyst — API Smoke Tests ==="
echo "Target: $BASE_URL"
echo ""

# Health
STATUS=$(curl -s -o /dev/null -w "%{http_code}" "$BASE_URL/api/health")
check "GET /api/health returns 200" "$STATUS" "200"

BODY=$(curl -s "$BASE_URL/api/health")
SVC=$(echo "$BODY" | python3 -c "import sys,json; print(json.load(sys.stdin)['status'])" 2>/dev/null || echo "error")
check "GET /api/health status=ok" "$SVC" "ok"

# Schema
SCHEMA_STATUS=$(curl -s -o /dev/null -w "%{http_code}" "$BASE_URL/api/schema")
check "GET /api/schema returns 200" "$SCHEMA_STATUS" "200"

SCHEMA_BODY=$(curl -s "$BASE_URL/api/schema")
if echo "$SCHEMA_BODY" | grep -q "countries"; then
  green "GET /api/schema contains schema info"
  PASS=$((PASS + 1))
else
  red "GET /api/schema missing schema info"
  FAIL=$((FAIL + 1))
fi

# Indicators
IND_STATUS=$(curl -s -o /dev/null -w "%{http_code}" "$BASE_URL/api/indicators")
check "GET /api/indicators returns 200" "$IND_STATUS" "200"

# History
HIST_STATUS=$(curl -s -o /dev/null -w "%{http_code}" "$BASE_URL/api/history")
check "GET /api/history returns 200" "$HIST_STATUS" "200"

# Ask — valid question
ASK_RESPONSE=$(curl -s -w "\n%{http_code}" -X POST "$BASE_URL/api/ask" \
  -H "Content-Type: application/json" \
  -d '{"question":"Top 5 countries by GDP growth in 2023"}')
ASK_STATUS=$(echo "$ASK_RESPONSE" | tail -1)
ASK_BODY=$(echo "$ASK_RESPONSE" | sed '$d')

check "POST /api/ask returns 200" "$ASK_STATUS" "200"

SQL=$(echo "$ASK_BODY" | python3 -c "import sys,json; print(json.load(sys.stdin).get('sql',''))" 2>/dev/null || echo "")
if [[ -n "$SQL" ]]; then
  green "POST /api/ask returns SQL"
  PASS=$((PASS + 1))
else
  red "POST /api/ask missing SQL"
  FAIL=$((FAIL + 1))
fi

TRACE_ID=$(echo "$ASK_BODY" | python3 -c "import sys,json; print(json.load(sys.stdin).get('trace_id',''))" 2>/dev/null || echo "")
if [[ -n "$TRACE_ID" ]]; then
  green "POST /api/ask returns trace_id"
  PASS=$((PASS + 1))
else
  red "POST /api/ask missing trace_id"
  FAIL=$((FAIL + 1))
fi

# Ask — empty question
BAD_STATUS=$(curl -s -o /dev/null -w "%{http_code}" -X POST "$BASE_URL/api/ask" \
  -H "Content-Type: application/json" \
  -d '{"question":""}')
check "POST /api/ask empty question returns 400" "$BAD_STATUS" "400"

# Ask — invalid JSON
INVALID_STATUS=$(curl -s -o /dev/null -w "%{http_code}" -X POST "$BASE_URL/api/ask" \
  -H "Content-Type: application/json" \
  -d 'not json')
check "POST /api/ask invalid JSON returns 400" "$INVALID_STATUS" "400"

# Summary
echo ""
echo "─────────────────────────────"
echo "Results: $PASS passed, $FAIL failed"
if [[ $FAIL -gt 0 ]]; then
  exit 1
fi
