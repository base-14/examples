#!/bin/bash
set -e

BASE_URL="${API_URL:-http://localhost:8000}"
PASS=0
FAIL=0

green() { echo -e "\033[32m$1\033[0m"; }
red() { echo -e "\033[31m$1\033[0m"; }
blue() { echo -e "\033[34m$1\033[0m"; }
yellow() { echo -e "\033[33m$1\033[0m"; }

blue "============================================"
blue "Scout/OpenTelemetry Verification"
blue "Express 5 + PostgreSQL"
blue "============================================"
echo ""

# Check if OTel collector is running
blue "=== Step 1: OTel Collector Health ==="
COLLECTOR_HEALTH=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:13133/ 2>/dev/null || echo "000")
if [ "$COLLECTOR_HEALTH" = "200" ]; then
  green "✓ OTel Collector is healthy"
  ((PASS++))
else
  red "✗ OTel Collector not responding (HTTP $COLLECTOR_HEALTH)"
  ((FAIL++))
  echo "  Make sure 'docker compose up otel-collector' is running"
fi
echo ""

# Check API health
blue "=== Step 2: API Health ==="
API_HEALTH=$(curl -s -o /dev/null -w "%{http_code}" "$BASE_URL/api/health" 2>/dev/null || echo "000")
if [ "$API_HEALTH" = "200" ]; then
  green "✓ API is healthy"
  ((PASS++))
else
  red "✗ API not responding (HTTP $API_HEALTH)"
  ((FAIL++))
fi
echo ""

# Generate some traffic with trace context
blue "=== Step 3: Generating Traced Requests ==="

TIMESTAMP=$(date +%s)
TEST_EMAIL="scout-test-${TIMESTAMP}@example.com"
TEST_PASSWORD="ScoutTest123!"

# Register user
echo "Registering test user..."
REGISTER_RESPONSE=$(curl -s -X POST -H "Content-Type: application/json" \
  -d "{\"email\":\"$TEST_EMAIL\",\"password\":\"$TEST_PASSWORD\",\"name\":\"Scout Test User\"}" \
  "$BASE_URL/api/register")

if echo "$REGISTER_RESPONSE" | jq -e '.token' > /dev/null 2>&1; then
  green "✓ User registered (creates user.register span)"
  ((PASS++))
  TOKEN=$(echo "$REGISTER_RESPONSE" | jq -r '.token')
else
  red "✗ Failed to register user"
  ((FAIL++))
  echo "$REGISTER_RESPONSE"
  TOKEN=""
fi

# Login
echo "Logging in..."
LOGIN_RESPONSE=$(curl -s -X POST -H "Content-Type: application/json" \
  -d "{\"email\":\"$TEST_EMAIL\",\"password\":\"$TEST_PASSWORD\"}" \
  "$BASE_URL/api/login")

if echo "$LOGIN_RESPONSE" | jq -e '.token' > /dev/null 2>&1; then
  green "✓ User logged in (creates user.login span)"
  ((PASS++))
else
  red "✗ Failed to login"
  ((FAIL++))
fi

# Create article (triggers background job)
if [ -n "$TOKEN" ]; then
  echo "Creating article (triggers article-created job)..."
  CREATE_RESPONSE=$(curl -s -X POST -H "Content-Type: application/json" \
    -H "Authorization: Bearer $TOKEN" \
    -d '{"title":"Scout Verification Article","description":"Testing OTel","body":"This article verifies trace context propagation."}' \
    "$BASE_URL/api/articles")

  if echo "$CREATE_RESPONSE" | jq -e '.slug // .article.slug' > /dev/null 2>&1; then
    green "✓ Article created (creates article.create span + job.enqueue span)"
    ((PASS++))
    ARTICLE_SLUG=$(echo "$CREATE_RESPONSE" | jq -r '.slug // .article.slug')

    # Favorite article (triggers another background job)
    echo "Favoriting article (triggers article-favorited job)..."
    FAV_RESPONSE=$(curl -s -X POST \
      -H "Authorization: Bearer $TOKEN" \
      "$BASE_URL/api/articles/$ARTICLE_SLUG/favorite")

    if echo "$FAV_RESPONSE" | jq -e '.favorited // .article.favorited' > /dev/null 2>&1; then
      green "✓ Article favorited (creates article.favorite span + job.enqueue span)"
      ((PASS++))
    else
      red "✗ Failed to favorite article"
      ((FAIL++))
    fi

    # Cleanup
    curl -s -X DELETE -H "Authorization: Bearer $TOKEN" "$BASE_URL/api/articles/$ARTICLE_SLUG" > /dev/null
  else
    red "✗ Failed to create article"
    ((FAIL++))
    echo "$CREATE_RESPONSE"
  fi
fi
echo ""

# Wait for trace export
blue "=== Step 4: Waiting for Trace Export ==="
echo "Waiting 10s for batch export to collector..."
sleep 10

# Check collector logs for spans
blue "=== Step 5: Checking Collector Logs ==="

COLLECTOR_LOGS=$(docker compose logs otel-collector 2>&1)

if echo "$COLLECTOR_LOGS" | grep -q "service.name"; then
  green "✓ service.name resource attribute found in collector logs"
  ((PASS++))
else
  red "✗ service.name not found in collector logs"
  ((FAIL++))
fi

if echo "$COLLECTOR_LOGS" | grep -qi "spans"; then
  green "✓ Trace spans found in collector logs"
  ((PASS++))
else
  red "✗ No trace spans found in collector logs"
  ((FAIL++))
fi
echo ""

# OTel metrics are exported via OTLP to collector (no /metrics endpoint)
echo ""

# Summary
echo ""
blue "============================================"
blue "Verification Summary"
blue "============================================"
green "Passed: $PASS"
if [ $FAIL -gt 0 ]; then
  red "Failed: $FAIL"
else
  echo "Failed: $FAIL"
fi
echo ""

echo "Expected telemetry in Scout:"
echo "  Service: express5-postgres-app"
echo "  Traces:"
echo "    - HTTP spans: POST /api/register, POST /api/login"
echo "    - HTTP spans: POST /api/articles, POST /api/articles/:slug/favorite"
echo "    - PostgreSQL query spans (auto-instrumented)"
echo "    - Background job spans: article-created, article-favorited"
echo ""

if [ $FAIL -eq 0 ]; then
  green "All automated checks passed!"
else
  red "Some checks failed. Review the output above."
  exit 1
fi
