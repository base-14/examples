#!/bin/bash

set -e

BASE_URL="${BASE_URL:-http://localhost:8000}"
TIMESTAMP=$(date +%s)
RED='\033[0;31m'
GREEN='\033[0;32m'
NC='\033[0m'

PASSED=0
FAILED=0

echo "Testing Flask + PostgreSQL + OpenTelemetry API"
echo "================================================"
echo "Base URL: $BASE_URL"
echo "Timestamp: $TIMESTAMP"
echo ""

# Wait for services to be ready
echo "Waiting for services to be ready..."
for i in {1..30}; do
    if curl -s "$BASE_URL/api/health" > /dev/null 2>&1; then
        echo "Services are ready!"
        break
    fi
    if [ $i -eq 30 ]; then
        echo -e "${RED}Services failed to start${NC}"
        exit 1
    fi
    echo "Waiting... ($i/30)"
    sleep 2
done

echo ""
echo "Health"
echo "------"

# Health check
echo -n "GET /api/health... "
HEALTH=$(curl -s "$BASE_URL/api/health")
if echo "$HEALTH" | grep -q '"status":.*"healthy"'; then
    echo -e "${GREEN}PASS${NC}"
    ((PASSED++))
else
    echo -e "${RED}FAIL${NC}"
    echo "$HEALTH"
    ((FAILED++))
fi

echo ""
echo "Authentication"
echo "--------------"

# Generate unique email
EMAIL="test-$TIMESTAMP@example.com"
EMAIL2="test2-$TIMESTAMP@example.com"

# Register user 1
echo -n "POST /api/register... "
REGISTER=$(curl -s -X POST "$BASE_URL/api/register" \
    -H "Content-Type: application/json" \
    -d "{\"email\":\"$EMAIL\",\"password\":\"password123\",\"name\":\"Test User\"}")
if echo "$REGISTER" | grep -q '"access_token"'; then
    TOKEN=$(echo "$REGISTER" | grep -o '"access_token":.*"[^"]*"' | sed 's/.*"access_token":[[:space:]]*"//' | sed 's/".*//')
    echo -e "${GREEN}PASS${NC}"
    ((PASSED++))
else
    echo -e "${RED}FAIL${NC}"
    echo "$REGISTER"
    ((FAILED++))
fi

# Register user 2 (for permission tests)
echo -n "POST /api/register (user 2)... "
REGISTER2=$(curl -s -X POST "$BASE_URL/api/register" \
    -H "Content-Type: application/json" \
    -d "{\"email\":\"$EMAIL2\",\"password\":\"password123\",\"name\":\"Test User 2\"}")
if echo "$REGISTER2" | grep -q '"access_token"'; then
    TOKEN2=$(echo "$REGISTER2" | grep -o '"access_token":.*"[^"]*"' | sed 's/.*"access_token":[[:space:]]*"//' | sed 's/".*//')
    echo -e "${GREEN}PASS${NC}"
    ((PASSED++))
else
    echo -e "${RED}FAIL${NC}"
    echo "$REGISTER2"
    ((FAILED++))
fi

# Register - validation error (missing fields)
echo -n "POST /api/register (missing fields -> 400)... "
VALIDATION=$(curl -s -X POST "$BASE_URL/api/register" \
    -H "Content-Type: application/json" \
    -d '{"email":"incomplete@example.com"}' \
    -o /dev/null -w "%{http_code}")
if [ "$VALIDATION" = "400" ]; then
    echo -e "${GREEN}PASS${NC}"
    ((PASSED++))
else
    echo -e "${RED}FAIL (expected 400, got $VALIDATION)${NC}"
    ((FAILED++))
fi

# Register - duplicate email
echo -n "POST /api/register (duplicate -> 409)... "
DUPLICATE=$(curl -s -X POST "$BASE_URL/api/register" \
    -H "Content-Type: application/json" \
    -d "{\"email\":\"$EMAIL\",\"password\":\"password123\",\"name\":\"Duplicate\"}" \
    -o /dev/null -w "%{http_code}")
if [ "$DUPLICATE" = "409" ]; then
    echo -e "${GREEN}PASS${NC}"
    ((PASSED++))
else
    echo -e "${RED}FAIL (expected 409, got $DUPLICATE)${NC}"
    ((FAILED++))
fi

# Login
echo -n "POST /api/login... "
LOGIN=$(curl -s -X POST "$BASE_URL/api/login" \
    -H "Content-Type: application/json" \
    -d "{\"email\":\"$EMAIL\",\"password\":\"password123\"}")
