#!/usr/bin/env bash
set -euo pipefail

# ---------------------------------------------------------------------------
# verify-scout.sh - End-to-end telemetry verification
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
#   COLLECTOR_LOG=/tmp/collector.log ./scripts/verify-scout.sh  # check a saved log
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
  local label="$1" pattern="$2" file="$3"
  if grep -q "$pattern" "$file" 2>/dev/null; then
    echo "  $(green "PASS") ${label}"
    PASS=$((PASS + 1))
  else
    echo "  $(red "FAIL") ${label} - pattern not found: ${pattern}"
    FAIL=$((FAIL + 1))
  fi
}

warn_log() {
  local label="$1" pattern="$2" file="$3"
  if grep -q "$pattern" "$file" 2>/dev/null; then
    echo "  $(green "PASS") ${label}"
    PASS=$((PASS + 1))
  else
    echo "  $(yellow "WARN") ${label} - pattern not found (may need more time): ${pattern}"
    WARN=$((WARN + 1))
  fi
}

echo ""
echo "$(cyan "=============================================")"
echo "$(cyan "  Telemetry Verification - Base14 Scout")"
echo "$(cyan "=============================================")"

# ---------------------------------------------------------------------------
# 1. Prerequisites
# ---------------------------------------------------------------------------
echo ""
echo "$(cyan "=== 1. Prerequisites ===")"
echo ""

# A saved log is read with the stack down, so the live checks do not apply.
if [ -n "${COLLECTOR_LOG:-}" ]; then
  echo "  $(dim "Reading a saved log, skipping the live health checks")"
  SKIP_LOG_CHECK=0
else
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
    echo "  $(yellow "WARN: Collector not reachable - telemetry log verification will be skipped")"
    echo "  $(dim  "       Start with: docker compose up -d")"
    SKIP_LOG_CHECK=1
  else
    SKIP_LOG_CHECK=0
  fi
fi

# ---------------------------------------------------------------------------
# 2. Send telemetry-generating requests
# ---------------------------------------------------------------------------
if [ "${SKIP_REQUESTS:-}" != "1" ] && [ -z "${COLLECTOR_LOG:-}" ]; then
  echo ""
  echo "$(cyan "=== 2. Sending Telemetry-Generating Requests ===")"
  echo ""

  DELAY="${REQUEST_DELAY:-2}"

  echo "  $(dim "[spans] chat span - marketing content")"
  curl -s -o /dev/null -X POST "${BASE_URL}/review" \
    -H "Content-Type: application/json" \
    -d '{"content": "This revolutionary product is the absolute best!", "content_type": "marketing"}'
  echo "  $(green "sent") POST /review (marketing)"
  sleep "$DELAY"

  echo "  $(dim "[spans] chat span - blog content")"
  curl -s -o /dev/null -X POST "${BASE_URL}/improve" \
    -H "Content-Type: application/json" \
    -d '{"content": "The thing is really good and stuff.", "content_type": "blog"}'
  echo "  $(green "sent") POST /improve (blog)"
  sleep "$DELAY"

  echo "  $(dim "[spans] chat span - technical content")"
  curl -s -o /dev/null -X POST "${BASE_URL}/score" \
    -H "Content-Type: application/json" \
    -d '{"content": "Kubernetes orchestrates containerized workloads across clusters.", "content_type": "technical"}'
  echo "  $(green "sent") POST /score (technical)"
  sleep "$DELAY"

  echo "  $(dim "[eval events] Review with many issues - triggers low evaluation score")"
  curl -s -o /dev/null -X POST "${BASE_URL}/review" \
    -H "Content-Type: application/json" \
    -d '{"content": "Everyone knows this is literally the most amazing thing ever! Studies prove 100% of people agree!", "content_type": "marketing"}'
  echo "  $(green "sent") POST /review (hyperbolic - eval event)"
  sleep "$DELAY"

  echo "  $(dim "[PII scrub] Content with email, phone, SSN in prompts")"
  curl -s -o /dev/null -X POST "${BASE_URL}/review" \
    -H "Content-Type: application/json" \
    -d '{"content": "Contact john@example.com or 555-123-4567. SSN 123-45-6789.", "content_type": "general"}'
  echo "  $(green "sent") POST /review (PII content - scrub verification)"

  echo "  $(dim "[error metrics] Validation error - triggers http 422 metric")"
  curl -s -o /dev/null -X POST "${BASE_URL}/review" \
    -H "Content-Type: application/json" \
    -d '{"content": ""}'
  echo "  $(green "sent") POST /review (empty - 422)"

  echo "  $(dim "[error metrics] Unknown route - triggers 404 + error span")"
  curl -s -o /dev/null "${BASE_URL}/nonexistent"
  echo "  $(green "sent") GET /nonexistent (404)"

  echo "  $(dim "[http metrics] Health endpoint - low-cost request for baseline")"
  curl -s -o /dev/null "${BASE_URL}/health"
  echo "  $(green "sent") GET /health"

  echo ""
  echo "  $(dim "Waiting 30s for batch export to collector...")"
  sleep 30
