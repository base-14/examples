#!/usr/bin/env bash
set -euo pipefail

# ---------------------------------------------------------------------------
# verify-scout.sh — End-to-end telemetry verification
#
# Sends requests that exercise every telemetry path, then inspects the
# OTel Collector debug logs to verify spans, metrics, and attributes
# arrived correctly. Optionally prints a Scout dashboard checklist.
#
# Prerequisites:
#   docker compose up -d
#   (wait for app + collector to be healthy)
#
# Usage:
#   ./scripts/verify-scout.sh              # full verification
#   SKIP_REQUESTS=1 ./scripts/verify-scout.sh  # only check logs
# ---------------------------------------------------------------------------

BASE_URL="${API_URL:-http://localhost:8000}"
COLLECTOR_HEALTH="${COLLECTOR_HEALTH_URL:-http://localhost:13133}"
COMPOSE_PROJECT="ai-content-quality"
PASS=0
FAIL=0
WARN=0

green() { printf "\033[32m%s\033[0m" "$1"; }
red()   { printf "\033[31m%s\033[0m" "$1"; }
cyan()  { printf "\033[36m%s\033[0m" "$1"; }
yellow(){ printf "\033[33m%s\033[0m" "$1"; }
dim()   { printf "\033[90m%s\033[0m" "$1"; }

check() {
  local label="$1" expected="$2" actual="$3"
  if [ "$actual" = "$expected" ]; then
    echo "  $(green "PASS") ${label}"
    PASS=$((PASS + 1))
  else
    echo "  $(red "FAIL") ${label} (expected ${expected}, got ${actual})"
    FAIL=$((FAIL + 1))
  fi
}

check_log() {
  local label="$1" pattern="$2" log_text="$3"
  if echo "$log_text" | grep -q "$pattern"; then
    echo "  $(green "PASS") ${label}"
    PASS=$((PASS + 1))
  else
    echo "  $(red "FAIL") ${label} — pattern not found: ${pattern}"
    FAIL=$((FAIL + 1))
  fi
}

warn_log() {
  local label="$1" pattern="$2" log_text="$3"
  if echo "$log_text" | grep -q "$pattern"; then
    echo "  $(green "PASS") ${label}"
    PASS=$((PASS + 1))
  else
    echo "  $(yellow "WARN") ${label} — pattern not found (may need more time): ${pattern}"
    WARN=$((WARN + 1))
  fi
}

echo ""
echo "$(cyan "=============================================")"
echo "$(cyan "  Telemetry Verification — Base14 Scout")"
echo "$(cyan "=============================================")"

# ---------------------------------------------------------------------------
# 1. Prerequisites
# ---------------------------------------------------------------------------
echo ""
echo "$(cyan "=== 1. Prerequisites ===")"
echo ""

echo "  $(dim "Checking app health...")"
APP_STATUS=$(curl -s -o /dev/null -w "%{http_code}" "${BASE_URL}/health" 2>/dev/null || echo "000")
check "App is healthy (${BASE_URL}/health)" "200" "$APP_STATUS"

if [ "$APP_STATUS" != "200" ]; then
  echo ""
  echo "  $(red "App is not running. Start it with: docker compose up -d")"
  exit 1
fi

echo "  $(dim "Checking OTel Collector health...")"
COLLECTOR_STATUS=$(curl -s -o /dev/null -w "%{http_code}" "${COLLECTOR_HEALTH}" 2>/dev/null || echo "000")
check "Collector is healthy (${COLLECTOR_HEALTH})" "200" "$COLLECTOR_STATUS"

if [ "$COLLECTOR_STATUS" != "200" ]; then
  echo ""
  echo "  $(yellow "WARN: Collector not reachable — telemetry log verification will be skipped")"
  echo "  $(dim  "       Start with: docker compose up -d")"
  SKIP_LOG_CHECK=1
else
  SKIP_LOG_CHECK=0
fi

