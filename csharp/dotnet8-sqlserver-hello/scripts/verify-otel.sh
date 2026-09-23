#!/bin/bash
# Checks that the collector received traces, metrics and logs from the API.
# Run after `docker compose up -d`. Metrics export every 60 seconds by default,
# so the script polls for up to 90 seconds.

set -e

SERVICE="dotnet8-sqlserver-hello"

echo "Checking collector health..."
curl -sf http://localhost:13133/health | grep -q "Server available"
echo "OK"

echo "Waiting for the API to become healthy (up to 90s)..."
for _ in $(seq 1 18); do
    if curl -sf http://localhost:8080/api/health > /dev/null; then
        break
    fi
    sleep 5
done
curl -sf http://localhost:8080/api/health > /dev/null || { echo "API not healthy. Inspect: docker compose logs api"; exit 1; }
echo "OK"

echo "Generating traffic..."
./scripts/test-api.sh > /dev/null
echo "OK"

echo "Waiting for the first metrics export (up to 90s)..."
for _ in $(seq 1 18); do
    if docker compose logs --no-color otel-collector 2>/dev/null | grep -q "http.server.request.duration"; then
        break
    fi
    sleep 5
done

LOGS=$(docker compose logs --no-color otel-collector 2>/dev/null)

expect() {
    if echo "$LOGS" | grep -q -- "$1"; then
        echo "found: $2"
    else
        echo "MISSING: $2"
        MISSING=1
    fi
}

expect "service.name: Str($SERVICE)" "resource service.name"
expect "process.runtime.version: Str(8.0.22)" "resource runtime version 8.0.22"
expect "telemetry.distro.name: Str(opentelemetry-dotnet-instrumentation)" "auto-instrumentation distro"
expect "Name           : GET /api/hello/{name}" "ASP.NET Core server span"
expect "db.system.name: Str(microsoft.sql_server)" "SqlClient span"
expect "http.server.request.duration" "ASP.NET Core request duration metric"
expect "process.runtime.dotnet" "runtime metric"
expect "Greeted World" "ILogger record"

if [ -z "$MISSING" ]; then
    echo "All signals received."
else
    echo "Some signals missing. Inspect: docker compose logs otel-collector"
    exit 1
fi
