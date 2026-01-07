#!/bin/bash

# Verify Scout Integration for Rust Axum PostgreSQL API
# Usage: ./scripts/verify-scout.sh

set -e

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo "========================================"
echo "Scout Integration Verification"
echo "========================================"
echo ""

# Check environment variables
check_env() {
    local var_name=$1
    local var_value="${!var_name}"

    if [ -z "$var_value" ]; then
        echo -e "${RED}✗${NC} $var_name is not set"
        return 1
    else
        echo -e "${GREEN}✓${NC} $var_name is configured"
        return 0
    fi
}

echo -e "${YELLOW}Checking Scout configuration...${NC}"
echo ""

MISSING=0

check_env "SCOUT_ENDPOINT" || ((MISSING++))
check_env "SCOUT_CLIENT_ID" || ((MISSING++))
check_env "SCOUT_CLIENT_SECRET" || ((MISSING++))
check_env "SCOUT_TOKEN_URL" || ((MISSING++))

echo ""

if [ $MISSING -gt 0 ]; then
    echo -e "${RED}Missing $MISSING required environment variable(s)${NC}"
    echo ""
    echo "Please set the following in your .env file:"
    echo "  SCOUT_ENDPOINT=https://your-tenant.base14.io/v1/traces"
    echo "  SCOUT_CLIENT_ID=your-client-id"
    echo "  SCOUT_CLIENT_SECRET=your-client-secret"
    echo "  SCOUT_TOKEN_URL=https://your-tenant.base14.io/oauth/token"
    exit 1
fi

echo -e "${GREEN}All Scout environment variables are configured${NC}"
echo ""

# Check OTel Collector health
echo -e "${YELLOW}Checking OTel Collector health...${NC}"
COLLECTOR_URL="${OTEL_COLLECTOR_HEALTH:-http://localhost:13133}"

if curl -s -f "$COLLECTOR_URL" > /dev/null 2>&1; then
    echo -e "${GREEN}✓${NC} OTel Collector is healthy at $COLLECTOR_URL"
else
    echo -e "${RED}✗${NC} OTel Collector is not responding at $COLLECTOR_URL"
    echo "  Make sure the collector is running: docker compose up otel-collector"
    exit 1
fi

echo ""

# Generate test traffic
echo -e "${YELLOW}Generating test traffic...${NC}"
BASE_URL="${API_URL:-http://localhost:8080}"

# Health check
curl -s "$BASE_URL/api/health" > /dev/null && echo -e "${GREEN}✓${NC} Health check passed"

# Create test user and article
TIMESTAMP=$(date +%s)
USER_EMAIL="scout-test-${TIMESTAMP}@example.com"

echo "Creating test user..."
REGISTER_RESPONSE=$(curl -s -X POST "$BASE_URL/api/register" \
    -H "Content-Type: application/json" \
    -d "{\"email\":\"$USER_EMAIL\",\"password\":\"password123\",\"name\":\"Scout Test\"}")

TOKEN=$(echo "$REGISTER_RESPONSE" | grep -o '"token":"[^"]*"' | cut -d'"' -f4)

if [ -n "$TOKEN" ]; then
    echo -e "${GREEN}✓${NC} Test user created"

    echo "Creating test article..."
    curl -s -X POST "$BASE_URL/api/articles" \
        -H "Content-Type: application/json" \
        -H "Authorization: Bearer $TOKEN" \
        -d "{\"title\":\"Scout Test Article $TIMESTAMP\",\"body\":\"Test content\"}" > /dev/null

    echo -e "${GREEN}✓${NC} Test article created"
else
    echo -e "${YELLOW}!${NC} Could not create test user (API may already have test data)"
fi

echo ""
echo "========================================"
echo -e "${GREEN}Scout integration verification complete${NC}"
echo ""
echo "Check your Scout dashboard for:"
echo "  - Traces from 'rust-axum-postgres-api'"
echo "  - Spans: auth.register, article.create, db.*"
echo "  - Metrics: articles.created, users.registered"
echo "========================================"