if echo "$LOGIN" | grep -q '"access_token"'; then
    TOKEN=$(echo "$LOGIN" | grep -o '"access_token":.*"[^"]*"' | sed 's/.*"access_token":[[:space:]]*"//' | sed 's/".*//')
    echo -e "${GREEN}PASS${NC}"
    ((PASSED++))
else
    echo -e "${RED}FAIL${NC}"
    echo "$LOGIN"
    ((FAILED++))
fi

# Login - wrong password
echo -n "POST /api/login (wrong password -> 401)... "
INVALID_LOGIN=$(curl -s -X POST "$BASE_URL/api/login" \
    -H "Content-Type: application/json" \
    -d "{\"email\":\"$EMAIL\",\"password\":\"wrongpassword\"}" \
    -o /dev/null -w "%{http_code}")
if [ "$INVALID_LOGIN" = "401" ]; then
    echo -e "${GREEN}PASS${NC}"
    ((PASSED++))
else
    echo -e "${RED}FAIL (expected 401, got $INVALID_LOGIN)${NC}"
    ((FAILED++))
fi

# Login - non-existent user
echo -n "POST /api/login (non-existent user -> 401)... "
NOUSER_LOGIN=$(curl -s -X POST "$BASE_URL/api/login" \
    -H "Content-Type: application/json" \
    -d '{"email":"nouser@example.com","password":"password123"}' \
    -o /dev/null -w "%{http_code}")
if [ "$NOUSER_LOGIN" = "401" ]; then
    echo -e "${GREEN}PASS${NC}"
    ((PASSED++))
else
    echo -e "${RED}FAIL (expected 401, got $NOUSER_LOGIN)${NC}"
    ((FAILED++))
fi

# Get current user
echo -n "GET /api/user... "
ME=$(curl -s "$BASE_URL/api/user" -H "Authorization: Bearer $TOKEN")
if echo "$ME" | grep -q "\"email\":.*\"$EMAIL\""; then
    echo -e "${GREEN}PASS${NC}"
    ((PASSED++))
else
    echo -e "${RED}FAIL${NC}"
    echo "$ME"
    ((FAILED++))
fi

# Get current user - no token
echo -n "GET /api/user (no token -> 401)... "
UNAUTH=$(curl -s "$BASE_URL/api/user" -o /dev/null -w "%{http_code}")
if [ "$UNAUTH" = "401" ]; then
    echo -e "${GREEN}PASS${NC}"
    ((PASSED++))
else
    echo -e "${RED}FAIL (expected 401, got $UNAUTH)${NC}"
    ((FAILED++))
fi

# Get current user - invalid token
echo -n "GET /api/user (invalid token -> 401)... "
BAD_TOKEN=$(curl -s "$BASE_URL/api/user" \
    -H "Authorization: Bearer invalid.token.here" \
    -o /dev/null -w "%{http_code}")
if [ "$BAD_TOKEN" = "401" ]; then
    echo -e "${GREEN}PASS${NC}"
    ((PASSED++))
else
    echo -e "${RED}FAIL (expected 401, got $BAD_TOKEN)${NC}"
    ((FAILED++))
fi

echo ""
echo "Articles"
echo "--------"

# Create article
echo -n "POST /api/articles/... "
ARTICLE=$(curl -s -X POST "$BASE_URL/api/articles/" \
    -H "Content-Type: application/json" \
    -H "Authorization: Bearer $TOKEN" \
    -d "{\"title\":\"Test Article $TIMESTAMP\",\"body\":\"This is test content.\",\"description\":\"A test article\"}")
if echo "$ARTICLE" | grep -q '"slug"'; then
    SLUG=$(echo "$ARTICLE" | grep -o '"slug":.*"[^"]*"' | sed 's/.*"slug":[[:space:]]*"//' | sed 's/".*//')
    echo -e "${GREEN}PASS${NC} (slug: $SLUG)"
    ((PASSED++))
else
    echo -e "${RED}FAIL${NC}"
    echo "$ARTICLE"
    ((FAILED++))
fi

# Create article - no auth
echo -n "POST /api/articles/ (no auth -> 401)... "
NO_AUTH_CREATE=$(curl -s -X POST "$BASE_URL/api/articles/" \
    -H "Content-Type: application/json" \
    -d '{"title":"Unauthorized","body":"Should fail"}' \
    -o /dev/null -w "%{http_code}")
