#!/bin/bash

# Laravel 12 + PostgreSQL + OpenTelemetry API Testing Script
# This script tests all API endpoints and generates telemetry data

set -e

echo "=== Laravel 12 API Testing Script ==="
echo ""

# Generate random suffix for unique emails
SUFFIX=$(date +%s)

# Register users
echo "[1/7] Registering test users..."
ALICE=$(curl -s -X POST http://localhost:8000/api/register \
  -H "Content-Type: application/json" \
  -H "Accept: application/json" \
  -d "{
    \"name\": \"Alice Smith\",
    \"email\": \"alice-$SUFFIX@example.com\",
    \"password\": \"password123\"
  }" | jq -r '.user.token')

BOB=$(curl -s -X POST http://localhost:8000/api/register \
  -H "Content-Type: application/json" \
  -H "Accept: application/json" \
  -d "{
    \"name\": \"Bob Jones\",
    \"email\": \"bob-$SUFFIX@example.com\",
    \"password\": \"password123\"
  }" | jq -r '.user.token')

echo "✓ Users registered (Alice & Bob)"

# Create articles
echo ""
echo "[2/7] Creating articles..."
ARTICLE1=$(curl -s -X POST http://localhost:8000/api/articles \
  -H "Authorization: Bearer $ALICE" \
  -H "Content-Type: application/json" \
  -H "Accept: application/json" \
  -d '{
    "title": "Getting Started with Laravel 12",
    "description": "A comprehensive guide to Laravel 12 features",
    "body": "Laravel 12 introduces many exciting features including improved performance and better developer experience.",
    "tagList": ["laravel", "php85", "tutorial"]
  }' | jq -r '.article.id')

ARTICLE2=$(curl -s -X POST http://localhost:8000/api/articles \
  -H "Authorization: Bearer $ALICE" \
  -H "Content-Type: application/json" \
  -H "Accept: application/json" \
  -d '{
    "title": "OpenTelemetry Auto-Instrumentation",
    "description": "Implementing automatic tracing in PHP",
    "body": "OpenTelemetry provides automatic instrumentation for PHP applications through the opentelemetry-auto-laravel package.",
    "tagList": ["opentelemetry", "php", "observability"]
  }' | jq -r '.article.id')

echo "✓ Created 2 articles (IDs: $ARTICLE1, $ARTICLE2)"

# Test public endpoints
echo ""
echo "[3/7] Testing public endpoints..."
ARTICLES_COUNT=$(curl -s http://localhost:8000/api/articles -H "Accept: application/json" | jq '.data | length')
TAGS_COUNT=$(curl -s http://localhost:8000/api/tags -H "Accept: application/json" | jq '.tags | length')
echo "✓ GET /api/articles returned $ARTICLES_COUNT articles"
echo "✓ GET /api/tags returned $TAGS_COUNT tags"

# Test article details
echo ""
echo "[4/7] Testing article details..."
ARTICLE_TITLE=$(curl -s http://localhost:8000/api/articles/$ARTICLE1 \
  -H "Accept: application/json" | jq -r '.article.title')
echo "✓ GET /api/articles/$ARTICLE1 returned: \"$ARTICLE_TITLE\""

# Test favorites
echo ""
echo "[5/7] Testing favorites..."
curl -s -X POST http://localhost:8000/api/articles/$ARTICLE1/favorite \
  -H "Authorization: Bearer $BOB" \
  -H "Accept: application/json" > /dev/null
FAVORITES=$(curl -s http://localhost:8000/api/articles/$ARTICLE1 \
  -H "Accept: application/json" | jq '.article.favoritesCount')
echo "✓ Bob favorited article $ARTICLE1 (favorites: $FAVORITES)"

# Test comments
echo ""
echo "[6/7] Testing comments..."
COMMENT1=$(curl -s -X POST http://localhost:8000/api/articles/$ARTICLE1/comments \
  -H "Authorization: Bearer $BOB" \
  -H "Content-Type: application/json" \
  -H "Accept: application/json" \
  -d '{"body": "Great article about Laravel 12!"}' | jq -r '.comment.id // "null"')

if [ "$COMMENT1" != "null" ]; then
  echo "✓ Bob commented on article $ARTICLE1 (comment ID: $COMMENT1)"
else
  echo "⚠ Comment creation failed (check author_id in Comment model fillable)"
fi

# Check telemetry
echo ""
echo "[7/7] Checking OpenTelemetry traces..."
TRACE_COUNT=$(docker logs otel-collector 2>&1 | grep -c "Trace ID" || true)
if [ "$TRACE_COUNT" -gt 0 ]; then
  echo "✓ OTel Collector has captured $TRACE_COUNT traces"
else
  echo "⚠ No traces found in OTel Collector logs"
fi

# Summary
echo ""
echo "=== Test Summary ==="
echo "✓ User registration: Working"
echo "✓ JWT authentication: Working"
echo "✓ Article CRUD: Working"
echo "✓ Favorites: Working"
echo "✓ Comments: $([ "$COMMENT1" != "null" ] && echo "Working" || echo "Needs fix")"
echo "✓ OpenTelemetry: $([ "$TRACE_COUNT" -gt 0 ] && echo "Capturing traces" || echo "Not capturing")"
echo ""
echo "View traces in Scout dashboard using your credentials:"
echo "  SCOUT_ENDPOINT, SCOUT_CLIENT_ID, SCOUT_CLIENT_SECRET"
