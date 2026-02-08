#!/usr/bin/env bash
set -euo pipefail

BASE_URL="${API_URL:-http://localhost:8000}"
DELAY="${REQUEST_DELAY:-2}"
PASS=0
FAIL=0

green() { printf "\033[32m%s\033[0m" "$1"; }
red()   { printf "\033[31m%s\033[0m" "$1"; }
cyan()  { printf "\033[36m%s\033[0m" "$1"; }
dim()   { printf "\033[90m%s\033[0m" "$1"; }

check() {
  local label="$1" expected="$2" actual="$3"
  if [ "$actual" = "$expected" ]; then
    echo "  $(green "PASS") ${label} (${actual})"
    PASS=$((PASS + 1))
  else
    echo "  $(red "FAIL") ${label} (expected ${expected}, got ${actual})"
    FAIL=$((FAIL + 1))
  fi
}

# ---------------------------------------------------------------------------
# 1. Smoke tests — basic endpoint availability
# ---------------------------------------------------------------------------
echo ""
echo "$(cyan "=== 1. Smoke Tests ===")"
echo ""

STATUS=$(curl -s -o /dev/null -w "%{http_code}" "${BASE_URL}/health")
check "GET  /health" "200" "$STATUS"

STATUS=$(curl -s -o /dev/null -w "%{http_code}" \
  -X POST "${BASE_URL}/review" \
  -H "Content-Type: application/json" \
  -d '{"content": "This is a test of the review endpoint."}')
check "POST /review" "200" "$STATUS"
sleep "$DELAY"

STATUS=$(curl -s -o /dev/null -w "%{http_code}" \
  -X POST "${BASE_URL}/improve" \
  -H "Content-Type: application/json" \
  -d '{"content": "This is a test of the improve endpoint."}')
check "POST /improve" "200" "$STATUS"
sleep "$DELAY"

STATUS=$(curl -s -o /dev/null -w "%{http_code}" \
  -X POST "${BASE_URL}/score" \
  -H "Content-Type: application/json" \
  -d '{"content": "This is a test of the score endpoint."}')
check "POST /score" "200" "$STATUS"

# ---------------------------------------------------------------------------
# 2. Validation error tests — expect 422 (no LLM calls, no delay needed)
# ---------------------------------------------------------------------------
echo ""
echo "$(cyan "=== 2. Validation Error Tests (expect 422) ===")"
echo ""

STATUS=$(curl -s -o /dev/null -w "%{http_code}" \
  -X POST "${BASE_URL}/review" \
  -H "Content-Type: application/json" \
  -d '{"content": ""}')
check "POST /review empty content" "422" "$STATUS"

STATUS=$(curl -s -o /dev/null -w "%{http_code}" \
  -X POST "${BASE_URL}/review" \
  -H "Content-Type: application/json" \
  -d '{}')
check "POST /review missing content" "422" "$STATUS"

STATUS=$(curl -s -o /dev/null -w "%{http_code}" \
  -X POST "${BASE_URL}/score" \
  -H "Content-Type: application/json" \
  -d '{"content": "test", "content_type": "invalid"}')
check "POST /score invalid content_type" "422" "$STATUS"

STATUS=$(curl -s -o /dev/null -w "%{http_code}" \
  -X POST "${BASE_URL}/improve" \
  -H "Content-Type: application/json" \
  -d 'not json')
check "POST /improve malformed JSON" "422" "$STATUS"

STATUS=$(curl -s -o /dev/null -w "%{http_code}" "${BASE_URL}/nonexistent")
check "GET  /nonexistent (404)" "404" "$STATUS"

# ---------------------------------------------------------------------------
# 3. Content type variants — exercises content.type span attribute
# ---------------------------------------------------------------------------
echo ""
echo "$(cyan "=== 3. Content Type Variants ===")"
echo "$(dim "    Each request generates a chat span with content.type attribute")"
echo ""

for CT in marketing technical blog general; do
  BODY=$(curl -s -X POST "${BASE_URL}/review" \
    -H "Content-Type: application/json" \
    -d "{\"content\": \"Testing the ${CT} content type.\", \"content_type\": \"${CT}\"}")
  STATUS=$(echo "$BODY" | python3 -c "import sys,json; d=json.load(sys.stdin); print('200')" 2>/dev/null || echo "ERR")
  check "POST /review content_type=${CT}" "200" "$STATUS"
  sleep "$DELAY"
done

# ---------------------------------------------------------------------------
# 4. Response body validation — verify LLM response structure
# ---------------------------------------------------------------------------
echo ""
echo "$(cyan "=== 4. Response Body Validation ===")"
echo ""

REVIEW_BODY=$(curl -s -X POST "${BASE_URL}/review" \
  -H "Content-Type: application/json" \
  -d '{"content": "This revolutionary product is the absolute best thing ever created in history!!", "content_type": "marketing"}')
echo "  $(dim "Review response (marketing hyperbole):")"
echo "$REVIEW_BODY" | python3 -m json.tool 2>/dev/null | head -20 | while IFS= read -r line; do echo "    $(dim "$line")"; done

