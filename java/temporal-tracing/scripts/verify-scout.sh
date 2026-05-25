#!/bin/bash

set -e

GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m'

PASS_COUNT=0
FAIL_COUNT=0

pass() { echo -e "${GREEN}✓${NC} $1"; PASS_COUNT=$((PASS_COUNT + 1)); }
fail() { echo -e "${RED}✗${NC} $1"; FAIL_COUNT=$((FAIL_COUNT + 1)); }

echo "========================================"
echo "  Scout/OpenTelemetry Verification"
echo "  Temporal Workflow Tracing"
echo "========================================"
echo ""

echo -e "${YELLOW}1. Checking OTel Collector Health${NC}"
echo "----------------------------------------"

COLLECTOR_HEALTH=$(curl -s -o /dev/null -w "%{http_code}" "http://localhost:13133/" 2>/dev/null || echo "000")

if [ "$COLLECTOR_HEALTH" = "200" ]; then
  pass "OTel Collector is healthy"
else
  fail "OTel Collector not responding (HTTP $COLLECTOR_HEALTH)"
  echo "  Make sure the collector is running: docker compose up -d"
fi
echo ""

echo -e "${YELLOW}2. Checking Trace Spans in Collector${NC}"
echo "----------------------------------------"

COLLECTOR_LOGS=$(docker compose logs otel-collector 2>&1)

if echo "$COLLECTOR_LOGS" | grep -q "StartWorkflow:GreetingWorkflow"; then
  pass "StartWorkflow span found"
else
  fail "StartWorkflow span not found"
fi

if echo "$COLLECTOR_LOGS" | grep -q "RunWorkflow:GreetingWorkflow"; then
  pass "RunWorkflow span found"
else
  fail "RunWorkflow span not found"
fi

if echo "$COLLECTOR_LOGS" | grep -q "StartActivity:ComposeGreeting"; then
  pass "StartActivity span found"
else
  fail "StartActivity span not found"
fi

if echo "$COLLECTOR_LOGS" | grep -q "RunActivity:ComposeGreeting"; then
  pass "RunActivity span found"
else
  fail "RunActivity span not found"
fi
echo ""

echo -e "${YELLOW}3. Checking Trace Propagation${NC}"
echo "----------------------------------------"

if echo "$COLLECTOR_LOGS" | grep -q "temporal-tracing-example"; then
  pass "Service name attribute present"
else
  fail "Service name attribute not found"
fi
echo ""

echo "========================================"
echo "  Results"
echo "========================================"
echo -e "Passed: ${GREEN}$PASS_COUNT${NC}"
echo -e "Failed: ${RED}$FAIL_COUNT${NC}"
echo ""

echo "Expected span tree:"
echo "  StartWorkflow:GreetingWorkflow (root)"
echo "    └── RunWorkflow:GreetingWorkflow"
echo "          └── StartActivity:ComposeGreeting"
echo "                └── RunActivity:ComposeGreeting"
echo ""

if [ $FAIL_COUNT -gt 0 ]; then
  echo -e "${RED}Some checks failed!${NC}"
  exit 1
else
  echo -e "${GREEN}All checks passed!${NC}"
  exit 0
fi
