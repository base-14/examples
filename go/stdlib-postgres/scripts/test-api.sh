#!/bin/bash

# Go stdlib + PostgreSQL + OpenTelemetry API testing script.
# Tests all 6 endpoints and validates observability signals.

set -eu

API_URL=${API_URL:-http://localhost:8080}
PASSED=0
FAILED=0
LAST_BODY=""

echo "=== stdlib-postgres API Testing Script ==="
echo "Target: $API_URL"
echo ""

test_endpoint() {
    local description="$1"
    local method="$2"
    local endpoint="$3"
    local data="$4"
    local expected_status="$5"

    local curl_args=(-s -w "\n%{http_code}" -X "$method" "$API_URL$endpoint")
    curl_args+=(-H "Content-Type: application/json" -H "Accept: application/json")
    if [ -n "$data" ]; then
        curl_args+=(-d "$data")
    fi

    local response
    response=$(curl "${curl_args[@]}")
    local body
    body=$(echo "$response" | sed '$d')
    local status
    status=$(echo "$response" | tail -n1)

    if [ "$status" -eq "$expected_status" ]; then
        echo "[PASS] $description (HTTP $status)"
        PASSED=$((PASSED + 1))
    else
        echo "[FAIL] $description - Expected $expected_status, got $status"
        FAILED=$((FAILED + 1))
    fi
    echo "$body" | head -1
    echo ""

    LAST_BODY="$body"
}

wait_for_services() {
    echo "Waiting for services to be ready..."
    local retries=30
    while [ $retries -gt 0 ]; do
        if curl -sf "$API_URL/api/health" > /dev/null 2>&1; then
            echo "Services ready."
            echo ""
            return 0
        fi
        retries=$((retries - 1))
        sleep 2
    done
    echo "ERROR: Services not ready after 60 seconds"
    exit 1
}

wait_for_services

echo "--- Health ---"
test_endpoint "Health check" "GET" "/api/health" "" 200

echo "--- Create ---"
test_endpoint "Create article" "POST" "/api/articles" \
    '{"title":"Test Article","body":"Integration test content"}' 201

ARTICLE_ID=$(echo "$LAST_BODY" | python3 -c "import sys,json; print(json.load(sys.stdin)['data']['id'])" 2>/dev/null || echo "")

if [ -z "$ARTICLE_ID" ]; then
    echo "[FAIL] Could not extract article ID from create response"
    FAILED=$((FAILED + 1))
else
    echo "--- Read ---"
    test_endpoint "Get article" "GET" "/api/articles/$ARTICLE_ID" "" 200

    echo "--- List ---"
    test_endpoint "List articles" "GET" "/api/articles?page=1&per_page=10" "" 200

    echo "--- Update ---"
    test_endpoint "Update article" "PUT" "/api/articles/$ARTICLE_ID" \
        '{"title":"Updated Title"}' 200

    echo "--- Delete ---"
    test_endpoint "Delete article" "DELETE" "/api/articles/$ARTICLE_ID" "" 204
fi

echo "--- Error Cases ---"
test_endpoint "400 - Invalid ID format" "GET" "/api/articles/abc" "" 400
test_endpoint "404 - Article not found" "GET" "/api/articles/99999" "" 404
test_endpoint "422 - Empty body" "POST" "/api/articles" '{}' 422

echo "--- Distributed Tracing ---"
TRACE_RESPONSE=$(curl -s -X POST "$API_URL/api/articles" \
    -H "Content-Type: application/json" \
    -d '{"title":"Trace Check","body":"Distributed trace test"}')
TRACE_ID=$(echo "$TRACE_RESPONSE" | python3 -c "import sys,json; print(json.load(sys.stdin)['meta']['trace_id'])" 2>/dev/null || echo "")

if [ -z "$TRACE_ID" ]; then
    echo "[FAIL] Could not extract trace_id from create response"
    FAILED=$((FAILED + 1))
else
    echo "trace_id: $TRACE_ID"
    sleep 8

    NOTIFY_LOG=$(docker compose logs notify 2>&1 | grep "$TRACE_ID" || true)
    if [ -n "$NOTIFY_LOG" ]; then
        echo "[PASS] Distributed trace - notify service received matching trace_id"
        PASSED=$((PASSED + 1))
    else
        echo "[FAIL] Distributed trace - trace_id not found in notify logs"
        FAILED=$((FAILED + 1))
    fi

    COLLECTOR_LOG=$(docker compose logs otel-collector 2>&1 | grep "$TRACE_ID" || true)
    if [ -n "$COLLECTOR_LOG" ]; then
        echo "[PASS] Collector received spans with matching trace_id"
        PASSED=$((PASSED + 1))
    else
        echo "[FAIL] Collector did not receive spans with trace_id $TRACE_ID"
        FAILED=$((FAILED + 1))
    fi
fi
echo ""

echo "--- Log Signals ---"
APP_LOGS=$(docker compose logs app 2>&1)

if echo "$APP_LOGS" | grep -q '"trace_id"'; then
    echo "[PASS] Logs contain trace_id field"
    PASSED=$((PASSED + 1))
else
    echo "[FAIL] Logs missing trace_id field"
    FAILED=$((FAILED + 1))
fi

if echo "$APP_LOGS" | grep -q '"span_id"'; then
    echo "[PASS] Logs contain span_id field"
    PASSED=$((PASSED + 1))
else
    echo "[FAIL] Logs missing span_id field"
    FAILED=$((FAILED + 1))
fi

if echo "$APP_LOGS" | grep -q '"WARN"'; then
    echo "[PASS] WARN log present for error conditions"
    PASSED=$((PASSED + 1))
else
    echo "[FAIL] No WARN log found"
    FAILED=$((FAILED + 1))
fi
echo ""

echo "--- Metrics (waiting 65s for periodic flush) ---"
sleep 65

COLLECTOR_LOGS=$(docker compose logs otel-collector 2>&1)

if echo "$COLLECTOR_LOGS" | grep -q "articles.created"; then
    echo "[PASS] articles.created metric found in collector"
    PASSED=$((PASSED + 1))
else
    echo "[FAIL] articles.created metric not found in collector"
    FAILED=$((FAILED + 1))
fi
echo ""

TOTAL=$((PASSED + FAILED))
echo "=== Results ==="
echo "Passed: $PASSED / $TOTAL"
echo "Failed: $FAILED / $TOTAL"

if [ "$FAILED" -gt 0 ]; then
    echo ""
    echo "SOME TESTS FAILED"
    exit 1
fi

echo ""
echo "ALL TESTS PASSED"
