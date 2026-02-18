#!/bin/bash

# Slim 4 + MongoDB + OpenTelemetry API Testing Script
# Tests all API endpoints and validates response status codes

set -e

API_URL=${API_URL:-http://localhost:8080}
PASSED=0
FAILED=0

echo "=== Slim 4 + MongoDB API Testing Script ==="
echo "Target: $API_URL"
echo ""

extract_json() {
    local json="$1"
    local field="$2"
    echo "$json" | jq -r "$field"
}

SUFFIX=$(date +%s)

# Health check
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

ALICE_TOKEN=$(echo "$ALICE_RESPONSE" | jq -r '.user.token // empty')
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

BOB_TOKEN=$(echo "$BOB_RESPONSE" | jq -r '.user.token // empty')
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

LOGIN_TOKEN=$(echo "$LOGIN_RESPONSE" | jq -r '.user.token // empty')
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
    -d '{"title":"Getting Started with Slim 4","description":"A guide to Slim 4","body":"Slim 4 is a modern micro-framework for PHP.","tagList":["slim","php","tutorial"]}')

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
        -d '{"title":"Updated Slim 4 Guide"}')
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

# Error scenarios
echo ""
echo "=== Error Scenarios ==="

# 404 - Article not found
NOT_FOUND_STATUS=$(curl -s -o /dev/null -w "%{http_code}" "$API_URL/api/articles/000000000000000000000000" \
    -H "Accept: application/json")
if [ "$NOT_FOUND_STATUS" -eq 404 ]; then
    echo "[PASS] Article not found (HTTP 404)"
    ((PASSED++))
else
    echo "[FAIL] Article not found - Expected 404, got $NOT_FOUND_STATUS"
    ((FAILED++))
fi

# 404 - Invalid ObjectId
INVALID_ID_STATUS=$(curl -s -o /dev/null -w "%{http_code}" "$API_URL/api/articles/invalid-id" \
    -H "Accept: application/json")
if [ "$INVALID_ID_STATUS" -eq 404 ]; then
    echo "[PASS] Invalid article ID (HTTP 404)"
    ((PASSED++))
else
    echo "[FAIL] Invalid article ID - Expected 404, got $INVALID_ID_STATUS"
    ((FAILED++))
fi

# 401 - Missing auth token
NO_AUTH_STATUS=$(curl -s -o /dev/null -w "%{http_code}" -X POST "$API_URL/api/articles" \
    -H "Content-Type: application/json" \
    -H "Accept: application/json" \
    -d '{"title":"Test","body":"Test"}')
if [ "$NO_AUTH_STATUS" -eq 401 ]; then
    echo "[PASS] Missing auth token (HTTP 401)"
    ((PASSED++))
else
    echo "[FAIL] Missing auth token - Expected 401, got $NO_AUTH_STATUS"
    ((FAILED++))
fi

# 401 - Invalid auth token
BAD_TOKEN_STATUS=$(curl -s -o /dev/null -w "%{http_code}" -X POST "$API_URL/api/articles" \
    -H "Authorization: Bearer invalid.token.here" \
    -H "Content-Type: application/json" \
    -H "Accept: application/json" \
    -d '{"title":"Test","body":"Test"}')
if [ "$BAD_TOKEN_STATUS" -eq 401 ]; then
    echo "[PASS] Invalid auth token (HTTP 401)"
    ((PASSED++))
else
    echo "[FAIL] Invalid auth token - Expected 401, got $BAD_TOKEN_STATUS"
    ((FAILED++))
fi

# 422 - Registration validation
REG_VALIDATION_STATUS=$(curl -s -o /dev/null -w "%{http_code}" -X POST "$API_URL/api/register" \
    -H "Content-Type: application/json" \
    -H "Accept: application/json" \
    -d '{}')
if [ "$REG_VALIDATION_STATUS" -eq 422 ]; then
    echo "[PASS] Registration validation (HTTP 422)"
    ((PASSED++))
else
    echo "[FAIL] Registration validation - Expected 422, got $REG_VALIDATION_STATUS"
    ((FAILED++))
fi