if [ "$NO_AUTH_CREATE" = "401" ]; then
    echo -e "${GREEN}PASS${NC}"
    ((PASSED++))
else
    echo -e "${RED}FAIL (expected 401, got $NO_AUTH_CREATE)${NC}"
    ((FAILED++))
fi

# List articles
echo -n "GET /api/articles/... "
ARTICLES=$(curl -s "$BASE_URL/api/articles/")
if echo "$ARTICLES" | grep -q '"articles"'; then
    echo -e "${GREEN}PASS${NC}"
    ((PASSED++))
else
    echo -e "${RED}FAIL${NC}"
    echo "$ARTICLES"
    ((FAILED++))
fi

# List articles with search
echo -n "GET /api/articles/?search=Test... "
SEARCH=$(curl -s "$BASE_URL/api/articles/?search=Test")
if echo "$SEARCH" | grep -q '"articles"'; then
    echo -e "${GREEN}PASS${NC}"
    ((PASSED++))
else
    echo -e "${RED}FAIL${NC}"
    echo "$SEARCH"
    ((FAILED++))
fi

# Get single article
echo -n "GET /api/articles/$SLUG... "
SINGLE=$(curl -s "$BASE_URL/api/articles/$SLUG")
if echo "$SINGLE" | grep -q "\"slug\":.*\"$SLUG\""; then
    echo -e "${GREEN}PASS${NC}"
    ((PASSED++))
else
    echo -e "${RED}FAIL${NC}"
    echo "$SINGLE"
    ((FAILED++))
fi

# Get article - not found
echo -n "GET /api/articles/non-existent-slug (not found -> 404)... "
NOT_FOUND=$(curl -s "$BASE_URL/api/articles/non-existent-slug-$TIMESTAMP" \
    -o /dev/null -w "%{http_code}")
if [ "$NOT_FOUND" = "404" ]; then
    echo -e "${GREEN}PASS${NC}"
    ((PASSED++))
else
    echo -e "${RED}FAIL (expected 404, got $NOT_FOUND)${NC}"
    ((FAILED++))
fi

# Update article
echo -n "PUT /api/articles/$SLUG... "
UPDATED=$(curl -s -X PUT "$BASE_URL/api/articles/$SLUG" \
    -H "Content-Type: application/json" \
    -H "Authorization: Bearer $TOKEN" \
    -d '{"title":"Updated Title"}')
if echo "$UPDATED" | grep -q '"title":.*"Updated Title"'; then
    echo -e "${GREEN}PASS${NC}"
    ((PASSED++))
else
    echo -e "${RED}FAIL${NC}"
    echo "$UPDATED"
    ((FAILED++))
fi

# Update article - not owner
echo -n "PUT /api/articles/$SLUG (not owner -> 403)... "
NOT_OWNER_UPDATE=$(curl -s -X PUT "$BASE_URL/api/articles/$SLUG" \
    -H "Content-Type: application/json" \
    -H "Authorization: Bearer $TOKEN2" \
    -d '{"title":"Should Fail"}' \
    -o /dev/null -w "%{http_code}")
if [ "$NOT_OWNER_UPDATE" = "403" ]; then
    echo -e "${GREEN}PASS${NC}"
    ((PASSED++))
else
    echo -e "${RED}FAIL (expected 403, got $NOT_OWNER_UPDATE)${NC}"
    ((FAILED++))
fi

echo ""
echo "Favorites"
echo "---------"

# Favorite article
echo -n "POST /api/articles/$SLUG/favorite... "
FAVORITE=$(curl -s -X POST "$BASE_URL/api/articles/$SLUG/favorite" \
    -H "Authorization: Bearer $TOKEN")
if echo "$FAVORITE" | grep -qE '"favorited":.*true|"favorites_count":.*1'; then
    echo -e "${GREEN}PASS${NC}"
    ((PASSED++))
else
    echo -e "${RED}FAIL${NC}"
    echo "$FAVORITE"
    ((FAILED++))
fi

# Favorite article - duplicate (should be idempotent or return 409)
echo -n "POST /api/articles/$SLUG/favorite (duplicate)... "
FAVORITE_DUPE=$(curl -s -X POST "$BASE_URL/api/articles/$SLUG/favorite" \
    -H "Authorization: Bearer $TOKEN" \
    -o /dev/null -w "%{http_code}")
