#!/bin/bash

set -e

GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m'

BASE_URL="${API_BASE_URL:-http://localhost:8000}"
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
echo "  FastAPI + Celery + PostgreSQL"
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

API_HEALTH=$(curl -s -o /dev/null -w "%{http_code}" "$BASE_URL/ping" 2>/dev/null || echo "000")

if [ "$API_HEALTH" = "200" ]; then
  pass "API is healthy (GET /ping)"
else
  fail "API not responding (HTTP $API_HEALTH)"
fi
echo ""

echo -e "${YELLOW}3. Generating Test Traces${NC}"
echo "----------------------------------------"

curl -s "$BASE_URL/ping" > /dev/null && pass "Ping request sent"

TIMESTAMP=$(date +%s)

TASK_RESPONSE=$(curl -s -X POST "$BASE_URL/tasks/" \
  -H "Content-Type: application/json" \
  -d "{\"title\":\"Scout Test Task $TIMESTAMP\"}")

TASK_ID=$(echo "$TASK_RESPONSE" | grep -o '"id":[0-9]*' | sed 's/"id"://')

if [ -n "$TASK_ID" ]; then
  pass "Task creation request sent (ID: $TASK_ID)"
else
  fail "Task creation failed"
fi

curl -s "$BASE_URL/tasks/" > /dev/null
pass "Task list request sent"

if [ -n "$TASK_ID" ]; then
  curl -s "$BASE_URL/tasks/$TASK_ID" > /dev/null
  pass "Task detail request sent"
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
echo "  Service: fastapi-celery-postgres"
echo "  Traces:"
echo "    - HTTP spans: GET /ping, POST /tasks/, GET /tasks/"
echo "    - Celery worker spans (distributed trace propagation)"
echo "    - PostgreSQL query spans (auto-instrumented via SQLAlchemy)"
echo ""

if [ $FAIL_COUNT -gt 0 ]; then
  echo -e "${RED}Some checks failed!${NC}"
  exit 1
else
  echo -e "${GREEN}All checks passed!${NC}"
  exit 0
fi