fi

# ---------------------------------------------------------------------------
# 3. Verify Collector debug logs
# ---------------------------------------------------------------------------
if [ "${SKIP_LOG_CHECK:-0}" = "0" ]; then
  echo ""
  echo "$(cyan "=== 3. Collector Debug Log Verification ===")"
  echo "$(dim "    Checking last 3 minutes of collector logs for expected telemetry")"
  echo ""

  OWN_LOG=0
  if [ -n "${COLLECTOR_LOG:-}" ]; then
    LOGS_FILE="$COLLECTOR_LOG"
    echo "  $(dim "Reading saved collector output: ${LOGS_FILE}")"
  else
    LOGS_FILE=$(mktemp /tmp/otel-logs-XXXXXX.txt)
    OWN_LOG=1
    docker compose logs otel-collector --since=3m --no-log-prefix >"$LOGS_FILE" 2>/dev/null || true
  fi

  if [ ! -s "$LOGS_FILE" ]; then
    echo "  $(yellow "WARN: Could not read collector logs. Are you in the project directory?")"
    echo "  $(dim  "       Try: cd $(pwd) && docker compose logs otel-collector --since=3m")"
    [ "$OWN_LOG" = "1" ] && rm -f "$LOGS_FILE"
  else
    # --- Spans ---
    echo "  $(dim "--- Trace Spans ---")"
    check_log "Span: chat {model}"              "Name *: chat "             "$LOGS_FILE"
    check_log "Span kind: Client on chat spans" "Kind *: Client"            "$LOGS_FILE"

    # --- Span attributes ---
    echo "  $(dim "--- Span Attributes ---")"
    warn_log  "Attr: base14.content.type"       "base14.content.type"       "$LOGS_FILE"
    warn_log  "Attr: base14.content.length"     "base14.content.length"     "$LOGS_FILE"
    warn_log  "Attr: gen_ai.request.model"      "gen_ai.request.model"     "$LOGS_FILE"
    warn_log  "Attr: gen_ai.provider.name"      "gen_ai.provider.name"     "$LOGS_FILE"
    warn_log  "Attr: gen_ai.operation.name"     "gen_ai.operation.name"    "$LOGS_FILE"
    warn_log  "Attr: server.address"            "server.address"           "$LOGS_FILE"
    warn_log  "Attr: server.port"               "server.port"              "$LOGS_FILE"
    warn_log  "Attr: gen_ai.response.model"     "gen_ai.response.model"   "$LOGS_FILE"
    warn_log  "Attr: gen_ai.request.temperature" "gen_ai.request.temperature" "$LOGS_FILE"
    warn_log  "Attr: gen_ai.usage.input_tokens" "gen_ai.usage.input_tokens" "$LOGS_FILE"
    warn_log  "Attr: gen_ai.usage.output_tokens" "gen_ai.usage.output_tokens" "$LOGS_FILE"
    warn_log  "Attr: base14.gen_ai.cost_usd"    "base14.gen_ai.cost_usd"   "$LOGS_FILE"

    # --- Error telemetry ---
    echo "  $(dim "--- Error Telemetry ---")"
    warn_log  "Attr: error.type (on error spans)" "error.type"              "$LOGS_FILE"

    # --- Span events ---
    # The inference event only appears when content capture is switched on, so
    # its absence is expected here. The two removed per-message events must be gone.
    echo "  $(dim "--- Span Events ---")"
    EVENTS_CLEAN=1
    for role in user assistant; do
      if grep -q "gen_ai.${role}.message" "$LOGS_FILE" 2>/dev/null; then
        echo "  $(red "FAIL") Removed per-message event still emitted for role: ${role}"
        FAIL=$((FAIL + 1))
        EVENTS_CLEAN=0
      fi
    done
    if [ "$EVENTS_CLEAN" = "1" ]; then
      echo "  $(green "PASS") The removed per-message events are absent"
      PASS=$((PASS + 1))
    fi
    warn_log  "Event: gen_ai.evaluation.result"   "gen_ai.evaluation.result"  "$LOGS_FILE"

    # --- PII scrubbing (should NOT appear in logs) ---
    echo "  $(dim "--- PII Scrubbing (should be absent) ---")"
    if grep -q "john@example.com" "$LOGS_FILE" 2>/dev/null; then
      echo "  $(red "FAIL") PII leak: john@example.com found in collector logs"
      FAIL=$((FAIL + 1))
    else
      echo "  $(green "PASS") No PII leak: john@example.com absent from collector logs"
      PASS=$((PASS + 1))
    fi

    if grep -q "123-45-6789" "$LOGS_FILE" 2>/dev/null; then
      echo "  $(red "FAIL") PII leak: SSN 123-45-6789 found in collector logs"
      FAIL=$((FAIL + 1))
    else
      echo "  $(green "PASS") No PII leak: SSN absent from collector logs"
      PASS=$((PASS + 1))
    fi

    # --- Metrics ---
    echo "  $(dim "--- Metrics ---")"
    warn_log  "Metric: gen_ai.client.token.usage"       "gen_ai.client.token.usage"       "$LOGS_FILE"
    warn_log  "Metric: gen_ai.client.operation.duration" "gen_ai.client.operation.duration" "$LOGS_FILE"
    warn_log  "Metric: base14.gen_ai.cost"               "Name: base14.gen_ai.cost"          "$LOGS_FILE"
    warn_log  "Metric: base14.gen_ai.evaluation.score"   "base14.gen_ai.evaluation.score"    "$LOGS_FILE"
    warn_log  "Metric: base14.gen_ai.error.count"        "base14.gen_ai.error.count"         "$LOGS_FILE"
    warn_log  "Metric: base14.gen_ai.retry.count"        "base14.gen_ai.retry.count"         "$LOGS_FILE"
    warn_log  "Metric: base14.gen_ai.fallback.count"     "base14.gen_ai.fallback.count"      "$LOGS_FILE"
    warn_log  "Metric: http.server.request.count"        "http.server.request.count"        "$LOGS_FILE"
    warn_log  "Metric: http.server.request.duration"     "http.server.request.duration"     "$LOGS_FILE"

    # --- Resource attributes ---
    echo "  $(dim "--- Resource Attributes ---")"
    warn_log  "Resource: service.name"           "service.name"           "$LOGS_FILE"
    warn_log  "Resource: deployment.environment"  "deployment.environment" "$LOGS_FILE"

    [ "$OWN_LOG" = "1" ] && rm -f "$LOGS_FILE"
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
echo "    [ ] Total Cost (24h) is non-zero for priced models and 0 for local Ollama models (base14.gen_ai.cost)"
echo "    [ ] Token Usage shows input vs output breakdown"
echo "    [ ] Cost by Endpoint shows /review, /improve, /score"
echo ""
echo "  $(cyan "Trace Explorer:")"
echo "    [ ] Traces show nested spans: HTTP -> chat {model} -> LlamaIndex"
echo "    [ ] chat spans are CLIENT kind"
echo "    [ ] chat spans have base14.content.type, base14.content.length, server.address attributes"
echo "    [ ] chat spans have gen_ai.request.temperature attribute"
echo "    [ ] The removed gen_ai.user.message / gen_ai.assistant.message events are absent"
echo "    [ ] gen_ai.client.inference.operation.details event present when content capture is enabled"
echo "    [ ] Event content fields are truncated to ~500 chars"
echo "    [ ] 422 error traces have error.type=RequestValidationError and ERROR status"
echo "    [ ] 404 error traces have error status on HTTP span"
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
