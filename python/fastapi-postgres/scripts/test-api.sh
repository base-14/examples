#!/bin/bash

# FastAPI + PostgreSQL API Testing Script

set -e

BASE_URL="${API_BASE_URL:-http://localhost:8000}"
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

echo -e "${YELLOW}=== FastAPI + PostgreSQL API Tests ===${NC}"
echo ""

# ------------------------------------------------------------------
# 1. Health check
# ------------------------------------------------------------------
echo "1. Health Check"
STATUS=$(curl -s -o /dev/null -w "%{http_code}" "$BASE_URL/")
check_status "GET / (health)" "200" "$STATUS"

# ------------------------------------------------------------------
# 2. Register users
# ------------------------------------------------------------------
echo ""
echo "2. User Registration"

RESPONSE=$(curl -s -w "\n%{http_code}" -X POST "$BASE_URL/users/" \
    -H "Content-Type: application/json" \
    -d "{\"email\":\"alice-${TIMESTAMP}@example.com\",\"password\":\"securepass1\"}")
STATUS=$(echo "$RESPONSE" | tail -1)
BODY=$(echo "$RESPONSE" | sed '$d')
check_status "POST /users/ (create user alice)" "201" "$STATUS"

USER1_ID=$(echo "$BODY" | grep -o '"id"[[:space:]]*:[[:space:]]*[0-9]*' | head -1 | sed 's/.*:[[:space:]]*//')

RESPONSE=$(curl -s -w "\n%{http_code}" -X POST "$BASE_URL/users/" \
    -H "Content-Type: application/json" \
    -d "{\"email\":\"bob-${TIMESTAMP}@example.com\",\"password\":\"securepass2\"}")
STATUS=$(echo "$RESPONSE" | tail -1)
BODY=$(echo "$RESPONSE" | sed '$d')
check_status "POST /users/ (create user bob)" "201" "$STATUS"

USER2_ID=$(echo "$BODY" | grep -o '"id"[[:space:]]*:[[:space:]]*[0-9]*' | head -1 | sed 's/.*:[[:space:]]*//')

STATUS=$(curl -s -o /dev/null -w "%{http_code}" -X POST "$BASE_URL/users/" \
    -H "Content-Type: application/json" \
    -d "{\"email\":\"alice-${TIMESTAMP}@example.com\",\"password\":\"securepass1\"}")
check_status "POST /users/ (duplicate email)" "500" "$STATUS"

STATUS=$(curl -s -o /dev/null -w "%{http_code}" -X POST "$BASE_URL/users/" \
    -H "Content-Type: application/json" \
    -d '{"email":"bad","password":"short"}')
check_status "POST /users/ (invalid data)" "422" "$STATUS"

# ------------------------------------------------------------------
# 3. Login
# ------------------------------------------------------------------
echo ""
echo "3. Authentication"

RESPONSE=$(curl -s -w "\n%{http_code}" -X POST "$BASE_URL/login" \
    -H "Content-Type: application/x-www-form-urlencoded" \
    -d "username=alice-${TIMESTAMP}@example.com&password=securepass1")
STATUS=$(echo "$RESPONSE" | tail -1)
BODY=$(echo "$RESPONSE" | sed '$d')
check_status "POST /login (valid credentials alice)" "200" "$STATUS"

TOKEN1=$(echo "$BODY" | grep -o '"access_token":"[^"]*"' | cut -d'"' -f4)

RESPONSE=$(curl -s -w "\n%{http_code}" -X POST "$BASE_URL/login" \
    -H "Content-Type: application/x-www-form-urlencoded" \
    -d "username=bob-${TIMESTAMP}@example.com&password=securepass2")
STATUS=$(echo "$RESPONSE" | tail -1)
BODY=$(echo "$RESPONSE" | sed '$d')
check_status "POST /login (valid credentials bob)" "200" "$STATUS"

TOKEN2=$(echo "$BODY" | grep -o '"access_token":"[^"]*"' | cut -d'"' -f4)

STATUS=$(curl -s -o /dev/null -w "%{http_code}" -X POST "$BASE_URL/login" \
    -H "Content-Type: application/x-www-form-urlencoded" \
    -d "username=wrong@example.com&password=wrongpass")
check_status "POST /login (invalid credentials)" "403" "$STATUS"

# ------------------------------------------------------------------
# 4. Get user by ID (requires auth)
# ------------------------------------------------------------------
echo ""
echo "4. Get User"

STATUS=$(curl -s -o /dev/null -w "%{http_code}" "$BASE_URL/users/$USER1_ID" \
    -H "Authorization: Bearer $TOKEN1")
check_status "GET /users/:id (authenticated)" "200" "$STATUS"

STATUS=$(curl -s -o /dev/null -w "%{http_code}" "$BASE_URL/users/$USER1_ID")
check_status "GET /users/:id (no auth)" "401" "$STATUS"

# ------------------------------------------------------------------
# 5. Create posts
# ------------------------------------------------------------------
echo ""
echo "5. Create Posts"

RESPONSE=$(curl -s -w "\n%{http_code}" -X POST "$BASE_URL/posts/" \
    -H "Content-Type: application/json" \
    -H "Authorization: Bearer $TOKEN1" \
    -d '{"title":"First Post","content":"Hello from the test script","published":true}')
STATUS=$(echo "$RESPONSE" | tail -1)
BODY=$(echo "$RESPONSE" | sed '$d')
check_status "POST /posts/ (create post 1)" "201" "$STATUS"

