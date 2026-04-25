#!/bin/bash

# Verify OTel export to Base14 Scout.
# Requires: SCOUT_ENDPOINT, SCOUT_CLIENT_ID, SCOUT_CLIENT_SECRET, SCOUT_TOKEN_URL.

set -eu

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

echo "--- Credentials ---"
MISSING=0
for var in SCOUT_ENDPOINT SCOUT_CLIENT_ID SCOUT_CLIENT_SECRET SCOUT_TOKEN_URL; do
    if [ -z "${!var:-}" ]; then
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

echo ""
echo "--- Collector ---"
docker compose up -d otel-collector > /dev/null 2>&1
sleep 5

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
echo "--- Waiting 70s for batch + metric flush ---"
sleep 70

echo ""
echo "--- Services ---"
SERVICES=$(docker compose logs otel-collector 2>&1 | grep "service.name:" | grep -v "otelcol-contrib" | sort -u)
echo "$SERVICES" | grep -q "stdlib-articles" && check "service: stdlib-articles" 0 || check "service: stdlib-articles" 1
echo "$SERVICES" | grep -q "stdlib-notify" && check "service: stdlib-notify" 0 || check "service: stdlib-notify" 1

echo ""
echo "--- Metrics ---"
METRIC_COUNT=$(docker compose logs otel-collector 2>&1 | grep -c "resource metrics" || true)
if [ "$METRIC_COUNT" -gt 0 ]; then
    check "Metrics exported ($METRIC_COUNT batches)" 0
else
    check "Metrics exported" 1
fi

docker compose logs otel-collector 2>&1 | grep -q "articles.created" && check "articles.created counter" 0 || check "articles.created counter" 1

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

echo ""
echo "--- Noise Filters ---"
HEALTH_SPANS=$(echo "$COLLECTOR_LOGS" | grep "Name.*health" | wc -l | tr -d ' ')
check "Health spans filtered ($HEALTH_SPANS found)" "$HEALTH_SPANS"

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
echo "Check your Scout dashboard for traces from 'stdlib-articles' service."
