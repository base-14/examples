#!/usr/bin/env bash
set -euo pipefail

# ---------------------------------------------------------------------------
# verify-scout.sh - End-to-end telemetry verification
#
# Drives the contract analysis pipeline, then reads the OTel Collector debug
# output to confirm the GenAI semconv spans, attributes, events and metrics
# arrived with the names this example claims to emit.
#
# Prerequisites:
#   docker compose up -d
#   (wait for app + collector to be healthy)
#
# Usage:
#   ./scripts/verify-scout.sh                  # full verification
#   SKIP_REQUESTS=1 ./scripts/verify-scout.sh  # only check logs (re-run)
#   COLLECTOR_LOG=/tmp/collector.log ./scripts/verify-scout.sh  # check a saved log
# ---------------------------------------------------------------------------

BASE_URL="${API_URL:-http://localhost:3000}"
COLLECTOR_HEALTH="${COLLECTOR_HEALTH_URL:-http://localhost:13133}"
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

absent_log() {
  local label="$1" pattern="$2" file="$3"
  if grep -q "$pattern" "$file" 2>/dev/null; then
    echo "  $(red "FAIL") ${label} - retired name still emitted: ${pattern}"
    FAIL=$((FAIL + 1))
  else
    echo "  $(green "PASS") ${label}"
    PASS=$((PASS + 1))
  fi
}

echo ""
echo "$(cyan "=============================================")"
echo "$(cyan "  Telemetry Verification - Base14 Scout")"
echo "$(cyan "  AI Contract Analyzer")"
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
fi

# ---------------------------------------------------------------------------
# 2. Run the pipeline (telemetry-generating requests)
# ---------------------------------------------------------------------------
if [ "${SKIP_REQUESTS:-}" != "1" ] && [ -z "${COLLECTOR_LOG:-}" ]; then
  echo ""
  echo "$(cyan "=== 2. Running the Contract Pipeline ===")"
  echo ""

  SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
  SAMPLE="${SCRIPT_DIR}/../data/contracts/sample-nda.txt"

  echo "  $(dim "Uploading sample NDA (ingest, route, embed, extract, score, summarize)...")"
  UPLOAD=$(curl -s --max-time 1800 -X POST "${BASE_URL}/api/contracts" \
    -F "file=@${SAMPLE};type=text/plain")
  CONTRACT_ID=$(echo "$UPLOAD" | python3 -c "import sys,json; print(json.load(sys.stdin).get('contract_id',''))" 2>/dev/null || echo "")

  if [ -z "$CONTRACT_ID" ]; then
    echo "  $(red "FAIL: analysis did not return a contract_id. Response: ${UPLOAD}")"
    exit 1
  fi
  RISK=$(echo "$UPLOAD" | python3 -c "import sys,json; print(json.load(sys.stdin).get('overall_risk',''))" 2>/dev/null || echo "")
  echo "  $(green "analyzed") contract id=${CONTRACT_ID} overall_risk=${RISK}"

  echo "  $(dim "Asking a question (embeddings + retrieval + chat)...")"
  curl -s --max-time 600 -o /dev/null -X POST "${BASE_URL}/api/contracts/${CONTRACT_ID}/query" \
    -H "Content-Type: application/json" \
    -d '{"question":"What is the confidentiality term?"}' || true
  echo "  $(green "sent") 1 query"

  echo "  $(dim "Running semantic search (embeddings + retrieval)...")"
  curl -s -o /dev/null -X POST "${BASE_URL}/api/search" \
    -H "Content-Type: application/json" \
    -d '{"query":"indemnification obligations","limit":5}' || true
  echo "  $(green "sent") 1 search"

  echo "  $(dim "Triggering error spans...")"
  curl -s -o /dev/null "${BASE_URL}/api/contracts/00000000-0000-0000-0000-000000000000" || true
  curl -s -o /dev/null -X POST "${BASE_URL}/api/contracts" -F "not_a_file=hello" || true
  echo "  $(green "sent") 404 and 400 requests"

  echo ""
  echo "  $(dim "Waiting 30s for batch export to the collector...")"
  sleep 30
fi

