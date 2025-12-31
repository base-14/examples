#!/bin/bash
# Express 5 + PostgreSQL + OpenTelemetry API Test Script
# Tests all endpoints with expected responses

BASE_URL="${BASE_URL:-http://localhost:8000}"
PASS=0
FAIL=0
TOKEN=""
ARTICLE_SLUG=""

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m'

log_pass() {
    echo -e "${GREEN}✓ PASS${NC}: $1"
    ((PASS++))
}

log_fail() {
    echo -e "${RED}✗ FAIL${NC}: $1"
    ((FAIL++))
}

log_info() {
    echo -e "${YELLOW}→${NC} $1"
}

test_endpoint() {
    local name="$1"
    local method="$2"
    local endpoint="$3"
    local expected_status="$4"
    local data="$5"
    local auth="$6"

    local curl_args=(-s -w "\n%{http_code}" -X "$method")

    if [ -n "$data" ]; then
        curl_args+=(-H "Content-Type: application/json" -d "$data")
    fi

    if [ -n "$auth" ]; then
        curl_args+=(-H "Authorization: Bearer $auth")
    fi

    local response
    response=$(curl "${curl_args[@]}" "${BASE_URL}${endpoint}")

    local body
    body=$(echo "$response" | sed '$d')
    local status
    status=$(echo "$response" | tail -n1)

    if [ "$status" = "$expected_status" ]; then
        log_pass "$name (HTTP $status)"
        echo "$body"
    else
        log_fail "$name (expected $expected_status, got $status)"
        echo "$body"
    fi

    echo ""
}

echo "========================================"
echo "Express 5 + PostgreSQL API Tests"
echo "========================================"
echo ""

# -----------------------------------------------------------------------------
# Health Check
# -----------------------------------------------------------------------------
log_info "Testing Health Endpoint..."
test_endpoint "Health check" "GET" "/api/health" "200"

# -----------------------------------------------------------------------------
# Authentication
# -----------------------------------------------------------------------------
log_info "Testing Authentication Endpoints..."

# Generate unique email
EMAIL="test-$(date +%s)@example.com"

# Register
log_info "Registering user: $EMAIL"
REGISTER_RESPONSE=$(curl -s -X POST "${BASE_URL}/api/register" \
    -H "Content-Type: application/json" \
    -d "{\"email\":\"$EMAIL\",\"password\":\"password123\",\"name\":\"Test User\"}")
echo "$REGISTER_RESPONSE"

if echo "$REGISTER_RESPONSE" | grep -q '"token"'; then
    log_pass "User registration"
    TOKEN=$(echo "$REGISTER_RESPONSE" | grep -o '"token":"[^"]*"' | cut -d'"' -f4)
else
    log_fail "User registration"
fi
echo ""

# Duplicate registration should fail
log_info "Testing duplicate registration..."
test_endpoint "Duplicate registration rejected" "POST" "/api/register" "409" \
    "{\"email\":\"$EMAIL\",\"password\":\"password123\",\"name\":\"Test User\"}"

# Login
log_info "Testing login..."
LOGIN_RESPONSE=$(curl -s -X POST "${BASE_URL}/api/login" \
    -H "Content-Type: application/json" \
    -d "{\"email\":\"$EMAIL\",\"password\":\"password123\"}")
echo "$LOGIN_RESPONSE"

if echo "$LOGIN_RESPONSE" | grep -q '"token"'; then
    log_pass "User login"
    TOKEN=$(echo "$LOGIN_RESPONSE" | grep -o '"token":"[^"]*"' | cut -d'"' -f4)
else
    log_fail "User login"
fi
echo ""

# Invalid credentials
log_info "Testing invalid credentials..."
test_endpoint "Invalid credentials rejected" "POST" "/api/login" "401" \
    "{\"email\":\"$EMAIL\",\"password\":\"wrongpassword\"}"

# Get current user
log_info "Testing get current user..."
test_endpoint "Get current user" "GET" "/api/user" "200" "" "$TOKEN"

# Get user without auth
log_info "Testing unauthorized access..."
test_endpoint "Unauthorized access rejected" "GET" "/api/user" "401"

# -----------------------------------------------------------------------------
# Articles
# -----------------------------------------------------------------------------
log_info "Testing Article Endpoints..."

# Create article
log_info "Creating article..."
CREATE_RESPONSE=$(curl -s -X POST "${BASE_URL}/api/articles" \
    -H "Content-Type: application/json" \
    -H "Authorization: Bearer $TOKEN" \
    -d '{"title":"Test Article","description":"A test article","body":"This is the body of the test article."}')
echo "$CREATE_RESPONSE"

