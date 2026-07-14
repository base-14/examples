#!/usr/bin/env bash
set -euo pipefail 2>/dev/null || set -eu

# ---------------------------------------------------------------------------
# verify-scout.sh — End-to-end telemetry verification for ai-runbook-assistant
#
# Sends a diagnosis request, then inspects the OTel Collector debug logs to
# confirm the expected GenAI-semconv span tree, attributes, and metrics arrived.
# Run it once per instrumentation mode:
#   INSTRUMENTATION_MODE=callback docker compose up -d --build && ./scripts/verify-scout.sh
#   INSTRUMENTATION_MODE=auto     docker compose up -d --build && ./scripts/verify-scout.sh
#
# Local-only: with SCOUT_* blank the otlphttp/b14 export fails (harmless) but the
# debug exporter still logs every span, so this script passes without Scout creds.
#
# Usage:
#   ./scripts/verify-scout.sh                  # full verification
#   SKIP_REQUESTS=1 ./scripts/verify-scout.sh  # only re-check logs
# ---------------------------------------------------------------------------

BASE_URL="${API_URL:-http://localhost:8000}"
COLLECTOR_HEALTH="${COLLECTOR_HEALTH_URL:-http://localhost:13133}"
MODE="${INSTRUMENTATION_MODE:-callback}"
PASS=0
FAIL=0
WARN=0

green()  { printf "\033[32m%s\033[0m" "$1"; }
red()    { printf "\033[31m%s\033[0m" "$1"; }
cyan()   { printf "\033[36m%s\033[0m" "$1"; }
yellow() { printf "\033[33m%s\033[0m" "$1"; }
dim()    { printf "\033[90m%s\033[0m" "$1"; }

check() {
  local label="$1" expected="$2" actual="$3"
  if [ "$actual" = "$expected" ]; then
    echo "  $(green "PASS") ${label}"; PASS=$((PASS + 1))
  else
    echo "  $(red "FAIL") ${label} (expected ${expected}, got ${actual})"; FAIL=$((FAIL + 1))
  fi
}

check_log() {
  local label="$1" pattern="$2" file="$3"
  if grep -q "$pattern" "$file" 2>/dev/null; then
    echo "  $(green "PASS") ${label}"; PASS=$((PASS + 1))
  else
    echo "  $(red "FAIL") ${label} — pattern not found: ${pattern}"; FAIL=$((FAIL + 1))
  fi
}

warn_log() {
  local label="$1" pattern="$2" file="$3"
  if grep -q "$pattern" "$file" 2>/dev/null; then
    echo "  $(green "PASS") ${label}"; PASS=$((PASS + 1))
  else
    echo "  $(yellow "WARN") ${label} — pattern not found (may need more time): ${pattern}"; WARN=$((WARN + 1))
  fi
}

echo ""
echo "$(cyan "=============================================")"
echo "$(cyan "  Telemetry Verification — Base14 Scout")"
echo "$(cyan "  ai-runbook-assistant  [mode: ${MODE}]")"
echo "$(cyan "=============================================")"

# --- 1. Prerequisites ------------------------------------------------------
echo ""
echo "$(cyan "=== 1. Prerequisites ===")"
echo ""
echo "  $(dim "Checking app health...")"
APP_STATUS=$(curl -s -o /dev/null -w "%{http_code}" "${BASE_URL}/healthz" 2>/dev/null || echo "000")
check "App is healthy (${BASE_URL}/healthz)" "200" "$APP_STATUS"
if [ "$APP_STATUS" != "200" ]; then
  echo ""; echo "  $(red "App is not running. Start it with: docker compose up -d --build")"; exit 1
fi

echo "  $(dim "Checking OTel Collector health...")"
COLLECTOR_STATUS=$(curl -s -o /dev/null -w "%{http_code}" "${COLLECTOR_HEALTH}" 2>/dev/null || echo "000")
check "Collector is healthy (${COLLECTOR_HEALTH})" "200" "$COLLECTOR_STATUS"
if [ "$COLLECTOR_STATUS" != "200" ]; then
  echo ""; echo "  $(yellow "WARN: Collector not reachable — log verification will be skipped")"; SKIP_LOG_CHECK=1
else
  SKIP_LOG_CHECK=0
fi

# --- 2. Generate telemetry -------------------------------------------------
if [ "${SKIP_REQUESTS:-}" != "1" ]; then
  echo ""
  echo "$(cyan "=== 2. Generating telemetry (diagnosis requests) ===")"
  echo ""
  for q in \
    "checkout pods are being OOMKilled, what do I do?" \
    "payments is timing out, p99 latency is high"; do
    echo "  $(dim "POST /api/v1/diagnose: ${q}")"
    curl -s -X POST "${BASE_URL}/api/v1/diagnose" \
      -H 'content-type: application/json' \
      -d "{\"question\": \"${q}\"}" >/dev/null || true
    echo "  $(green "sent")"
  done
  # Error span: malformed payload → 422
  echo "  $(dim "Triggering 422 validation-error span...")"
  curl -s -o /dev/null -X POST "${BASE_URL}/api/v1/diagnose" \
    -H 'content-type: application/json' -d '{}' || true
  echo "  $(green "sent") POST /api/v1/diagnose (invalid — 422)"
  echo ""
  echo "  $(dim "Waiting 20s for batch export to the collector...")"
  sleep 20
fi

