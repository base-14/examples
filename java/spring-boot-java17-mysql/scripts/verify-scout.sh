#!/bin/bash

set -e

GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m'

BASE_URL="${API_BASE_URL:-http://localhost:8080}"
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
echo "  Spring Boot Java 17 + MySQL"
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

API_HEALTH=$(curl -s -o /dev/null -w "%{http_code}" "$BASE_URL/actuator/health" 2>/dev/null || echo "000")

if [ "$API_HEALTH" = "200" ]; then
  pass "API is healthy (actuator)"
else
  fail "API not responding (HTTP $API_HEALTH)"
fi
echo ""

echo -e "${YELLOW}3. Generating Test Traces${NC}"
echo "----------------------------------------"

curl -s "$BASE_URL/actuator/health" > /dev/null && pass "Health check request sent"

TIMESTAMP=$(date +%s)

SAVE_RESPONSE=$(curl -s -X POST "$BASE_URL/users/saveUser" \
  -H "Content-Type: application/json" \
  -d "{\"name\":\"Scout Test $TIMESTAMP\",\"address\":\"123 Test Street\"}")

if echo "$SAVE_RESPONSE" | grep -q '"name"'; then
  pass "User creation request sent"
else
  fail "User creation failed"
fi

curl -s "$BASE_URL/users/" > /dev/null
pass "User list request sent"

curl -s "$BASE_URL/users/testMessage" > /dev/null
pass "Test message request sent"
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
echo "  Service: spring-boot-java17-mysql"
echo "  Traces:"
echo "    - HTTP spans: GET /actuator/health, POST /users/saveUser"
echo "    - HTTP spans: GET /users/, GET /users/testMessage"
echo "    - JDBC/Hibernate query spans (auto-instrumented)"
echo ""

if [ $FAIL_COUNT -gt 0 ]; then
  echo -e "${RED}Some checks failed!${NC}"
  exit 1
else
  echo -e "${GREEN}All checks passed!${NC}"
  exit 0
fi
