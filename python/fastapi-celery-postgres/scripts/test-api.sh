#!/bin/bash
set -e

# Configuration
API_URL=${API_URL:-http://localhost:8000}
TIMESTAMP=$(date +%s)
PASSED=0
FAILED=0

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Test function with status code validation
test_endpoint() {
    local description="$1"
    local method="$2"
    local path="$3"
    local data="$4"
    local expected_status="$5"

    echo -n "Testing: $description... "

    if [ "$method" = "GET" ]; then
        response=$(curl -s -w "\n%{http_code}" -X GET "$API_URL$path")
    elif [ "$method" = "POST" ]; then
        response=$(curl -s -w "\n%{http_code}" -X POST "$API_URL$path" \
            -H "Content-Type: application/json" \
            -d "$data")
    elif [ "$method" = "DELETE" ]; then
        response=$(curl -s -w "\n%{http_code}" -X DELETE "$API_URL$path")
    fi

    status_code=$(echo "$response" | tail -n 1)
    body=$(echo "$response" | sed '$d')

    if [ "$status_code" = "$expected_status" ]; then
        echo -e "${GREEN}PASSED${NC} (HTTP $status_code)"
        ((PASSED++))
        echo "$body"
        return 0
    else
        echo -e "${RED}FAILED${NC} (Expected $expected_status, got $status_code)"
        ((FAILED++))
        echo "$body"
        return 1
    fi
}

# Extract JSON value (simple extraction for common fields)
extract_json() {
    local json="$1"
    local key="$2"
    echo "$json" | grep -o "\"$key\":[^,}]*" | sed 's/"'$key'"://' | tr -d '"' | head -1
}

echo "========================================"
echo "FastAPI + Celery + PostgreSQL API Tests"
echo "========================================"
echo "API URL: $API_URL"
echo "Timestamp: $TIMESTAMP"
echo ""

# Wait for services to be ready
echo "Waiting for services to be ready..."
for i in {1..30}; do
    if curl -s "$API_URL/ping" > /dev/null 2>&1; then
        echo "Services are ready!"
        break
    fi
    echo "Waiting... ($i/30)"
    sleep 2
done

echo ""
echo "=== Health Check ==="
test_endpoint "Health check (ping)" GET "/ping" "" 200 || true

echo ""
echo "=== Task Operations ==="

# Create a task
echo ""
TASK_TITLE="Test Task $TIMESTAMP"
RESPONSE=$(curl -s -X POST "$API_URL/tasks/" \
    -H "Content-Type: application/json" \
    -d "{\"title\": \"$TASK_TITLE\"}")

TASK_ID=$(echo "$RESPONSE" | grep -o '"id":[0-9]*' | sed 's/"id"://')

if [ -n "$TASK_ID" ]; then
    echo -e "Created task with ID: $TASK_ID ${GREEN}PASSED${NC}"
    ((PASSED++))
else
    echo -e "Failed to create task ${RED}FAILED${NC}"
    ((FAILED++))
fi

# List tasks
echo ""
test_endpoint "List all tasks" GET "/tasks/" "" 200 || true

# Get specific task
if [ -n "$TASK_ID" ]; then
    echo ""
    test_endpoint "Get task by ID ($TASK_ID)" GET "/tasks/$TASK_ID" "" 200 || true
fi

# Get non-existent task (should return 404)
echo ""
test_endpoint "Get non-existent task (expect 404)" GET "/tasks/99999" "" 404 || true

# Create another task to test pagination
echo ""
RESPONSE=$(curl -s -X POST "$API_URL/tasks/" \
    -H "Content-Type: application/json" \
    -d "{\"title\": \"Second Task $TIMESTAMP\"}")
echo "Created second task for pagination test"

# Test pagination parameters
echo ""
test_endpoint "List tasks with pagination (skip=0, limit=1)" GET "/tasks/?skip=0&limit=1" "" 200 || true

echo ""
echo "========================================"
echo "Test Summary"
echo "========================================"
echo -e "Passed: ${GREEN}$PASSED${NC}"
echo -e "Failed: ${RED}$FAILED${NC}"
echo ""

if [ $FAILED -gt 0 ]; then
    echo -e "${RED}Some tests failed!${NC}"
    exit 1
else
    echo -e "${GREEN}All tests passed!${NC}"
    exit 0
fi
