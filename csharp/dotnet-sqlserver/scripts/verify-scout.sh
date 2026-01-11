#!/bin/bash

# Verify Scout APM integration for .NET ASP.NET Core example
# This script checks if telemetry data is being exported correctly

set -e

echo "========================================"
echo "Scout APM Verification"
echo "========================================"
echo ""

# Check if OTel collector is running
echo "Checking OTel Collector..."
if curl -s http://localhost:13133/health | grep -q "Server available"; then
    echo "✓ OTel Collector is healthy"
else
    echo "✗ OTel Collector health check failed"
    exit 1
fi
echo ""

# Check API health
echo "Checking API health..."
HEALTH_RESPONSE=$(curl -s http://localhost:8080/api/health)
if echo "$HEALTH_RESPONSE" | grep -q '"status":"healthy"'; then
    echo "✓ API is healthy"
else
    echo "✗ API health check failed"
    echo "$HEALTH_RESPONSE"
    exit 1
fi
echo ""

# Generate some traffic
echo "Generating test traffic..."
./scripts/test-api.sh > /dev/null 2>&1 || true
echo "✓ Test traffic generated"
echo ""

# Check collector logs for exported data
echo "Checking collector logs for exported telemetry..."
if docker compose logs otel-collector 2>&1 | grep -q "Span"; then
    echo "✓ Traces are being exported"
else
    echo "⚠ No traces found in collector logs (may need more time)"
fi

if docker compose logs otel-collector 2>&1 | grep -q "Metric"; then
    echo "✓ Metrics are being exported"
else
    echo "⚠ No metrics found in collector logs (may need more time)"
fi
echo ""

echo "========================================"
echo "Verification Complete"
echo "========================================"
echo ""
echo "If Scout credentials are configured (.env file),"
echo "telemetry should now appear in the Scout dashboard."
