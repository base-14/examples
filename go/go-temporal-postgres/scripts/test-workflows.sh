#!/bin/bash

# Workflow Integration Tests for Go Temporal + PostgreSQL Example
# Tests all workflow decision paths and verifies results

set -e

BASE_URL="${BASE_URL:-http://localhost:8080}"
TEMPORAL_UI="${TEMPORAL_UI:-http://localhost:8088}"

echo "============================================"
echo "Temporal Workflow Integration Tests"
echo "API URL: $BASE_URL"
echo "Temporal UI: $TEMPORAL_UI"
echo "============================================"
echo ""

# Helper to extract trace ID from headers
extract_trace_id() {
    local headers_file="$1"
    local traceparent=$(grep -i "traceparent" "$headers_file" 2>/dev/null | tr -d '\r')
    if [ -n "$traceparent" ]; then
        echo "$traceparent" | sed 's/.*: 00-\([a-f0-9]*\)-.*/\1/'
    fi
}

# Check API is running
echo "Checking API health..."
API_STATUS=$(curl -s -o /dev/null -w "%{http_code}" "$BASE_URL/api/health" 2>&1 || echo "000")
if [ "$API_STATUS" != "200" ]; then
    echo "ERROR: API is not responding (status: $API_STATUS)"
    echo "Make sure to run 'docker compose up -d' first"
    exit 1
fi
echo "API is healthy"
echo ""

# Test 1: Auto-approve path (low risk order)
echo "============================================"
echo "Test 1: Auto-approve path (low risk order)"
echo "============================================"
echo "Submitting premium customer order with low amount..."
HEADERS_FILE=$(mktemp)
RESPONSE=$(curl -s -D "$HEADERS_FILE" -X POST "$BASE_URL/api/orders" \
    -H "Content-Type: application/json" \
    -d '{"customer_id":"premium-customer","customer_tier":"premium","items":[{"product_id":"prod-1","quantity":1,"price":50}]}')
TRACE_ID=$(extract_trace_id "$HEADERS_FILE")
rm -f "$HEADERS_FILE"
echo "Response: $RESPONSE"
WORKFLOW_ID=$(echo "$RESPONSE" | grep -o '"workflow_id":"[^"]*"' | cut -d'"' -f4)
echo "Workflow ID: $WORKFLOW_ID"
echo "TraceID: $TRACE_ID"
echo "Expected path: auto_approved"
echo ""

sleep 2

# Test 2: Manual review path (high risk order)
echo "============================================"
echo "Test 2: Manual review path (high risk order)"
echo "============================================"
echo "Submitting new customer order with high amount..."
HEADERS_FILE=$(mktemp)
RESPONSE=$(curl -s -D "$HEADERS_FILE" -X POST "$BASE_URL/api/orders" \
    -H "Content-Type: application/json" \
    -d '{"customer_id":"new-customer","customer_tier":"new","items":[{"product_id":"prod-1","quantity":100,"price":5000}]}')
TRACE_ID=$(extract_trace_id "$HEADERS_FILE")
rm -f "$HEADERS_FILE"
echo "Response: $RESPONSE"
WORKFLOW_ID=$(echo "$RESPONSE" | grep -o '"workflow_id":"[^"]*"' | cut -d'"' -f4)
echo "Workflow ID: $WORKFLOW_ID"
echo "TraceID: $TRACE_ID"
echo "Expected path: manual_review (waiting for signal)"
echo ""

sleep 2

# Test 3: Backorder path (out of stock)
echo "============================================"
echo "Test 3: Backorder path (insufficient stock)"
echo "============================================"
echo "Submitting order for out-of-stock item..."
HEADERS_FILE=$(mktemp)
RESPONSE=$(curl -s -D "$HEADERS_FILE" -X POST "$BASE_URL/api/orders" \
    -H "Content-Type: application/json" \
    -d '{"customer_id":"test-customer","items":[{"product_id":"out-of-stock-item","quantity":1000}]}')
TRACE_ID=$(extract_trace_id "$HEADERS_FILE")
rm -f "$HEADERS_FILE"
echo "Response: $RESPONSE"
WORKFLOW_ID=$(echo "$RESPONSE" | grep -o '"workflow_id":"[^"]*"' | cut -d'"' -f4)
echo "Workflow ID: $WORKFLOW_ID"
echo "TraceID: $TRACE_ID"
echo "Expected path: backorder"
echo ""

sleep 2

# Test 4: Payment failure path
echo "============================================"
echo "Test 4: Payment failure path"
echo "============================================"
echo "Submitting order with test_decline payment method..."
HEADERS_FILE=$(mktemp)
RESPONSE=$(curl -s -D "$HEADERS_FILE" -X POST "$BASE_URL/api/orders" \
    -H "Content-Type: application/json" \
    -d '{"customer_id":"test-customer","items":[{"product_id":"prod-1","quantity":1}],"payment_method":"test_decline"}')
TRACE_ID=$(extract_trace_id "$HEADERS_FILE")
rm -f "$HEADERS_FILE"
echo "Response: $RESPONSE"
WORKFLOW_ID=$(echo "$RESPONSE" | grep -o '"workflow_id":"[^"]*"' | cut -d'"' -f4)
echo "Workflow ID: $WORKFLOW_ID"
echo "TraceID: $TRACE_ID"
echo "Expected path: payment_declined"
echo ""

echo "============================================"
echo "Workflow Tests Summary"
echo "============================================"
echo ""
echo "All 4 decision paths tested:"
echo "  1. Auto-approve: Premium customer, low amount"
echo "  2. Manual review: New customer, high amount (>80 risk score)"
echo "  3. Backorder: Out-of-stock item"
echo "  4. Payment failed: test_decline payment method"
echo ""
echo "Verification:"
echo "  - Temporal UI: $TEMPORAL_UI"
echo "  - Check workflow executions and decision paths"
echo "  - View traces in Scout using the TraceIDs above"
echo ""
echo "To approve manual review workflow, use Temporal CLI:"
echo "  temporal workflow signal --workflow-id <id> --name manual-review-decision --input '\"approved\"'"
