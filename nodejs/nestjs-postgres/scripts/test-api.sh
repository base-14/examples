#!/bin/bash

set -e

BASE_URL="${BASE_URL:-http://localhost:3000}"
RED='\033[0;31m'
GREEN='\033[0;32m'
NC='\033[0m'

echo "Testing NestJS + PostgreSQL API"
echo "================================"
echo "Base URL: $BASE_URL"
echo ""

# Health
echo "Health"
echo "------"
echo -n "GET /api/health... "
HEALTH=$(curl -s "$BASE_URL/api/health")
if echo "$HEALTH" | grep -q '"status":"ok"'; then
    echo -e "${GREEN}PASS${NC}"
else
    echo -e "${RED}FAIL${NC}"
    echo "$HEALTH"
    exit 1
fi

# Generate unique email
EMAIL="test-$(date +%s)@example.com"

echo ""
echo "Authentication"
echo "--------------"

# Register
echo -n "POST /api/auth/register... "
REGISTER=$(curl -s -X POST "$BASE_URL/api/auth/register" \
    -H "Content-Type: application/json" \
    -d "{\"email\":\"$EMAIL\",\"password\":\"password123\",\"name\":\"Test User\"}")
if echo "$REGISTER" | grep -q '"token"'; then
    TOKEN=$(echo "$REGISTER" | grep -o '"token":"[^"]*"' | cut -d'"' -f4)
    echo -e "${GREEN}PASS${NC}"
else
    echo -e "${RED}FAIL${NC}"
    echo "$REGISTER"
    exit 1
fi

# Register - validation error
echo -n "POST /api/auth/register (missing fields → 400)... "
VALIDATION=$(curl -s -X POST "$BASE_URL/api/auth/register" \
    -H "Content-Type: application/json" \
    -d '{"email":"incomplete@example.com"}' \
    -o /dev/null -w "%{http_code}")
if [ "$VALIDATION" = "400" ]; then
    echo -e "${GREEN}PASS${NC}"
else
    echo -e "${RED}FAIL (expected 400, got $VALIDATION)${NC}"
    exit 1
fi

# Register - duplicate
echo -n "POST /api/auth/register (duplicate → 409)... "
DUPLICATE=$(curl -s -X POST "$BASE_URL/api/auth/register" \
    -H "Content-Type: application/json" \
    -d "{\"email\":\"$EMAIL\",\"password\":\"password123\",\"name\":\"Test User\"}" \
    -o /dev/null -w "%{http_code}")
if [ "$DUPLICATE" = "409" ]; then
    echo -e "${GREEN}PASS${NC}"
else
    echo -e "${RED}FAIL (expected 409, got $DUPLICATE)${NC}"
    exit 1
fi

# Login
echo -n "POST /api/auth/login... "
LOGIN=$(curl -s -X POST "$BASE_URL/api/auth/login" \
    -H "Content-Type: application/json" \
    -d "{\"email\":\"$EMAIL\",\"password\":\"password123\"}")
if echo "$LOGIN" | grep -q '"token"'; then
    TOKEN=$(echo "$LOGIN" | grep -o '"token":"[^"]*"' | cut -d'"' -f4)
    echo -e "${GREEN}PASS${NC}"
else
    echo -e "${RED}FAIL${NC}"
    echo "$LOGIN"
    exit 1
fi

# Login - wrong password
echo -n "POST /api/auth/login (wrong password → 401)... "
INVALID_LOGIN=$(curl -s -X POST "$BASE_URL/api/auth/login" \
    -H "Content-Type: application/json" \
    -d "{\"email\":\"$EMAIL\",\"password\":\"wrongpassword\"}" \
    -o /dev/null -w "%{http_code}")
if [ "$INVALID_LOGIN" = "401" ]; then
    echo -e "${GREEN}PASS${NC}"
else
    echo -e "${RED}FAIL (expected 401, got $INVALID_LOGIN)${NC}"
    exit 1
fi