if [ "$FAVORITE_DUPE" = "200" ] || [ "$FAVORITE_DUPE" = "409" ]; then
    echo -e "${GREEN}PASS${NC} (HTTP $FAVORITE_DUPE)"
    ((PASSED++))
else
    echo -e "${RED}FAIL (expected 200 or 409, got $FAVORITE_DUPE)${NC}"
    ((FAILED++))
fi

# Verify favorites count
echo -n "GET /api/articles/$SLUG (favorites_count=1)... "
AFTER_FAV=$(curl -s "$BASE_URL/api/articles/$SLUG")
if echo "$AFTER_FAV" | grep -qE '"favorites_count":.*1'; then
    echo -e "${GREEN}PASS${NC}"
    ((PASSED++))
else
    echo -e "${RED}FAIL${NC}"
    echo "$AFTER_FAV"
    ((FAILED++))
fi

# Unfavorite article
echo -n "DELETE /api/articles/$SLUG/favorite... "
UNFAVORITE_STATUS=$(curl -s -X DELETE "$BASE_URL/api/articles/$SLUG/favorite" \
    -H "Authorization: Bearer $TOKEN" \
    -o /dev/null -w "%{http_code}")
if [ "$UNFAVORITE_STATUS" = "200" ]; then
    echo -e "${GREEN}PASS${NC}"
    ((PASSED++))
else
    echo -e "${RED}FAIL (expected 200, got $UNFAVORITE_STATUS)${NC}"
    ((FAILED++))
fi

# Verify favorites count after unfavorite
echo -n "GET /api/articles/$SLUG (favorites_count=0)... "
AFTER_UNFAV=$(curl -s "$BASE_URL/api/articles/$SLUG")
if echo "$AFTER_UNFAV" | grep -qE '"favorites_count":.*0'; then
    echo -e "${GREEN}PASS${NC}"
    ((PASSED++))
else
    echo -e "${RED}FAIL${NC}"
    echo "$AFTER_UNFAV"
    ((FAILED++))
fi

echo ""
echo "Cleanup"
echo "-------"

# Delete article - not owner
echo -n "DELETE /api/articles/$SLUG (not owner -> 403)... "
NOT_OWNER_DELETE=$(curl -s -X DELETE "$BASE_URL/api/articles/$SLUG" \
    -H "Authorization: Bearer $TOKEN2" \
    -o /dev/null -w "%{http_code}")
if [ "$NOT_OWNER_DELETE" = "403" ]; then
    echo -e "${GREEN}PASS${NC}"
    ((PASSED++))
else
    echo -e "${RED}FAIL (expected 403, got $NOT_OWNER_DELETE)${NC}"
    ((FAILED++))
fi

# Delete article
echo -n "DELETE /api/articles/$SLUG... "
DELETE=$(curl -s -X DELETE "$BASE_URL/api/articles/$SLUG" \
    -H "Authorization: Bearer $TOKEN" \
    -o /dev/null -w "%{http_code}")
if [ "$DELETE" = "204" ]; then
    echo -e "${GREEN}PASS${NC}"
    ((PASSED++))
else
    echo -e "${RED}FAIL (expected 204, got $DELETE)${NC}"
    ((FAILED++))
fi

# Verify article deleted
echo -n "GET /api/articles/$SLUG (after delete -> 404)... "
DELETED=$(curl -s "$BASE_URL/api/articles/$SLUG" \
    -o /dev/null -w "%{http_code}")
if [ "$DELETED" = "404" ]; then
    echo -e "${GREEN}PASS${NC}"
    ((PASSED++))
else
    echo -e "${RED}FAIL (expected 404, got $DELETED)${NC}"
    ((FAILED++))
fi

# Logout
echo -n "POST /api/logout... "
LOGOUT=$(curl -s -X POST "$BASE_URL/api/logout" \
    -H "Authorization: Bearer $TOKEN")
if echo "$LOGOUT" | grep -q '"message"'; then
    echo -e "${GREEN}PASS${NC}"
    ((PASSED++))
else
    echo -e "${RED}FAIL${NC}"
    echo "$LOGOUT"
    ((FAILED++))
fi

echo ""
echo "========================================"
echo "Test Summary"
echo "========================================"
echo -e "Passed: ${GREEN}$PASSED${NC}"
echo -e "Failed: ${RED}$FAILED${NC}"
echo ""

if [ $FAILED -gt 0 ]; then
    echo -e "${RED}Some tests failed!${NC}"
    exit 1
else
    echo -e "${GREEN}All tests passed!${NC}"
    exit 0
fi