# 422 - Duplicate email registration
DUP_EMAIL_STATUS=$(curl -s -o /dev/null -w "%{http_code}" -X POST "$API_URL/api/register" \
    -H "Content-Type: application/json" \
    -H "Accept: application/json" \
    -d "{\"name\":\"Alice Duplicate\",\"email\":\"alice-$SUFFIX@example.com\",\"password\":\"password123\"}")
if [ "$DUP_EMAIL_STATUS" -eq 422 ]; then
    echo "[PASS] Duplicate email registration (HTTP 422)"
    ((PASSED++))
else
    echo "[FAIL] Duplicate email - Expected 422, got $DUP_EMAIL_STATUS"
    ((FAILED++))
fi

# 422 - Login validation
LOGIN_VALIDATION_STATUS=$(curl -s -o /dev/null -w "%{http_code}" -X POST "$API_URL/api/login" \
    -H "Content-Type: application/json" \
    -H "Accept: application/json" \
    -d '{}')
if [ "$LOGIN_VALIDATION_STATUS" -eq 422 ]; then
    echo "[PASS] Login validation (HTTP 422)"
    ((PASSED++))
else
    echo "[FAIL] Login validation - Expected 422, got $LOGIN_VALIDATION_STATUS"
    ((FAILED++))
fi

# 401 - Invalid credentials
BAD_CREDS_STATUS=$(curl -s -o /dev/null -w "%{http_code}" -X POST "$API_URL/api/login" \
    -H "Content-Type: application/json" \
    -H "Accept: application/json" \
    -d '{"email":"nobody@example.com","password":"wrongpassword"}')
if [ "$BAD_CREDS_STATUS" -eq 401 ]; then
    echo "[PASS] Invalid credentials (HTTP 401)"
    ((PASSED++))
else
    echo "[FAIL] Invalid credentials - Expected 401, got $BAD_CREDS_STATUS"
    ((FAILED++))
fi

# 422 - Article creation validation
ART_VALIDATION_STATUS=$(curl -s -o /dev/null -w "%{http_code}" -X POST "$API_URL/api/articles" \
    -H "Authorization: Bearer $ALICE_TOKEN" \
    -H "Content-Type: application/json" \
    -H "Accept: application/json" \
    -d '{}')
if [ "$ART_VALIDATION_STATUS" -eq 422 ]; then
    echo "[PASS] Article creation validation (HTTP 422)"
    ((PASSED++))
else
    echo "[FAIL] Article creation validation - Expected 422, got $ART_VALIDATION_STATUS"
    ((FAILED++))
fi

# 403 - Forbidden (Bob tries to update Alice's deleted article — create a new one first)
TEMP_ARTICLE=$(curl -s -X POST "$API_URL/api/articles" \
    -H "Authorization: Bearer $ALICE_TOKEN" \
    -H "Content-Type: application/json" \
    -d '{"title":"Temp Article","body":"For forbidden test"}')
TEMP_ID=$(echo "$TEMP_ARTICLE" | jq -r '.article.id // empty')
if [ -n "$TEMP_ID" ]; then
    FORBIDDEN_STATUS=$(curl -s -o /dev/null -w "%{http_code}" -X PUT "$API_URL/api/articles/$TEMP_ID" \
        -H "Authorization: Bearer $BOB_TOKEN" \
        -H "Content-Type: application/json" \
        -H "Accept: application/json" \
        -d '{"title":"Hacked"}')
    if [ "$FORBIDDEN_STATUS" -eq 403 ]; then
        echo "[PASS] Forbidden update by non-owner (HTTP 403)"
        ((PASSED++))
    else
        echo "[FAIL] Forbidden update - Expected 403, got $FORBIDDEN_STATUS"
        ((FAILED++))
    fi
    # Clean up temp article
    curl -s -o /dev/null -X DELETE "$API_URL/api/articles/$TEMP_ID" \
        -H "Authorization: Bearer $ALICE_TOKEN"
fi

# Telemetry check
echo ""
echo "=== Telemetry ==="
TRACE_COUNT=$(docker logs slim4-otel-collector 2>&1 | grep -c "Span" || true)
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
