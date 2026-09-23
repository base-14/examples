#!/bin/bash
# Smoke test for the .NET 8 hello-world API.
# Usage: ./scripts/test-api.sh [base_url]

set -e

BASE_URL="${1:-http://localhost:8080}"
PASS=0
FAIL=0

check() {
    local description=$1
    local endpoint=$2
    local expected=$3

    local response status body
    response=$(curl -s -w '\n%{http_code}' "$BASE_URL$endpoint" || printf 'curl failed\n000')
    status=$(echo "$response" | tail -n 1)
    body=$(echo "$response" | sed '$d')

    if [ "$status" = "200" ] && echo "$body" | grep -q "$expected"; then
        echo "PASS: $description ($status) $body"
        PASS=$((PASS + 1))
    else
        echo "FAIL: $description ($status) $body"
        FAIL=$((FAIL + 1))
    fi
}

check "health" "/api/health" '"status":"healthy"'
check "hello World" "/api/hello/World" '"message":"Hello, World!"'
check "hello Scout" "/api/hello/Scout" '"greetingCount":'

echo ""
echo "Passed: $PASS  Failed: $FAIL"
[ "$FAIL" -eq 0 ]
