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

echo "=== AI Report Generator — API Smoke Tests ==="
echo "Target: $BASE_URL"
echo ""

# 1. Health check
STATUS=$(curl -s -o /dev/null -w "%{http_code}" "$BASE_URL/api/health")
check "GET /api/health returns 200" "$STATUS" "200"

BODY=$(curl -s "$BASE_URL/api/health")
SVC=$(echo "$BODY" | python3 -c "import sys,json; print(json.load(sys.stdin)['status'])" 2>/dev/null || echo "error")
check "GET /api/health status=ok" "$SVC" "ok"

# 2. List indicators
IND_STATUS=$(curl -s -o /dev/null -w "%{http_code}" "$BASE_URL/api/indicators")
check "GET /api/indicators returns 200" "$IND_STATUS" "200"

IND_BODY=$(curl -s "$BASE_URL/api/indicators")
IND_COUNT=$(echo "$IND_BODY" | python3 -c "import sys,json; print(len(json.load(sys.stdin)))" 2>/dev/null || echo "0")
if [[ "$IND_COUNT" -gt 0 ]]; then
  green "GET /api/indicators has $IND_COUNT items"
  PASS=$((PASS + 1))
else
  red "GET /api/indicators returned empty list"
  FAIL=$((FAIL + 1))
fi

# 3. Generate report
REPORT_RESPONSE=$(curl -s -w "\n%{http_code}" -X POST "$BASE_URL/api/reports" \
  -H "Content-Type: application/json" \
  -d '{"indicators":["UNRATE","CPIAUCSL"],"start_date":"2020-01-01","end_date":"2023-12-31"}')
REPORT_STATUS=$(echo "$REPORT_RESPONSE" | tail -1)
REPORT_BODY=$(echo "$REPORT_RESPONSE" | sed '$d')

check "POST /api/reports returns 200" "$REPORT_STATUS" "200"

REPORT_TITLE=$(echo "$REPORT_BODY" | python3 -c "import sys,json; print(json.load(sys.stdin).get('title',''))" 2>/dev/null || echo "")
if [[ -n "$REPORT_TITLE" ]]; then
  green "POST /api/reports returns title: $REPORT_TITLE"
  PASS=$((PASS + 1))
else
  red "POST /api/reports missing title"
  FAIL=$((FAIL + 1))
fi

REPORT_ID=$(echo "$REPORT_BODY" | python3 -c "import sys,json; print(json.load(sys.stdin).get('id',''))" 2>/dev/null || echo "")
if [[ -n "$REPORT_ID" ]]; then
  green "POST /api/reports returns id: $REPORT_ID"
  PASS=$((PASS + 1))
else
  red "POST /api/reports missing id"
  FAIL=$((FAIL + 1))
fi

# 4. List reports
LIST_STATUS=$(curl -s -o /dev/null -w "%{http_code}" "$BASE_URL/api/reports")
check "GET /api/reports returns 200" "$LIST_STATUS" "200"

LIST_BODY=$(curl -s "$BASE_URL/api/reports")
LIST_COUNT=$(echo "$LIST_BODY" | python3 -c "import sys,json; print(len(json.load(sys.stdin)))" 2>/dev/null || echo "0")
if [[ "$LIST_COUNT" -gt 0 ]]; then
  green "GET /api/reports has $LIST_COUNT reports"
  PASS=$((PASS + 1))
else
  red "GET /api/reports returned empty list"
  FAIL=$((FAIL + 1))
fi

# 5. Get report by ID
if [[ -n "$REPORT_ID" ]]; then
  GET_STATUS=$(curl -s -o /dev/null -w "%{http_code}" "$BASE_URL/api/reports/$REPORT_ID")
  check "GET /api/reports/$REPORT_ID returns 200" "$GET_STATUS" "200"

  GET_BODY=$(curl -s "$BASE_URL/api/reports/$REPORT_ID")
  GET_TITLE=$(echo "$GET_BODY" | python3 -c "import sys,json; print(json.load(sys.stdin).get('title',''))" 2>/dev/null || echo "")
  if [[ -n "$GET_TITLE" ]]; then
    green "GET /api/reports/{id} returns title"
    PASS=$((PASS + 1))
  else
    red "GET /api/reports/{id} missing title"
    FAIL=$((FAIL + 1))
  fi
else
  red "Skipping GET /api/reports/{id} — no report ID from step 3"
  FAIL=$((FAIL + 2))
fi

# 6. Invalid request — empty indicators
BAD_IND_STATUS=$(curl -s -o /dev/null -w "%{http_code}" -X POST "$BASE_URL/api/reports" \
  -H "Content-Type: application/json" \
  -d '{"indicators":[],"start_date":"2020-01-01","end_date":"2023-12-31"}')
check "POST /api/reports empty indicators returns 400" "$BAD_IND_STATUS" "400"

# 7. Invalid request — bad date format
BAD_DATE_STATUS=$(curl -s -o /dev/null -w "%{http_code}" -X POST "$BASE_URL/api/reports" \
  -H "Content-Type: application/json" \
  -d '{"indicators":["UNRATE"],"start_date":"bad","end_date":"2023-12-31"}')
check "POST /api/reports bad date returns 400" "$BAD_DATE_STATUS" "400"

# 8. Report not found
NOT_FOUND_STATUS=$(curl -s -o /dev/null -w "%{http_code}" "$BASE_URL/api/reports/00000000-0000-0000-0000-000000000000")
check "GET /api/reports/{nonexistent} returns 404" "$NOT_FOUND_STATUS" "404"

# Summary
echo ""
echo "─────────────────────────────"
echo "Results: $PASS passed, $FAIL failed"
if [[ $FAIL -gt 0 ]]; then
  exit 1
fi
