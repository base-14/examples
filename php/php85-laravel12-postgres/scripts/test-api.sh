#!/bin/bash

# Laravel 12 + PostgreSQL + OpenTelemetry API Testing Script
# Tests all API endpoints and validates response status codes

set -e

API_URL=${API_URL:-http://localhost:8000}
PASSED=0
FAILED=0

echo "=== Laravel 12 API Testing Script ==="
echo "Target: $API_URL"
echo ""

test_endpoint() {
    local description="$1"
    local method="$2"
    local endpoint="$3"
    local data="$4"
    local expected_status="$5"
    local auth_header="$6"

    local curl_args=(-s -w "\n%{http_code}" -X "$method" "$API_URL$endpoint")
    curl_args+=(-H "Content-Type: application/json" -H "Accept: application/json")

    if [ -n "$auth_header" ]; then
        curl_args+=(-H "Authorization: Bearer $auth_header")
    fi

    if [ -n "$data" ]; then
        curl_args+=(-d "$data")
    fi

    local response
    response=$(curl "${curl_args[@]}")
    local body
    body=$(echo "$response" | sed '$d')
    local status
    status=$(echo "$response" | tail -n1)

    if [ "$status" -eq "$expected_status" ]; then
        echo "[PASS] $description (HTTP $status)"
        ((PASSED++))
        echo "$body"
    else
        echo "[FAIL] $description - Expected $expected_status, got $status"
        ((FAILED++))
        echo "$body"
    fi
}

extract_json() {
    local json="$1"
    local field="$2"
    echo "$json" | jq -r "$field"
}

SUFFIX=$(date +%s)

# Health check
echo ""
echo "=== System Endpoints ==="
HEALTH_RESPONSE=$(curl -s "$API_URL/api/health")
HEALTH_STATUS=$(echo "$HEALTH_RESPONSE" | jq -r '.status')
if [ "$HEALTH_STATUS" = "healthy" ]; then
    echo "[PASS] Health check (status: healthy)"
    ((PASSED++))
else
    echo "[FAIL] Health check - Expected healthy, got $HEALTH_STATUS"
    ((FAILED++))
fi

METRICS_STATUS=$(curl -s -o /dev/null -w "%{http_code}" "$API_URL/api/metrics")
if [ "$METRICS_STATUS" -eq 200 ]; then
    echo "[PASS] Metrics endpoint (HTTP 200)"
    ((PASSED++))
else
    echo "[FAIL] Metrics endpoint - Expected 200, got $METRICS_STATUS"
    ((FAILED++))
fi

# User registration
echo ""
echo "=== Authentication ==="
ALICE_RESPONSE=$(curl -s -X POST "$API_URL/api/register" \
    -H "Content-Type: application/json" \
    -H "Accept: application/json" \
    -d "{\"name\":\"Alice Smith\",\"email\":\"alice-$SUFFIX@example.com\",\"password\":\"password123\"}")

ALICE_TOKEN=$(echo "$ALICE_RESPONSE" | jq -r '.user.token // .token // empty')
if [ -n "$ALICE_TOKEN" ] && [ "$ALICE_TOKEN" != "null" ]; then
    echo "[PASS] Register Alice (token received)"
    ((PASSED++))
else
    echo "[FAIL] Register Alice - No token in response"
    echo "$ALICE_RESPONSE"
    ((FAILED++))
fi

BOB_RESPONSE=$(curl -s -X POST "$API_URL/api/register" \
    -H "Content-Type: application/json" \
    -H "Accept: application/json" \
    -d "{\"name\":\"Bob Jones\",\"email\":\"bob-$SUFFIX@example.com\",\"password\":\"password123\"}")

BOB_TOKEN=$(echo "$BOB_RESPONSE" | jq -r '.user.token // .token // empty')
if [ -n "$BOB_TOKEN" ] && [ "$BOB_TOKEN" != "null" ]; then
    echo "[PASS] Register Bob (token received)"
    ((PASSED++))
else
    echo "[FAIL] Register Bob - No token in response"
    ((FAILED++))
fi

# Login test
LOGIN_RESPONSE=$(curl -s -X POST "$API_URL/api/login" \
    -H "Content-Type: application/json" \
    -H "Accept: application/json" \
    -d "{\"email\":\"alice-$SUFFIX@example.com\",\"password\":\"password123\"}")

LOGIN_TOKEN=$(echo "$LOGIN_RESPONSE" | jq -r '.user.token // .token // empty')
if [ -n "$LOGIN_TOKEN" ] && [ "$LOGIN_TOKEN" != "null" ]; then
    echo "[PASS] Login Alice (token received)"
    ((PASSED++))
else
    echo "[FAIL] Login Alice - No token in response"
    ((FAILED++))
fi

# Get current user
USER_STATUS=$(curl -s -o /dev/null -w "%{http_code}" "$API_URL/api/user" \
    -H "Authorization: Bearer $ALICE_TOKEN" \
    -H "Accept: application/json")
if [ "$USER_STATUS" -eq 200 ]; then
    echo "[PASS] Get current user (HTTP 200)"
    ((PASSED++))
else
    echo "[FAIL] Get current user - Expected 200, got $USER_STATUS"
    ((FAILED++))
fi

# Article CRUD
echo ""
echo "=== Article CRUD ==="

# Create article
ARTICLE1_RESPONSE=$(curl -s -X POST "$API_URL/api/articles" \
    -H "Authorization: Bearer $ALICE_TOKEN" \
    -H "Content-Type: application/json" \
    -H "Accept: application/json" \
    -d '{"title":"Getting Started with Laravel 12","description":"A guide to Laravel 12","body":"Laravel 12 introduces many features.","tagList":["laravel","php","tutorial"]}')

ARTICLE1_ID=$(echo "$ARTICLE1_RESPONSE" | jq -r '.article.id // empty')
if [ -n "$ARTICLE1_ID" ] && [ "$ARTICLE1_ID" != "null" ]; then
    echo "[PASS] Create article (ID: $ARTICLE1_ID)"
    ((PASSED++))
else
    echo "[FAIL] Create article - No ID in response"
    echo "$ARTICLE1_RESPONSE"
    ((FAILED++))
fi

# List articles
ARTICLES_STATUS=$(curl -s -o /dev/null -w "%{http_code}" "$API_URL/api/articles" \
    -H "Accept: application/json")
if [ "$ARTICLES_STATUS" -eq 200 ]; then
    echo "[PASS] List articles (HTTP 200)"
    ((PASSED++))
else
    echo "[FAIL] List articles - Expected 200, got $ARTICLES_STATUS"
    ((FAILED++))
fi

# Get single article
if [ -n "$ARTICLE1_ID" ]; then
    ARTICLE_STATUS=$(curl -s -o /dev/null -w "%{http_code}" "$API_URL/api/articles/$ARTICLE1_ID" \
        -H "Accept: application/json")
    if [ "$ARTICLE_STATUS" -eq 200 ]; then
        echo "[PASS] Get article $ARTICLE1_ID (HTTP 200)"
        ((PASSED++))
    else
        echo "[FAIL] Get article - Expected 200, got $ARTICLE_STATUS"
        ((FAILED++))
    fi
fi

# Update article
if [ -n "$ARTICLE1_ID" ]; then
    UPDATE_STATUS=$(curl -s -o /dev/null -w "%{http_code}" -X PUT "$API_URL/api/articles/$ARTICLE1_ID" \
        -H "Authorization: Bearer $ALICE_TOKEN" \
        -H "Content-Type: application/json" \
        -H "Accept: application/json" \
        -d '{"title":"Updated Laravel 12 Guide"}')
    if [ "$UPDATE_STATUS" -eq 200 ]; then
        echo "[PASS] Update article (HTTP 200)"
        ((PASSED++))
    else
        echo "[FAIL] Update article - Expected 200, got $UPDATE_STATUS"
        ((FAILED++))
    fi
fi

# Social features
echo ""
echo "=== Social Features ==="

# Favorite article
if [ -n "$ARTICLE1_ID" ]; then
    FAV_STATUS=$(curl -s -o /dev/null -w "%{http_code}" -X POST "$API_URL/api/articles/$ARTICLE1_ID/favorite" \
        -H "Authorization: Bearer $BOB_TOKEN" \
        -H "Accept: application/json")
    if [ "$FAV_STATUS" -eq 200 ]; then
        echo "[PASS] Favorite article (HTTP 200)"
        ((PASSED++))
    else
        echo "[FAIL] Favorite article - Expected 200, got $FAV_STATUS"
        ((FAILED++))
    fi
fi

# Unfavorite article
if [ -n "$ARTICLE1_ID" ]; then
    UNFAV_STATUS=$(curl -s -o /dev/null -w "%{http_code}" -X DELETE "$API_URL/api/articles/$ARTICLE1_ID/favorite" \
        -H "Authorization: Bearer $BOB_TOKEN" \
        -H "Accept: application/json")
    if [ "$UNFAV_STATUS" -eq 200 ]; then
        echo "[PASS] Unfavorite article (HTTP 200)"
        ((PASSED++))
    else
        echo "[FAIL] Unfavorite article - Expected 200, got $UNFAV_STATUS"
        ((FAILED++))
    fi
fi

# Tags
echo ""
echo "=== Tags ==="
TAGS_STATUS=$(curl -s -o /dev/null -w "%{http_code}" "$API_URL/api/tags" \
    -H "Accept: application/json")
if [ "$TAGS_STATUS" -eq 200 ]; then
    echo "[PASS] List tags (HTTP 200)"
    ((PASSED++))
else
    echo "[FAIL] List tags - Expected 200, got $TAGS_STATUS"
    ((FAILED++))
fi

# Delete article
echo ""
echo "=== Cleanup ==="
if [ -n "$ARTICLE1_ID" ]; then
    DELETE_STATUS=$(curl -s -o /dev/null -w "%{http_code}" -X DELETE "$API_URL/api/articles/$ARTICLE1_ID" \
        -H "Authorization: Bearer $ALICE_TOKEN" \
        -H "Accept: application/json")
    if [ "$DELETE_STATUS" -eq 200 ]; then
        echo "[PASS] Delete article (HTTP 200)"
        ((PASSED++))
    else
        echo "[FAIL] Delete article - Expected 200, got $DELETE_STATUS"
        ((FAILED++))
    fi
fi

# Telemetry check
echo ""
echo "=== Telemetry ==="
TRACE_COUNT=$(docker logs otel-collector 2>&1 | grep -c "Span" || true)
if [ "$TRACE_COUNT" -gt 0 ]; then
    echo "[PASS] OTel Collector captured spans ($TRACE_COUNT found)"
    ((PASSED++))
else
    echo "[WARN] No spans found in OTel Collector logs"
fi

# Summary
echo ""
echo "========================================="
echo "           TEST SUMMARY"
echo "========================================="
echo "Passed: $PASSED"
echo "Failed: $FAILED"
echo "Total:  $((PASSED + FAILED))"
echo "========================================="

if [ "$FAILED" -gt 0 ]; then
    echo "Some tests failed!"
    exit 1
else
    echo "All tests passed!"
    exit 0
fi
