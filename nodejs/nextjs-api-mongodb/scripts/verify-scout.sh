#!/bin/bash

set -e

GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m'

BASE_URL="${API_BASE_URL:-http://localhost:3000}"
OTEL_ENDPOINT="${OTEL_EXPORTER_OTLP_ENDPOINT:-http://localhost:4318}"

echo "========================================"
echo "  Scout/OpenTelemetry Verification"
echo "========================================"
echo ""

echo -e "${YELLOW}1. Checking OTel Collector Health${NC}"
echo "----------------------------------------"

COLLECTOR_HEALTH=$(curl -s -o /dev/null -w "%{http_code}" "http://localhost:13133/" 2>/dev/null || echo "000")

if [ "$COLLECTOR_HEALTH" = "200" ]; then
  echo -e "${GREEN}✓${NC} OTel Collector is healthy"
else
  echo -e "${RED}✗${NC} OTel Collector not responding (HTTP $COLLECTOR_HEALTH)"
  echo "  Make sure the collector is running: docker compose up otel-collector"
fi
echo ""

echo -e "${YELLOW}2. Generating Test Traces${NC}"
echo "----------------------------------------"

echo "Making API requests to generate traces..."

curl -s "$BASE_URL/api/health" > /dev/null && echo -e "${GREEN}✓${NC} Health check request sent"

RANDOM_SUFFIX=$RANDOM
TEST_EMAIL="scout-test-${RANDOM_SUFFIX}@example.com"
TEST_USERNAME="scouttest${RANDOM_SUFFIX}"

REGISTER_RESPONSE=$(curl -s -X POST "$BASE_URL/api/auth/register" \
  -H "Content-Type: application/json" \
  -d "{\"email\": \"$TEST_EMAIL\", \"username\": \"$TEST_USERNAME\", \"password\": \"Password123!\"}")

if echo "$REGISTER_RESPONSE" | grep -q '"success":true'; then
  echo -e "${GREEN}✓${NC} Registration request sent"
  TOKEN=$(echo "$REGISTER_RESPONSE" | grep -o '"token":"[^"]*"' | cut -d'"' -f4)
else
  echo -e "${RED}✗${NC} Registration failed"
  TOKEN=""
fi

if [ -n "$TOKEN" ]; then
  curl -s -X POST "$BASE_URL/api/articles" \
    -H "Content-Type: application/json" \
    -H "Authorization: Bearer $TOKEN" \
    -d '{"title": "Scout Test Article", "description": "Testing traces", "body": "Body content", "tags": ["test"]}' > /dev/null
  echo -e "${GREEN}✓${NC} Article creation request sent"

  curl -s "$BASE_URL/api/articles" > /dev/null
  echo -e "${GREEN}✓${NC} Article list request sent"

  curl -s -X POST "$BASE_URL/api/jobs" \
    -H "Content-Type: application/json" \
    -H "Authorization: Bearer $TOKEN" \
    -d '{"type": "email", "data": {"to": "test@example.com", "subject": "Scout Test", "body": "Testing"}}' > /dev/null
  echo -e "${GREEN}✓${NC} Background job request sent"
fi

echo ""

echo -e "${YELLOW}3. Expected Trace Spans${NC}"
echo "----------------------------------------"
echo "After requests, you should see these spans in Scout/Jaeger:"
echo ""
echo "  HTTP Spans (auto-instrumented):"
echo "    - GET /api/health"
echo "    - POST /api/auth/register"
echo "    - POST /api/articles"
echo "    - GET /api/articles"
echo "    - POST /api/jobs"
echo ""
echo "  Custom Application Spans:"
echo "    - health.check"
echo "    - auth.register"
echo "    - articles.create"
echo "    - articles.list"
echo "    - jobs.trigger"
echo ""
echo "  Database Spans (auto-instrumented):"
echo "    - mongoose.User.findOne"
echo "    - mongoose.User.create"
echo "    - mongoose.Article.create"
echo "    - mongoose.Article.find"
echo ""
echo "  Background Job Spans (if worker running):"
echo "    - job.email.send"
echo "    - job.analytics.track"
echo ""

echo -e "${YELLOW}4. Expected Attributes${NC}"
echo "----------------------------------------"
echo "Spans should include these attributes:"
echo ""
echo "  HTTP spans:"
echo "    - http.method"
echo "    - http.route"
echo "    - http.status_code"
echo "    - http.url"
echo ""
echo "  Custom spans:"
echo "    - user.id (after auth)"
echo "    - article.id"
echo "    - article.slug"
echo "    - job.id"
echo "    - job.queue"
echo ""

echo -e "${YELLOW}5. Metrics Verification${NC}"
echo "----------------------------------------"
echo "Expected metrics being exported:"
echo ""
echo "  - http.server.requests (counter)"
echo "  - http.server.duration (histogram)"
echo "  - http.server.errors (counter)"
echo "  - auth.operations (counter)"
echo "  - articles.operations (counter)"
echo "  - favorites.operations (counter)"
echo "  - db.operation.duration (histogram)"
echo ""

echo -e "${YELLOW}6. Log Correlation${NC}"
echo "----------------------------------------"
echo "Logs should include trace context for correlation:"
echo ""
echo '  {"level":"info","traceId":"abc123...","spanId":"def456...","msg":"..."}'
echo ""
echo "This allows linking logs to traces in your observability platform."
echo ""

echo "========================================"
echo "  Verification Complete"
echo "========================================"
echo ""
echo "Next steps:"
echo "  1. Open Scout/Jaeger UI to view traces"
echo "  2. Verify span hierarchy matches expected patterns"
echo "  3. Check that job spans link back to originating requests"
echo "  4. Confirm metrics appear in your metrics backend"
echo ""
