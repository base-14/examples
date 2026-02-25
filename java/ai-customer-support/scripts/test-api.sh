#!/usr/bin/env bash
set -euo pipefail

BASE_URL="${API_URL:-http://localhost:8080}"
PASS=0
FAIL=0

green() { printf '\033[0;32m✓ %s\033[0m\n' "$1"; }
red()   { printf '\033[0;31m✗ %s\033[0m\n' "$1"; }

check() {
  local name="$1"
  local actual="$2"
  local expected="$3"
  if [[ "$actual" == "$expected" ]]; then
    green "$name"
    PASS=$((PASS + 1))
  else
    red "$name (expected '$expected', got '$actual')"
    FAIL=$((FAIL + 1))
  fi
}

echo "=== AI Customer Support — API Smoke Tests ==="
echo "Target: $BASE_URL"
echo ""

# Health
STATUS=$(curl -s -o /dev/null -w "%{http_code}" "$BASE_URL/api/health")
check "GET /api/health returns 200" "$STATUS" "200"

BODY=$(curl -s "$BASE_URL/api/health")
SVC=$(echo "$BODY" | python3 -c "import sys,json; print(json.load(sys.stdin)['status'])" 2>/dev/null || echo "error")
check "GET /api/health status=ok" "$SVC" "ok"

# Conversations
CONV_STATUS=$(curl -s -o /dev/null -w "%{http_code}" "$BASE_URL/api/conversations")
check "GET /api/conversations returns 200" "$CONV_STATUS" "200"

# Products
PROD_STATUS=$(curl -s -o /dev/null -w "%{http_code}" "$BASE_URL/api/products")
check "GET /api/products returns 200" "$PROD_STATUS" "200"

PROD_BODY=$(curl -s "$BASE_URL/api/products")
if echo "$PROD_BODY" | grep -q "sku"; then
  green "GET /api/products contains product data"
  PASS=$((PASS + 1))
else
  red "GET /api/products missing product data"
  FAIL=$((FAIL + 1))
fi

# Chat — valid message
CHAT_RESPONSE=$(curl -s -w "\n%{http_code}" -X POST "$BASE_URL/api/chat" \
  -H "Content-Type: application/json" \
  -d '{"message":"What is your return policy?"}')
CHAT_STATUS=$(echo "$CHAT_RESPONSE" | tail -1)
CHAT_BODY=$(echo "$CHAT_RESPONSE" | sed '$d')

check "POST /api/chat returns 200" "$CHAT_STATUS" "200"

CONTENT=$(echo "$CHAT_BODY" | python3 -c "import sys,json; print(json.load(sys.stdin).get('content',''))" 2>/dev/null || echo "")
if [[ -n "$CONTENT" ]]; then
  green "POST /api/chat returns content"
  PASS=$((PASS + 1))
else
  red "POST /api/chat missing content"
  FAIL=$((FAIL + 1))
fi

INTENT=$(echo "$CHAT_BODY" | python3 -c "import sys,json; print(json.load(sys.stdin).get('intent',''))" 2>/dev/null || echo "")
if [[ -n "$INTENT" ]]; then
  green "POST /api/chat returns intent"
  PASS=$((PASS + 1))
else
  red "POST /api/chat missing intent"
  FAIL=$((FAIL + 1))
fi

CONV_ID=$(echo "$CHAT_BODY" | python3 -c "import sys,json; print(json.load(sys.stdin).get('conversationId',''))" 2>/dev/null || echo "")
if [[ -n "$CONV_ID" ]]; then
  green "POST /api/chat returns conversationId"
  PASS=$((PASS + 1))
else
  red "POST /api/chat missing conversationId"
  FAIL=$((FAIL + 1))
fi

# Chat — multi-turn (reuse conversation)
if [[ -n "$CONV_ID" ]]; then
  TURN2_STATUS=$(curl -s -o /dev/null -w "%{http_code}" -X POST "$BASE_URL/api/chat" \
    -H "Content-Type: application/json" \
    -d "{\"message\":\"What about electronics?\",\"conversationId\":\"$CONV_ID\"}")
  check "POST /api/chat multi-turn returns 200" "$TURN2_STATUS" "200"
fi

# Chat — empty message
BAD_STATUS=$(curl -s -o /dev/null -w "%{http_code}" -X POST "$BASE_URL/api/chat" \
  -H "Content-Type: application/json" \
  -d '{"message":""}')
check "POST /api/chat empty message returns 400" "$BAD_STATUS" "400"

# Chat — invalid JSON
INVALID_STATUS=$(curl -s -o /dev/null -w "%{http_code}" -X POST "$BASE_URL/api/chat" \
  -H "Content-Type: application/json" \
  -d 'not json')
check "POST /api/chat invalid JSON returns 400" "$INVALID_STATUS" "400"

# SSE stream endpoint
STREAM_STATUS=$(curl -s -o /dev/null -w "%{http_code}" -X POST "$BASE_URL/api/chat/stream" \
  -H "Content-Type: application/json" \
  -d '{"message":"Hello"}')
check "POST /api/chat/stream returns 200" "$STREAM_STATUS" "200"

# Summary
echo ""
echo "─────────────────────────────"
echo "Results: $PASS passed, $FAIL failed"
if [[ $FAIL -gt 0 ]]; then
  exit 1
fi
