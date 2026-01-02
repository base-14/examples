#!/bin/bash

set -e

BASE_URL="${BASE_URL:-http://localhost:8080}"
PASSED=0
FAILED=0
TOKEN=""

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

print_result() {
    local name=$1
    local expected=$2
    local actual=$3

    if [ "$expected" = "$actual" ]; then
        echo -e "${GREEN}✓${NC} $name (HTTP $actual)"
        PASSED=$((PASSED + 1))
    else
        echo -e "${RED}✗${NC} $name (expected $expected, got $actual)"
        FAILED=$((FAILED + 1))
    fi
}

echo -e "${YELLOW}=== Quarkus + PostgreSQL + OpenTelemetry API Tests ===${NC}"
echo ""

echo "1. Health Check"
STATUS=$(curl -s -o /dev/null -w "%{http_code}" "$BASE_URL/api/health")
print_result "GET /api/health" "200" "$STATUS"

echo ""
echo "2. User Registration"

TIMESTAMP=$(date +%s)
USER_EMAIL="testuser${TIMESTAMP}@example.com"

RESPONSE=$(curl -s -w "\n%{http_code}" -X POST "$BASE_URL/api/register" \
    -H "Content-Type: application/json" \
    -d "{\"email\":\"$USER_EMAIL\",\"password\":\"password123\",\"name\":\"Test User\"}")
STATUS=$(echo "$RESPONSE" | tail -1)
BODY=$(echo "$RESPONSE" | sed '$d')
print_result "POST /api/register (new user)" "201" "$STATUS"

TOKEN=$(echo "$BODY" | grep -o '"token":"[^"]*"' | cut -d'"' -f4)

RESPONSE=$(curl -s -w "\n%{http_code}" -X POST "$BASE_URL/api/register" \
    -H "Content-Type: application/json" \
    -d "{\"email\":\"$USER_EMAIL\",\"password\":\"password123\",\"name\":\"Test User\"}")
STATUS=$(echo "$RESPONSE" | tail -1)
print_result "POST /api/register (duplicate email)" "409" "$STATUS"

STATUS=$(curl -s -o /dev/null -w "%{http_code}" -X POST "$BASE_URL/api/register" \
    -H "Content-Type: application/json" \
    -d '{"email":"","password":"","name":""}')
print_result "POST /api/register (invalid data)" "400" "$STATUS"

echo ""
echo "3. User Login"

RESPONSE=$(curl -s -w "\n%{http_code}" -X POST "$BASE_URL/api/login" \
    -H "Content-Type: application/json" \
    -d "{\"email\":\"$USER_EMAIL\",\"password\":\"password123\"}")
STATUS=$(echo "$RESPONSE" | tail -1)
BODY=$(echo "$RESPONSE" | sed '$d')
print_result "POST /api/login (valid credentials)" "200" "$STATUS"

TOKEN=$(echo "$BODY" | grep -o '"token":"[^"]*"' | cut -d'"' -f4)

STATUS=$(curl -s -o /dev/null -w "%{http_code}" -X POST "$BASE_URL/api/login" \
    -H "Content-Type: application/json" \
    -d '{"email":"wrong@example.com","password":"wrongpass"}')
print_result "POST /api/login (invalid credentials)" "401" "$STATUS"

echo ""
echo "4. Get Current User"

STATUS=$(curl -s -o /dev/null -w "%{http_code}" "$BASE_URL/api/user" \
    -H "Authorization: Bearer $TOKEN")
print_result "GET /api/user (authenticated)" "200" "$STATUS"

STATUS=$(curl -s -o /dev/null -w "%{http_code}" "$BASE_URL/api/user")
print_result "GET /api/user (no token)" "401" "$STATUS"

STATUS=$(curl -s -o /dev/null -w "%{http_code}" "$BASE_URL/api/user" \
    -H "Authorization: Bearer invalidtoken")
print_result "GET /api/user (invalid token)" "401" "$STATUS"

echo ""
echo "5. Create Article"

RESPONSE=$(curl -s -w "\n%{http_code}" -X POST "$BASE_URL/api/articles" \
    -H "Content-Type: application/json" \
    -H "Authorization: Bearer $TOKEN" \
    -d '{"title":"Test Article","description":"A test article","body":"This is the body of the test article."}')
STATUS=$(echo "$RESPONSE" | tail -1)
BODY=$(echo "$RESPONSE" | sed '$d')
print_result "POST /api/articles (authenticated)" "201" "$STATUS"

SLUG=$(echo "$BODY" | grep -o '"slug":"[^"]*"' | cut -d'"' -f4)

STATUS=$(curl -s -o /dev/null -w "%{http_code}" -X POST "$BASE_URL/api/articles" \
    -H "Content-Type: application/json" \
    -d '{"title":"Unauthorized Article","body":"Should fail"}')
