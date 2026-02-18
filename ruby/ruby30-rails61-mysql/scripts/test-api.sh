#!/bin/bash

# Ruby 3.0 + Rails 6.1 + MySQL JSON API Testing Script

BASE_URL="${API_BASE_URL:-http://localhost:3000}"
PASS_COUNT=0
FAIL_COUNT=0

GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m'

pass() { echo -e "${GREEN}PASS${NC}: $1"; PASS_COUNT=$((PASS_COUNT + 1)); }
fail() { echo -e "${RED}FAIL${NC}: $1 (expected $2, got $3)"; FAIL_COUNT=$((FAIL_COUNT + 1)); }

check_status() {
    local description=$1
    local expected=$2
    local actual=$3
    if [ "$expected" = "$actual" ]; then
        pass "$description"
    else
        fail "$description" "$expected" "$actual"
    fi
}

TIMESTAMP=$(date +%s)

echo -e "${YELLOW}=== Ruby 3.0 + Rails 6.1 + MySQL + OpenTelemetry Tests ===${NC}"
echo ""

echo "Waiting for API to be ready..."
for i in $(seq 1 30); do
    STATUS=$(curl -s -o /dev/null -w "%{http_code}" "$BASE_URL/api/health" 2>/dev/null || echo "000")
    if [ "$STATUS" = "200" ]; then
        break
    fi
    sleep 1
done
echo ""

# ------------------------------------------------------------------
# 1. Health check
# ------------------------------------------------------------------
echo "1. Health Check"
STATUS=$(curl -s -o /dev/null -w "%{http_code}" "$BASE_URL/api/health" 2>/dev/null || echo "000")
check_status "GET /api/health" "200" "$STATUS"

BODY=$(curl -s "$BASE_URL/api/health")
if echo "$BODY" | grep -q '"status":"healthy"'; then
    pass "Health response contains status=healthy"
else
    fail "Health response body" "contains status=healthy" "$BODY"
fi

# ------------------------------------------------------------------
# 2. Create item
# ------------------------------------------------------------------
echo ""
echo "2. Create Item"
RESPONSE=$(curl -s -w "\n%{http_code}" -X POST "$BASE_URL/api/items" \
    -H "Content-Type: application/json" \
    -d "{\"item\":{\"title\":\"Test Item ${TIMESTAMP}\",\"description\":\"A test item\"}}")
STATUS=$(echo "$RESPONSE" | tail -1)
BODY=$(echo "$RESPONSE" | sed '$d')
check_status "POST /api/items (create)" "201" "$STATUS"

ITEM_ID=$(echo "$BODY" | grep -o '"id" *: *[0-9]*' | head -1 | grep -o '[0-9]*$')
if [ -n "$ITEM_ID" ]; then
    pass "Response contains item id=$ITEM_ID"
else
    fail "Response contains item id" "id present" "id missing"
fi

# ------------------------------------------------------------------
# 3. Get item
# ------------------------------------------------------------------
echo ""
echo "3. Get Item"
if [ -n "$ITEM_ID" ]; then
    STATUS=$(curl -s -o /dev/null -w "%{http_code}" "$BASE_URL/api/items/$ITEM_ID")
    check_status "GET /api/items/$ITEM_ID" "200" "$STATUS"
else
    fail "GET /api/items/:id (skipped, no item id)" "200" "N/A"
fi

# ------------------------------------------------------------------
# 4. Get missing item (404 with trace_id)
# ------------------------------------------------------------------
echo ""
echo "4. Get Missing Item (404)"
RESPONSE=$(curl -s -w "\n%{http_code}" "$BASE_URL/api/items/99999")
STATUS=$(echo "$RESPONSE" | tail -1)
BODY=$(echo "$RESPONSE" | sed '$d')
check_status "GET /api/items/99999 (not found)" "404" "$STATUS"

if echo "$BODY" | grep -q '"trace_id"'; then
    pass "404 response contains trace_id"
else
    fail "404 response contains trace_id" "trace_id present" "$BODY"
fi

# ------------------------------------------------------------------
# 5. Create duplicate title (triggers WARN log)
# ------------------------------------------------------------------
echo ""
echo "5. Duplicate Title (WARN log)"
STATUS=$(curl -s -o /dev/null -w "%{http_code}" -X POST "$BASE_URL/api/items" \
    -H "Content-Type: application/json" \
    -d "{\"item\":{\"title\":\"Test Item ${TIMESTAMP}\",\"description\":\"Duplicate title\"}}")
check_status "POST /api/items (duplicate title, still 201)" "201" "$STATUS"
echo "  (Check docker logs for WARN about duplicate title)"

# ------------------------------------------------------------------
# Summary
# ------------------------------------------------------------------
echo ""
echo -e "${YELLOW}=== Test Summary ===${NC}"
echo -e "Passed: ${GREEN}$PASS_COUNT${NC}"
echo -e "Failed: ${RED}$FAIL_COUNT${NC}"
TOTAL=$((PASS_COUNT + FAIL_COUNT))
echo "Total:  $TOTAL"

if [ "$FAIL_COUNT" -eq 0 ]; then
    echo -e "${GREEN}All tests passed!${NC}"
    exit 0
else
    echo -e "${RED}Some tests failed!${NC}"
    exit 1
fi
