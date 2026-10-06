#!/usr/bin/env bash
set -euo pipefail 2>/dev/null || set -eu

# ---------------------------------------------------------------------------
# verify-scout.sh - End-to-end telemetry verification for ai-runbook-assistant
#
# Sends a diagnosis request, then inspects the OTel Collector debug logs to
# confirm the expected GenAI-semconv span tree, attributes, and metrics arrived:
#   docker compose up -d --build && ./scripts/verify-scout.sh
# Set OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT=span_only for both the
# stack and this script to check that captured content is scrubbed.
#
# With SCOUT_* blank the export to Scout fails (harmless) but the debug exporter
# still logs every span, so this script passes without Scout credentials.
#
# Usage:
#   ./scripts/verify-scout.sh                  # full verification
#   SKIP_REQUESTS=1 ./scripts/verify-scout.sh  # only re-check logs
# ---------------------------------------------------------------------------

BASE_URL="${API_URL:-http://localhost:8000}"
COLLECTOR_HEALTH="${COLLECTOR_HEALTH_URL:-http://localhost:13133}"
CAPTURE="$(echo "${OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT:-no_content}" | tr '[:upper:]' '[:lower:]')"
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
    echo "  $(red "FAIL") ${label} - pattern not found: ${pattern}"; FAIL=$((FAIL + 1))
  fi
}

warn_log() {
  local label="$1" pattern="$2" file="$3"
  if grep -q "$pattern" "$file" 2>/dev/null; then
    echo "  $(green "PASS") ${label}"; PASS=$((PASS + 1))
  else
    echo "  $(yellow "WARN") ${label} - pattern not found (may need more time): ${pattern}"; WARN=$((WARN + 1))
  fi
}

echo ""
echo "$(cyan "=============================================")"
echo "$(cyan "  Telemetry Verification - Base14 Scout")"
echo "$(cyan "  ai-runbook-assistant  [content capture: ${CAPTURE}]")"
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
  echo ""; echo "  $(yellow "WARN: Collector not reachable - log verification will be skipped")"; SKIP_LOG_CHECK=1
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
  echo "  $(green "sent") POST /api/v1/diagnose (invalid - 422)"
  echo ""
  echo "  $(dim "Waiting 20s for batch export to the collector...")"
  sleep 20
fi

