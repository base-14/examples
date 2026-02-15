#!/bin/bash

# Spring Boot Java 25 + MongoDB (Java Agent) API Testing Script

set -e

BASE_URL="${API_BASE_URL:-http://localhost:8080}"
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

echo -e "${YELLOW}=== Spring Boot Java 25 + MongoDB (Java Agent) API Tests ===${NC}"
echo ""

# ------------------------------------------------------------------
# 1. Health check (Spring Boot Actuator)
# ------------------------------------------------------------------
echo "1. Health Check"
STATUS=$(curl -s -o /dev/null -w "%{http_code}" "$BASE_URL/actuator/health")
check_status "GET /actuator/health" "200" "$STATUS"

# ------------------------------------------------------------------
# 2. Test message endpoint
# ------------------------------------------------------------------
echo ""
echo "2. Test Message"
STATUS=$(curl -s -o /dev/null -w "%{http_code}" "$BASE_URL/users/testMessage")
check_status "GET /users/testMessage" "200" "$STATUS"

# ------------------------------------------------------------------
# 3. Create users
# ------------------------------------------------------------------
echo ""
echo "3. Create Users"

TIMESTAMP=$(date +%s)

RESPONSE=$(curl -s -w "\n%{http_code}" -X POST "$BASE_URL/users/saveUser" \
    -H "Content-Type: application/json" \
    -d "{\"name\":\"Alice ${TIMESTAMP}\",\"address\":\"123 Main St\"}")
STATUS=$(echo "$RESPONSE" | tail -1)
BODY=$(echo "$RESPONSE" | sed '$d')
check_status "POST /users/saveUser (create user 1)" "200" "$STATUS"

# MongoDB uses string IDs
USER1_ID=$(echo "$BODY" | grep -o '"id":"[^"]*"' | head -1 | cut -d'"' -f4)

RESPONSE=$(curl -s -w "\n%{http_code}" -X POST "$BASE_URL/users/saveUser" \
    -H "Content-Type: application/json" \
    -d "{\"name\":\"Bob ${TIMESTAMP}\",\"address\":\"456 Oak Ave\"}")
STATUS=$(echo "$RESPONSE" | tail -1)
BODY=$(echo "$RESPONSE" | sed '$d')
check_status "POST /users/saveUser (create user 2)" "200" "$STATUS"

USER2_ID=$(echo "$BODY" | grep -o '"id":"[^"]*"' | head -1 | cut -d'"' -f4)

echo "  Created users with IDs: $USER1_ID, $USER2_ID"

# ------------------------------------------------------------------
# 4. List all users
# ------------------------------------------------------------------
echo ""
echo "4. List Users"

STATUS=$(curl -s -o /dev/null -w "%{http_code}" "$BASE_URL/users/")
check_status "GET /users/ (list all)" "200" "$STATUS"

# ------------------------------------------------------------------
# 5. Update user
# ------------------------------------------------------------------
echo ""
echo "5. Update User"

STATUS=$(curl -s -o /dev/null -w "%{http_code}" -X PUT "$BASE_URL/users/$USER1_ID" \
    -H "Content-Type: application/json" \
    -d "{\"id\":\"$USER1_ID\",\"name\":\"Alice Updated ${TIMESTAMP}\",\"address\":\"789 Pine Rd\"}")
check_status "PUT /users/:id (update user)" "200" "$STATUS"

STATUS=$(curl -s -o /dev/null -w "%{http_code}" -X PUT "$BASE_URL/users/000000000000000000000000" \
    -H "Content-Type: application/json" \
    -d '{"id":"000000000000000000000000","name":"Ghost","address":"Nowhere"}')
check_status "PUT /users/:id (not found)" "404" "$STATUS"

# ------------------------------------------------------------------
# 6. Delete user
# ------------------------------------------------------------------
echo ""
echo "6. Delete User"

STATUS=$(curl -s -o /dev/null -w "%{http_code}" -X DELETE "$BASE_URL/users/$USER2_ID")
check_status "DELETE /users/:id (delete user)" "200" "$STATUS"

STATUS=$(curl -s -o /dev/null -w "%{http_code}" -X DELETE "$BASE_URL/users/000000000000000000000000")
check_status "DELETE /users/:id (not found)" "404" "$STATUS"

# ------------------------------------------------------------------
# 7. Verify deletion
# ------------------------------------------------------------------
echo ""
echo "7. Verify State"

RESPONSE=$(curl -s "$BASE_URL/users/")
HAS_USER1=$(echo "$RESPONSE" | grep -c "Alice Updated" || true)
if [ "$HAS_USER1" -gt 0 ]; then
    pass "Updated user 1 still present in list"
else
    fail "Updated user 1 should still be in list" "present" "missing"
fi

# Cleanup
echo ""
echo "Cleanup: Deleting remaining test user..."
curl -s -o /dev/null -X DELETE "$BASE_URL/users/$USER1_ID"

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