# Login - non-existent user
echo -n "POST /api/auth/login (non-existent user → 401)... "
NOUSER_LOGIN=$(curl -s -X POST "$BASE_URL/api/auth/login" \
    -H "Content-Type: application/json" \
    -d '{"email":"nouser@example.com","password":"password123"}' \
    -o /dev/null -w "%{http_code}")
if [ "$NOUSER_LOGIN" = "401" ]; then
    echo -e "${GREEN}PASS${NC}"
else
    echo -e "${RED}FAIL (expected 401, got $NOUSER_LOGIN)${NC}"
    exit 1
fi

# Get current user
echo -n "GET /api/auth/me... "
ME=$(curl -s "$BASE_URL/api/auth/me" -H "Authorization: Bearer $TOKEN")
if echo "$ME" | grep -q "\"email\":\"$EMAIL\""; then
    echo -e "${GREEN}PASS${NC}"
else
    echo -e "${RED}FAIL${NC}"
    echo "$ME"
    exit 1
fi

# Get current user - no token
echo -n "GET /api/auth/me (no token → 401)... "
UNAUTH=$(curl -s "$BASE_URL/api/auth/me" -o /dev/null -w "%{http_code}")
if [ "$UNAUTH" = "401" ]; then
    echo -e "${GREEN}PASS${NC}"
else
    echo -e "${RED}FAIL (expected 401, got $UNAUTH)${NC}"
    exit 1
fi

# Get current user - invalid token
echo -n "GET /api/auth/me (invalid token → 401)... "
BAD_TOKEN=$(curl -s "$BASE_URL/api/auth/me" \
    -H "Authorization: Bearer invalid.token.here" \
    -o /dev/null -w "%{http_code}")
if [ "$BAD_TOKEN" = "401" ]; then
    echo -e "${GREEN}PASS${NC}"
else
    echo -e "${RED}FAIL (expected 401, got $BAD_TOKEN)${NC}"
    exit 1
fi

echo ""
echo "Articles"
echo "--------"

# Create article
echo -n "POST /api/articles... "
ARTICLE=$(curl -s -X POST "$BASE_URL/api/articles" \
    -H "Content-Type: application/json" \
    -H "Authorization: Bearer $TOKEN" \
    -d '{"title":"Test Article","content":"This is test content.","tags":["test","api"]}')
if echo "$ARTICLE" | grep -q '"id"'; then
    ARTICLE_ID=$(echo "$ARTICLE" | grep -o '"id":"[^"]*"' | head -1 | cut -d'"' -f4)
    echo -e "${GREEN}PASS${NC}"
else
    echo -e "${RED}FAIL${NC}"
    echo "$ARTICLE"
    exit 1
fi

# Create article - no auth
echo -n "POST /api/articles (no auth → 401)... "
NO_AUTH_CREATE=$(curl -s -X POST "$BASE_URL/api/articles" \
    -H "Content-Type: application/json" \
    -d '{"title":"Unauthorized","content":"Should fail"}' \
    -o /dev/null -w "%{http_code}")
if [ "$NO_AUTH_CREATE" = "401" ]; then
    echo -e "${GREEN}PASS${NC}"
else
    echo -e "${RED}FAIL (expected 401, got $NO_AUTH_CREATE)${NC}"
    exit 1
fi

# List articles
echo -n "GET /api/articles... "
ARTICLES=$(curl -s "$BASE_URL/api/articles")
if echo "$ARTICLES" | grep -q '"data"'; then
    echo -e "${GREEN}PASS${NC}"
else
    echo -e "${RED}FAIL${NC}"
    echo "$ARTICLES"
    exit 1
fi

# Get single article
echo -n "GET /api/articles/:id... "
SINGLE=$(curl -s "$BASE_URL/api/articles/$ARTICLE_ID")
if echo "$SINGLE" | grep -q '"title":"Test Article"'; then
    echo -e "${GREEN}PASS${NC}"
else
    echo -e "${RED}FAIL${NC}"
    echo "$SINGLE"
    exit 1
fi

