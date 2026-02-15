#!/bin/bash

# Rails 8 + SQLite API Testing Script
#
# This is an HTML app (not a JSON API). Tests verify HTTP status codes
# and basic page content. CSRF protection is active, so mutating requests
# grab the authenticity token from the rendered form first.

set -e

BASE_URL="${API_BASE_URL:-http://localhost:3000}"
PASS_COUNT=0
FAIL_COUNT=0
COOKIE_JAR=$(mktemp)

GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m'

pass() { echo -e "${GREEN}PASS${NC}: $1"; PASS_COUNT=$((PASS_COUNT + 1)); }
fail() { echo -e "${RED}FAIL${NC}: $1 (expected $2, got $3)"; FAIL_COUNT=$((FAIL_COUNT + 1)); }

cleanup() { rm -f "$COOKIE_JAR"; }
trap cleanup EXIT

check_status() {
    local description=$1
    local expected=$2
    local actual=$3
    if [ "$expected" = "$actual" ]; then
        pass "$description"
    else
        fail "$description" "$expected" "$actual"
    fi
}

extract_csrf_token() {
    local html=$1
    echo "$html" | grep -o 'name="authenticity_token" value="[^"]*"' | head -1 | sed 's/.*value="//;s/"$//'
}

TIMESTAMP=$(date +%s)

echo -e "${YELLOW}=== Rails 8 + SQLite Tests ===${NC}"
echo ""

# ------------------------------------------------------------------
# 1. Health check
# ------------------------------------------------------------------
echo "1. Health Check"
STATUS=$(curl -s -o /dev/null -w "%{http_code}" "$BASE_URL/up")
check_status "GET /up (Rails health check)" "200" "$STATUS"

# ------------------------------------------------------------------
# 2. Home page (redirects to login when not authenticated)
# ------------------------------------------------------------------
echo ""
echo "2. Home Page (unauthenticated)"
STATUS=$(curl -s -o /dev/null -w "%{http_code}" -L -c "$COOKIE_JAR" "$BASE_URL/")
check_status "GET / (redirects to login)" "200" "$STATUS"

# ------------------------------------------------------------------
# 3. Signup page
# ------------------------------------------------------------------
echo ""
echo "3. Signup"

SIGNUP_PAGE=$(curl -s -c "$COOKIE_JAR" -b "$COOKIE_JAR" "$BASE_URL/signup")
STATUS=$(echo "$SIGNUP_PAGE" | head -1)
CSRF_TOKEN=$(extract_csrf_token "$SIGNUP_PAGE")

if [ -n "$CSRF_TOKEN" ]; then
    pass "GET /signup (page loads with CSRF token)"
else
    fail "GET /signup (CSRF token missing)" "token present" "token missing"
fi

# ------------------------------------------------------------------
# 4. Create user via signup
# ------------------------------------------------------------------
echo ""
echo "4. Create User (POST /signup)"

RESPONSE=$(curl -s -w "\n%{http_code}" -L \
    -c "$COOKIE_JAR" -b "$COOKIE_JAR" \
    -X POST "$BASE_URL/signup" \
    -H "Content-Type: application/x-www-form-urlencoded" \
    -d "authenticity_token=$(python3 -c "import urllib.parse; print(urllib.parse.quote('''$CSRF_TOKEN'''))")&user%5Bname%5D=TestUser+${TIMESTAMP}&user%5Bemail%5D=testuser-${TIMESTAMP}%40example.com&user%5Bpassword%5D=password123&user%5Bpassword_confirmation%5D=password123")
STATUS=$(echo "$RESPONSE" | tail -1)
check_status "POST /signup (create user)" "200" "$STATUS"

# ------------------------------------------------------------------
# 5. Home page (authenticated, should show content)
# ------------------------------------------------------------------
echo ""
echo "5. Home Page (authenticated)"

RESPONSE=$(curl -s -w "\n%{http_code}" -b "$COOKIE_JAR" "$BASE_URL/")
STATUS=$(echo "$RESPONSE" | tail -1)
check_status "GET / (authenticated)" "200" "$STATUS"

