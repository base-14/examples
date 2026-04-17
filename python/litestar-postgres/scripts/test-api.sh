#!/usr/bin/env bash
# End-to-end CRUD smoke. Assumes `make docker-up` is already running.
# Exits non-zero on the first failure so it slots into CI cleanly.

set -euo pipefail

BASE_URL="${API_BASE_URL:-http://localhost:8080}"
NOTIFY_URL="${NOTIFY_BASE_URL:-http://localhost:8081}"

GREEN='\033[0;32m'; RED='\033[0;31m'; YELLOW='\033[1;33m'; NC='\033[0m'
PASS=0; FAIL=0

pass() { echo -e "${GREEN}PASS${NC} $1"; PASS=$((PASS+1)); }
fail() { echo -e "${RED}FAIL${NC} $1 — expected $2, got $3"; FAIL=$((FAIL+1)); }

check() {
    local desc=$1 expected=$2 actual=$3
    [ "$expected" = "$actual" ] && pass "$desc" || fail "$desc" "$expected" "$actual"
}

status_of() {
    curl -s -o /dev/null -w "%{http_code}" "$@"
}

echo -e "${YELLOW}=== Litestar + PostgreSQL API tests ===${NC}"

# 1. health checks
check "GET /api/health (articles)" 200 "$(status_of "$BASE_URL/api/health")"
check "GET /health (notify)"        200 "$(status_of "$NOTIFY_URL/health")"

# 2. create
RESP=$(curl -s -w "\n%{http_code}" -X POST "$BASE_URL/api/articles" \
    -H 'Content-Type: application/json' \
    -d '{"title":"smoke","body":"created by test-api.sh"}')
CREATE_STATUS=$(echo "$RESP" | tail -1)
CREATE_BODY=$(echo "$RESP" | sed '$d')
check "POST /api/articles" 201 "$CREATE_STATUS"
ARTICLE_ID=$(echo "$CREATE_BODY" | python3 -c "import sys,json;print(json.load(sys.stdin)['id'])")
echo "    created article id=$ARTICLE_ID"

# 3. get one
check "GET /api/articles/{id}" 200 "$(status_of "$BASE_URL/api/articles/$ARTICLE_ID")"

# 4. list with pagination
LIST_BODY=$(curl -s "$BASE_URL/api/articles?limit=10&offset=0")
TOTAL=$(echo "$LIST_BODY" | python3 -c "import sys,json;print(json.load(sys.stdin)['total'])")
[ "$TOTAL" -ge 1 ] && pass "GET /api/articles returned total>=1 (got $TOTAL)" \
    || fail "GET /api/articles total" ">=1" "$TOTAL"

# 5. update
check "PUT /api/articles/{id}" 200 "$(status_of -X PUT "$BASE_URL/api/articles/$ARTICLE_ID" \
    -H 'Content-Type: application/json' \
    -d '{"title":"smoke-updated","body":"after PUT"}')"

# 6. delete
check "DELETE /api/articles/{id}" 204 "$(status_of -X DELETE "$BASE_URL/api/articles/$ARTICLE_ID")"

# 7. 404 paths
check "GET missing article  → 404"    404 "$(status_of "$BASE_URL/api/articles/$ARTICLE_ID")"
check "PUT missing article  → 404"    404 "$(status_of -X PUT "$BASE_URL/api/articles/9999999" \
    -H 'Content-Type: application/json' -d '{"title":"x","body":"y"}')"
check "DELETE missing article → 404"  404 "$(status_of -X DELETE "$BASE_URL/api/articles/9999999")"

echo
echo -e "${YELLOW}=== Summary: $PASS passed, $FAIL failed ===${NC}"
[ "$FAIL" -eq 0 ]
