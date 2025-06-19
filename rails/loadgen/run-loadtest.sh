#!/bin/bash

# Load Test Runner Script
# Usage: ./run-loadtest.sh [pattern] [rps] [duration]

set -e

PATTERN=${1:-normal}
RPS=${2:-2}
DURATION=${3:-300}

echo "🚀 Starting load test with pattern: $PATTERN"
echo "📊 Requests per second: $RPS"
echo "⏱️  Duration: $DURATION seconds"
echo ""

# Set environment variables
export LOAD_PATTERN=$PATTERN
export LOAD_RPS=$RPS
export LOAD_DURATION=$DURATION

# Function to cleanup on exit
cleanup() {
    echo ""
    echo "🧹 Cleaning up load test containers..."
    docker-compose --profile loadgen down
}

# Register cleanup function
trap cleanup EXIT

# Check if the application is healthy
echo "🔍 Checking application health..."
if ! curl -f http://localhost:3000/up > /dev/null 2>&1; then
    echo "❌ Application not healthy. Starting services first..."
    docker-compose up -d web otel-collector
    
    echo "⏳ Waiting for services to be ready..."
    sleep 30
    
    # Check again
    if ! curl -f http://localhost:3000/up > /dev/null 2>&1; then
        echo "❌ Application still not healthy. Please check the logs."
        exit 1
    fi
fi

echo "✅ Application is healthy"
echo ""

# Run the load test
echo "🎯 Starting load generation..."
docker-compose --profile loadgen up --build loadgen

echo ""
echo "📈 Load test completed!"
echo "🔍 Check traces at: http://localhost:55679 (OTel Collector zPages)"
echo "📊 Check collector health at: http://localhost:13133"

# Keep collector running for a bit to export final telemetry
echo "⏳ Waiting 30 seconds for final telemetry export..."
sleep 30