# Get article - not found
echo -n "GET /api/articles/:id (not found → 404)... "
NOT_FOUND=$(curl -s "$BASE_URL/api/articles/00000000-0000-0000-0000-000000000000" \
    -o /dev/null -w "%{http_code}")
if [ "$NOT_FOUND" = "404" ]; then
    echo -e "${GREEN}PASS${NC}"
else
    echo -e "${RED}FAIL (expected 404, got $NOT_FOUND)${NC}"
    exit 1
fi

# Get article - invalid UUID
echo -n "GET /api/articles/:id (invalid UUID → 400)... "
INVALID_UUID=$(curl -s "$BASE_URL/api/articles/not-a-uuid" \
    -o /dev/null -w "%{http_code}")
if [ "$INVALID_UUID" = "400" ]; then
    echo -e "${GREEN}PASS${NC}"
else
    echo -e "${RED}FAIL (expected 400, got $INVALID_UUID)${NC}"
    exit 1
fi

# Update article
echo -n "PUT /api/articles/:id... "
UPDATED=$(curl -s -X PUT "$BASE_URL/api/articles/$ARTICLE_ID" \
    -H "Content-Type: application/json" \
    -H "Authorization: Bearer $TOKEN" \
    -d '{"title":"Updated Title","published":true}')
if echo "$UPDATED" | grep -q '"title":"Updated Title"'; then
    echo -e "${GREEN}PASS${NC}"
else
    echo -e "${RED}FAIL${NC}"
    echo "$UPDATED"
    exit 1
fi

echo ""
echo "Favorites"
echo "---------"

# Favorite article
echo -n "POST /api/articles/:id/favorite... "
FAVORITE=$(curl -s -X POST "$BASE_URL/api/articles/$ARTICLE_ID/favorite" \
    -H "Authorization: Bearer $TOKEN")
if echo "$FAVORITE" | grep -q '"message"'; then
    echo -e "${GREEN}PASS${NC}"
else
    echo -e "${RED}FAIL${NC}"
    echo "$FAVORITE"
    exit 1
fi

# Verify favorites count
echo -n "GET /api/articles/:id (favoritesCount=1)... "
AFTER_FAV=$(curl -s "$BASE_URL/api/articles/$ARTICLE_ID")
if echo "$AFTER_FAV" | grep -q '"favoritesCount":1'; then
    echo -e "${GREEN}PASS${NC}"
else
    echo -e "${RED}FAIL${NC}"
    echo "$AFTER_FAV"
    exit 1
fi

# Unfavorite article
echo -n "DELETE /api/articles/:id/favorite... "
UNFAVORITE=$(curl -s -X DELETE "$BASE_URL/api/articles/$ARTICLE_ID/favorite" \
    -H "Authorization: Bearer $TOKEN")
if echo "$UNFAVORITE" | grep -q '"message"'; then
    echo -e "${GREEN}PASS${NC}"
else
    echo -e "${RED}FAIL${NC}"
    echo "$UNFAVORITE"
    exit 1
fi

echo ""
echo "Cleanup"
echo "-------"

# Delete article
echo -n "DELETE /api/articles/:id... "
DELETE=$(curl -s -X DELETE "$BASE_URL/api/articles/$ARTICLE_ID" \
    -H "Authorization: Bearer $TOKEN" -o /dev/null -w "%{http_code}")
if [ "$DELETE" = "204" ]; then
    echo -e "${GREEN}PASS${NC}"
else
    echo -e "${RED}FAIL (HTTP $DELETE)${NC}"
    exit 1
fi

# Logout
echo -n "POST /api/auth/logout... "
LOGOUT=$(curl -s -X POST "$BASE_URL/api/auth/logout" -H "Authorization: Bearer $TOKEN")
if echo "$LOGOUT" | grep -q '"message"'; then
    echo -e "${GREEN}PASS${NC}"
else
    echo -e "${RED}FAIL${NC}"
    echo "$LOGOUT"
    exit 1
fi

echo ""
echo -e "${GREEN}All tests passed!${NC}"
