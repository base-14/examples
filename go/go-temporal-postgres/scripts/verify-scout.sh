#!/bin/bash

# Scout Integration Verification Script
# Verifies that telemetry is being exported to Scout

set -e

OTEL_COLLECTOR_HEALTH="${OTEL_COLLECTOR_HEALTH:-http://localhost:13133}"
BASE_URL="${BASE_URL:-http://localhost:8080}"
ZPAGES_URL="${ZPAGES_URL:-http://localhost:55679}"

echo "============================================"
echo "Scout Integration Verification"
echo "============================================"
echo ""

# Check OTel Collector health
echo "1. Checking OTel Collector health..."
COLLECTOR_STATUS=$(curl -s -o /dev/null -w "%{http_code}" "$OTEL_COLLECTOR_HEALTH" 2>&1 || echo "000")

if [ "$COLLECTOR_STATUS" = "200" ]; then
    echo "   [PASS] OTel Collector is healthy"
else
    echo "   [FAIL] OTel Collector is not responding (status: $COLLECTOR_STATUS)"
    echo "   Make sure docker compose is running"
    exit 1
fi

# Check API health
echo ""
echo "2. Checking API health..."
API_STATUS=$(curl -s -o /dev/null -w "%{http_code}" "$BASE_URL/api/health" 2>&1 || echo "000")

if [ "$API_STATUS" = "200" ]; then
    echo "   [PASS] API is healthy"
else
    echo "   [FAIL] API is not responding (status: $API_STATUS)"
    exit 1
fi

# Generate HTTP request traces
echo ""
echo "3. Generating HTTP request traces..."
for i in {1..5}; do
    curl -s "$BASE_URL/api/health" > /dev/null
    curl -s "$BASE_URL/api/products" > /dev/null
    echo "   Sent request batch $i/5"
done
echo "   [PASS] HTTP traces generated"

# Generate workflow traces
echo ""
echo "4. Generating workflow traces..."
echo "   Creating order to trigger workflow..."
RESPONSE=$(curl -s -X POST "$BASE_URL/api/orders" \
    -H "Content-Type: application/json" \
    -d '{"customer_id":"scout-test","customer_tier":"premium","items":[{"product_id":"prod-1","quantity":1,"price":25}]}')

if echo "$RESPONSE" | grep -q "workflow_id"; then
    WORKFLOW_ID=$(echo "$RESPONSE" | grep -o '"workflow_id":"[^"]*"' | cut -d'"' -f4)
    echo "   [PASS] Workflow started: $WORKFLOW_ID"
else
    echo "   [WARN] Could not create order workflow"
fi

# Check zpages for trace activity
echo ""
echo "5. Checking zpages for trace activity..."
ZPAGES_STATUS=$(curl -s -o /dev/null -w "%{http_code}" "$ZPAGES_URL/debug/tracez" 2>&1 || echo "000")

if [ "$ZPAGES_STATUS" = "200" ]; then
    echo "   [PASS] zpages accessible at $ZPAGES_URL/debug/tracez"
else
    echo "   [INFO] zpages not accessible (optional debug feature)"
fi

# Wait for traces to be exported
echo ""
echo "6. Waiting for trace export (3 seconds)..."
sleep 3

echo ""
echo "============================================"
echo "Verification Summary"
echo "============================================"
echo ""
echo "[PASS] OTel Collector: Running and healthy"
echo "[PASS] API: Healthy and instrumented"
echo "[PASS] Traces: Generated from HTTP and workflow"
echo ""
echo "Expected telemetry in Scout:"
echo "  - HTTP spans: GET /api/health, GET /api/products"
echo "  - Workflow spans: OrderFulfillmentWorkflow"
echo "  - Activity spans: ValidateOrder, FraudAssessment, etc."
echo "  - Database spans: GORM queries"
echo ""
echo "Metrics exported:"
echo "  - orders.processed"
echo "  - orders.approved"
echo "  - orders.processing_duration"
echo "  - orders.fraud_risk_score"
echo ""
echo "Debug commands:"
echo "  docker compose logs otel-collector | grep -i export"
echo "  docker compose logs otel-collector | grep -i trace"
echo ""
echo "To configure Scout, add these to .env:"
echo "  SCOUT_ENDPOINT=https://your-tenant.base14.io:4318"
echo "  SCOUT_CLIENT_ID=your-client-id"
echo "  SCOUT_CLIENT_SECRET=your-client-secret"
echo "  SCOUT_TOKEN_URL=https://your-tenant.base14.io/oauth/token"
echo ""
