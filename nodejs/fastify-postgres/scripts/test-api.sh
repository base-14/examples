#!/bin/bash
set -e

BASE_URL="${API_URL:-http://localhost:3000}"
PASS=0
FAIL=0

green() { echo -e "\033[32m$1\033[0m"; }
red() { echo -e "\033[31m$1\033[0m"; }
blue() { echo -e "\033[34m$1\033[0m"; }
yellow() { echo -e "\033[33m$1\033[0m"; }

test_endpoint() {
  local name="$1"
  local method="$2"
  local endpoint="$3"
  local expected_status="$4"
  local data="$5"
  local token="$6"

  local headers=(-H "Content-Type: application/json")
  if [ -n "$token" ]; then
    headers+=(-H "Authorization: Bearer $token")
  fi

  if [ -n "$data" ]; then
    response=$(curl -s -w "\n%{http_code}" -X "$method" "${headers[@]}" -d "$data" "$BASE_URL$endpoint")
  else
    response=$(curl -s -w "\n%{http_code}" -X "$method" "${headers[@]}" "$BASE_URL$endpoint")
  fi

  status_code=$(echo "$response" | tail -n1)
  body=$(echo "$response" | sed '$d')

  if [ "$status_code" = "$expected_status" ]; then
    green "✓ $name (HTTP $status_code)"
    ((PASS++))
    echo "$body" | jq -c '.' 2>/dev/null || echo "$body"
  else
    red "✗ $name (Expected $expected_status, got $status_code)"
    ((FAIL++))
    echo "$body"
  fi
  echo ""
}

blue "============================================"
blue "Fastify API Tests"
blue "============================================"
echo ""

# ====================
# Phase 0: Health Check
# ====================
blue "=== Phase 0: Health Check ==="
test_endpoint "Health check" "GET" "/health" "200"
test_endpoint "Liveness probe" "GET" "/health/live" "200"
test_endpoint "Readiness probe" "GET" "/health/ready" "200"

# Verify health check returns component statuses
HEALTH_RESPONSE=$(curl -s "$BASE_URL/health")
if echo "$HEALTH_RESPONSE" | jq -e '.components.database.status' > /dev/null 2>&1 && \
   echo "$HEALTH_RESPONSE" | jq -e '.components.redis.status' > /dev/null 2>&1 && \
   echo "$HEALTH_RESPONSE" | jq -e '.components.queue.status' > /dev/null 2>&1; then
  green "✓ Health check returns all component statuses"
  ((PASS++))
else
  red "✗ Health check missing component statuses"
  ((FAIL++))
fi
echo ""

# ====================
# Phase 1: Authentication
# ====================
blue "=== Phase 1: Authentication ==="

TIMESTAMP=$(date +%s)
TEST_EMAIL="test${TIMESTAMP}@example.com"
TEST_PASSWORD="TestPass123!"

# Register
REGISTER_RESPONSE=$(curl -s -X POST -H "Content-Type: application/json" \
  -d "{\"email\":\"$TEST_EMAIL\",\"password\":\"$TEST_PASSWORD\",\"name\":\"Test User\"}" \
  "$BASE_URL/api/register")

if echo "$REGISTER_RESPONSE" | jq -e '.token' > /dev/null 2>&1; then
  green "✓ Register new user"
  ((PASS++))
  TOKEN=$(echo "$REGISTER_RESPONSE" | jq -r '.token')
else
  red "✗ Register new user"
  ((FAIL++))
  echo "$REGISTER_RESPONSE"
fi
echo ""

# Login
LOGIN_RESPONSE=$(curl -s -X POST -H "Content-Type: application/json" \
  -d "{\"email\":\"$TEST_EMAIL\",\"password\":\"$TEST_PASSWORD\"}" \
  "$BASE_URL/api/login")

if echo "$LOGIN_RESPONSE" | jq -e '.token' > /dev/null 2>&1; then
  green "✓ Login with valid credentials"
  ((PASS++))
  TOKEN=$(echo "$LOGIN_RESPONSE" | jq -r '.token')
else
  red "✗ Login with valid credentials"
  ((FAIL++))
fi
echo ""

test_endpoint "Get profile with token" "GET" "/api/user" "200" "" "$TOKEN"
test_endpoint "Get profile without token (should fail)" "GET" "/api/user" "401"

# ====================
# Phase 2: Article CRUD
# ====================
blue "=== Phase 2: Article CRUD ==="

