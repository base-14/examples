#!/bin/bash

# API Integration Tests for Go Temporal + PostgreSQL Example
# Tests all API endpoints and workflow triggers

set -e

BASE_URL="${BASE_URL:-http://localhost:8080}"
PASS=0
FAIL=0

echo "============================================"
echo "Go Temporal + PostgreSQL API Integration Tests"
echo "Base URL: $BASE_URL"
echo "============================================"
echo ""

run_test() {
    local name="$1"
    local method="$2"
    local endpoint="$3"
    local data="$4"
    local expected="$5"

    echo -n "Testing: $name... "

    # Create temp file for headers
    local headers_file=$(mktemp)

    if [ -n "$data" ]; then
        response=$(curl -s -D "$headers_file" -X "$method" "$BASE_URL$endpoint" \
            -H "Content-Type: application/json" \
            -d "$data" 2>&1)
    else
        response=$(curl -s -D "$headers_file" -X "$method" "$BASE_URL$endpoint" 2>&1)
    fi

    # Extract trace ID from traceparent header (format: 00-traceid-spanid-flags)
    local traceparent=$(grep -i "traceparent" "$headers_file" 2>/dev/null | tr -d '\r')
    local trace_id=""
    if [ -n "$traceparent" ]; then
        trace_id=$(echo "$traceparent" | sed 's/.*: 00-\([a-f0-9]*\)-.*/\1/')
    fi
    rm -f "$headers_file"

    if echo "$response" | grep -q "$expected"; then
        echo "PASS"
        if [ -n "$trace_id" ]; then
            echo "  TraceID: $trace_id"
        fi
        PASS=$((PASS + 1))
    else
        echo "FAIL"
        echo "  Expected: $expected"
        echo "  Got: $response"
        if [ -n "$trace_id" ]; then
            echo "  TraceID: $trace_id"
        fi
        FAIL=$((FAIL + 1))
    fi
}

# Health Check
run_test "Health Check" "GET" "/api/health" "" "ok"

# List Products
run_test "List Products" "GET" "/api/products" "" "products"

# Get Product by SKU
run_test "Get Product" "GET" "/api/products/prod-1" "" "product"

# List Orders (empty initially)
run_test "List Orders" "GET" "/api/orders" "" "orders"

# Create Order - Auto-approve path
echo ""
echo "Testing order creation paths..."
run_test "Create Order (auto-approve)" "POST" "/api/orders" \
    '{"customer_id":"premium-customer","customer_tier":"premium","items":[{"product_id":"prod-1","quantity":1,"price":50}]}' \
    "workflow_id"

# Create Order - High risk (manual review)
run_test "Create Order (high risk)" "POST" "/api/orders" \
    '{"customer_id":"new-customer","customer_tier":"new","items":[{"product_id":"prod-1","quantity":100,"price":5000}]}' \
    "workflow_id"

# Create Order - Backorder path
run_test "Create Order (backorder)" "POST" "/api/orders" \
    '{"customer_id":"test-customer","items":[{"product_id":"out-of-stock-item","quantity":1000}]}' \
    "workflow_id"

# Create Order - Payment failure
run_test "Create Order (payment fail)" "POST" "/api/orders" \
    '{"customer_id":"test-customer","items":[{"product_id":"prod-1","quantity":1}],"payment_method":"test_decline"}' \
    "workflow_id"

# List Orders (should have 4 now)
run_test "List Orders (populated)" "GET" "/api/orders" "" "orders"

echo ""
echo "============================================"
echo "Test Results: $PASS passed, $FAIL failed"
echo "============================================"

if [ $FAIL -gt 0 ]; then
    exit 1
fi

echo ""
echo "Next steps:"
echo "  - Check Temporal UI at http://localhost:8088"
echo "  - Run 'make verify-scout' to verify telemetry"
echo "  - View traces in Scout using the TraceIDs above"
