#!/bin/bash
set -e

BASE_URL="${API_BASE_URL:-http://localhost:4000}"
PASS=0
FAIL=0

GREEN='\033[0;32m'
RED='\033[0;31m'
NC='\033[0m'

pass() { echo -e "${GREEN}✓ PASS${NC}: $1"; PASS=$((PASS + 1)); }
fail() { echo -e "${RED}✗ FAIL${NC}: $1 (expected $2, got $3)"; FAIL=$((FAIL + 1)); }

echo "========================================="
echo "Testing Phoenix ChatApp"
echo "========================================="
echo ""

# Health check (root page)
STATUS=$(curl -s -o /dev/null -w "%{http_code}" "$BASE_URL/")
if [ "$STATUS" = "200" ]; then pass "GET / (home page)"; else fail "GET / (home page)" "200" "$STATUS"; fi

# LiveDashboard (dev routes)
STATUS=$(curl -s -o /dev/null -w "%{http_code}" "$BASE_URL/dev/dashboard")
if [ "$STATUS" = "200" ] || [ "$STATUS" = "302" ]; then pass "GET /dev/dashboard"; else fail "GET /dev/dashboard" "200|302" "$STATUS"; fi

echo ""
echo "========================================="
echo "Passed: ${PASS}"
echo "Failed: ${FAIL}"
echo "========================================="

if [ $FAIL -gt 0 ]; then exit 1; fi