# ---------------------------------------------------------------------------
# 3. Verify Collector debug logs
# ---------------------------------------------------------------------------
echo ""
echo "$(cyan "=== 3. Collector Debug Log Verification ===")"
echo ""

OWN_LOG=0
if [ -n "${COLLECTOR_LOG:-}" ]; then
  LOGS_FILE="$COLLECTOR_LOG"
  echo "$(dim "    Reading saved collector output: ${LOGS_FILE}")"
else
  LOGS_FILE=$(mktemp /tmp/otel-logs-XXXXXX.txt)
  OWN_LOG=1
  echo "$(dim "    Checking the last 15 minutes of collector output")"
  docker compose logs otel-collector --since=15m --no-log-prefix >"$LOGS_FILE" 2>/dev/null || true
fi
echo ""

if [ ! -s "$LOGS_FILE" ]; then
  echo "  $(yellow "WARN: Could not read collector logs. Are you in the project directory?")"
  [ "$OWN_LOG" = "1" ] && rm -f "$LOGS_FILE"
else
  echo "  $(dim "--- Trace Spans ---")"
  check_log "Span: chat {model}"                "Name *: chat "               "$LOGS_FILE"
  check_log "Span kind: Client on GenAI spans"  "Kind *: Client"              "$LOGS_FILE"
  check_log "Span: embeddings {model}"          "Name *: embeddings "         "$LOGS_FILE"
  check_log "Span: retrieval contract_chunks"   "Name *: retrieval contract_chunks" "$LOGS_FILE"
  check_log "Span: POST /api/contracts"         "POST /api/contracts"         "$LOGS_FILE"
  warn_log  "Span kind: Server on HTTP spans"   "Kind *: Server"              "$LOGS_FILE"
  warn_log  "Span: pipeline_stage extract"      "pipeline_stage extract"      "$LOGS_FILE"
  warn_log  "Span: analyze_contract"            "analyze_contract"            "$LOGS_FILE"

  echo "  $(dim "--- Required GenAI Span Attributes ---")"
  check_log "Attr: gen_ai.operation.name"       "gen_ai.operation.name"       "$LOGS_FILE"
  check_log "Attr: gen_ai.provider.name"        "gen_ai.provider.name"        "$LOGS_FILE"
  check_log "Attr: gen_ai.request.model"        "gen_ai.request.model"        "$LOGS_FILE"
  check_log "Attr: gen_ai.data_source.id"       "gen_ai.data_source.id"       "$LOGS_FILE"

  echo "  $(dim "--- Recommended GenAI Span Attributes ---")"
  warn_log  "Attr: server.address"              "server.address"              "$LOGS_FILE"
  warn_log  "Attr: server.port (11434 for Ollama)" "server.port"              "$LOGS_FILE"
  warn_log  "Attr: gen_ai.response.model"       "gen_ai.response.model"       "$LOGS_FILE"
  warn_log  "Attr: gen_ai.response.finish_reasons" "gen_ai.response.finish_reasons" "$LOGS_FILE"
  warn_log  "Attr: gen_ai.usage.input_tokens"   "gen_ai.usage.input_tokens"   "$LOGS_FILE"
  warn_log  "Attr: gen_ai.usage.output_tokens"  "gen_ai.usage.output_tokens"  "$LOGS_FILE"
  check_log "Attr: base14.gen_ai.cost_usd"      "base14.gen_ai.cost_usd"      "$LOGS_FILE"

  echo "  $(dim "--- Retired Names (should be absent) ---")"
  absent_log "No gen_ai.chat span name"         "Name *: gen_ai.chat"         "$LOGS_FILE"
  absent_log "No gen_ai.user.message event"     "gen_ai.user.message"         "$LOGS_FILE"
  absent_log "No gen_ai.assistant.message event" "gen_ai.assistant.message"   "$LOGS_FILE"
  absent_log "No gen_ai.usage.cost_usd attr"    "gen_ai.usage.cost_usd"       "$LOGS_FILE"
  absent_log "No gen_ai.client.cost metric"     "gen_ai.client.cost"          "$LOGS_FILE"
  absent_log "No gen_ai.client.retry.count metric"    "gen_ai.client.retry.count"    "$LOGS_FILE"
  absent_log "No gen_ai.client.fallback.count metric" "gen_ai.client.fallback.count" "$LOGS_FILE"
  absent_log "No gen_ai.client.error.count metric"    "gen_ai.client.error.count"    "$LOGS_FILE"

  # The inference event appears only when content capture is switched on, so
  # its absence in a default run is expected.
  echo "  $(dim "--- Span Events ---")"
  warn_log  "Event: gen_ai.client.inference.operation.details" \
            "gen_ai.client.inference.operation.details" "$LOGS_FILE"

  echo "  $(dim "--- Error Telemetry ---")"
  warn_log  "Attr: error.type"                  "error.type"                  "$LOGS_FILE"
  check_log "Status: Error on 4xx HTTP spans"   "Status code .*: Error"       "$LOGS_FILE"

  echo "  $(dim "--- Metrics ---")"
  check_log "Metric: gen_ai.client.token.usage"        "gen_ai.client.token.usage"        "$LOGS_FILE"
  check_log "Metric: gen_ai.client.operation.duration" "gen_ai.client.operation.duration" "$LOGS_FILE"
  check_log "Metric: base14.gen_ai.cost"               "base14.gen_ai.cost"               "$LOGS_FILE"
  warn_log  "Metric: base14.gen_ai.retry.count"        "base14.gen_ai.retry.count"        "$LOGS_FILE"
  warn_log  "Metric: base14.gen_ai.fallback.count"     "base14.gen_ai.fallback.count"     "$LOGS_FILE"
  warn_log  "Metric: base14.gen_ai.error.count"        "base14.gen_ai.error.count"        "$LOGS_FILE"
  warn_log  "Metric: base14.contract.analysis.duration" "base14.contract.analysis.duration" "$LOGS_FILE"
  warn_log  "Metric: http.server.request.duration"     "http.server.request.duration"     "$LOGS_FILE"

  echo "  $(dim "--- Resource Attributes ---")"
  warn_log  "Resource: service.name"            "service.name"                "$LOGS_FILE"
  warn_log  "Resource: deployment.environment"  "deployment.environment"      "$LOGS_FILE"

  [ "$OWN_LOG" = "1" ] && rm -f "$LOGS_FILE"
