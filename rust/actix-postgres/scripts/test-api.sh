#!/bin/bash

# Test script for Rust Actix Web PostgreSQL API
# Usage: ./scripts/test-api.sh [base_url]

set -e

BASE_URL="${1:-http://localhost:8080}"
PASS=0
FAIL=0

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m'

log_pass() {
    echo -e "${GREEN}✓ PASS${NC}: $1"
    PASS=$((PASS + 1))
}

log_fail() {
    echo -e "${RED}✗ FAIL${NC}: $1"
    FAIL=$((FAIL + 1))
}

log_info() {
    echo -e "${YELLOW}→${NC} $1"
}

test_endpoint() {
    local method=$1
    local endpoint=$2
    local expected_status=$3
    local data=$4
    local auth=$5
    local description=$6

    log_info "Testing: $description"

    local curl_args="-s -w '\n%{http_code}' -X $method"

    if [ -n "$data" ]; then
        curl_args="$curl_args -H 'Content-Type: application/json' -d '$data'"
    fi

    if [ -n "$auth" ]; then
        curl_args="$curl_args -H 'Authorization: Bearer $auth'"
    fi

    local response
    response=$(eval "curl $curl_args '$BASE_URL$endpoint'")
    local status_code=$(echo "$response" | tail -n 1)
    local body=$(echo "$response" | sed '$d')

    if [ "$status_code" = "$expected_status" ]; then
        log_pass "$description (status: $status_code)"
        echo "$body"
    else
        log_fail "$description (expected: $expected_status, got: $status_code)"
        echo "$body"
    fi

    echo ""
}

echo "========================================"
echo "Rust Actix Web PostgreSQL API Test Suite"
echo "Base URL: $BASE_URL"
echo "========================================"
echo ""

# Health Check
test_endpoint "GET" "/api/health" "200" "" "" "Health check"

# Register User
TIMESTAMP=$(date +%s)
USER_EMAIL="test${TIMESTAMP}@example.com"
USER_DATA="{\"email\":\"$USER_EMAIL\",\"password\":\"password123\",\"name\":\"Test User\"}"

log_info "Registering user: $USER_EMAIL"
REGISTER_RESPONSE=$(curl -s -X POST "$BASE_URL/api/register" \
    -H "Content-Type: application/json" \
    -d "$USER_DATA")

TOKEN=$(echo "$REGISTER_RESPONSE" | grep -o '"token":"[^"]*"' | cut -d'"' -f4)

if [ -n "$TOKEN" ]; then
    log_pass "User registration"
    echo "Token received: ${TOKEN:0:20}..."
else
    log_fail "User registration - no token received"
    echo "$REGISTER_RESPONSE"
fi
echo ""

# Duplicate registration
log_info "Testing duplicate registration"
DUP_RESPONSE=$(curl -s -w '\n%{http_code}' -X POST "$BASE_URL/api/register" \
    -H "Content-Type: application/json" \
    -d "$USER_DATA")
DUP_STATUS=$(echo "$DUP_RESPONSE" | tail -n 1)

if [ "$DUP_STATUS" = "409" ]; then
    log_pass "Duplicate registration rejected (status: 409)"
else
    log_fail "Duplicate registration (expected: 409, got: $DUP_STATUS)"
fi
echo ""

# Login
log_info "Testing login"
LOGIN_DATA="{\"email\":\"$USER_EMAIL\",\"password\":\"password123\"}"
LOGIN_RESPONSE=$(curl -s -X POST "$BASE_URL/api/login" \
    -H "Content-Type: application/json" \
    -d "$LOGIN_DATA")

LOGIN_TOKEN=$(echo "$LOGIN_RESPONSE" | grep -o '"token":"[^"]*"' | cut -d'"' -f4)

if [ -n "$LOGIN_TOKEN" ]; then
    log_pass "User login"
else
    log_fail "User login - no token received"
fi
echo ""

# Login with wrong password
log_info "Testing login with wrong password"
WRONG_LOGIN=$(curl -s -w '\n%{http_code}' -X POST "$BASE_URL/api/login" \
    -H "Content-Type: application/json" \
    -d "{\"email\":\"$USER_EMAIL\",\"password\":\"wrong\"}")
WRONG_STATUS=$(echo "$WRONG_LOGIN" | tail -n 1)

if [ "$WRONG_STATUS" = "401" ]; then
    log_pass "Wrong password rejected (status: 401)"
else
    log_fail "Wrong password (expected: 401, got: $WRONG_STATUS)"
fi
echo ""

# Get User Profile
test_endpoint "GET" "/api/user" "200" "" "$TOKEN" "Get user profile (authenticated)"

# Get User Profile - Unauthorized
test_endpoint "GET" "/api/user" "401" "" "" "Get user profile (unauthorized)"

# Create Article
ARTICLE_DATA="{\"title\":\"Test Article $TIMESTAMP\",\"description\":\"Test description\",\"body\":\"This is the article body.\"}"
log_info "Creating article"
CREATE_RESPONSE=$(curl -s -X POST "$BASE_URL/api/articles" \
    -H "Content-Type: application/json" \
    -H "Authorization: Bearer $TOKEN" \
    -d "$ARTICLE_DATA")

ARTICLE_SLUG=$(echo "$CREATE_RESPONSE" | grep -o '"slug":"[^"]*"' | cut -d'"' -f4)

if [ -n "$ARTICLE_SLUG" ]; then
    log_pass "Create article"
    echo "Article slug: $ARTICLE_SLUG"
else
    log_fail "Create article - no slug received"
    echo "$CREATE_RESPONSE"
fi
echo ""

