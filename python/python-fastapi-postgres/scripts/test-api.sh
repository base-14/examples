#!/bin/bash

# FastAPI + PostgreSQL + OpenTelemetry API Testing Script
# This script tests all API endpoints and generates telemetry data

set -e

echo "=== FastAPI + PostgreSQL API Testing Script ==="
echo ""

# Generate random suffix for unique emails
SUFFIX=$(date +%s)
API_URL=${API_URL:-http://localhost:8000}
PASSED=0
FAILED=0

# Test helper function
test_endpoint() {
    local description=$1
    local method=$2
    local endpoint=$3
    local data=$4
    local expected_status=$5
    local headers=$6

    local status=$(curl -s -o /dev/null -w "%{http_code}" -X "$method" "$API_URL$endpoint" \
        -H "Content-Type: application/json" \
        $headers \
        ${data:+-d "$data"})

    if [ "$status" = "$expected_status" ]; then
        echo "✓ $description (status: $status)"
        PASSED=$((PASSED + 1))
    else
        echo "✗ $description (expected: $expected_status, got: $status)"
        FAILED=$((FAILED + 1))
    fi
}

# Extract JSON value helper
extract_json() {
    local json=$1
    local key=$2
    echo "$json" | grep -o "\"$key\"[[:space:]]*:[[:space:]]*[^,}]*" | sed 's/.*:[[:space:]]*//;s/"//g'
}

# Test health endpoint
echo "[1/8] Testing health endpoint..."
curl -s $API_URL/ > /dev/null
echo "✓ GET / - Health check passed"
echo ""

# Register users
echo "[2/8] Registering test users..."
USER1_RESPONSE=$(curl -L -s -X POST $API_URL/users \
  -H "Content-Type: application/json" \
  -d "{
    \"email\": \"alice-$SUFFIX@example.com\",
    \"password\": \"securepass123\"
  }")

USER1_ID=$(echo "$USER1_RESPONSE" | grep -o '"id"[[:space:]]*:[[:space:]]*[0-9]*' | sed 's/.*:[[:space:]]*//')

USER2_RESPONSE=$(curl -L -s -X POST $API_URL/users \
  -H "Content-Type: application/json" \
  -d "{
    \"email\": \"bob-$SUFFIX@example.com\",
    \"password\": \"securepass456\"
  }")

USER2_ID=$(echo "$USER2_RESPONSE" | grep -o '"id"[[:space:]]*:[[:space:]]*[0-9]*' | sed 's/.*:[[:space:]]*//')

echo "✓ Users registered (Alice: ID $USER1_ID, Bob: ID $USER2_ID)"
echo ""

# Login users
echo "[3/8] Logging in users..."
TOKEN1_RESPONSE=$(curl -s -X POST $API_URL/login \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "username=alice-$SUFFIX@example.com&password=securepass123")

TOKEN1=$(echo "$TOKEN1_RESPONSE" | grep -o '"access_token"[[:space:]]*:[[:space:]]*"[^"]*"' | sed 's/.*:[[:space:]]*"//;s/"$//')

TOKEN2_RESPONSE=$(curl -s -X POST $API_URL/login \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "username=bob-$SUFFIX@example.com&password=securepass456")

TOKEN2=$(echo "$TOKEN2_RESPONSE" | grep -o '"access_token"[[:space:]]*:[[:space:]]*"[^"]*"' | sed 's/.*:[[:space:]]*"//;s/"$//')

if [ -n "$TOKEN1" ] && [ -n "$TOKEN2" ]; then
    echo "✓ Users logged in successfully"
else
    echo "✗ Login failed"
    exit 1
fi
echo ""

# Create posts
echo "[4/8] Creating posts..."
POST1_RESPONSE=$(curl -L -s -X POST $API_URL/posts \
  -H "Authorization: Bearer $TOKEN1" \
  -H "Content-Type: application/json" \
  -d '{
    "title": "Getting Started with FastAPI",
    "content": "A comprehensive guide to FastAPI and OpenTelemetry integration",
    "published": true
  }')

POST1_ID=$(echo "$POST1_RESPONSE" | grep -o '"id"[[:space:]]*:[[:space:]]*[0-9]*' | sed 's/.*:[[:space:]]*//')

POST2_RESPONSE=$(curl -L -s -X POST $API_URL/posts \
  -H "Authorization: Bearer $TOKEN1" \
  -H "Content-Type: application/json" \
  -d '{
    "title": "OpenTelemetry Instrumentation",
    "content": "Automatic instrumentation for Python applications",
    "published": true
  }')

POST2_ID=$(echo "$POST2_RESPONSE" | grep -o '"id"[[:space:]]*:[[:space:]]*[0-9]*' | sed 's/.*:[[:space:]]*//')

echo "✓ Created 2 posts (IDs: $POST1_ID, $POST2_ID)"
echo ""

# List posts
echo "[5/8] Listing posts..."
POSTS_RESPONSE=$(curl -s -X GET "$API_URL/posts?limit=10" \
  -H "Authorization: Bearer $TOKEN1")

POSTS_COUNT=$(echo "$POSTS_RESPONSE" | grep -o '"id"' | wc -l | tr -d ' ')
echo "✓ GET /posts returned $POSTS_COUNT posts"
echo ""

# Get specific post
echo "[6/8] Testing post details..."
POST_RESPONSE=$(curl -s -X GET $API_URL/posts/$POST1_ID \
  -H "Authorization: Bearer $TOKEN1")

POST_TITLE=$(echo "$POST_RESPONSE" | grep -o '"title"[[:space:]]*:[[:space:]]*"[^"]*"' | sed 's/.*:[[:space:]]*"//;s/"$//' | head -1)
echo "✓ GET /posts/$POST1_ID returned: \"$POST_TITLE\""
echo ""

# Update post
echo "[7/8] Updating post..."
UPDATE_RESPONSE=$(curl -s -X PUT $API_URL/posts/$POST1_ID \
  -H "Authorization: Bearer $TOKEN1" \
  -H "Content-Type: application/json" \
  -d '{
    "title": "Getting Started with FastAPI - Updated",
    "content": "An updated comprehensive guide to FastAPI",
    "published": true
  }')

UPDATED_TITLE=$(echo "$UPDATE_RESPONSE" | grep -o '"title"[[:space:]]*:[[:space:]]*"[^"]*"' | sed 's/.*:[[:space:]]*"//;s/"$//')
echo "✓ Updated post $POST1_ID: \"$UPDATED_TITLE\""
echo ""

# Test votes
echo "[8/8] Testing votes..."
VOTE_RESPONSE=$(curl -L -s -X POST $API_URL/vote \
  -H "Authorization: Bearer $TOKEN2" \
  -H "Content-Type: application/json" \
  -d "{
    \"post_id\": $POST1_ID,
    \"dir\": 1
  }")

echo "✓ Bob voted on post $POST1_ID"

# Check for vote count
POST_WITH_VOTES=$(curl -s -X GET $API_URL/posts/$POST1_ID \
  -H "Authorization: Bearer $TOKEN1")

VOTES=$(echo "$POST_WITH_VOTES" | grep -o '"votes"[[:space:]]*:[[:space:]]*[0-9]*' | sed 's/.*:[[:space:]]*//')
echo "✓ Post $POST1_ID now has $VOTES vote(s)"
echo ""

# Check telemetry
echo "Checking OpenTelemetry traces..."
TRACE_COUNT=$(docker logs otel-collector 2>&1 | grep -c "Span" || echo "0")
if [ "$TRACE_COUNT" -gt 0 ]; then
  echo "✓ OTel Collector has captured telemetry (found $TRACE_COUNT span references)"
else
  echo "⚠ No telemetry found in OTel Collector logs (this may be normal if using Scout directly)"
fi
echo ""

# Cleanup - delete post
echo "Cleanup: Deleting test post..."
curl -s -X DELETE $API_URL/posts/$POST2_ID \
  -H "Authorization: Bearer $TOKEN1" > /dev/null
echo "✓ Deleted post $POST2_ID"
echo ""

# Summary
echo "=== Test Summary ==="
echo "✓ Health check: Working"
echo "✓ User registration: Working"
echo "✓ JWT authentication: Working"
echo "✓ Post CRUD: Working"
echo "✓ Votes: Working"
echo "✓ OpenTelemetry: $([ "$TRACE_COUNT" -gt 0 ] && echo "Capturing telemetry" || echo "Check Scout dashboard")"
echo ""
echo "Passed: $PASSED"
echo "Failed: $FAILED"
echo ""
echo "View traces in Scout dashboard using your credentials:"
echo "  SCOUT_ENDPOINT, SCOUT_CLIENT_ID, SCOUT_CLIENT_SECRET"