if echo "$CREATE_RESPONSE" | grep -q '"slug"'; then
    log_pass "Article creation"
    ARTICLE_SLUG=$(echo "$CREATE_RESPONSE" | grep -o '"slug":"[^"]*"' | cut -d'"' -f4)
    log_info "Created article with slug: $ARTICLE_SLUG"
else
    log_fail "Article creation"
fi
echo ""

# Create article without auth
log_info "Testing article creation without auth..."
test_endpoint "Article creation without auth rejected" "POST" "/api/articles" "401" \
    '{"title":"Unauthorized Article","body":"Should fail"}'

# List articles
log_info "Testing article listing..."
test_endpoint "List articles" "GET" "/api/articles" "200"

# List articles with pagination
log_info "Testing article listing with pagination..."
test_endpoint "List articles with pagination" "GET" "/api/articles?page=1&per_page=10" "200"

# List articles with search
log_info "Testing article search..."
test_endpoint "List articles with search" "GET" "/api/articles?search=Test" "200"

# Get single article
if [ -n "$ARTICLE_SLUG" ]; then
    log_info "Testing get single article..."
    test_endpoint "Get article by slug" "GET" "/api/articles/$ARTICLE_SLUG" "200"
fi

# Get non-existent article
log_info "Testing non-existent article..."
test_endpoint "Non-existent article returns 404" "GET" "/api/articles/non-existent-slug" "404"

# Update article
if [ -n "$ARTICLE_SLUG" ]; then
    log_info "Testing article update..."
    test_endpoint "Update article" "PUT" "/api/articles/$ARTICLE_SLUG" "200" \
        '{"title":"Updated Test Article","body":"Updated body content."}' "$TOKEN"
fi

# Update article without auth
if [ -n "$ARTICLE_SLUG" ]; then
    log_info "Testing article update without auth..."
    test_endpoint "Update article without auth rejected" "PUT" "/api/articles/$ARTICLE_SLUG" "401" \
        '{"title":"Should Fail"}'
fi

# -----------------------------------------------------------------------------
# Favorites
# -----------------------------------------------------------------------------
log_info "Testing Favorite Endpoints..."

if [ -n "$ARTICLE_SLUG" ]; then
    # Favorite article
    log_info "Testing favorite article..."
    test_endpoint "Favorite article" "POST" "/api/articles/$ARTICLE_SLUG/favorite" "200" "" "$TOKEN"

    # Favorite again (idempotent)
    log_info "Testing favorite again (should be idempotent)..."
    test_endpoint "Favorite article again" "POST" "/api/articles/$ARTICLE_SLUG/favorite" "200" "" "$TOKEN"

    # Unfavorite article
    log_info "Testing unfavorite article..."
    test_endpoint "Unfavorite article" "DELETE" "/api/articles/$ARTICLE_SLUG/favorite" "200" "" "$TOKEN"

    # Unfavorite again (idempotent)
    log_info "Testing unfavorite again (should be idempotent)..."
    test_endpoint "Unfavorite article again" "DELETE" "/api/articles/$ARTICLE_SLUG/favorite" "200" "" "$TOKEN"
fi

# Favorite without auth
if [ -n "$ARTICLE_SLUG" ]; then
    log_info "Testing favorite without auth..."
    test_endpoint "Favorite without auth rejected" "POST" "/api/articles/$ARTICLE_SLUG/favorite" "401"
fi

# -----------------------------------------------------------------------------
# Delete article
# -----------------------------------------------------------------------------
if [ -n "$ARTICLE_SLUG" ]; then
    log_info "Testing article deletion..."
    test_endpoint "Delete article" "DELETE" "/api/articles/$ARTICLE_SLUG" "204" "" "$TOKEN"

    # Verify deletion
    log_info "Verifying article deletion..."
    test_endpoint "Deleted article returns 404" "GET" "/api/articles/$ARTICLE_SLUG" "404"
fi

# -----------------------------------------------------------------------------
# Logout
# -----------------------------------------------------------------------------
log_info "Testing logout..."
test_endpoint "Logout" "POST" "/api/logout" "200" "" "$TOKEN"

# -----------------------------------------------------------------------------
# Summary
# -----------------------------------------------------------------------------
echo "========================================"
echo "Test Summary"
echo "========================================"
echo -e "${GREEN}Passed: $PASS${NC}"
echo -e "${RED}Failed: $FAIL${NC}"
echo ""

if [ $FAIL -gt 0 ]; then
    echo -e "${RED}Some tests failed!${NC}"
    exit 1
else
    echo -e "${GREEN}All tests passed!${NC}"
    exit 0
fi
