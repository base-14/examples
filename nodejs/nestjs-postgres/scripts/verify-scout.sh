#!/bin/bash

set -e

BASE_URL="${BASE_URL:-http://localhost:3000}"
METRICS_URL="${METRICS_URL:-http://localhost:9464}"
COLLECTOR_HEALTH="${COLLECTOR_HEALTH:-http://localhost:13133}"
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo "Verifying Scout Integration"
echo "==========================="
echo ""

# Check app health
echo -n "App health... "
APP_HEALTH=$(curl -s "$BASE_URL/api/health" 2>/dev/null || echo "")
if echo "$APP_HEALTH" | grep -q '"status":"ok"'; then
    echo -e "${GREEN}OK${NC}"
else
    echo -e "${RED}FAIL${NC}"
    echo "App is not healthy or not running"
    exit 1
fi

# Check collector health
echo -n "OTel Collector health... "
COLLECTOR=$(curl -s "$COLLECTOR_HEALTH" 2>/dev/null || echo "")
if [ -n "$COLLECTOR" ]; then
    echo -e "${GREEN}OK${NC}"
else
    echo -e "${RED}FAIL${NC}"
    echo "Collector is not running"
    exit 1
fi

# Check Prometheus metrics endpoint
echo -n "Prometheus metrics... "
METRICS=$(curl -s "$METRICS_URL/metrics" 2>/dev/null || echo "")
if echo "$METRICS" | grep -q "# HELP"; then
    echo -e "${GREEN}OK${NC}"
else
    echo -e "${RED}FAIL${NC}"
    echo "Prometheus metrics endpoint not responding"
    exit 1
fi

# Generate some telemetry
echo ""
echo "Generating telemetry..."
EMAIL="scout-test-$(date +%s)@example.com"

# Register and login to generate auth metrics
curl -s -X POST "$BASE_URL/api/auth/register" \
    -H "Content-Type: application/json" \
    -d "{\"email\":\"$EMAIL\",\"password\":\"Password123\",\"name\":\"Scout Test\"}" > /dev/null

TOKEN=$(curl -s -X POST "$BASE_URL/api/auth/login" \
    -H "Content-Type: application/json" \
    -d "{\"email\":\"$EMAIL\",\"password\":\"Password123\"}" | grep -o '"token":"[^"]*"' | cut -d'"' -f4)

# Create article to generate article metrics
ARTICLE_ID=$(curl -s -X POST "$BASE_URL/api/articles" \
    -H "Content-Type: application/json" \
    -H "Authorization: Bearer $TOKEN" \
    -d '{"title":"Scout Test Article","content":"Testing telemetry for observability demo."}' | grep -o '"id":"[^"]*"' | head -1 | cut -d'"' -f4)

# Publish article to demonstrate trace propagation (HTTP → Queue → Worker → WebSocket)
curl -s -X POST "$BASE_URL/api/articles/$ARTICLE_ID/publish" \
    -H "Authorization: Bearer $TOKEN" > /dev/null

# Wait for background job to process
sleep 2

# Favorite to generate favorite metrics
curl -s -X POST "$BASE_URL/api/articles/$ARTICLE_ID/favorite" \
    -H "Authorization: Bearer $TOKEN" > /dev/null

# Generate an error for error logging
curl -s "$BASE_URL/api/articles/00000000-0000-0000-0000-000000000000" > /dev/null

# Cleanup
curl -s -X DELETE "$BASE_URL/api/articles/$ARTICLE_ID" \
    -H "Authorization: Bearer $TOKEN" > /dev/null

echo -e "${GREEN}Done${NC}"

# Wait for metrics to be collected
echo ""
echo "Waiting for metrics collection..."
sleep 3

# Verify custom metrics exist
echo ""
echo "Verifying custom metrics..."

echo -n "auth.registration.total... "
if curl -s "$METRICS_URL/metrics" | grep -q "auth_registration_total"; then
    echo -e "${GREEN}OK${NC}"
else
    echo -e "${YELLOW}PENDING${NC} (may need more time)"
fi

echo -n "auth.login.success... "
if curl -s "$METRICS_URL/metrics" | grep -q "auth_login_success"; then
    echo -e "${GREEN}OK${NC}"
else
    echo -e "${YELLOW}PENDING${NC} (may need more time)"
fi

echo -n "articles.created... "
if curl -s "$METRICS_URL/metrics" | grep -q "articles_created"; then
    echo -e "${GREEN}OK${NC}"
else
    echo -e "${YELLOW}PENDING${NC} (may need more time)"
fi

echo -n "articles.favorited... "
if curl -s "$METRICS_URL/metrics" | grep -q "articles_favorited"; then
    echo -e "${GREEN}OK${NC}"
else
    echo -e "${YELLOW}PENDING${NC} (may need more time)"
fi

echo -n "articles.published... "
if curl -s "$METRICS_URL/metrics" | grep -q "articles_published"; then
    echo -e "${GREEN}OK${NC}"
else
    echo -e "${YELLOW}PENDING${NC} (may need more time)"
fi

echo -n "jobs.completed... "
if curl -s "$METRICS_URL/metrics" | grep -q "jobs_completed"; then
    echo -e "${GREEN}OK${NC}"
else
    echo -e "${YELLOW}PENDING${NC} (may need more time)"
fi

echo -n "job_queue_waiting (gauge)... "
if curl -s "$METRICS_URL/metrics" | grep -q "job_queue_waiting"; then
    echo -e "${GREEN}OK${NC}"
else
    echo -e "${YELLOW}PENDING${NC} (may need more time)"
fi

echo -n "http_errors_total... "
if curl -s "$METRICS_URL/metrics" | grep -q "http_errors_total"; then
    echo -e "${GREEN}OK${NC}"
else
    echo -e "${YELLOW}PENDING${NC} (may need more time)"
fi

echo ""
echo "Verification Summary"
echo "===================="
echo "- App: Running with health check"
echo "- Collector: Running and receiving telemetry"
echo "- Prometheus: Metrics endpoint available at $METRICS_URL/metrics"
echo ""
echo -e "${GREEN}To view traces in Scout:${NC}"
echo "1. Log into your base14 Scout dashboard"
echo "2. Navigate to TraceX"
echo "3. Filter by service: nestjs-postgres-app"
echo ""
echo -e "${GREEN}Expected traces:${NC}"
echo "- auth.register, auth.login, auth.getProfile"
echo "- article.create, article.findAll, article.findOne"
echo "- article.update, article.delete, article.favorite"
echo ""
echo -e "${GREEN}Trace propagation demo (HTTP → Queue → Worker → WebSocket):${NC}"
echo "- article.publish (HTTP endpoint)"
echo "  └── job.process (BullMQ worker, linked via trace context)"
echo "      ├── article.publish.update (database update)"
echo "      ├── notification.send (simulated email)"
echo "      └── websocket.emit (real-time event)"
echo ""
echo -e "${GREEN}Auto-instrumented:${NC}"
echo "- PostgreSQL queries (via pg instrumentation)"
echo "- Redis commands (via ioredis instrumentation)"
echo "- HTTP requests (via http instrumentation)"
echo ""