# ------------------------------------------------------------------
# 6. Hotels listing
# ------------------------------------------------------------------
echo ""
echo "6. Hotels"

STATUS=$(curl -s -o /dev/null -w "%{http_code}" -b "$COOKIE_JAR" "$BASE_URL/hotels")
check_status "GET /hotels (list hotels)" "200" "$STATUS"

# ------------------------------------------------------------------
# 7. Profile page
# ------------------------------------------------------------------
echo ""
echo "7. Profile"

STATUS=$(curl -s -o /dev/null -w "%{http_code}" -b "$COOKIE_JAR" "$BASE_URL/profile")
check_status "GET /profile (user profile)" "200" "$STATUS"

# ------------------------------------------------------------------
# 8. Orders page
# ------------------------------------------------------------------
echo ""
echo "8. Orders"

STATUS=$(curl -s -o /dev/null -w "%{http_code}" -b "$COOKIE_JAR" "$BASE_URL/orders")
check_status "GET /orders (order listing)" "200" "$STATUS"

# ------------------------------------------------------------------
# 9. Logout
# ------------------------------------------------------------------
echo ""
echo "9. Logout"

# Get a page with a CSRF token for the delete request
HOME_PAGE=$(curl -s -c "$COOKIE_JAR" -b "$COOKIE_JAR" "$BASE_URL/")
CSRF_TOKEN=$(extract_csrf_token "$HOME_PAGE")

STATUS=$(curl -s -o /dev/null -w "%{http_code}" -L \
    -c "$COOKIE_JAR" -b "$COOKIE_JAR" \
    -X DELETE "$BASE_URL/logout" \
    -H "Content-Type: application/x-www-form-urlencoded" \
    -d "authenticity_token=$(python3 -c "import urllib.parse; print(urllib.parse.quote('''$CSRF_TOKEN'''))")")
check_status "DELETE /logout (sign out)" "200" "$STATUS"

# ------------------------------------------------------------------
# 10. Login with existing user
# ------------------------------------------------------------------
echo ""
echo "10. Login"

LOGIN_PAGE=$(curl -s -c "$COOKIE_JAR" -b "$COOKIE_JAR" "$BASE_URL/login")
CSRF_TOKEN=$(extract_csrf_token "$LOGIN_PAGE")

if [ -n "$CSRF_TOKEN" ]; then
    pass "GET /login (page loads with CSRF token)"
else
    fail "GET /login (CSRF token missing)" "token present" "token missing"
fi

RESPONSE=$(curl -s -w "\n%{http_code}" -L \
    -c "$COOKIE_JAR" -b "$COOKIE_JAR" \
    -X POST "$BASE_URL/login" \
    -H "Content-Type: application/x-www-form-urlencoded" \
    -d "authenticity_token=$(python3 -c "import urllib.parse; print(urllib.parse.quote('''$CSRF_TOKEN'''))")&email=testuser-${TIMESTAMP}%40example.com&password=password123")
STATUS=$(echo "$RESPONSE" | tail -1)
check_status "POST /login (valid credentials)" "200" "$STATUS"

# Verify we're authenticated again
STATUS=$(curl -s -o /dev/null -w "%{http_code}" -b "$COOKIE_JAR" "$BASE_URL/profile")
check_status "GET /profile (after re-login)" "200" "$STATUS"

# ------------------------------------------------------------------
# Summary
# ------------------------------------------------------------------
echo ""
echo -e "${YELLOW}=== Test Summary ===${NC}"
echo -e "Passed: ${GREEN}$PASS_COUNT${NC}"
echo -e "Failed: ${RED}$FAIL_COUNT${NC}"
TOTAL=$((PASS_COUNT + FAIL_COUNT))
echo "Total:  $TOTAL"

if [ "$FAIL_COUNT" -eq 0 ]; then
    echo -e "${GREEN}All tests passed!${NC}"
    exit 0
else
    echo -e "${RED}Some tests failed!${NC}"
    exit 1
fi
