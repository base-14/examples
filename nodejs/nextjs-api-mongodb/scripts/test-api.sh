#!/bin/bash

set -e

BASE_URL="${API_BASE_URL:-http://localhost:3000}"
PASS_COUNT=0
FAIL_COUNT=0

GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m'

log_pass() {
  echo -e "${GREEN}✓ PASS${NC}: $1"
  PASS_COUNT=$((PASS_COUNT + 1))
}

log_fail() {
  echo -e "${RED}✗ FAIL${NC}: $1"
  FAIL_COUNT=$((FAIL_COUNT + 1))
}

log_info() {
  echo -e "${YELLOW}→${NC} $1"
}

test_endpoint() {
  local method=$1
  local endpoint=$2
  local expected_status=$3
  local description=$4
  local data=$5
  local auth_header=$6

  local curl_args=(-s -w "\n%{http_code}" -X "$method")

  if [ -n "$data" ]; then
    curl_args+=(-H "Content-Type: application/json" -d "$data")
  fi

  if [ -n "$auth_header" ]; then
    curl_args+=(-H "Authorization: Bearer $auth_header")
  fi

  local response
  response=$(curl "${curl_args[@]}" "$BASE_URL$endpoint")

  local status_code
  status_code=$(echo "$response" | tail -n1)
  local body
  body=$(echo "$response" | sed '$d')

  if [ "$status_code" = "$expected_status" ]; then
    log_pass "$description (HTTP $status_code)"
    echo "$body"
  else
    log_fail "$description - Expected $expected_status, got $status_code"
    echo "$body"
  fi

  echo ""
}

echo "========================================"
echo "  Next.js API MongoDB - API Tests"
echo "========================================"
echo ""
echo "Base URL: $BASE_URL"
echo ""

echo "----------------------------------------"
echo "1. Health Check"
echo "----------------------------------------"
test_endpoint "GET" "/api/health" "200" "Health check returns 200"

echo "----------------------------------------"
echo "2. User Registration"
echo "----------------------------------------"

RANDOM_SUFFIX=$RANDOM
TEST_EMAIL="testuser${RANDOM_SUFFIX}@example.com"
TEST_USERNAME="testuser${RANDOM_SUFFIX}"
TEST_PASSWORD='Password123!'

log_info "Registering new user: $TEST_EMAIL"

REGISTER_RESPONSE=$(curl -s -X POST "$BASE_URL/api/auth/register" \
  -H "Content-Type: application/json" \
  -d "{\"email\": \"$TEST_EMAIL\", \"username\": \"$TEST_USERNAME\", \"password\": \"$TEST_PASSWORD\"}")

if echo "$REGISTER_RESPONSE" | grep -q '"success":true'; then
  log_pass "User registration successful"
  TOKEN=$(echo "$REGISTER_RESPONSE" | grep -o '"token":"[^"]*"' | cut -d'"' -f4)
  USER_ID=$(echo "$REGISTER_RESPONSE" | grep -o '"id":"[^"]*"' | cut -d'"' -f4)
  log_info "Token received: ${TOKEN:0:20}..."
else
  log_fail "User registration failed"
  echo "$REGISTER_RESPONSE"
  TOKEN=""
fi

echo ""

echo "----------------------------------------"
echo "3. User Registration - Validation"
echo "----------------------------------------"
test_endpoint "POST" "/api/auth/register" "400" "Invalid email rejected" \
  '{"email": "invalid-email", "username": "test", "password": "password123"}'

echo "----------------------------------------"
echo "4. User Registration - Duplicate"
echo "----------------------------------------"
test_endpoint "POST" "/api/auth/register" "409" "Duplicate email rejected" \
  "{\"email\": \"$TEST_EMAIL\", \"username\": \"another\", \"password\": \"Password123!\"}"

echo "----------------------------------------"
echo "5. User Login"
echo "----------------------------------------"
LOGIN_RESPONSE=$(curl -s -X POST "$BASE_URL/api/auth/login" \
  -H "Content-Type: application/json" \
  -d "{\"email\": \"$TEST_EMAIL\", \"password\": \"$TEST_PASSWORD\"}")