fi

# ---------------------------------------------------------------------------
# 4. Scout Dashboard Checklist
# ---------------------------------------------------------------------------
echo ""
echo "$(cyan "=== 4. Scout Dashboard Checklist ===")"
echo "$(dim "    Open Base14 Scout and verify these manually:")"
echo ""
echo "  $(cyan "Trace Explorer:")"
echo "    [ ] One trace per upload: POST /api/contracts wraps analyze_contract and its six stages"
echo "    [ ] chat spans are CLIENT and named chat {model}"
echo "    [ ] gen_ai.usage.input_tokens and output_tokens sit on chat spans, not on stage spans"
echo "    [ ] embeddings {model} and retrieval contract_chunks spans appear under /api/search"
echo "    [ ] 400 and 404 responses leave the HTTP span with error status"
echo ""
echo "  $(cyan "Cost and Token Dashboard:")"
echo "    [ ] base14.gen_ai.cost is non-zero for a hosted provider, zero for Ollama"
echo "    [ ] gen_ai.client.token.usage splits by gen_ai.token.type"
echo "    [ ] base14.gen_ai.cost_usd appears per chat span"
echo ""
echo "  $(cyan "Error and Retry Dashboard:")"
echo "    [ ] base14.gen_ai.retry.count is visible (zero when no transient errors)"
echo "    [ ] base14.gen_ai.fallback.count is visible (zero when the primary is healthy)"
echo "    [ ] base14.gen_ai.error.count carries gen_ai.provider.name and error.type"
echo ""
echo "  $(cyan "Logs:")"
echo "    [ ] Log records carry trace_id and span_id"
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
  echo "  $(green "${PASS} passed"), $(yellow "${WARN} warnings") (may need a longer batch interval)"
else
  echo "  $(green "${PASS} passed"), $(red "${FAIL} failed"), $(yellow "${WARN} warnings")"
fi
echo ""

[ "$FAIL" -eq 0 ]
