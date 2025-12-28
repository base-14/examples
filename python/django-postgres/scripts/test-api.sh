#!/bin/bash

set -e

BASE_URL="${BASE_URL:-http://localhost:8000}"
PASS=0
FAIL=0

green() { echo -e "\033[32m$1\033[0m"; }
red() { echo -e "\033[31m$1\033[0m"; }
blue() { echo -e "\033[34m$1\033[0m"; }

test_endpoint() {
    local name="$1"
    local method="$2"
    local endpoint="$3"
    local expected_status="$4"
    local data="$5"
    local auth="$6"

    local curl_args="-s -w '\n%{http_code}' -X $method"

    if [ -n "$data" ]; then
        curl_args="$curl_args -H 'Content-Type: application/json' -d '$data'"
    fi

    if [ -n "$auth" ]; then
        curl_args="$curl_args -H 'Authorization: Bearer $auth'"
    fi

    local response
    response=$(eval "curl $curl_args '$BASE_URL$endpoint'")
    local body=$(echo "$response" | sed '$d')
    local status=$(echo "$response" | tail -1 | tr -d "'" | tr -d '\n')

    if [ "$status" = "$expected_status" ]; then
        green "✓ $name (HTTP $status)"
        ((PASS++))
        echo "$body"
    else
        red "✗ $name (expected $expected_status, got $status)"
        ((FAIL++))
        echo "$body"
    fi
    echo ""
}

echo "======================================"
blue "Django + PostgreSQL API Test Suite"
echo "======================================"
echo ""

TIMESTAMP=$(date +%s)
USER1_EMAIL="alice-${TIMESTAMP}@example.com"
USER2_EMAIL="bob-${TIMESTAMP}@example.com"

blue "1. Health Check"
test_endpoint "Health check" "GET" "/api/health" "200"

blue "2. User Registration"
RESPONSE=$(curl -s -X POST "$BASE_URL/api/register" \
    -H "Content-Type: application/json" \
    -d "{\"email\": \"$USER1_EMAIL\", \"name\": \"Alice\", \"password\": \"password123\"}")
echo "$RESPONSE" | grep -q "access_token" && green "✓ User 1 registered" && ((PASS++)) || (red "✗ User 1 registration failed" && ((FAIL++)))
USER1_TOKEN=$(echo "$RESPONSE" | grep -o '"access_token":"[^"]*"' | cut -d'"' -f4)
echo ""

RESPONSE=$(curl -s -X POST "$BASE_URL/api/register" \
    -H "Content-Type: application/json" \
    -d "{\"email\": \"$USER2_EMAIL\", \"name\": \"Bob\", \"password\": \"password123\"}")
echo "$RESPONSE" | grep -q "access_token" && green "✓ User 2 registered" && ((PASS++)) || (red "✗ User 2 registration failed" && ((FAIL++)))
USER2_TOKEN=$(echo "$RESPONSE" | grep -o '"access_token":"[^"]*"' | cut -d'"' -f4)
echo ""

blue "3. User Login"
test_endpoint "Login with valid credentials" "POST" "/api/login" "200" \
    "{\"email\": \"$USER1_EMAIL\", \"password\": \"password123\"}"

test_endpoint "Login with invalid credentials" "POST" "/api/login" "401" \
    "{\"email\": \"$USER1_EMAIL\", \"password\": \"wrongpassword\"}"

blue "4. Get Current User"
test_endpoint "Get current user (authenticated)" "GET" "/api/user" "200" "" "$USER1_TOKEN"

blue "5. Create Articles"
RESPONSE=$(curl -s -X POST "$BASE_URL/api/articles/" \
    -H "Content-Type: application/json" \
    -H "Authorization: Bearer $USER1_TOKEN" \
    -d "{\"title\": \"Test Article ${TIMESTAMP}\", \"body\": \"This is the article body.\", \"description\": \"A test article\"}")
echo "$RESPONSE" | grep -q "slug" && green "✓ Article created" && ((PASS++)) || (red "✗ Article creation failed" && ((FAIL++)))
ARTICLE_SLUG=$(echo "$RESPONSE" | grep -o '"slug":"[^"]*"' | cut -d'"' -f4)
echo "Article slug: $ARTICLE_SLUG"
echo ""

blue "6. List Articles"
test_endpoint "List articles" "GET" "/api/articles/" "200"

test_endpoint "List articles with search" "GET" "/api/articles/?search=Test" "200"

blue "7. Get Single Article"
test_endpoint "Get article by slug" "GET" "/api/articles/$ARTICLE_SLUG" "200"

test_endpoint "Get non-existent article" "GET" "/api/articles/non-existent-slug" "404"

blue "8. Update Article"
test_endpoint "Update article (owner)" "PUT" "/api/articles/$ARTICLE_SLUG" "200" \
    "{\"title\": \"Updated Title ${TIMESTAMP}\"}" "$USER1_TOKEN"

test_endpoint "Update article (non-owner)" "PUT" "/api/articles/$ARTICLE_SLUG" "403" \
    "{\"title\": \"Hacked Title\"}" "$USER2_TOKEN"

blue "9. Favorite Article"
test_endpoint "Favorite article" "POST" "/api/articles/$ARTICLE_SLUG/favorite" "200" "" "$USER2_TOKEN"

test_endpoint "Favorite again (conflict)" "POST" "/api/articles/$ARTICLE_SLUG/favorite" "409" "" "$USER2_TOKEN"

test_endpoint "Unfavorite article" "DELETE" "/api/articles/$ARTICLE_SLUG/favorite" "200" "" "$USER2_TOKEN"

blue "10. Delete Article"
test_endpoint "Delete article (non-owner)" "DELETE" "/api/articles/$ARTICLE_SLUG" "403" "" "$USER2_TOKEN"

test_endpoint "Delete article (owner)" "DELETE" "/api/articles/$ARTICLE_SLUG" "204" "" "$USER1_TOKEN"

echo "======================================"
blue "Test Summary"
echo "======================================"
green "Passed: $PASS"
red "Failed: $FAIL"
echo ""

if [ $FAIL -gt 0 ]; then
    red "Some tests failed!"
    exit 1
else
    green "All tests passed!"
    exit 0
fi
