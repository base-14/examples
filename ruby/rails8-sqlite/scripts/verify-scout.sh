#!/bin/bash

set -e

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
echo "  Rails 8 + SQLite"
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

API_HEALTH=$(curl -s -o /dev/null -w "%{http_code}" "$BASE_URL/up" 2>/dev/null || echo "000")

if [ "$API_HEALTH" = "200" ]; then
  pass "Rails health check passed (GET /up)"
else
  fail "Rails not responding (HTTP $API_HEALTH)"
fi
echo ""

echo -e "${YELLOW}3. Generating Test Traces${NC}"
echo "----------------------------------------"

curl -s "$BASE_URL/up" > /dev/null && pass "Health check request sent"

ROOT_STATUS=$(curl -s -o /dev/null -w "%{http_code}" "$BASE_URL/" 2>/dev/null || echo "000")
if [ "$ROOT_STATUS" = "200" ] || [ "$ROOT_STATUS" = "302" ]; then
  pass "Root page request sent (HTTP $ROOT_STATUS)"
else
  fail "Root page request failed (HTTP $ROOT_STATUS)"
fi

HOTELS_STATUS=$(curl -s -o /dev/null -w "%{http_code}" "$BASE_URL/hotels" 2>/dev/null || echo "000")
if [ "$HOTELS_STATUS" = "200" ] || [ "$HOTELS_STATUS" = "302" ]; then
  pass "Hotels page request sent (HTTP $HOTELS_STATUS)"
else
  fail "Hotels page request failed (HTTP $HOTELS_STATUS)"
fi

SIGNUP_STATUS=$(curl -s -o /dev/null -w "%{http_code}" "$BASE_URL/signup" 2>/dev/null || echo "000")
if [ "$SIGNUP_STATUS" = "200" ]; then
  pass "Signup page request sent"
else
  fail "Signup page request failed (HTTP $SIGNUP_STATUS)"
fi

LOGIN_STATUS=$(curl -s -o /dev/null -w "%{http_code}" "$BASE_URL/login" 2>/dev/null || echo "000")
if [ "$LOGIN_STATUS" = "200" ]; then
  pass "Login page request sent"
else
  fail "Login page request failed (HTTP $LOGIN_STATUS)"
fi
echo ""

echo -e "${YELLOW}4. Waiting for Trace Export${NC}"
echo "----------------------------------------"
echo "Waiting 5s for batch export to collector..."
sleep 5

echo ""
echo -e "${YELLOW}5. Checking Collector Logs${NC}"
echo "----------------------------------------"

COLLECTOR_LOGS=$(docker compose logs otel-collector 2>&1)

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
echo "  Service: rails8-sqlite"
echo "  Traces:"
echo "    - HTTP spans: GET /up, GET /, GET /hotels"
echo "    - HTTP spans: GET /signup, GET /login"
echo "    - SQLite query spans (auto-instrumented via OpenTelemetry)"
echo ""

if [ $FAIL_COUNT -gt 0 ]; then
  echo -e "${RED}Some checks failed!${NC}"
  exit 1
else
  echo -e "${GREEN}All checks passed!${NC}"
  exit 0
fi