# --- 3. Verify collector debug logs ----------------------------------------
if [ "${SKIP_LOG_CHECK:-0}" = "0" ]; then
  echo ""
  echo "$(cyan "=== 3. Collector Debug Log Verification ===")"
  echo ""
  LOGS_FILE=$(mktemp /tmp/otel-logs-XXXXXX.txt)
  docker compose logs otel-collector --since=15m --no-log-prefix >"$LOGS_FILE" 2>/dev/null || true

  if [ ! -s "$LOGS_FILE" ]; then
    echo "  $(yellow "WARN: Could not read collector logs — run from the project directory")"
    rm -f "$LOGS_FILE"
  else
    echo "  $(dim "--- Span tree ---")"
    if [ "$MODE" = "callback" ]; then
      # Custom handler → GenAI-semconv span names
      check_log "Span: invoke_agent runbook_assistant" "invoke_agent runbook_assistant" "$LOGS_FILE"
      check_log "Span: chat {model} (semconv name)"    "chat qwen"                       "$LOGS_FILE"
      check_log "Span: execute_tool"                   "execute_tool"                    "$LOGS_FILE"
      warn_log  "Span: retrieval"                      "retrieval"                       "$LOGS_FILE"
    else
      # OpenLLMetry (auto) → ChatOllama.chat naming + traceloop.* attrs
      check_log "Span: ChatOllama.chat (OpenLLMetry)" "ChatOllama.chat"                  "$LOGS_FILE"
      warn_log  "Attr: traceloop.* association"       "traceloop"                        "$LOGS_FILE"
    fi

    echo "  $(dim "--- GenAI span attributes ---")"
    warn_log "Attr: gen_ai.operation.name"   "gen_ai.operation.name"   "$LOGS_FILE"
    warn_log "Attr: gen_ai.provider.name"    "gen_ai.provider.name"    "$LOGS_FILE"
    warn_log "Attr: gen_ai.usage.input_tokens"  "gen_ai.usage.input_tokens"  "$LOGS_FILE"
    warn_log "Attr: gen_ai.usage.output_tokens" "gen_ai.usage.output_tokens" "$LOGS_FILE"

    echo "  $(dim "--- Persistence + HTTP spans ---")"
    warn_log "Span: SQLAlchemy INSERT (diagnoses)" "diagnoses" "$LOGS_FILE"
    warn_log "Span: HTTP POST /api/v1/diagnose"    "/api/v1/diagnose" "$LOGS_FILE"

    echo "  $(dim "--- Metrics ---")"
    warn_log "Metric: gen_ai.client.token.usage"        "gen_ai.client.token.usage"        "$LOGS_FILE"
    warn_log "Metric: gen_ai.client.operation.duration" "gen_ai.client.operation.duration" "$LOGS_FILE"

    echo "  $(dim "--- Resource attributes ---")"
    check_log "Resource: service.name = ai-runbook-assistant" "ai-runbook-assistant" "$LOGS_FILE"
    warn_log  "Resource: deployment.environment"              "deployment.environment:" "$LOGS_FILE"
    warn_log  "Resource: environment (dual-key)"              "> environment: Str(" "$LOGS_FILE"

    echo "  $(dim "--- Content capture ---")"
    if [ "$MODE" = "callback" ]; then
      # Custom handler: content OFF unless OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT=true
      if grep -q "OOMKilled, what do I do" "$LOGS_FILE" 2>/dev/null; then
        echo "  $(red "FAIL") prompt content leaked (capture should be OFF by default)"; FAIL=$((FAIL + 1))
      else
        echo "  $(green "PASS") no prompt content in spans (capture OFF by default)"; PASS=$((PASS + 1))
      fi
    else
      # OpenLLMetry captures prompt/completion content BY DEFAULT — this is the
      # documented contrast with the custom handler. Disable with
      # TRACELOOP_TRACE_CONTENT=false. We assert the default behaviour here.
      if grep -qE "gen_ai.prompt|gen_ai.completion|gen_ai.input.messages|OOMKilled, what do I do" "$LOGS_FILE" 2>/dev/null; then
        echo "  $(green "PASS") OpenLLMetry captures content by default (set TRACELOOP_TRACE_CONTENT=false to disable)"; PASS=$((PASS + 1))
      else
        echo "  $(yellow "WARN") expected OpenLLMetry default content capture not observed"; WARN=$((WARN + 1))
      fi
    fi
    rm -f "$LOGS_FILE"
  fi
fi

# --- 4. Scout dashboard checklist (manual, when Scout creds are set) --------
echo ""
echo "$(cyan "=== 4. Scout Dashboard Checklist ===")"
echo "$(dim "    With SCOUT_* set, open Base14 Scout and verify:")"
echo "    [ ] Trace shows invoke_agent → chat / execute_tool / retrieval span tree"
echo "    [ ] gen_ai.usage.input_tokens / output_tokens / cost_usd on chat spans"
echo "    [ ] diagnoses INSERT span linked in the same trace (trace_id)"
echo "    [ ] token.usage + operation.duration metrics non-empty"
echo ""

# --- Summary ---------------------------------------------------------------
TOTAL=$((PASS + FAIL + WARN))
echo "$(cyan "=== Summary ===")"
echo ""
if [ "$FAIL" -eq 0 ] && [ "$WARN" -eq 0 ]; then
  echo "  $(green "All ${TOTAL} checks passed")"
elif [ "$FAIL" -eq 0 ]; then
  echo "  $(green "${PASS} passed"), $(yellow "${WARN} warnings")"
else
  echo "  $(green "${PASS} passed"), $(red "${FAIL} failed"), $(yellow "${WARN} warnings")"
fi
echo ""
[ "$FAIL" -eq 0 ]