HAS_ISSUES=$(echo "$REVIEW_BODY" | python3 -c "import sys,json; d=json.load(sys.stdin); print('yes' if 'issues' in d else 'no')" 2>/dev/null || echo "no")
check "Review has 'issues' field" "yes" "$HAS_ISSUES"

HAS_QUALITY=$(echo "$REVIEW_BODY" | python3 -c "import sys,json; d=json.load(sys.stdin); print('yes' if d.get('overall_quality') in ('poor','fair','good','excellent') else 'no')" 2>/dev/null || echo "no")
check "Review has valid overall_quality" "yes" "$HAS_QUALITY"
sleep "$DELAY"

IMPROVE_BODY=$(curl -s -X POST "${BASE_URL}/improve" \
  -H "Content-Type: application/json" \
  -d '{"content": "The thing is really good and stuff and you should buy it.", "content_type": "blog"}')
echo ""
echo "  $(dim "Improve response (vague blog content):")"
echo "$IMPROVE_BODY" | python3 -m json.tool 2>/dev/null | head -20 | while IFS= read -r line; do echo "    $(dim "$line")"; done

HAS_SUGGESTIONS=$(echo "$IMPROVE_BODY" | python3 -c "import sys,json; d=json.load(sys.stdin); print('yes' if 'suggestions' in d else 'no')" 2>/dev/null || echo "no")
check "Improve has 'suggestions' field" "yes" "$HAS_SUGGESTIONS"
sleep "$DELAY"

SCORE_BODY=$(curl -s -X POST "${BASE_URL}/score" \
  -H "Content-Type: application/json" \
  -d '{"content": "Kubernetes orchestrates containerized workloads across distributed clusters, providing declarative configuration and automation.", "content_type": "technical"}')
echo ""
echo "  $(dim "Score response (technical content):")"
echo "$SCORE_BODY" | python3 -m json.tool 2>/dev/null | head -15 | while IFS= read -r line; do echo "    $(dim "$line")"; done

SCORE_VALID=$(echo "$SCORE_BODY" | python3 -c "
import sys, json
d = json.load(sys.stdin)
ok = 0 <= d.get('score', -1) <= 100
ok = ok and all(0 <= d.get('breakdown', {}).get(k, -1) <= 100 for k in ('clarity','accuracy','engagement','originality'))
print('yes' if ok else 'no')
" 2>/dev/null || echo "no")
check "Score in 0-100 with valid breakdown" "yes" "$SCORE_VALID"

# ---------------------------------------------------------------------------
# 5. Telemetry exercise scenarios
# ---------------------------------------------------------------------------
echo ""
echo "$(cyan "=== 5. Telemetry Exercise Scenarios ===")"
echo "$(dim "    These requests exercise specific telemetry paths for manual verification")"
echo ""

echo "  $(dim "[token metrics] High-quality technical content (expect higher token usage)...")"
sleep "$DELAY"
STATUS=$(curl -s -o /dev/null -w "%{http_code}" \
  -X POST "${BASE_URL}/score" \
  -H "Content-Type: application/json" \
  -d '{"content": "Machine learning models leverage gradient descent optimization to minimize loss functions across high-dimensional parameter spaces. Regularization techniques such as L1 and L2 penalties prevent overfitting by constraining model complexity.", "content_type": "technical"}')
check "Score technical (token metrics path)" "200" "$STATUS"

echo "  $(dim "[evaluation events] Content with many issues (triggers low eval score)...")"
sleep "$DELAY"
STATUS=$(curl -s -o /dev/null -w "%{http_code}" \
  -X POST "${BASE_URL}/review" \
  -H "Content-Type: application/json" \
  -d '{"content": "This is literally the most amazing revolutionary groundbreaking product ever created! Everyone agrees it is the best. Studies show 100% satisfaction. Buy now!!", "content_type": "marketing"}')
check "Review hyperbolic marketing (eval event path)" "200" "$STATUS"

echo "  $(dim "[PII scrubbing] Content with PII (should be scrubbed from span events)...")"
sleep "$DELAY"
STATUS=$(curl -s -o /dev/null -w "%{http_code}" \
  -X POST "${BASE_URL}/review" \
  -H "Content-Type: application/json" \
  -d '{"content": "Contact john.doe@example.com or call 555-123-4567 for details about our product.", "content_type": "general"}')
check "Review with PII content (scrub path)" "200" "$STATUS"

echo "  $(dim "[cost tracking] Multiple endpoints to generate cost breakdown...")"
for EP in review improve score; do
  sleep "$DELAY"
  STATUS=$(curl -s -o /dev/null -w "%{http_code}" \
    -X POST "${BASE_URL}/${EP}" \
    -H "Content-Type: application/json" \
    -d '{"content": "Evaluate this content for cost tracking purposes.", "content_type": "general"}')
  check "POST /${EP} (cost tracking)" "200" "$STATUS"
done

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
echo ""
TOTAL=$((PASS + FAIL))
if [ "$FAIL" -eq 0 ]; then
  echo "$(green "=== All ${TOTAL} tests passed ===")"
else
  echo "$(red "=== ${FAIL}/${TOTAL} tests failed ===")"
  exit 1
fi
echo ""
