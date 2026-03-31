#!/bin/bash

# Verify OTel export to Base14 Scout
# Requires: SCOUT_ENDPOINT, SCOUT_CLIENT_ID, SCOUT_CLIENT_SECRET, SCOUT_TOKEN_URL

set -e

API_URL=${API_URL:-http://localhost:8080}
PASSED=0
FAILED=0

check() {
    local description="$1"
    local result="$2"
    if [ "$result" -eq 0 ]; then
        echo "[OK]   $description"
        PASSED=$((PASSED + 1))
    else
        echo "[FAIL] $description"
        FAILED=$((FAILED + 1))
    fi
}

echo "=== Verify Scout Export ==="
echo ""

# Step 1: Check credentials
echo "--- Credentials ---"
MISSING=0
for var in SCOUT_ENDPOINT SCOUT_CLIENT_ID SCOUT_CLIENT_SECRET SCOUT_TOKEN_URL; do
    if [ -z "${!var}" ]; then
        echo "[FAIL] Missing required env var: $var"
        MISSING=1
    else
        echo "[OK]   $var is set"
    fi
done

if [ $MISSING -eq 1 ]; then
    echo ""
    echo "Set Scout credentials in .env or environment before running."
    echo "See .env.example for the required variables."
    exit 1
fi

# Step 2: Ensure collector is running
echo ""
echo "--- Collector ---"
docker compose up -d otel-collector > /dev/null 2>&1
sleep 5

# Step 3: Send test traffic — success, 400-level, and 500-level scenarios
echo ""
echo "--- Test Traffic ---"

curl -sf -X POST "$API_URL/api/articles" \
    -H "Content-Type: application/json" \
    -d '{"title":"Scout Verify","body":"Testing Scout export"}' > /dev/null
echo "[OK]   POST /api/articles (201 create + notify)"

curl -sf "$API_URL/api/articles" > /dev/null
echo "[OK]   GET /api/articles (200 list)"

curl -sf "$API_URL/api/articles/99999" > /dev/null 2>&1 || true
echo "[OK]   GET /api/articles/99999 (404 WARN)"

curl -sf -X POST "$API_URL/api/articles" \
    -H "Content-Type: application/json" \
    -d '{}' > /dev/null 2>&1 || true
echo "[OK]   POST /api/articles {} (422 WARN)"

curl -sf "$API_URL/api/articles/abc" > /dev/null 2>&1 || true
echo "[OK]   GET /api/articles/abc (400 WARN)"

echo ""
echo "--- Waiting 15s for batch flush ---"
sleep 15

# Step 4: Check for export errors
echo ""
echo "--- Export Errors ---"
ERRORS=$(docker compose logs otel-collector 2>&1 | grep -iw "failed to export\|Exporting failed\| 401 \| 403 \|connection refused\|Unauthorized\|Forbidden" | tail -5 || true)
if [ -n "$ERRORS" ]; then
    echo "[FAIL] Export errors found:"
    echo "$ERRORS"
    FAILED=$((FAILED + 1))
else
    check "No export errors" 0
fi

# Step 5: Verify traces exported
echo ""
echo "--- Traces ---"
TRACE_COUNT=$(docker compose logs otel-collector 2>&1 | grep -c "resource spans" || true)
if [ "$TRACE_COUNT" -gt 0 ]; then
    check "Traces exported ($TRACE_COUNT batches)" 0
else
    check "Traces exported" 1
fi

SERVICES=$(docker compose logs otel-collector 2>&1 | grep "service.name:" | grep -v "otelcol-contrib" | sort -u)
echo "$SERVICES" | grep -q "elysia-articles" && check "service: elysia-articles" 0 || check "service: elysia-articles" 1
echo "$SERVICES" | grep -q "elysia-notify" && check "service: elysia-notify" 0 || check "service: elysia-notify" 1

# Step 6: Verify metrics exported
echo ""
echo "--- Metrics ---"
METRIC_COUNT=$(docker compose logs otel-collector 2>&1 | grep -c "resource metrics" || true)
if [ "$METRIC_COUNT" -gt 0 ]; then
    check "Metrics exported ($METRIC_COUNT batches)" 0
else
    check "Metrics exported" 1
fi

docker compose logs otel-collector 2>&1 | grep -q "articles.created" && check "articles.created counter" 0 || check "articles.created counter" 1

# Step 7: Verify logs exported
echo ""
echo "--- Logs ---"
LOG_COUNT=$(docker compose logs otel-collector 2>&1 | grep -c "log records" || true)
if [ "$LOG_COUNT" -gt 0 ]; then
    check "Logs exported ($LOG_COUNT batches)" 0
else
    check "Logs exported" 1
fi

docker compose logs otel-collector 2>&1 | grep "Body: Str" | grep -q "Article created" && check "Log: Article created (INFO)" 0 || check "Log: Article created (INFO)" 1
docker compose logs otel-collector 2>&1 | grep "Body: Str" | grep -q "Article not found" && check "Log: Article not found (WARN)" 0 || check "Log: Article not found (WARN)" 1
docker compose logs otel-collector 2>&1 | grep "Body: Str" | grep -q "Validation failed" && check "Log: Validation failed (WARN)" 0 || check "Log: Validation failed (WARN)" 1
docker compose logs otel-collector 2>&1 | grep "Body: Str" | grep -q "Invalid article ID" && check "Log: Invalid ID format (WARN)" 0 || check "Log: Invalid ID format (WARN)" 1

# Step 8: Verify log/trace correlation
echo ""
echo "--- Log/Trace Correlation ---"
COLLECTOR_LOGS=$(docker compose logs otel-collector 2>&1)

CORRELATED_LOGS=$(echo "$COLLECTOR_LOGS" | grep "Trace ID:" | grep -v " -> " | grep -v "Trace ID: $" | grep -v "00000000000000000000000000000000" | head -1)
if [ -n "$CORRELATED_LOGS" ]; then
    check "Exported logs carry Trace ID" 0
else
    check "Exported logs carry Trace ID" 1
fi

CORRELATED_SPANS=$(echo "$COLLECTOR_LOGS" | grep "Span ID:" | grep -v " -> " | grep -v "Span ID: $" | grep -v "0000000000000000" | head -1)
if [ -n "$CORRELATED_SPANS" ]; then
    check "Exported logs carry Span ID" 0
else
    check "Exported logs carry Span ID" 1
fi

WARN_WITH_TRACE=$(echo "$COLLECTOR_LOGS" | grep -A5 "Article not found\|Validation failed\|Invalid article ID" | grep "Trace ID:" | grep -v "00000000000000000000000000000000" | head -1)
if [ -n "$WARN_WITH_TRACE" ]; then
    check "WARN logs (400/404/422) have trace correlation" 0
else
    check "WARN logs (400/404/422) have trace correlation" 1
fi

# Step 9: Verify noise filtered
echo ""
echo "--- Noise Filters ---"
HEALTH_SPANS=$(echo "$COLLECTOR_LOGS" | grep "Name.*health" | wc -l | tr -d ' ')
check "Health spans filtered ($HEALTH_SPANS found)" "$HEALTH_SPANS"

# Summary
echo ""
TOTAL=$((PASSED + FAILED))
echo "=== Results ==="
echo "Passed: $PASSED / $TOTAL"
echo "Failed: $FAILED / $TOTAL"

if [ $FAILED -gt 0 ]; then
    echo ""
    echo "SOME CHECKS FAILED — review collector logs: docker compose logs otel-collector"
    exit 1
fi

echo ""
echo "ALL CHECKS PASSED"
echo "Check your Scout dashboard for traces from 'elysia-articles' service."
