#!/bin/bash

GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m'

BASE_URL="${API_BASE_URL:-http://localhost:3000}"
PASS_COUNT=0
FAIL_COUNT=0

pass() {
  echo -e "${GREEN}✓${NC} $1"
  PASS_COUNT=$((PASS_COUNT + 1))
}

fail() {
  echo -e "${RED}✗${NC} $1"
  FAIL_COUNT=$((FAIL_COUNT + 1))
}

echo "========================================"
echo "  Scout/OpenTelemetry Verification"
echo "  Ruby 3.0 + Rails 6.1 + MySQL"
echo "========================================"
echo ""

echo -e "${YELLOW}1. Checking OTel Collector Health${NC}"
echo "----------------------------------------"

COLLECTOR_HEALTH=$(curl -s -o /dev/null -w "%{http_code}" "http://localhost:13133/" 2>/dev/null || echo "000")

if [ "$COLLECTOR_HEALTH" = "200" ]; then
  pass "OTel Collector is healthy"
else
  fail "OTel Collector not responding (HTTP $COLLECTOR_HEALTH)"
  echo "  Make sure the collector is running: docker compose up otel-collector"
fi
echo ""

echo -e "${YELLOW}2. Checking API Health${NC}"
echo "----------------------------------------"

API_HEALTH=$(curl -s -o /dev/null -w "%{http_code}" "$BASE_URL/api/health" 2>/dev/null || echo "000")

if [ "$API_HEALTH" = "200" ]; then
  pass "Rails health check passed (GET /api/health)"
else
  fail "Rails not responding (HTTP $API_HEALTH)"
fi
echo ""

echo -e "${YELLOW}3. Generating Test Traces${NC}"
echo "----------------------------------------"

HEALTH_STATUS=$(curl -s -o /dev/null -w "%{http_code}" "$BASE_URL/api/health" 2>/dev/null || echo "000")
if [ "$HEALTH_STATUS" = "200" ]; then
  pass "Health check request sent"
else
  fail "Health check request failed (HTTP $HEALTH_STATUS)"
fi

TIMESTAMP=$(date +%s)

CREATE_STATUS=$(curl -s -o /dev/null -w "%{http_code}" -X POST "$BASE_URL/api/items" \
    -H "Content-Type: application/json" \
    -d "{\"item\":{\"title\":\"Scout Test ${TIMESTAMP}\",\"description\":\"Verification item\"}}" 2>/dev/null || echo "000")
if [ "$CREATE_STATUS" = "201" ]; then
  pass "Create item request sent (HTTP $CREATE_STATUS)"
else
  fail "Create item request failed (HTTP $CREATE_STATUS)"
fi

SHOW_STATUS=$(curl -s -o /dev/null -w "%{http_code}" "$BASE_URL/api/items/1" 2>/dev/null || echo "000")
if [ "$SHOW_STATUS" = "200" ] || [ "$SHOW_STATUS" = "404" ]; then
  pass "Get item request sent (HTTP $SHOW_STATUS)"
else
  fail "Get item request failed (HTTP $SHOW_STATUS)"
fi

NOTFOUND_STATUS=$(curl -s -o /dev/null -w "%{http_code}" "$BASE_URL/api/items/99999" 2>/dev/null || echo "000")
if [ "$NOTFOUND_STATUS" = "404" ]; then
  pass "Not-found request sent (HTTP $NOTFOUND_STATUS)"
else
  fail "Not-found request failed (HTTP $NOTFOUND_STATUS)"
fi
echo ""

echo -e "${YELLOW}4. Waiting for Trace Export${NC}"
echo "----------------------------------------"
echo "Waiting 12s for batch export to collector..."
sleep 12

echo ""
echo -e "${YELLOW}5. Checking Collector Logs${NC}"
echo "----------------------------------------"

COLLECTOR_LOGS=$(docker compose logs --since 60s otel-collector 2>&1)

if echo "$COLLECTOR_LOGS" | grep -q "service.name"; then
  pass "service.name resource attribute found in collector logs"
else
  fail "service.name not found in collector logs"
fi

if echo "$COLLECTOR_LOGS" | grep -qi "spans"; then
  pass "Trace spans found in collector logs"
else
  fail "No trace spans found in collector logs"
fi

echo ""
echo "========================================"
echo "  Verification Results"
echo "========================================"
echo -e "Passed: ${GREEN}$PASS_COUNT${NC}"
echo -e "Failed: ${RED}$FAIL_COUNT${NC}"
echo ""

echo "Expected telemetry in Scout:"
echo "  Service: ruby30-rails61-mysql-otel"
echo "  Traces:"
echo "    - HTTP spans: POST /api/items, GET /api/items/:id"
echo "    - Custom span: item.create with item.title, item.id attributes"
echo "    - MySQL query spans (auto-instrumented via OpenTelemetry)"
echo "    - Error span: GET /api/items/99999 (RecordNotFound)"
echo ""

if [ $FAIL_COUNT -gt 0 ]; then
  echo -e "${RED}Some checks failed!${NC}"
  exit 1
else
  echo -e "${GREEN}All checks passed!${NC}"
  exit 0
fi
