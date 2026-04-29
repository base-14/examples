#!/bin/bash

set -eu

API_URL=${API_URL:-http://localhost:8080}
PASSED=0
FAILED=0
LAST_BODY=""

echo "=== aspire-postgres API Testing Script ==="
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
    local retries=60
    while [ $retries -gt 0 ]; do
        if curl -sf "$API_URL/api/health" > /dev/null 2>&1; then
            echo "Services ready."
            echo ""
            return 0
        fi
        retries=$((retries - 1))
        sleep 2
    done
    echo "ERROR: Services not ready after 120 seconds"
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
test_endpoint "404 - Article not found" "GET" "/api/articles/99999" "" 404
test_endpoint "422 - Validation failed (empty body)" "POST" "/api/articles" '{}' 422

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

    # .NET BatchSpanProcessor flushes every 5s; wait one cycle past it.
    echo "Waiting 8s for span flush..."
    sleep 8

    COLLECTOR_NAME=$(docker ps --format '{{.Names}}' | grep -E '^(otel-collector-|aspire-postgres-otel-collector-)' | head -1)
    if [ -z "$COLLECTOR_NAME" ]; then
        echo "[FAIL] Could not find an otel-collector container to inspect"
        FAILED=$((FAILED + 1))
    else
        COLLECTOR_LOGS=$(docker logs "$COLLECTOR_NAME" 2>&1)

        # Same trace_id must appear under both services.
        # HttpClient instrumentation injects W3C `traceparent`;
        # ASP.NET Core extracts it on the receiving end.
        ARTICLES_HIT=$(echo "$COLLECTOR_LOGS" \
            | awk -v t="$TRACE_ID" '
                /service\.name: Str\(articles-api\)/ {svc="articles-api"}
                /service\.name: Str\(notify-svc\)/   {svc="notify-svc"}
                $0 ~ "Trace ID *: " t && svc=="articles-api" {print "yes"; exit}')
        NOTIFY_HIT=$(echo "$COLLECTOR_LOGS" \
            | awk -v t="$TRACE_ID" '
                /service\.name: Str\(articles-api\)/ {svc="articles-api"}
                /service\.name: Str\(notify-svc\)/   {svc="notify-svc"}
                $0 ~ "Trace ID *: " t && svc=="notify-svc" {print "yes"; exit}')

        if [ "$ARTICLES_HIT" = "yes" ]; then
            echo "[PASS] Distributed trace - articles-api emitted span with trace_id=$TRACE_ID"
            PASSED=$((PASSED + 1))
        else
            echo "[FAIL] Distributed trace - no span from articles-api with trace_id=$TRACE_ID"
            FAILED=$((FAILED + 1))
        fi
        if [ "$NOTIFY_HIT" = "yes" ]; then
            echo "[PASS] Distributed trace - notify-svc emitted span with same trace_id"
            PASSED=$((PASSED + 1))
        else
            echo "[FAIL] Distributed trace - no span from notify-svc with trace_id=$TRACE_ID (W3C traceparent did not propagate)"
            FAILED=$((FAILED + 1))
        fi
    fi
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
