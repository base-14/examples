#!/bin/bash

set -e

BASE_URL="${BASE_URL:-http://localhost:8080}"
PASS=0
FAIL=0

print_result() {
    if [ $1 -eq 0 ]; then
        echo "✓ $2"
        PASS=$((PASS + 1))
    else
        echo "✗ $2"
        FAIL=$((FAIL + 1))
    fi
}

test_endpoint() {
    local method=$1
    local endpoint=$2
    local expected_status=$3
    local description=$4
    local data=$5
    local token=$6

    local status

    if [ -n "$token" ] && [ -n "$data" ]; then
        status=$(curl -s -w '%{http_code}' -o /tmp/response.json \
            -X "$method" \
            -H "Authorization: Bearer $token" \
            -H "Content-Type: application/json" \
            -d "$data" \
            "${BASE_URL}${endpoint}")
    elif [ -n "$token" ]; then
        status=$(curl -s -w '%{http_code}' -o /tmp/response.json \
            -X "$method" \
            -H "Authorization: Bearer $token" \
            "${BASE_URL}${endpoint}")
    elif [ -n "$data" ]; then
        status=$(curl -s -w '%{http_code}' -o /tmp/response.json \
            -X "$method" \
            -H "Content-Type: application/json" \
            -d "$data" \
            "${BASE_URL}${endpoint}")
    else
        status=$(curl -s -w '%{http_code}' -o /tmp/response.json \
            -X "$method" \
            "${BASE_URL}${endpoint}")
    fi

    if [ "$status" = "$expected_status" ]; then
        print_result 0 "$description (HTTP $status)"
        return 0
    else
        print_result 1 "$description (expected $expected_status, got $status)"
        cat /tmp/response.json 2>/dev/null || true
        echo ""
        return 1
    fi
}

echo "============================================"
echo "Go Echo + PostgreSQL API Test Suite"
echo "============================================"
echo ""

TIMESTAMP=$(date +%s)
TEST_EMAIL="test${TIMESTAMP}@example.com"
TEST_PASSWORD="password123"
TEST_NAME="Test User"

echo "--- Health Check ---"
test_endpoint GET "/api/health" 200 "Health check returns 200"

echo ""
echo "--- User Registration ---"
test_endpoint POST "/api/register" 201 "Register new user" \
    "{\"email\":\"$TEST_EMAIL\",\"password\":\"$TEST_PASSWORD\",\"name\":\"$TEST_NAME\"}"

TOKEN=$(cat /tmp/response.json | grep -o '"token":"[^"]*"' | cut -d'"' -f4)

test_endpoint POST "/api/register" 409 "Reject duplicate email" \
    "{\"email\":\"$TEST_EMAIL\",\"password\":\"$TEST_PASSWORD\",\"name\":\"$TEST_NAME\"}"

test_endpoint POST "/api/register" 400 "Reject missing email" \
    "{\"password\":\"$TEST_PASSWORD\",\"name\":\"$TEST_NAME\"}"

test_endpoint POST "/api/register" 400 "Reject short password" \
    "{\"email\":\"short${TIMESTAMP}@example.com\",\"password\":\"123\",\"name\":\"$TEST_NAME\"}"

echo ""
echo "--- User Login ---"
test_endpoint POST "/api/login" 200 "Login with valid credentials" \
    "{\"email\":\"$TEST_EMAIL\",\"password\":\"$TEST_PASSWORD\"}"

TOKEN=$(cat /tmp/response.json | grep -o '"token":"[^"]*"' | cut -d'"' -f4)

test_endpoint POST "/api/login" 401 "Reject invalid password" \
    "{\"email\":\"$TEST_EMAIL\",\"password\":\"wrongpassword\"}"

test_endpoint POST "/api/login" 401 "Reject non-existent user" \
    "{\"email\":\"nonexistent@example.com\",\"password\":\"$TEST_PASSWORD\"}"

echo ""
echo "--- Current User ---"
test_endpoint GET "/api/user" 200 "Get current user with token" "" "$TOKEN"

test_endpoint GET "/api/user" 401 "Reject without token"

test_endpoint GET "/api/user" 401 "Reject with invalid token" "" "invalid.token.here"

echo ""
echo "--- Articles (Unauthenticated) ---"
test_endpoint GET "/api/articles" 200 "List articles without auth"

echo ""
echo "--- Article Creation ---"
test_endpoint POST "/api/articles" 201 "Create article with auth" \
    "{\"title\":\"Test Article ${TIMESTAMP}\",\"description\":\"Test description\",\"body\":\"This is the article body.\"}" "$TOKEN"

ARTICLE_SLUG=$(cat /tmp/response.json | grep -o '"slug":"[^"]*"' | cut -d'"' -f4)

test_endpoint POST "/api/articles" 401 "Reject create without auth" \
    "{\"title\":\"Unauthorized Article\",\"body\":\"Should fail\"}"

test_endpoint POST "/api/articles" 400 "Reject create without title" \
    "{\"body\":\"Body without title\"}" "$TOKEN"

echo ""
echo "--- Article Read ---"
test_endpoint GET "/api/articles/$ARTICLE_SLUG" 200 "Get article by slug"

test_endpoint GET "/api/articles/non-existent-slug" 404 "Return 404 for non-existent article"

echo ""
echo "--- Article Update ---"
test_endpoint PUT "/api/articles/$ARTICLE_SLUG" 200 "Update own article" \
    "{\"title\":\"Updated Title ${TIMESTAMP}\",\"description\":\"Updated description\"}" "$TOKEN"

UPDATED_SLUG=$(cat /tmp/response.json | grep -o '"slug":"[^"]*"' | cut -d'"' -f4)

test_endpoint PUT "/api/articles/$UPDATED_SLUG" 401 "Reject update without auth" \
    "{\"title\":\"Should fail\"}"

echo ""
echo "--- Article Favorites ---"
test_endpoint POST "/api/articles/$UPDATED_SLUG/favorite" 200 "Favorite article" "" "$TOKEN"

test_endpoint POST "/api/articles/$UPDATED_SLUG/favorite" 409 "Reject double favorite" "" "$TOKEN"

test_endpoint DELETE "/api/articles/$UPDATED_SLUG/favorite" 200 "Unfavorite article" "" "$TOKEN"

test_endpoint DELETE "/api/articles/$UPDATED_SLUG/favorite" 409 "Reject unfavorite when not favorited" "" "$TOKEN"

test_endpoint POST "/api/articles/$UPDATED_SLUG/favorite" 401 "Reject favorite without auth"

echo ""
echo "--- Article Deletion ---"
test_endpoint DELETE "/api/articles/$UPDATED_SLUG" 401 "Reject delete without auth"

test_endpoint DELETE "/api/articles/$UPDATED_SLUG" 204 "Delete own article" "" "$TOKEN"

test_endpoint GET "/api/articles/$UPDATED_SLUG" 404 "Confirm article deleted"

echo ""
echo "--- Logout ---"
test_endpoint POST "/api/logout" 200 "Logout" "" "$TOKEN"

echo ""
echo "============================================"
echo "Test Results: $PASS passed, $FAIL failed"
echo "============================================"

if [ $FAIL -gt 0 ]; then
    exit 1
fi