POST1_ID=$(echo "$BODY" | grep -o '"id"[[:space:]]*:[[:space:]]*[0-9]*' | head -1 | sed 's/.*:[[:space:]]*//')

RESPONSE=$(curl -s -w "\n%{http_code}" -X POST "$BASE_URL/posts/" \
    -H "Content-Type: application/json" \
    -H "Authorization: Bearer $TOKEN1" \
    -d '{"title":"Second Post","content":"Another post for testing","published":true}')
STATUS=$(echo "$RESPONSE" | tail -1)
BODY=$(echo "$RESPONSE" | sed '$d')
check_status "POST /posts/ (create post 2)" "201" "$STATUS"

POST2_ID=$(echo "$BODY" | grep -o '"id"[[:space:]]*:[[:space:]]*[0-9]*' | head -1 | sed 's/.*:[[:space:]]*//')

STATUS=$(curl -s -o /dev/null -w "%{http_code}" -X POST "$BASE_URL/posts/" \
    -H "Content-Type: application/json" \
    -d '{"title":"No Auth Post","content":"Should fail","published":true}')
check_status "POST /posts/ (no auth)" "401" "$STATUS"

# ------------------------------------------------------------------
# 6. List posts
# ------------------------------------------------------------------
echo ""
echo "6. List Posts"

STATUS=$(curl -s -o /dev/null -w "%{http_code}" "$BASE_URL/posts/?limit=10" \
    -H "Authorization: Bearer $TOKEN1")
check_status "GET /posts/ (list posts)" "200" "$STATUS"

# ------------------------------------------------------------------
# 7. Get single post
# ------------------------------------------------------------------
echo ""
echo "7. Get Single Post"

STATUS=$(curl -s -o /dev/null -w "%{http_code}" "$BASE_URL/posts/$POST1_ID" \
    -H "Authorization: Bearer $TOKEN1")
check_status "GET /posts/:id" "200" "$STATUS"

STATUS=$(curl -s -o /dev/null -w "%{http_code}" "$BASE_URL/posts/999999" \
    -H "Authorization: Bearer $TOKEN1")
check_status "GET /posts/:id (not found)" "404" "$STATUS"

# ------------------------------------------------------------------
# 8. Update post
# ------------------------------------------------------------------
echo ""
echo "8. Update Post"

STATUS=$(curl -s -o /dev/null -w "%{http_code}" -X PUT "$BASE_URL/posts/$POST1_ID" \
    -H "Content-Type: application/json" \
    -H "Authorization: Bearer $TOKEN1" \
    -d '{"title":"Updated First Post","content":"Updated content","published":true}')
check_status "PUT /posts/:id (owner)" "200" "$STATUS"

STATUS=$(curl -s -o /dev/null -w "%{http_code}" -X PUT "$BASE_URL/posts/$POST1_ID" \
    -H "Content-Type: application/json" \
    -H "Authorization: Bearer $TOKEN2" \
    -d '{"title":"Hijack","content":"Should fail","published":true}')
check_status "PUT /posts/:id (not owner)" "403" "$STATUS"

# ------------------------------------------------------------------
# 9. Vote
# ------------------------------------------------------------------
echo ""
echo "9. Votes"

STATUS=$(curl -s -o /dev/null -w "%{http_code}" -X POST "$BASE_URL/vote/" \
    -H "Content-Type: application/json" \
    -H "Authorization: Bearer $TOKEN2" \
    -d "{\"post_id\":$POST1_ID,\"voted\":true}")
check_status "POST /vote/ (add vote)" "201" "$STATUS"

STATUS=$(curl -s -o /dev/null -w "%{http_code}" -X POST "$BASE_URL/vote/" \
    -H "Content-Type: application/json" \
    -H "Authorization: Bearer $TOKEN2" \
    -d "{\"post_id\":$POST1_ID,\"voted\":true}")
check_status "POST /vote/ (duplicate vote)" "409" "$STATUS"

STATUS=$(curl -s -o /dev/null -w "%{http_code}" -X POST "$BASE_URL/vote/" \
    -H "Content-Type: application/json" \
    -H "Authorization: Bearer $TOKEN2" \
    -d "{\"post_id\":$POST1_ID,\"voted\":false}")
check_status "POST /vote/ (remove vote)" "201" "$STATUS"

STATUS=$(curl -s -o /dev/null -w "%{http_code}" -X POST "$BASE_URL/vote/" \
    -H "Content-Type: application/json" \
    -H "Authorization: Bearer $TOKEN2" \
    -d '{"post_id":999999,"voted":true}')
check_status "POST /vote/ (non-existent post)" "404" "$STATUS"

# ------------------------------------------------------------------
# 10. Delete post
# ------------------------------------------------------------------
echo ""
echo "10. Delete Post"

STATUS=$(curl -s -o /dev/null -w "%{http_code}" -X DELETE "$BASE_URL/posts/$POST1_ID" \
    -H "Authorization: Bearer $TOKEN2")
check_status "DELETE /posts/:id (not owner)" "403" "$STATUS"

STATUS=$(curl -s -o /dev/null -w "%{http_code}" -X DELETE "$BASE_URL/posts/$POST1_ID" \
    -H "Authorization: Bearer $TOKEN1")
check_status "DELETE /posts/:id (owner)" "204" "$STATUS"

STATUS=$(curl -s -o /dev/null -w "%{http_code}" -X DELETE "$BASE_URL/posts/$POST2_ID" \
    -H "Authorization: Bearer $TOKEN1")
check_status "DELETE /posts/:id (cleanup post 2)" "204" "$STATUS"

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
