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
echo "  Temporal Tracing - Workflow Test"
echo "========================================"
echo ""

echo -e "${YELLOW}1. Checking Temporal server${NC}"
echo "----------------------------------------"

TEMPORAL_UP=$(docker compose ps temporal --format '{{.Status}}' 2>/dev/null | grep -c "Up" || echo "0")
if [ "$TEMPORAL_UP" -ge 1 ]; then
  pass "Temporal server is running"
else
  fail "Temporal server is not running"
  echo "  Run: docker compose up -d"
  exit 1
fi
echo ""

echo -e "${YELLOW}2. Checking app execution${NC}"
echo "----------------------------------------"

APP_LOGS=$(docker compose logs app 2>&1)

if echo "$APP_LOGS" | grep -q "Workflow result: Hello World!"; then
  pass "Workflow executed successfully"
else
  fail "Workflow result not found in app logs"
  echo "  Check: docker compose logs app"
fi

if echo "$APP_LOGS" | grep -q "Worker started on task queue"; then
  pass "Worker started"
else
  fail "Worker did not start"
fi
echo ""

echo "========================================"
echo "  Results"
echo "========================================"
echo -e "Passed: ${GREEN}$PASS_COUNT${NC}"
echo -e "Failed: ${RED}$FAIL_COUNT${NC}"

if [ $FAIL_COUNT -gt 0 ]; then
  exit 1
fi