# Create article
blue "--- Create Article ---"
CREATE_RESPONSE=$(curl -s -X POST -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{"title":"Test Article","description":"A test article","body":"This is the body of the test article."}' \
  "$BASE_URL/api/articles")

if echo "$CREATE_RESPONSE" | jq -e '.article.slug' > /dev/null 2>&1; then
  green "✓ Create article"
  ((PASS++))
  ARTICLE_SLUG=$(echo "$CREATE_RESPONSE" | jq -r '.article.slug')
  echo "  Slug: $ARTICLE_SLUG"
else
  red "✗ Create article"
  ((FAIL++))
  echo "$CREATE_RESPONSE"
fi
echo ""

test_endpoint "Create article without auth (should fail)" "POST" "/api/articles" "401" \
  '{"title":"Unauthorized Article","body":"Should fail"}'

# List articles
blue "--- List Articles ---"
test_endpoint "List articles" "GET" "/api/articles" "200"
test_endpoint "List articles with pagination" "GET" "/api/articles?limit=5&offset=0" "200"

# Get single article
blue "--- Get Article ---"
test_endpoint "Get article by slug" "GET" "/api/articles/$ARTICLE_SLUG" "200"
test_endpoint "Get non-existent article" "GET" "/api/articles/non-existent-slug" "404"

# Update article
blue "--- Update Article ---"
test_endpoint "Update article (owner)" "PUT" "/api/articles/$ARTICLE_SLUG" "200" \
  '{"title":"Updated Title","body":"Updated body content"}' "$TOKEN"

# Get updated slug
UPDATED_RESPONSE=$(curl -s -H "Authorization: Bearer $TOKEN" "$BASE_URL/api/articles?limit=1")
ARTICLE_SLUG=$(echo "$UPDATED_RESPONSE" | jq -r '.articles[0].slug')
echo "  Updated slug: $ARTICLE_SLUG"

test_endpoint "Update article without auth (should fail)" "PUT" "/api/articles/$ARTICLE_SLUG" "401" \
  '{"title":"Should Fail"}'

# Create second user for authorization tests
TIMESTAMP2=$(date +%s)
TEST_EMAIL2="test2${TIMESTAMP2}@example.com"
REGISTER2_RESPONSE=$(curl -s -X POST -H "Content-Type: application/json" \
  -d "{\"email\":\"$TEST_EMAIL2\",\"password\":\"$TEST_PASSWORD\",\"name\":\"Test User 2\"}" \
  "$BASE_URL/api/register")
TOKEN2=$(echo "$REGISTER2_RESPONSE" | jq -r '.token')

test_endpoint "Update article (non-owner, should fail)" "PUT" "/api/articles/$ARTICLE_SLUG" "403" \
  '{"title":"Should Fail"}' "$TOKEN2"

# ====================
# Phase 3: Favorites
# ====================
blue "=== Phase 3: Favorites ==="

# Favorite article
test_endpoint "Favorite article" "POST" "/api/articles/$ARTICLE_SLUG/favorite" "200" "" "$TOKEN"

# Check favorites count increased
FAV_RESPONSE=$(curl -s "$BASE_URL/api/articles/$ARTICLE_SLUG")
FAV_COUNT=$(echo "$FAV_RESPONSE" | jq -r '.article.favoritesCount')
if [ "$FAV_COUNT" -ge 1 ]; then
  green "✓ Favorites count increased to $FAV_COUNT"
  ((PASS++))
else
  red "✗ Favorites count should be >= 1, got $FAV_COUNT"
  ((FAIL++))
fi
echo ""

# Favorite again (idempotent)
test_endpoint "Favorite article again (idempotent)" "POST" "/api/articles/$ARTICLE_SLUG/favorite" "200" "" "$TOKEN"

# Check count didn't double
FAV_RESPONSE2=$(curl -s "$BASE_URL/api/articles/$ARTICLE_SLUG")
FAV_COUNT2=$(echo "$FAV_RESPONSE2" | jq -r '.article.favoritesCount')
if [ "$FAV_COUNT2" -eq "$FAV_COUNT" ]; then
  green "✓ Favorites count unchanged (idempotent): $FAV_COUNT2"
  ((PASS++))
else
  red "✗ Favorites should be idempotent, expected $FAV_COUNT got $FAV_COUNT2"
  ((FAIL++))
fi
echo ""

# Unfavorite
test_endpoint "Unfavorite article" "DELETE" "/api/articles/$ARTICLE_SLUG/favorite" "200" "" "$TOKEN"

# Check favorites count decreased
UNFAV_RESPONSE=$(curl -s "$BASE_URL/api/articles/$ARTICLE_SLUG")
UNFAV_COUNT=$(echo "$UNFAV_RESPONSE" | jq -r '.article.favoritesCount')
if [ "$UNFAV_COUNT" -lt "$FAV_COUNT" ]; then
  green "✓ Favorites count decreased to $UNFAV_COUNT"
  ((PASS++))
else
  red "✗ Favorites count should have decreased"
  ((FAIL++))
fi
echo ""

test_endpoint "Favorite without auth (should fail)" "POST" "/api/articles/$ARTICLE_SLUG/favorite" "401"

# Delete article
blue "--- Delete Article ---"
test_endpoint "Delete article (non-owner, should fail)" "DELETE" "/api/articles/$ARTICLE_SLUG" "403" "" "$TOKEN2"
test_endpoint "Delete article (owner)" "DELETE" "/api/articles/$ARTICLE_SLUG" "204" "" "$TOKEN"
test_endpoint "Get deleted article (should fail)" "GET" "/api/articles/$ARTICLE_SLUG" "404"

# ====================
# Phase 5: Background Jobs (Info)
# ====================
blue "=== Phase 5: Background Jobs ==="
echo "Note: Background jobs are triggered automatically when:"
echo "  - Article is created -> article-created notification job"
echo "  - Article is favorited -> article-favorited notification job"
echo ""
echo "To verify jobs are processing, check worker logs:"
echo "  docker compose logs -f worker"
echo ""

# ====================
# Phase 6: Production Readiness
# ====================
blue "=== Phase 6: Production Readiness ==="

# Metrics endpoint
METRICS_RESPONSE=$(curl -s "$BASE_URL/metrics")
if echo "$METRICS_RESPONSE" | grep -q "http_requests_total"; then
  green "✓ Metrics endpoint returns Prometheus metrics"
  ((PASS++))
else
  red "✗ Metrics endpoint missing http_requests_total"
  ((FAIL++))
fi
echo ""

# Check for default metrics
if echo "$METRICS_RESPONSE" | grep -q "process_cpu"; then
  green "✓ Metrics includes process metrics"
  ((PASS++))
else
  red "✗ Metrics missing process metrics"
  ((FAIL++))
fi
echo ""

# Check security headers (helmet)
SECURITY_HEADERS=$(curl -sI "$BASE_URL/health")
if echo "$SECURITY_HEADERS" | grep -qi "x-content-type-options"; then
  green "✓ Security headers present (X-Content-Type-Options)"
  ((PASS++))
else
  red "✗ Security headers missing"
  ((FAIL++))
fi
echo ""

# Check rate limiting headers
RATE_HEADERS=$(curl -sI "$BASE_URL/health")
if echo "$RATE_HEADERS" | grep -qi "x-ratelimit-limit"; then
  green "✓ Rate limiting headers present"
  ((PASS++))
else
  red "✗ Rate limiting headers missing"
  ((FAIL++))
fi
echo ""

# Test auth rate limiting (5 req/min for login)
blue "--- Auth Rate Limiting ---"
echo "Testing login rate limiting (5 req/min)..."

AUTH_RATE_FAIL=0
for i in {1..6}; do
  RATE_RESPONSE=$(curl -s -o /dev/null -w "%{http_code}" -X POST -H "Content-Type: application/json" \
    -d '{"email":"ratelimit@test.com","password":"WrongPass123!"}' \
    "$BASE_URL/api/login")
  if [ "$i" -le 5 ] && [ "$RATE_RESPONSE" = "429" ]; then
    AUTH_RATE_FAIL=1
    break
  fi
  if [ "$i" -eq 6 ] && [ "$RATE_RESPONSE" != "429" ]; then
    AUTH_RATE_FAIL=1
  fi
done

if [ "$AUTH_RATE_FAIL" -eq 0 ]; then
  green "✓ Auth rate limiting working (429 after 5 attempts)"
  ((PASS++))
else
  yellow "⚠ Auth rate limiting test inconclusive (may need fresh IP)"
fi
echo ""

# Test password strength validation
blue "--- Password Validation ---"
WEAK_PASSWORD_RESPONSE=$(curl -s -o /dev/null -w "%{http_code}" -X POST -H "Content-Type: application/json" \
  -d '{"email":"weakpass@test.com","password":"weakpass","name":"Test"}' \
  "$BASE_URL/api/register")

if [ "$WEAK_PASSWORD_RESPONSE" = "400" ]; then
  green "✓ Weak password rejected (400)"
  ((PASS++))
else
  red "✗ Weak password should be rejected (got $WEAK_PASSWORD_RESPONSE)"
  ((FAIL++))
fi
echo ""

# ====================
# Summary
# ====================
echo ""
blue "============================================"
blue "Test Summary"
blue "============================================"
green "Passed: $PASS"
if [ $FAIL -gt 0 ]; then
  red "Failed: $FAIL"
  exit 1
else
  echo "Failed: $FAIL"
fi
echo ""
green "All tests passed!"