# ---------------------------------------------------------------------------
# 2. Send telemetry-generating requests
# ---------------------------------------------------------------------------
if [ "${SKIP_REQUESTS:-}" != "1" ]; then
  echo ""
  echo "$(cyan "=== 2. Sending Telemetry-Generating Requests ===")"
  echo ""

  echo "  $(dim "[spans] content_analysis review — marketing content")"
  curl -s -o /dev/null -X POST "${BASE_URL}/review" \
    -H "Content-Type: application/json" \
    -d '{"content": "This revolutionary product is the absolute best!", "content_type": "marketing"}'
  echo "  $(green "sent") POST /review (marketing)"

  echo "  $(dim "[spans] content_analysis improve — blog content")"
  curl -s -o /dev/null -X POST "${BASE_URL}/improve" \
    -H "Content-Type: application/json" \
    -d '{"content": "The thing is really good and stuff.", "content_type": "blog"}'
  echo "  $(green "sent") POST /improve (blog)"

  echo "  $(dim "[spans] content_analysis score — technical content")"
  curl -s -o /dev/null -X POST "${BASE_URL}/score" \
    -H "Content-Type: application/json" \
    -d '{"content": "Kubernetes orchestrates containerized workloads across clusters.", "content_type": "technical"}'
  echo "  $(green "sent") POST /score (technical)"

  echo "  $(dim "[eval events] Review with many issues — triggers low evaluation score")"
  curl -s -o /dev/null -X POST "${BASE_URL}/review" \
    -H "Content-Type: application/json" \
    -d '{"content": "Everyone knows this is literally the most amazing thing ever! Studies prove 100% of people agree!", "content_type": "marketing"}'
  echo "  $(green "sent") POST /review (hyperbolic — eval event)"

  echo "  $(dim "[PII scrub] Content with email, phone, SSN in prompts")"
  curl -s -o /dev/null -X POST "${BASE_URL}/review" \
    -H "Content-Type: application/json" \
    -d '{"content": "Contact john@example.com or 555-123-4567. SSN 123-45-6789.", "content_type": "general"}'
  echo "  $(green "sent") POST /review (PII content — scrub verification)"

  echo "  $(dim "[error metrics] Validation error — triggers http 422 metric")"
  curl -s -o /dev/null -X POST "${BASE_URL}/review" \
    -H "Content-Type: application/json" \
    -d '{"content": ""}'
  echo "  $(green "sent") POST /review (empty — 422)"

  echo "  $(dim "[http metrics] Health endpoint — low-cost request for baseline")"
  curl -s -o /dev/null "${BASE_URL}/health"
  echo "  $(green "sent") GET /health"

  echo ""
  echo "  $(dim "Waiting 15s for batch export to collector...")"
  sleep 15
fi

# ---------------------------------------------------------------------------
# 3. Verify Collector debug logs
# ---------------------------------------------------------------------------
if [ "${SKIP_LOG_CHECK:-0}" = "0" ]; then
  echo ""
  echo "$(cyan "=== 3. Collector Debug Log Verification ===")"
  echo "$(dim "    Checking last 500 lines of collector logs for expected telemetry")"
  echo ""

  LOGS=$(docker compose logs otel-collector --tail=500 --no-log-prefix 2>/dev/null || echo "")

  if [ -z "$LOGS" ]; then
    echo "  $(yellow "WARN: Could not read collector logs. Are you in the project directory?")"
    echo "  $(dim  "       Try: cd $(pwd) && docker compose logs otel-collector --tail=100")"
  else
    # --- Spans ---
    echo "  $(dim "--- Trace Spans ---")"
    check_log "Span: content_analysis review"   "content_analysis review"   "$LOGS"
    check_log "Span: content_analysis improve"  "content_analysis improve"  "$LOGS"
    check_log "Span: content_analysis score"    "content_analysis score"    "$LOGS"

    # --- Span attributes ---
    echo "  $(dim "--- Span Attributes ---")"
    warn_log  "Attr: content.type"              "content.type"              "$LOGS"
    warn_log  "Attr: content.length"            "content.length"            "$LOGS"
    warn_log  "Attr: gen_ai.request.model"      "gen_ai.request.model"     "$LOGS"
    warn_log  "Attr: gen_ai.provider.name"      "gen_ai.provider.name"     "$LOGS"
    warn_log  "Attr: gen_ai.operation.name"     "gen_ai.operation.name"    "$LOGS"

    # --- Span events ---
    echo "  $(dim "--- Span Events ---")"
    warn_log  "Event: gen_ai.system.message"    "gen_ai.system.message"    "$LOGS"
    warn_log  "Event: gen_ai.user.message"      "gen_ai.user.message"      "$LOGS"
    warn_log  "Event: gen_ai.assistant.message"  "gen_ai.assistant.message" "$LOGS"
    warn_log  "Event: gen_ai.evaluation.result"  "gen_ai.evaluation.result" "$LOGS"

    # --- PII scrubbing (should NOT appear in logs) ---
    echo "  $(dim "--- PII Scrubbing (should be absent) ---")"
    if echo "$LOGS" | grep -q "john@example.com"; then
      echo "  $(red "FAIL") PII leak: john@example.com found in collector logs"
      FAIL=$((FAIL + 1))
    else
      echo "  $(green "PASS") No PII leak: john@example.com absent from collector logs"
      PASS=$((PASS + 1))
    fi

    if echo "$LOGS" | grep -q "123-45-6789"; then
      echo "  $(red "FAIL") PII leak: SSN 123-45-6789 found in collector logs"
      FAIL=$((FAIL + 1))
    else
      echo "  $(green "PASS") No PII leak: SSN absent from collector logs"
      PASS=$((PASS + 1))
    fi

    # --- Metrics ---
    echo "  $(dim "--- Metrics ---")"
    warn_log  "Metric: gen_ai.client.token.usage"       "gen_ai.client.token.usage"       "$LOGS"
    warn_log  "Metric: gen_ai.client.operation.duration" "gen_ai.client.operation.duration" "$LOGS"
    warn_log  "Metric: gen_ai.client.cost"               "gen_ai.client.cost"               "$LOGS"
    warn_log  "Metric: gen_ai.evaluation.score"          "gen_ai.evaluation.score"          "$LOGS"
    warn_log  "Metric: http.server.request.count"        "http.server.request.count"        "$LOGS"
    warn_log  "Metric: http.server.request.duration"     "http.server.request.duration"     "$LOGS"

    # --- Resource attributes ---
    echo "  $(dim "--- Resource Attributes ---")"
    warn_log  "Resource: service.name"           "service.name"           "$LOGS"
    warn_log  "Resource: deployment.environment"  "deployment.environment" "$LOGS"
  fi