if echo "$LOGIN_RESPONSE" | grep -q '"success":true'; then
  log_pass "User login successful"
  TOKEN=$(echo "$LOGIN_RESPONSE" | grep -o '"token":"[^"]*"' | cut -d'"' -f4)
else
  log_fail "User login failed"
  echo "$LOGIN_RESPONSE"
fi

echo ""

echo "----------------------------------------"
echo "6. User Login - Invalid Credentials"
echo "----------------------------------------"
test_endpoint "POST" "/api/auth/login" "401" "Invalid password rejected" \
  "{\"email\": \"$TEST_EMAIL\", \"password\": \"wrongpassword\"}"

echo "----------------------------------------"
echo "7. Get Current User (Authenticated)"
echo "----------------------------------------"
if [ -n "$TOKEN" ]; then
  test_endpoint "GET" "/api/user" "200" "Get current user with valid token" "" "$TOKEN"
else
  log_fail "Skipping - no token available"
fi

echo "----------------------------------------"
echo "8. Get Current User (Unauthenticated)"
echo "----------------------------------------"
test_endpoint "GET" "/api/user" "401" "Get user without token returns 401"

echo "----------------------------------------"
echo "9. Create Article"
echo "----------------------------------------"
if [ -n "$TOKEN" ]; then
  ARTICLE_RESPONSE=$(curl -s -X POST "$BASE_URL/api/articles" \
    -H "Content-Type: application/json" \
    -H "Authorization: Bearer $TOKEN" \
    -d '{"title": "Test Article", "description": "A test article", "body": "This is the body of the test article.", "tags": ["test", "api"]}')

  if echo "$ARTICLE_RESPONSE" | grep -q '"success":true'; then
    log_pass "Article creation successful"
    ARTICLE_SLUG=$(echo "$ARTICLE_RESPONSE" | grep -o '"slug":"[^"]*"' | cut -d'"' -f4)
    ARTICLE_ID=$(echo "$ARTICLE_RESPONSE" | grep -o '"id":"[^"]*"' | cut -d'"' -f4)
    log_info "Article slug: $ARTICLE_SLUG"
  else
    log_fail "Article creation failed"
    echo "$ARTICLE_RESPONSE"
    ARTICLE_SLUG=""
  fi
else
  log_fail "Skipping - no token available"
  ARTICLE_SLUG=""
fi

echo ""

echo "----------------------------------------"
echo "10. List Articles"
echo "----------------------------------------"
test_endpoint "GET" "/api/articles?page=1&limit=10" "200" "List articles returns 200"

echo "----------------------------------------"
echo "11. Get Single Article"
echo "----------------------------------------"
if [ -n "$ARTICLE_SLUG" ]; then
  test_endpoint "GET" "/api/articles/$ARTICLE_SLUG" "200" "Get single article by slug"
else
  log_fail "Skipping - no article slug available"
fi

echo "----------------------------------------"
echo "12. Update Article"
echo "----------------------------------------"
if [ -n "$ARTICLE_SLUG" ] && [ -n "$TOKEN" ]; then
  UPDATE_RESPONSE=$(curl -s -X PUT "$BASE_URL/api/articles/$ARTICLE_SLUG" \
    -H "Content-Type: application/json" \
    -H "Authorization: Bearer $TOKEN" \
    -d '{"title": "Updated Test Article", "description": "Updated description"}')

  if echo "$UPDATE_RESPONSE" | grep -q '"success":true'; then
    log_pass "Update article (HTTP 200)"
    ARTICLE_SLUG=$(echo "$UPDATE_RESPONSE" | grep -o '"slug":"[^"]*"' | cut -d'"' -f4)
    log_info "Updated article slug: $ARTICLE_SLUG"
  else
    log_fail "Update article failed"
    echo "$UPDATE_RESPONSE"
  fi
else
  log_fail "Skipping - no article slug or token available"
fi

echo "----------------------------------------"
echo "13. Favorite Article"
echo "----------------------------------------"
if [ -n "$ARTICLE_SLUG" ] && [ -n "$TOKEN" ]; then
  test_endpoint "POST" "/api/articles/$ARTICLE_SLUG/favorite" "200" "Favorite article" "" "$TOKEN"
