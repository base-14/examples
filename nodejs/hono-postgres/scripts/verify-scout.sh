#!/bin/bash
set -e

BASE_URL="${API_URL:-http://localhost:3000}"
PASS=0
FAIL=0

green() { echo -e "\033[32m$1\033[0m"; }
red() { echo -e "\033[31m$1\033[0m"; }
blue() { echo -e "\033[34m$1\033[0m"; }
yellow() { echo -e "\033[33m$1\033[0m"; }

blue "============================================"
blue "Scout/OpenTelemetry Verification"
blue "============================================"
echo ""

# Check if OTel collector is running
blue "=== Step 1: OTel Collector Health ==="
COLLECTOR_HEALTH=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:13133/health 2>/dev/null || echo "000")
if [ "$COLLECTOR_HEALTH" = "200" ]; then
  green "✓ OTel Collector is healthy"
  ((PASS++))
else
  red "✗ OTel Collector not responding (HTTP $COLLECTOR_HEALTH)"
  ((FAIL++))
  echo "  Make sure 'docker compose up otel-collector' is running"
fi
echo ""

# Generate some traffic with trace context
blue "=== Step 2: Generating Traced Requests ==="

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

  if echo "$CREATE_RESPONSE" | jq -e '.article.slug' > /dev/null 2>&1; then
    green "✓ Article created (creates article.create span + job.enqueue span)"
    ((PASS++))
    ARTICLE_SLUG=$(echo "$CREATE_RESPONSE" | jq -r '.article.slug')

    # Favorite article (triggers another background job)
    echo "Favoriting article (triggers article-favorited job)..."
    FAV_RESPONSE=$(curl -s -X POST \
      -H "Authorization: Bearer $TOKEN" \
      "$BASE_URL/api/articles/$ARTICLE_SLUG/favorite")

    if echo "$FAV_RESPONSE" | jq -e '.article' > /dev/null 2>&1; then
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

# Verify expected spans
blue "=== Step 3: Expected Spans in Scout ==="
echo ""
yellow "After running this script, verify the following in Scout APM:"
echo ""
echo "1. HTTP Spans:"
echo "   - POST /api/register"
echo "   - POST /api/login"
echo "   - POST /api/articles"
echo "   - POST /api/articles/:slug/favorite"
echo ""
echo "2. Custom Service Spans:"
echo "   - user.register (with user.email_domain attribute)"
echo "   - user.login (with user.email_domain attribute)"
echo "   - article.create (with article.id, article.slug attributes)"
echo "   - article.favorite (with favorite_added event)"
echo ""
echo "3. Database Spans:"
echo "   - PostgreSQL queries with db.statement attribute"
echo ""
echo "4. Background Job Spans:"
echo "   - job.enqueue.article-created"
echo "   - job.enqueue.article-favorited"
echo "   - job.article-created (in worker service)"
echo "   - job.article-favorited (in worker service)"
echo ""
echo "5. Trace Context Propagation:"
yellow "   CRITICAL: Verify that job spans share the same trace_id as the HTTP request"
echo "   - Click on a POST /api/articles span"
echo "   - Verify linked job.article-created span appears"
echo "   - Both should have the same trace ID"
echo ""

blue "=== Step 4: Metrics Verification ==="
METRICS_RESPONSE=$(curl -s "$BASE_URL/metrics")
if echo "$METRICS_RESPONSE" | grep -q "http_requests_total"; then
  green "✓ Prometheus metrics available at /metrics"
  ((PASS++))

  echo ""
  echo "Sample metrics:"
  echo "$METRICS_RESPONSE" | grep -E "^(http_requests_total|http_request_duration)" | head -5
else
  red "✗ Metrics endpoint not returning expected data"
  ((FAIL++))
fi
echo ""

blue "=== Step 5: Structured Logging ==="
echo ""
echo "Verify logs include trace correlation:"
echo "  docker compose logs app 2>&1 | grep -E 'traceId|spanId' | head -3"
echo ""
echo "Expected log format:"
echo '  {"level":30,"time":...,"traceId":"abc123","spanId":"def456",...}'
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

if [ $FAIL -eq 0 ]; then
  green "All automated checks passed!"
  echo ""
  yellow "Manual verification required:"
  echo "  1. Open Scout APM dashboard"
  echo "  2. Filter by service: hono-postgres-app"
  echo "  3. Verify spans listed above are visible"
  echo "  4. Verify trace context propagation to worker"
else
  red "Some checks failed. Review the output above."
  exit 1
fi