fi

# ---------------------------------------------------------------------------
# 4. Scout Dashboard Checklist
# ---------------------------------------------------------------------------
echo ""
echo "$(cyan "=== 4. Scout Dashboard Checklist ===")"
echo "$(dim "    Open Base14 Scout and verify these manually:")"
echo ""
echo "  $(cyan "Content Quality Dashboard:")"
echo "    [ ] Avg Quality Score panel shows data"
echo "    [ ] Score Distribution histogram has buckets"
echo "    [ ] Quality Over Time shows recent data points"
echo "    [ ] Issues by Type shows breakdown (hyperbole, grammar, etc.)"
echo "    [ ] Quality by Content Type shows marketing, technical, blog"
echo ""
echo "  $(cyan "Eval Pass Rate Dashboard:")"
echo "    [ ] gen_ai.evaluation.result events visible in traces"
echo "    [ ] Score values present (passed >= 60, failed < 60)"
echo ""
echo "  $(cyan "Cost & Token Dashboard:")"
echo "    [ ] Total Cost (24h) shows non-zero value"
echo "    [ ] Token Usage shows input vs output breakdown"
echo "    [ ] Cost by Endpoint shows /review, /improve, /score"
echo ""
echo "  $(cyan "Trace Explorer:")"
echo "    [ ] Traces show nested spans: HTTP → content_analysis → LlamaIndex"
echo "    [ ] content_analysis spans have content.type, content.length attributes"
echo "    [ ] gen_ai.system.message events show [EMAIL] not raw emails"
echo "    [ ] gen_ai.user.message events are truncated to ~500 chars"
echo "    [ ] Error traces (if any) show error.type attribute"
echo ""
echo "  $(cyan "Logs:")"
echo "    [ ] Log records include trace_id and span_id correlation"
echo "    [ ] Warning logs for token unavailability (if using non-OpenAI provider)"
echo ""

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
TOTAL=$((PASS + FAIL + WARN))
echo "$(cyan "=== Summary ===")"
echo ""
if [ "$FAIL" -eq 0 ] && [ "$WARN" -eq 0 ]; then
  echo "  $(green "All ${TOTAL} checks passed")"
elif [ "$FAIL" -eq 0 ]; then
  echo "  $(green "${PASS} passed"), $(yellow "${WARN} warnings") (may need longer batch interval)"
else
  echo "  $(green "${PASS} passed"), $(red "${FAIL} failed"), $(yellow "${WARN} warnings")"
fi
echo ""