# --- 3. Verify collector debug logs ----------------------------------------
if [ "${SKIP_LOG_CHECK:-0}" = "0" ]; then
  echo ""
  echo "$(cyan "=== 3. Collector Debug Log Verification ===")"
  echo ""
  LOGS_FILE="${COLLECTOR_LOG:-}"
  CLEANUP_LOGS=0
  if [ -z "$LOGS_FILE" ]; then
    LOGS_FILE=$(mktemp /tmp/otel-logs-XXXXXX.txt)
    CLEANUP_LOGS=1
    docker compose logs otel-collector --since=15m --no-log-prefix >"$LOGS_FILE" 2>/dev/null || true
  fi

  if [ ! -s "$LOGS_FILE" ]; then
    echo "  $(yellow "WARN: Could not read collector logs - run from the project directory")"
    [ "$CLEANUP_LOGS" = "1" ] && rm -f "$LOGS_FILE"
  else
    echo "  $(dim "--- Span tree ---")"
    check_log "Span: invoke_agent runbook_assistant" "invoke_agent runbook_assistant" "$LOGS_FILE"
    check_log "Span: chat {model}"                   "Name *: chat "                   "$LOGS_FILE"
    check_log "Span kind: Client on chat spans"      "Kind *: Client"                  "$LOGS_FILE"
    check_log "Span: execute_tool {name}"            "Name *: execute_tool "           "$LOGS_FILE"
    warn_log  "Span: retrieval"                      "Name *: retrieval"               "$LOGS_FILE"
    warn_log  "Span: embeddings {model}"             "Name *: embeddings "             "$LOGS_FILE"

    # Every chat span comes from the LangChain instrumentation, and no chat span
    # is the child of another: a model wrapped in another model would double them.
    CHAT_REPORT=$(awk '
      /ScopeSpans #/{spans=1} /ScopeMetrics #|ScopeLogs #/{spans=0}
      spans && /InstrumentationScope/{scope=$2}
      spans && /^ *Parent ID *:/{parent=$NF}
      spans && /^ *ID *:/{id=$NF}
      spans && /Name *: chat /{chat[id]=1; parents[id]=parent; scopes[scope]++}
      END{
        nested=0; for (c in chat) if (parents[c] in chat) nested++
        for (s in scopes) printf "scope %s %d\n", s, scopes[s]
        printf "nested %d\n", nested
      }' "$LOGS_FILE")
    if echo "$CHAT_REPORT" | grep -q "^scope " && ! echo "$CHAT_REPORT" | grep "^scope " | grep -qv "opentelemetry.instrumentation.genai.langchain"; then
      echo "  $(green "PASS") Every chat span comes from the LangChain instrumentation"; PASS=$((PASS + 1))
    else
      echo "  $(red "FAIL") chat spans from other scopes, or none:"; echo "$CHAT_REPORT" | sed 's/^/      /'; FAIL=$((FAIL + 1))
    fi
    if echo "$CHAT_REPORT" | grep -q "^nested 0$"; then
      echo "  $(green "PASS") No chat span nested inside another"; PASS=$((PASS + 1))
    else
      echo "  $(red "FAIL") chat spans nested inside chat spans: $(echo "$CHAT_REPORT" | grep ^nested)"; FAIL=$((FAIL + 1))
    fi
    check_log "Attr: gen_ai.agent.name on invoke_agent" "gen_ai.agent.name: Str(runbook_assistant)" "$LOGS_FILE"
    warn_log  "Attr: app.retrieval.chunk_count on retrieval" "app.retrieval.chunk_count" "$LOGS_FILE"

    echo "  $(dim "--- Required GenAI span attributes ---")"
    warn_log "Attr: gen_ai.operation.name"    "gen_ai.operation.name"    "$LOGS_FILE"
    warn_log "Attr: gen_ai.provider.name"     "gen_ai.provider.name"     "$LOGS_FILE"
    warn_log "Attr: gen_ai.request.model"     "gen_ai.request.model"     "$LOGS_FILE"
    warn_log "Attr: gen_ai.data_source.id"    "gen_ai.data_source.id"    "$LOGS_FILE"

    echo "  $(dim "--- Recommended GenAI span attributes ---")"
    warn_log "Attr: server.address"                "server.address"                "$LOGS_FILE"
    warn_log "Attr: server.port"                   "server.port"                   "$LOGS_FILE"
    warn_log "Attr: gen_ai.request.temperature"    "gen_ai.request.temperature"    "$LOGS_FILE"
    warn_log "Attr: gen_ai.request.max_tokens"     "gen_ai.request.max_tokens"     "$LOGS_FILE"
    warn_log "Attr: gen_ai.response.model"         "gen_ai.response.model"         "$LOGS_FILE"
    warn_log "Attr: gen_ai.response.finish_reasons" "gen_ai.response.finish_reasons" "$LOGS_FILE"
    warn_log "Attr: gen_ai.usage.input_tokens"     "gen_ai.usage.input_tokens"     "$LOGS_FILE"
    warn_log "Attr: gen_ai.usage.output_tokens"    "gen_ai.usage.output_tokens"    "$LOGS_FILE"
    warn_log "Attr: base14.gen_ai.cost_usd"        "base14.gen_ai.cost_usd"        "$LOGS_FILE"
    warn_log "Attr: gen_ai.tool.call.id"           "gen_ai.tool.call.id"           "$LOGS_FILE"
    warn_log "Attr: gen_ai.conversation.id"        "gen_ai.conversation.id"        "$LOGS_FILE"

    echo "  $(dim "--- Span events ---")"
    # The inference event only appears when content capture is switched on, so
    # its absence is expected here. The two removed message events must be gone.
    EVENTS_CLEAN=1
    for role in user assistant; do
      if grep -q "gen_ai.${role}.message" "$LOGS_FILE" 2>/dev/null; then
        echo "  $(red "FAIL") Removed per-message event still emitted for role: ${role}"
        FAIL=$((FAIL + 1)); EVENTS_CLEAN=0
      fi
    done
    if [ "$EVENTS_CLEAN" = "1" ]; then
      echo "  $(green "PASS") The removed per-message events are absent"; PASS=$((PASS + 1))
    fi

    echo "  $(dim "--- Persistence + HTTP spans ---")"
    warn_log "Span: SQLAlchemy INSERT (diagnoses)" "diagnoses"        "$LOGS_FILE"
    warn_log "Span: HTTP POST /api/v1/diagnose"    "/api/v1/diagnose" "$LOGS_FILE"

    echo "  $(dim "--- Error telemetry ---")"
    warn_log "Attr: error.type (on the 422 span)" "error.type" "$LOGS_FILE"

    echo "  $(dim "--- Metrics ---")"
    warn_log "Metric: gen_ai.client.token.usage"        "gen_ai.client.token.usage"        "$LOGS_FILE"
    warn_log "Metric: gen_ai.client.operation.duration" "gen_ai.client.operation.duration" "$LOGS_FILE"
    warn_log "Metric: base14.gen_ai.cost"               "Name: base14.gen_ai.cost"         "$LOGS_FILE"
    warn_log "Metric: base14.gen_ai.retry.count"        "base14.gen_ai.retry.count"        "$LOGS_FILE"
    warn_log "Metric: base14.gen_ai.fallback.count"     "base14.gen_ai.fallback.count"     "$LOGS_FILE"
    warn_log "Metric: base14.gen_ai.error.count"        "base14.gen_ai.error.count"        "$LOGS_FILE"
    # The FastAPI instrumentation still emits the old HTTP metric names; only
    # the GenAI conventions are opted in. Accept either name.
    warn_log "Metric: http server request duration" \
      "http.server.request.duration\|http.server.duration" "$LOGS_FILE"

    echo "  $(dim "--- Resource attributes ---")"
    check_log "Resource: service.name = ai-runbook-assistant" "ai-runbook-assistant" "$LOGS_FILE"
    warn_log  "Resource: deployment.environment.name"              "deployment.environment.name:" "$LOGS_FILE"
    warn_log  "Resource: environment (dual-key)"              "> environment: Str(" "$LOGS_FILE"

    echo "  $(dim "--- Content capture ---")"
    case "$CAPTURE" in
      span_only|span_and_event)
        if grep -q "gen_ai.input.messages" "$LOGS_FILE" 2>/dev/null; then
          echo "  $(green "PASS") prompt content captured on spans (${CAPTURE})"; PASS=$((PASS + 1))
        else
          echo "  $(red "FAIL") ${CAPTURE} is set but no gen_ai.input.messages on any span"; FAIL=$((FAIL + 1))
        fi
        ;;
      *)
        if grep -q "OOMKilled, what do I do" "$LOGS_FILE" 2>/dev/null; then
          echo "  $(red "FAIL") prompt content leaked (capture is ${CAPTURE})"; FAIL=$((FAIL + 1))
        else
          echo "  $(green "PASS") no prompt content in spans (capture is ${CAPTURE})"; PASS=$((PASS + 1))
        fi
        ;;
    esac
    [ "$CLEANUP_LOGS" = "1" ] && rm -f "$LOGS_FILE"
  fi
fi

# --- 4. Scout dashboard checklist (manual, when Scout creds are set) --------
echo ""
echo "$(cyan "=== 4. Scout Dashboard Checklist ===")"
echo "$(dim "    With SCOUT_* set, open Base14 Scout and verify:")"
echo "    [ ] Trace shows invoke_agent → chat / execute_tool / retrieval / embeddings span tree"
echo "    [ ] gen_ai.usage.input_tokens, output_tokens and base14.gen_ai.cost_usd on chat spans"
echo "    [ ] diagnoses INSERT span linked in the same trace (trace_id)"
echo "    [ ] token.usage and operation.duration metrics non-empty"
echo "    [ ] base14.gen_ai.retry.count and .fallback.count visible (zero when the provider is healthy)"
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