print_result "POST /api/articles (no auth)" "401" "$STATUS"

STATUS=$(curl -s -o /dev/null -w "%{http_code}" -X POST "$BASE_URL/api/articles" \
    -H "Content-Type: application/json" \
    -H "Authorization: Bearer $TOKEN" \
    -d '{"title":"","body":""}')
print_result "POST /api/articles (invalid data)" "400" "$STATUS"

echo ""
echo "6. List Articles"

STATUS=$(curl -s -o /dev/null -w "%{http_code}" "$BASE_URL/api/articles")
print_result "GET /api/articles" "200" "$STATUS"

STATUS=$(curl -s -o /dev/null -w "%{http_code}" "$BASE_URL/api/articles?limit=5&offset=0")
print_result "GET /api/articles (with pagination)" "200" "$STATUS"

echo ""
echo "7. Get Single Article"

STATUS=$(curl -s -o /dev/null -w "%{http_code}" "$BASE_URL/api/articles/$SLUG")
print_result "GET /api/articles/:slug" "200" "$STATUS"

STATUS=$(curl -s -o /dev/null -w "%{http_code}" "$BASE_URL/api/articles/nonexistent-slug")
print_result "GET /api/articles/:slug (not found)" "404" "$STATUS"

echo ""
echo "8. Update Article"

RESPONSE=$(curl -s -w "\n%{http_code}" -X PUT "$BASE_URL/api/articles/$SLUG" \
    -H "Content-Type: application/json" \
    -H "Authorization: Bearer $TOKEN" \
    -d '{"title":"Updated Article Title","description":"Updated description"}')
STATUS=$(echo "$RESPONSE" | tail -1)
BODY=$(echo "$RESPONSE" | sed '$d')
print_result "PUT /api/articles/:slug (owner)" "200" "$STATUS"

SLUG=$(echo "$BODY" | grep -o '"slug":"[^"]*"' | cut -d'"' -f4)

STATUS=$(curl -s -o /dev/null -w "%{http_code}" -X PUT "$BASE_URL/api/articles/$SLUG" \
    -H "Content-Type: application/json" \
    -d '{"title":"Should Fail"}')
print_result "PUT /api/articles/:slug (no auth)" "401" "$STATUS"

echo ""
echo "9. Favorite Article"

STATUS=$(curl -s -o /dev/null -w "%{http_code}" -X POST "$BASE_URL/api/articles/$SLUG/favorite" \
    -H "Authorization: Bearer $TOKEN")
print_result "POST /api/articles/:slug/favorite" "200" "$STATUS"

STATUS=$(curl -s -o /dev/null -w "%{http_code}" -X POST "$BASE_URL/api/articles/$SLUG/favorite" \
    -H "Authorization: Bearer $TOKEN")
print_result "POST /api/articles/:slug/favorite (already favorited)" "409" "$STATUS"

echo ""
echo "10. Unfavorite Article"

STATUS=$(curl -s -o /dev/null -w "%{http_code}" -X DELETE "$BASE_URL/api/articles/$SLUG/favorite" \
    -H "Authorization: Bearer $TOKEN")
print_result "DELETE /api/articles/:slug/favorite" "200" "$STATUS"

STATUS=$(curl -s -o /dev/null -w "%{http_code}" -X DELETE "$BASE_URL/api/articles/$SLUG/favorite" \
    -H "Authorization: Bearer $TOKEN")
print_result "DELETE /api/articles/:slug/favorite (not favorited)" "409" "$STATUS"

echo ""
echo "11. Delete Article"

STATUS=$(curl -s -o /dev/null -w "%{http_code}" -X DELETE "$BASE_URL/api/articles/$SLUG" \
    -H "Authorization: Bearer $TOKEN")
print_result "DELETE /api/articles/:slug (owner)" "204" "$STATUS"

STATUS=$(curl -s -o /dev/null -w "%{http_code}" "$BASE_URL/api/articles/$SLUG")
print_result "GET /api/articles/:slug (after delete)" "404" "$STATUS"

echo ""
echo "12. Logout"

STATUS=$(curl -s -o /dev/null -w "%{http_code}" -X POST "$BASE_URL/api/logout" \
    -H "Authorization: Bearer $TOKEN")
print_result "POST /api/logout" "200" "$STATUS"

echo ""
echo -e "${YELLOW}=== Test Summary ===${NC}"
echo -e "Passed: ${GREEN}$PASSED${NC}"
echo -e "Failed: ${RED}$FAILED${NC}"
TOTAL=$((PASSED + FAILED))
echo "Total: $TOTAL"

if [ $FAILED -eq 0 ]; then
    echo -e "${GREEN}All tests passed!${NC}"
    exit 0
else
    echo -e "${RED}Some tests failed!${NC}"
    exit 1
fi
