#!/bin/bash

# Load Test Runner Script
# Usage: ./run-loadtest.sh [target_url] [otel_endpoint] [rps] [duration]
# Example: ./run-loadtest.sh http://host.docker.internal:3000 http://host.docker.internal:4317 2 300

set -e

TARGET_URL=${1:-http://host.docker.internal:3000}
OTEL_ENDPOINT=${2:-http://host.docker.internal:4317}
RPS=${3:-2}
DURATION=${4:-300}

echo "🎯 Target URL: $TARGET_URL"
echo "📡 OTEL Endpoint: $OTEL_ENDPOINT"
echo "📊 Requests per second: $RPS"
echo "⏱️  Duration: $DURATION seconds"
echo ""

# Set environment variables for docker-compose
export TARGET_URL
export OTEL_EXPORTER_OTLP_ENDPOINT=$OTEL_ENDPOINT
export REQUESTS_PER_SECOND=$RPS
export DURATION_SECONDS=$DURATION

# Function to cleanup on exit (including errors)
cleanup() {
    EXIT_CODE=$?
    echo ""
    if [ $EXIT_CODE -ne 0 ]; then
        echo "❌ Error detected (exit code: $EXIT_CODE)"
    fi
    echo "🧹 Cleaning up load test containers..."
    docker-compose down 2>/dev/null || true
}

# Register cleanup function for EXIT and ERR
trap cleanup EXIT ERR

# Check if the application is healthy
echo "🔍 Checking application health..."
# Convert host.docker.internal to localhost for health check from host
HEALTH_CHECK_URL="${TARGET_URL/host.docker.internal/localhost}"
HEALTH_URL="${HEALTH_CHECK_URL}/up"
if ! curl -f "$HEALTH_URL" > /dev/null 2>&1; then
    echo "⚠️  Warning: Application health check failed at $HEALTH_URL"
    echo "Make sure your target application is running before continuing."
    read -p "Continue anyway? (y/N): " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        echo "Aborted."
        exit 1
    fi
else
    echo "✅ Application is healthy"
fi

echo ""

# Run the load test
echo "🎯 Starting load generation..."
docker-compose up --build

echo ""
echo "📈 Load test completed!"
echo "🔍 Check traces at: http://localhost:55679 (OTel Collector zPages)"
echo "📊 Check collector health at: http://localhost:13133"

# Keep collector running for a bit to export final telemetry
echo "⏳ Waiting 30 seconds for final telemetry export..."
sleep 30