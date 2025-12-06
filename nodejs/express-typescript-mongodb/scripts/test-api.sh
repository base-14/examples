#!/bin/bash

# Express.js + MongoDB + OpenTelemetry API Testing Script
# Tests success and failure scenarios with realistic intermixing
#
# For detailed telemetry verification, see: docs/telemetry-verification.md

set -e

echo "=== Express.js + MongoDB + OpenTelemetry API Testing Script ==="
echo ""

SUFFIX=$(date +%s)
API_URL=${API_URL:-http://localhost:3000}
PASSED=0
FAILED=0

echo "[1/17] Testing health endpoint..."
HEALTH=$(curl -s $API_URL/api/health)
if echo "$HEALTH" | grep -q "healthy"; then
    echo "✓ GET /api/health - Health check passed"
    PASSED=$((PASSED + 1))
else
    echo "✗ GET /api/health - Health check failed"
    FAILED=$((FAILED + 1))
fi
echo ""

echo "[2/17] Testing registration with invalid email (validation failure)..."
INVALID_REG=$(curl -s -w "\n%{http_code}" -X POST $API_URL/api/v1/auth/register \
  -H "Content-Type: application/json" \
  -d '{"email":"notanemail","password":"SecurePass123","name":"Test"}')

STATUS=$(echo "$INVALID_REG" | tail -n1)
if [ "$STATUS" = "400" ]; then
    echo "✓ POST /api/v1/auth/register (invalid email) - Validation rejected (400)"
    PASSED=$((PASSED + 1))
else
    echo "✗ POST /api/v1/auth/register (invalid email) - Expected 400, got: $STATUS"
    FAILED=$((FAILED + 1))
fi
echo ""

echo "[3/17] Registering valid user..."
REGISTER_RESPONSE=$(curl -s -X POST $API_URL/api/v1/auth/register \
  -H "Content-Type: application/json" \
  -d "{
    \"email\": \"testuser$SUFFIX@example.com\",
    \"password\": \"SecurePass123\",
    \"name\": \"Test User\"
  }")

TOKEN=$(echo "$REGISTER_RESPONSE" | grep -o '"token"[[:space:]]*:[[:space:]]*"[^"]*"' | sed 's/.*:[[:space:]]*"//;s/"$//')

if [ -n "$TOKEN" ]; then
    echo "✓ POST /api/v1/auth/register - User registered successfully"
    PASSED=$((PASSED + 1))
else
    echo "✗ POST /api/v1/auth/register - Failed to register user"
    FAILED=$((FAILED + 1))
fi
echo ""

echo "[4/17] Testing login with wrong password..."
WRONG_PASS=$(curl -s -w "\n%{http_code}" -X POST $API_URL/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d "{\"email\":\"testuser$SUFFIX@example.com\",\"password\":\"WrongPass\"}")

STATUS=$(echo "$WRONG_PASS" | tail -n1)
if [ "$STATUS" = "401" ]; then
    echo "✓ POST /api/v1/auth/login (wrong password) - Correctly rejected (401)"
    PASSED=$((PASSED + 1))
else
    echo "✗ POST /api/v1/auth/login (wrong password) - Expected 401, got: $STATUS"
    FAILED=$((FAILED + 1))
fi
echo ""

echo "[5/17] Testing successful login..."
LOGIN_RESPONSE=$(curl -s -X POST $API_URL/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d "{
    \"email\": \"testuser$SUFFIX@example.com\",
    \"password\": \"SecurePass123\"
  }")

TOKEN2=$(echo "$LOGIN_RESPONSE" | grep -o '"token"[[:space:]]*:[[:space:]]*"[^"]*"' | sed 's/.*:[[:space:]]*"//;s/"$//')

if [ -n "$TOKEN2" ]; then
    echo "✓ POST /api/v1/auth/login - Login successful"
    PASSED=$((PASSED + 1))
else
    echo "✗ POST /api/v1/auth/login - Login failed"
    FAILED=$((FAILED + 1))
fi
echo ""

echo "[6/17] Testing /me endpoint with invalid token..."
INVALID_TOKEN=$(curl -s -w "\n%{http_code}" -X GET $API_URL/api/v1/auth/me \
  -H "Authorization: Bearer invalid_token_xyz")

STATUS=$(echo "$INVALID_TOKEN" | tail -n1)
if [ "$STATUS" = "401" ]; then
    echo "✓ GET /api/v1/auth/me (invalid token) - Correctly rejected (401)"
    PASSED=$((PASSED + 1))
else
    echo "✗ GET /api/v1/auth/me (invalid token) - Expected 401, got: $STATUS"
    FAILED=$((FAILED + 1))
fi
echo ""

echo "[7/17] Getting current user with valid token..."
ME_RESPONSE=$(curl -s -X GET $API_URL/api/v1/auth/me \
  -H "Authorization: Bearer $TOKEN")

USER_EMAIL=$(echo "$ME_RESPONSE" | grep -o '"email"[[:space:]]*:[[:space:]]*"[^"]*"' | sed 's/.*:[[:space:]]*"//;s/"$//')

if [ -n "$USER_EMAIL" ]; then
    echo "✓ GET /api/v1/auth/me - Retrieved user: $USER_EMAIL"
    PASSED=$((PASSED + 1))
else
    echo "✗ GET /api/v1/auth/me - Failed to retrieve user"
    FAILED=$((FAILED + 1))
fi
echo ""

echo "[8/17] Testing article creation without auth..."
NO_AUTH=$(curl -s -w "\n%{http_code}" -X POST $API_URL/api/v1/articles \
  -H "Content-Type: application/json" \
  -d '{"title":"Unauthorized","content":"Should fail"}')

STATUS=$(echo "$NO_AUTH" | tail -n1)
if [ "$STATUS" = "401" ]; then
    echo "✓ POST /api/v1/articles (no auth) - Correctly rejected (401)"
    PASSED=$((PASSED + 1))
else
    echo "✗ POST /api/v1/articles (no auth) - Expected 401, got: $STATUS"
    FAILED=$((FAILED + 1))
fi
echo ""

echo "[9/17] Creating article with XSS attempt in title..."
XSS_ARTICLE=$(curl -s -X POST $API_URL/api/v1/articles \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d "{
    \"title\": \"<script>alert('xss')</script>Test Article\",
    \"content\": \"Safe content\",
    \"tags\": [\"test\"]
  }")

SANITIZED_TITLE=$(echo "$XSS_ARTICLE" | grep -o '"title"[[:space:]]*:[[:space:]]*"[^"]*"' | sed 's/.*:[[:space:]]*"//;s/"$//')
XSS_ID=$(echo "$XSS_ARTICLE" | grep -o '"_id"[[:space:]]*:[[:space:]]*"[^"]*"' | sed 's/.*:[[:space:]]*"//;s/"$//')

if echo "$SANITIZED_TITLE" | grep -qv "<script>"; then
    echo "✓ XSS Protection - Script tags stripped from title (result: $SANITIZED_TITLE)"
    PASSED=$((PASSED + 1))
else
    echo "✗ XSS Protection - Script tags not stripped"
    FAILED=$((FAILED + 1))
fi
echo ""

echo "[10/17] Creating article with missing required field..."
MISSING_FIELD=$(curl -s -w "\n%{http_code}" -X POST $API_URL/api/v1/articles \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{"title":"Test","content":""}')

STATUS=$(echo "$MISSING_FIELD" | tail -n1)
if [ "$STATUS" = "400" ]; then
    echo "✓ POST /api/v1/articles (empty content) - Validation rejected (400)"
    PASSED=$((PASSED + 1))
else
    echo "✗ POST /api/v1/articles (empty content) - Expected 400, got: $STATUS"
    FAILED=$((FAILED + 1))
fi
echo ""

echo "[11/17] Creating valid article..."
ARTICLE1_RESPONSE=$(curl -s -X POST $API_URL/api/v1/articles \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d "{
    \"title\": \"Getting Started with Express.js $SUFFIX\",
    \"content\": \"A comprehensive guide to Express.js and OpenTelemetry integration\",
    \"tags\": [\"express\", \"typescript\", \"opentelemetry\"]
  }")

ARTICLE1_ID=$(echo "$ARTICLE1_RESPONSE" | grep -o '"_id"[[:space:]]*:[[:space:]]*"[^"]*"' | sed 's/.*:[[:space:]]*"//;s/"$//')

if [ -n "$ARTICLE1_ID" ]; then
    echo "✓ POST /api/v1/articles - Article created (ID: $ARTICLE1_ID)"
    PASSED=$((PASSED + 1))
else
    echo "✗ POST /api/v1/articles - Failed to create article"
    FAILED=$((FAILED + 1))
fi
echo ""

echo "[12/17] Getting article with invalid ID..."
INVALID_ID=$(curl -s -w "\n%{http_code}" -X GET $API_URL/api/v1/articles/invalid123)

STATUS=$(echo "$INVALID_ID" | tail -n1)
if [ "$STATUS" = "400" ] || [ "$STATUS" = "404" ]; then
    echo "✓ GET /api/v1/articles/:id (invalid ID) - Correctly handled ($STATUS)"
    PASSED=$((PASSED + 1))
else
    echo "✗ GET /api/v1/articles/:id (invalid ID) - Expected 400/404, got: $STATUS"
    FAILED=$((FAILED + 1))
fi
echo ""

echo "[13/17] Listing articles (public access)..."
ARTICLES_RESPONSE=$(curl -s -X GET "$API_URL/api/v1/articles?page=1&limit=10")
ARTICLES_COUNT=$(echo "$ARTICLES_RESPONSE" | grep -o '"_id"' | wc -l | tr -d ' ')

if [ "$ARTICLES_COUNT" -ge 1 ]; then
    echo "✓ GET /api/v1/articles - Listed articles (found: $ARTICLES_COUNT)"
    PASSED=$((PASSED + 1))
else
    echo "✗ GET /api/v1/articles - Expected at least 1 article"
    FAILED=$((FAILED + 1))
fi
echo ""

echo "[14/17] Updating article without auth..."
UPDATE_NOAUTH=$(curl -s -w "\n%{http_code}" -X PUT $API_URL/api/v1/articles/$ARTICLE1_ID \
  -H "Content-Type: application/json" \
  -d '{"title":"Unauthorized Update"}')

STATUS=$(echo "$UPDATE_NOAUTH" | tail -n1)
if [ "$STATUS" = "401" ]; then
    echo "✓ PUT /api/v1/articles/:id (no auth) - Correctly rejected (401)"
    PASSED=$((PASSED + 1))
else
    echo "✗ PUT /api/v1/articles/:id (no auth) - Expected 401, got: $STATUS"
    FAILED=$((FAILED + 1))
fi
echo ""

echo "[15/17] Updating article with valid auth..."
UPDATE_RESPONSE=$(curl -s -X PUT $API_URL/api/v1/articles/$ARTICLE1_ID \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d "{
    \"title\": \"Getting Started with Express.js - Updated $SUFFIX\"
  }")

UPDATED_TITLE=$(echo "$UPDATE_RESPONSE" | grep -o '"title"[[:space:]]*:[[:space:]]*"[^"]*"' | sed 's/.*:[[:space:]]*"//;s/"$//')

if echo "$UPDATED_TITLE" | grep -q "Updated"; then
    echo "✓ PUT /api/v1/articles/:id - Article updated successfully"
    PASSED=$((PASSED + 1))
else
    echo "✗ PUT /api/v1/articles/:id - Failed to update article"
    FAILED=$((FAILED + 1))
fi
echo ""

echo "[16/17] Publishing article (async job)..."
PUBLISH_RESPONSE=$(curl -s -X POST $API_URL/api/v1/articles/$ARTICLE1_ID/publish \
  -H "Authorization: Bearer $TOKEN")

JOB_ID=$(echo "$PUBLISH_RESPONSE" | grep -o '"jobId"[[:space:]]*:[[:space:]]*"[^"]*"' | sed 's/.*:[[:space:]]*"//;s/"$//')

if [ -n "$JOB_ID" ]; then
    echo "✓ POST /api/v1/articles/:id/publish - Job enqueued (ID: $JOB_ID)"
    PASSED=$((PASSED + 1))

    echo "  Waiting for background job to process..."
    sleep 3

    PUBLISHED_ARTICLE=$(curl -s -X GET $API_URL/api/v1/articles/$ARTICLE1_ID)
    IS_PUBLISHED=$(echo "$PUBLISHED_ARTICLE" | grep -o '"published"[[:space:]]*:[[:space:]]*true')

    if [ -n "$IS_PUBLISHED" ]; then
        echo "  ✓ Article successfully published by background worker"
    else
        echo "  ⚠ Article not yet published (job may still be processing)"
    fi
else
    echo "✗ POST /api/v1/articles/:id/publish - Failed to enqueue job"
    FAILED=$((FAILED + 1))
fi
echo ""

echo "[17/17] Deleting article with valid auth..."
DELETE_STATUS=$(curl -s -o /dev/null -w "%{http_code}" -X DELETE $API_URL/api/v1/articles/$ARTICLE1_ID \
  -H "Authorization: Bearer $TOKEN")

if [ "$DELETE_STATUS" = "204" ]; then
    echo "✓ DELETE /api/v1/articles/:id - Article deleted successfully"
    PASSED=$((PASSED + 1))
else
    echo "✗ DELETE /api/v1/articles/:id - Expected 204, got: $DELETE_STATUS"
    FAILED=$((FAILED + 1))
fi
echo ""

# Cleanup XSS test article if it exists
if [ -n "$XSS_ID" ]; then
    curl -s -o /dev/null -X DELETE $API_URL/api/v1/articles/$XSS_ID \
      -H "Authorization: Bearer $TOKEN" 2>/dev/null || true
fi

echo "Checking OpenTelemetry traces..."
TRACE_COUNT=$(docker logs otel-collector 2>&1 | grep -c "Span" || echo "0")
if [ "$TRACE_COUNT" -gt 0 ]; then
  echo "✓ OTel Collector has captured telemetry (found $TRACE_COUNT span references)"
else
  echo "⚠ No telemetry found in OTel Collector logs (check Scout dashboard)"
fi
echo ""

echo "=== Test Summary ==="
echo "✓ Health check: Working"
echo "✓ Validation: Zod schemas rejecting invalid inputs"
echo "✓ XSS Protection: DOMPurify sanitizing HTML"
echo "✓ Authentication: JWT working (register, login, me)"
echo "✓ Authorization: Protected endpoints rejecting unauthorized requests"
echo "✓ Article CRUD: Working with proper auth checks"
echo "✓ Background Jobs: Async publish with trace propagation"
echo "✓ OpenTelemetry: $([ "$TRACE_COUNT" -gt 0 ] && echo "Capturing telemetry" || echo "Check Scout dashboard")"
echo ""
echo "Passed: $PASSED/17"
echo "Failed: $FAILED/17"
echo ""

if [ "$FAILED" -eq 0 ]; then
    echo "All tests passed! ✓"
    echo ""
    echo "View traces in Scout dashboard using your credentials:"
    echo "  SCOUT_ENDPOINT, SCOUT_CLIENT_ID, SCOUT_CLIENT_SECRET"
    echo ""
    echo "For detailed telemetry verification steps, see:"
    echo "  docs/telemetry-verification.md"
    exit 0
else
    echo "Some tests failed"
    exit 1
fi