else
  log_fail "Skipping - no article slug or token available"
fi

echo "----------------------------------------"
echo "14. Unfavorite Article"
echo "----------------------------------------"
if [ -n "$ARTICLE_SLUG" ] && [ -n "$TOKEN" ]; then
  test_endpoint "DELETE" "/api/articles/$ARTICLE_SLUG/favorite" "200" "Unfavorite article" "" "$TOKEN"
else
  log_fail "Skipping - no article slug or token available"
fi

echo "----------------------------------------"
echo "15. Create Comment"
echo "----------------------------------------"
if [ -n "$ARTICLE_SLUG" ] && [ -n "$TOKEN" ]; then
  COMMENT_RESPONSE=$(curl -s -X POST "$BASE_URL/api/articles/$ARTICLE_SLUG/comments" \
    -H "Content-Type: application/json" \
    -H "Authorization: Bearer $TOKEN" \
    -d '{"body": "This is a test comment!"}')

  if echo "$COMMENT_RESPONSE" | grep -q '"success":true'; then
    log_pass "Create comment successful"
    COMMENT_ID=$(echo "$COMMENT_RESPONSE" | grep -o '"id":"[^"]*"' | head -1 | cut -d'"' -f4)
    log_info "Comment ID: $COMMENT_ID"
  else
    log_fail "Create comment failed"
    echo "$COMMENT_RESPONSE"
    COMMENT_ID=""
  fi
else
  log_fail "Skipping - no article slug or token available"
  COMMENT_ID=""
fi

echo ""

echo "----------------------------------------"
echo "16. List Comments"
echo "----------------------------------------"
if [ -n "$ARTICLE_SLUG" ]; then
  test_endpoint "GET" "/api/articles/$ARTICLE_SLUG/comments" "200" "List comments for article"
else
  log_fail "Skipping - no article slug available"
fi

echo "----------------------------------------"
echo "17. Delete Comment"
echo "----------------------------------------"
if [ -n "$ARTICLE_SLUG" ] && [ -n "$COMMENT_ID" ] && [ -n "$TOKEN" ]; then
  test_endpoint "DELETE" "/api/articles/$ARTICLE_SLUG/comments/$COMMENT_ID" "200" "Delete comment" "" "$TOKEN"
else
  log_fail "Skipping - no article slug, comment ID, or token available"
fi

echo "----------------------------------------"
echo "18. Delete Article"
echo "----------------------------------------"
if [ -n "$ARTICLE_SLUG" ] && [ -n "$TOKEN" ]; then
  test_endpoint "DELETE" "/api/articles/$ARTICLE_SLUG" "200" "Delete article" "" "$TOKEN"
else
  log_fail "Skipping - no article slug or token available"
fi

echo "----------------------------------------"
echo "19. Logout"
echo "----------------------------------------"
test_endpoint "POST" "/api/auth/logout" "200" "Logout returns 200"

echo "----------------------------------------"
echo "20. Tags Endpoint"
echo "----------------------------------------"
test_endpoint "GET" "/api/tags" "200" "Get all tags"

echo "----------------------------------------"
echo "21. Prometheus Metrics"
echo "----------------------------------------"
METRICS_RESPONSE=$(curl -s "$BASE_URL/api/metrics")
if echo "$METRICS_RESPONSE" | grep -q "http_server_duration"; then
  log_pass "Prometheus metrics endpoint returns metrics"
else
  log_fail "Prometheus metrics endpoint failed"
  echo "$METRICS_RESPONSE" | head -5
fi

echo "========================================"
echo "  Test Results"
echo "========================================"
echo -e "Passed: ${GREEN}$PASS_COUNT${NC}"
echo -e "Failed: ${RED}$FAIL_COUNT${NC}"
echo ""

if [ $FAIL_COUNT -gt 0 ]; then
  echo -e "${RED}Some tests failed!${NC}"
  exit 1
else
  echo -e "${GREEN}All tests passed!${NC}"
  exit 0
fi