# Create Article - Unauthorized
test_endpoint "POST" "/api/articles" "401" "$ARTICLE_DATA" "" "Create article (unauthorized)"

# Create Second Article
ARTICLE2_DATA="{\"title\":\"Second Article $TIMESTAMP\",\"body\":\"Second body\"}"
log_info "Creating second article"
CREATE2_RESPONSE=$(curl -s -X POST "$BASE_URL/api/articles" \
    -H "Content-Type: application/json" \
    -H "Authorization: Bearer $TOKEN" \
    -d "$ARTICLE2_DATA")

ARTICLE2_SLUG=$(echo "$CREATE2_RESPONSE" | grep -o '"slug":"[^"]*"' | cut -d'"' -f4)

if [ -n "$ARTICLE2_SLUG" ]; then
    log_pass "Create second article"
else
    log_fail "Create second article"
fi
echo ""

# List Articles
test_endpoint "GET" "/api/articles" "200" "" "" "List articles (public)"

# List Articles with pagination
test_endpoint "GET" "/api/articles?limit=1&offset=0" "200" "" "" "List articles (paginated)"

# Get Single Article
if [ -n "$ARTICLE_SLUG" ]; then
    test_endpoint "GET" "/api/articles/$ARTICLE_SLUG" "200" "" "" "Get single article"
fi

# Get Non-existent Article
test_endpoint "GET" "/api/articles/non-existent-slug" "404" "" "" "Get non-existent article"

# Update Article
if [ -n "$ARTICLE_SLUG" ]; then
    UPDATE_DATA="{\"title\":\"Updated Article $TIMESTAMP\",\"description\":\"Updated description\"}"
    log_info "Updating article"
    UPDATE_RESPONSE=$(curl -s -X PUT "$BASE_URL/api/articles/$ARTICLE_SLUG" \
        -H "Content-Type: application/json" \
        -H "Authorization: Bearer $TOKEN" \
        -d "$UPDATE_DATA")

    NEW_SLUG=$(echo "$UPDATE_RESPONSE" | grep -o '"slug":"[^"]*"' | cut -d'"' -f4)

    if [ -n "$NEW_SLUG" ]; then
        log_pass "Update article (owner)"
        echo "New slug: $NEW_SLUG"
        ARTICLE_SLUG="$NEW_SLUG"
    else
        log_fail "Update article - no slug received"
        echo "$UPDATE_RESPONSE"
    fi
    echo ""
fi

# Update Article - Unauthorized
if [ -n "$ARTICLE_SLUG" ]; then
    test_endpoint "PUT" "/api/articles/$ARTICLE_SLUG" "401" "$UPDATE_DATA" "" "Update article (unauthorized)"
fi

# Register second user for ownership tests
USER2_EMAIL="test2-${TIMESTAMP}@example.com"
USER2_DATA="{\"email\":\"$USER2_EMAIL\",\"password\":\"password123\",\"name\":\"Test User 2\"}"
USER2_RESPONSE=$(curl -s -X POST "$BASE_URL/api/register" \
    -H "Content-Type: application/json" \
    -d "$USER2_DATA")
TOKEN2=$(echo "$USER2_RESPONSE" | grep -o '"token":"[^"]*"' | cut -d'"' -f4)

# Update Article - Wrong Owner
if [ -n "$ARTICLE_SLUG" ] && [ -n "$TOKEN2" ]; then
    test_endpoint "PUT" "/api/articles/$ARTICLE_SLUG" "403" "{\"title\":\"Hijacked\"}" "$TOKEN2" "Update article (wrong owner)"
fi

# Favorite Article
if [ -n "$ARTICLE_SLUG" ]; then
    test_endpoint "POST" "/api/articles/$ARTICLE_SLUG/favorite" "200" "" "$TOKEN" "Favorite article"
fi

# Favorite same article again (idempotent)
if [ -n "$ARTICLE_SLUG" ]; then
    test_endpoint "POST" "/api/articles/$ARTICLE_SLUG/favorite" "200" "" "$TOKEN" "Favorite article (idempotent)"
fi

# Unfavorite Article
if [ -n "$ARTICLE_SLUG" ]; then
    test_endpoint "DELETE" "/api/articles/$ARTICLE_SLUG/favorite" "200" "" "$TOKEN" "Unfavorite article"
fi

# Delete Article - Wrong Owner
if [ -n "$ARTICLE_SLUG" ] && [ -n "$TOKEN2" ]; then
    test_endpoint "DELETE" "/api/articles/$ARTICLE_SLUG" "403" "" "$TOKEN2" "Delete article (wrong owner)"
fi

# Delete Article
if [ -n "$ARTICLE_SLUG" ]; then
    test_endpoint "DELETE" "/api/articles/$ARTICLE_SLUG" "204" "" "$TOKEN" "Delete article (owner)"
fi

# Delete Non-existent Article
test_endpoint "DELETE" "/api/articles/non-existent-slug" "404" "" "$TOKEN" "Delete non-existent article"

# Clean up second article
if [ -n "$ARTICLE2_SLUG" ]; then
    test_endpoint "DELETE" "/api/articles/$ARTICLE2_SLUG" "204" "" "$TOKEN" "Delete second article"
fi

# Logout
test_endpoint "POST" "/api/logout" "200" "" "$TOKEN" "Logout"

# Summary
echo "========================================"
echo "Test Summary"
echo "========================================"
echo -e "${GREEN}Passed: $PASS${NC}"
echo -e "${RED}Failed: $FAIL${NC}"
echo ""

if [ $FAIL -gt 0 ]; then
    exit 1
fi
