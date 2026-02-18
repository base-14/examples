#!/bin/bash

# Verify Scout Integration Script
# Generates test traffic and verifies traces are exported to Base14 Scout

set -e

API_URL=${API_URL:-http://localhost:8080}
COLLECTOR_HEALTH=${COLLECTOR_HEALTH:-http://localhost:13133}

echo "=== Scout Integration Verification ==="
echo ""

# Check collector health
echo "[1/4] Checking OTel Collector health..."
COLLECTOR_STATUS=$(curl -s -o /dev/null -w "%{http_code}" "$COLLECTOR_HEALTH" || echo "000")
if [ "$COLLECTOR_STATUS" -eq 200 ]; then
    echo "  OK - Collector is healthy"
else
    echo "  FAIL - Collector not responding (HTTP $COLLECTOR_STATUS)"
    echo "  Make sure the collector is running: docker compose ps"
    exit 1
fi

# Check Scout credentials
echo ""
echo "[2/4] Checking Scout credentials..."
if [ -z "$SCOUT_ENDPOINT" ]; then
    echo "  WARN - SCOUT_ENDPOINT not set"
    echo "  Export your Scout credentials before running this script"
else
    echo "  OK - SCOUT_ENDPOINT is set"
fi

if [ -z "$SCOUT_CLIENT_ID" ] || [ -z "$SCOUT_CLIENT_SECRET" ]; then
    echo "  WARN - Scout OAuth credentials not fully set"
else
    echo "  OK - Scout OAuth credentials are set"
fi

# Generate test traffic
echo ""
echo "[3/4] Generating test traffic..."
SUFFIX=$(date +%s)

# Register a user
curl -s -X POST "$API_URL/api/register" \
    -H "Content-Type: application/json" \
    -H "Accept: application/json" \
    -d "{\"name\":\"Scout Test\",\"email\":\"scout-$SUFFIX@example.com\",\"password\":\"password123\"}" > /dev/null

# Health check
curl -s "$API_URL/api/health" > /dev/null

# List articles
curl -s "$API_URL/api/articles" -H "Accept: application/json" > /dev/null

echo "  OK - Generated 3 requests"

# Wait for export
echo ""
echo "[4/4] Waiting for traces to export (5 seconds)..."
sleep 5

# Check collector logs for export success
EXPORT_SUCCESS=$(docker logs slim4-otel-collector 2>&1 | grep -c "Exporting data" || true)
SPANS_SENT=$(docker logs slim4-otel-collector 2>&1 | grep -c "TracesExporter" || true)

echo ""
echo "=== Verification Results ==="
if [ "$EXPORT_SUCCESS" -gt 0 ] || [ "$SPANS_SENT" -gt 0 ]; then
    echo "OK - Traces are being exported to Scout"
    echo ""
    echo "View your traces at:"
    echo "  1. Login to your Scout dashboard"
    echo "  2. Navigate to Traces"
    echo "  3. Filter by service: php-slim4-mongodb-otel"
else
    echo "WARN - No export activity detected"
    echo ""
    echo "Troubleshooting steps:"
    echo "  1. Check collector logs: docker compose logs otel-collector"
    echo "  2. Verify Scout credentials are correct"
    echo "  3. Check OAuth token errors in logs"
    echo "  4. Ensure SCOUT_ENDPOINT is reachable"
fi

echo ""
echo "Collector metrics available at: http://localhost:13133/metrics"
echo "Collector zPages available at: http://localhost:55679/debug/tracez"
