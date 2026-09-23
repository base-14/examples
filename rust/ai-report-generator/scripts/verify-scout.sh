#!/usr/bin/env bash
set -euo pipefail

BASE_URL="${API_URL:-http://localhost:8080}"
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
    echo "  $(yellow "WARN") ${label} - pattern not found: ${pattern}"
    WARN=$((WARN + 1))
  fi
}

echo ""
echo "$(cyan "=============================================")"
echo "$(cyan "  Telemetry Verification - Base14 Scout")"
echo "$(cyan "  AI Report Generator")"
echo "$(cyan "=============================================")"

# ── 1. Prerequisites ──────────────────────────────────────────
echo ""
echo "$(cyan "=== 1. Prerequisites ===")"
echo ""

# A saved log is read with the stack down, so the live checks do not apply.
if [ -n "${COLLECTOR_LOG:-}" ]; then
  echo "  $(dim "Reading a saved log, skipping the live health checks")"
  SKIP_LOG_CHECK=0
else
  echo "  $(dim "Checking app health...")"
  APP_STATUS=$(curl -s -o /dev/null -w "%{http_code}" "${BASE_URL}/api/health" 2>/dev/null || echo "000")
  check "App is healthy (${BASE_URL}/api/health)" "200" "$APP_STATUS"

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
    SKIP_LOG_CHECK=1
  else
    SKIP_LOG_CHECK=0
  fi
fi

# ── 2. Generate Traffic ───────────────────────────────────────
if [ "${SKIP_REQUESTS:-}" != "1" ] && [ -z "${COLLECTOR_LOG:-}" ]; then
  echo ""
  echo "$(cyan "=== 2. Generating Telemetry Traffic ===")"
  echo ""

  echo "  $(dim "Generating report with 2 indicators...")"
  curl -s -o /dev/null -X POST "${BASE_URL}/api/reports" \
    -H "Content-Type: application/json" \
    -d '{"indicators":["UNRATE","CPIAUCSL"],"start_date":"2020-01-01","end_date":"2023-12-31"}' || true
  echo "  $(green "sent") POST /api/reports"

  echo "  $(dim "Hitting GET endpoints...")"
  curl -s -o /dev/null "${BASE_URL}/api/indicators" || true
  curl -s -o /dev/null "${BASE_URL}/api/reports" || true
  echo "  $(green "sent") 2 GET requests"

  echo ""
  echo "  $(dim "Generating error traffic...")"

  ERR_STATUS=$(curl -s -o /dev/null -w "%{http_code}" -X POST "${BASE_URL}/api/reports" \
    -H "Content-Type: application/json" \
    -d '{"indicators":[],"start_date":"2022-01-01","end_date":"2023-12-31"}' 2>/dev/null || echo "000")
  check "Empty indicators returns 400" "400" "$ERR_STATUS"

  ERR_STATUS=$(curl -s -o /dev/null -w "%{http_code}" \
    "${BASE_URL}/api/reports/00000000-0000-0000-0000-000000000000" 2>/dev/null || echo "000")
  check "Non-existent report returns 404" "404" "$ERR_STATUS"

  ERR_STATUS=$(curl -s -o /dev/null -w "%{http_code}" -X POST "${BASE_URL}/api/reports" \
    -H "Content-Type: application/json" \
    -d '{"bad json' 2>/dev/null || echo "000")
  check "Malformed JSON returns 400" "400" "$ERR_STATUS"

  echo "  $(dim "Triggering LLM error (bad model → retries + fallback + error)...")"
  LLM_ERR=$(curl -s --max-time 60 -X POST "${BASE_URL}/api/test/llm-error" 2>/dev/null || echo "{}")
  LLM_ERR_STATUS=$(echo "$LLM_ERR" | grep -o '"error_triggered"' || echo "")
  if [ -n "$LLM_ERR_STATUS" ]; then
    echo "  $(green "sent") POST /api/test/llm-error - error path exercised"
  else
    echo "  $(yellow "warn") POST /api/test/llm-error - unexpected response: ${LLM_ERR}"
  fi

  echo ""
  echo "  $(dim "Waiting 15s for batch export to collector...")"
  sleep 15
fi

# ── 3. Collector Debug Log Verification ───────────────────────
if [ "${SKIP_LOG_CHECK:-0}" = "0" ]; then
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
    echo "$(dim "    Checking last 15 minutes of collector logs")"
    docker compose logs otel-collector --since=15m --no-log-prefix >"$LOGS_FILE" 2>/dev/null || true
  fi
  echo ""

  if [ ! -s "$LOGS_FILE" ]; then
    echo "  $(yellow "WARN: Could not read collector logs")"
    [ "$OWN_LOG" = "1" ] && rm -f "$LOGS_FILE"
  else

    # ── GenAI Spans ──
    echo "  $(dim "--- GenAI Spans ---")"
    check_log "Span: chat {model}"                   "Name *: chat "           "$LOGS_FILE"
    check_log "Span kind: Client on chat spans"      "Kind *: Client"          "$LOGS_FILE"
    check_log "Attr: gen_ai.operation.name"          "gen_ai.operation.name"   "$LOGS_FILE"
    check_log "Attr: gen_ai.provider.name"           "gen_ai.provider.name"    "$LOGS_FILE"
    check_log "Attr: gen_ai.request.model"           "gen_ai.request.model"    "$LOGS_FILE"
    check_log "Attr: gen_ai.usage.input_tokens"      "gen_ai.usage.input_tokens"  "$LOGS_FILE"
    check_log "Attr: gen_ai.usage.output_tokens"     "gen_ai.usage.output_tokens" "$LOGS_FILE"

    # ── GenAI Span Events ──
    # Content capture is off by default, so no inference event is expected; the removed message events must not reappear.
    echo "  $(dim "--- GenAI Span Events ---")"
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

    # ── Recommended GenAI Span Attributes ──
    echo "  $(dim "--- Recommended GenAI Span Attributes ---")"
    check_log "Attr: server.address"                 "server.address"          "$LOGS_FILE"
    check_log "Attr: server.port"                    "server.port"             "$LOGS_FILE"
    check_log "Attr: gen_ai.request.temperature"     "gen_ai.request.temperature" "$LOGS_FILE"
    check_log "Attr: gen_ai.request.max_tokens"      "gen_ai.request.max_tokens"  "$LOGS_FILE"
    check_log "Attr: gen_ai.response.model"          "gen_ai.response.model"   "$LOGS_FILE"
    check_log "Attr: gen_ai.response.finish_reasons" "gen_ai.response.finish_reasons" "$LOGS_FILE"
    warn_log  "Attr: gen_ai.response.id"             "gen_ai.response.id"      "$LOGS_FILE"
    check_log "Attr: base14.gen_ai.cost_usd"         "base14.gen_ai.cost_usd"  "$LOGS_FILE"

    # ── Pipeline Stage Spans ──
    echo "  $(dim "--- Pipeline Stage Spans ---")"
    check_log "Stage span: retrieve"                 "pipeline_stage retrieve" "$LOGS_FILE"
    check_log "Stage span: analyze"                  "pipeline_stage analyze"  "$LOGS_FILE"
    check_log "Stage span: generate"                 "pipeline_stage generate" "$LOGS_FILE"
    check_log "Stage span: format"                   "pipeline_stage format"   "$LOGS_FILE"
    check_log "Attr: base14.pipeline.stage = retrieve" "Str(retrieve)"        "$LOGS_FILE"
    check_log "Attr: base14.pipeline.stage = analyze"  "Str(analyze)"         "$LOGS_FILE"
    check_log "Attr: base14.pipeline.stage = generate" "Str(generate)"        "$LOGS_FILE"
    check_log "Attr: base14.pipeline.stage = format"   "Str(format)"          "$LOGS_FILE"
    check_log "Root span: pipeline report"           "pipeline report"        "$LOGS_FILE"

    # ── HTTP Spans ──
    echo "  $(dim "--- HTTP Spans ---")"
    check_log "Span: POST /api/reports"              "POST /api/reports"       "$LOGS_FILE"
    check_log "Span: GET /api/indicators"            "GET /api/indicators"     "$LOGS_FILE"
    check_log "Span kind: Server on HTTP spans"      "Kind *: Server"          "$LOGS_FILE"
    check_log "Attr: http.response.status_code"      "http.response.status_code" "$LOGS_FILE"

    # ── Error Telemetry ──
    echo "  $(dim "--- Error Telemetry ---")"
    check_log "HTTP 400 in traces"                    "400"                     "$LOGS_FILE"
    check_log "HTTP 404 in traces"                    "404"                     "$LOGS_FILE"
    check_log "Attr: error.type (on LLM error spans)" "error.type"             "$LOGS_FILE"
    check_log "Event: exception on failed spans"      "exception.type"         "$LOGS_FILE"
    warn_log  "Event: provider_fallback"              "provider_fallback"      "$LOGS_FILE"

    # ── GenAI Metrics (6 required) ──
    echo "  $(dim "--- GenAI Metrics ---")"
    check_log "Metric: gen_ai.client.token.usage"        "gen_ai.client.token.usage"        "$LOGS_FILE"
    check_log "Metric: gen_ai.client.operation.duration"  "gen_ai.client.operation.duration" "$LOGS_FILE"
    check_log "Metric: base14.gen_ai.cost"               "base14.gen_ai.cost"               "$LOGS_FILE"
    check_log "Metric: base14.gen_ai.retry.count"        "base14.gen_ai.retry.count"        "$LOGS_FILE"
    warn_log  "Metric: base14.gen_ai.fallback.count"     "base14.gen_ai.fallback.count"     "$LOGS_FILE"
    check_log "Metric: base14.gen_ai.error.count"        "base14.gen_ai.error.count"        "$LOGS_FILE"
    echo "  $(dim "(fallback.count only emits when a fallback provider is configured and triggered)")"

    # ── Domain Metrics ──
    echo "  $(dim "--- Domain Metrics ---")"
    check_log "Metric: base14.report.generation.duration" "base14.report.generation.duration" "$LOGS_FILE"
    check_log "Metric: base14.report.data_points"          "base14.report.data_points"         "$LOGS_FILE"
    check_log "Metric: base14.report.sections"             "base14.report.sections"            "$LOGS_FILE"

    # ── HTTP Metrics ──
    echo "  $(dim "--- HTTP Metrics ---")"
    check_log "Metric: base14.http.requests.total"       "base14.http.requests.total"       "$LOGS_FILE"
    check_log "Metric: base14.http.request.duration"     "base14.http.request.duration"     "$LOGS_FILE"

    # ── Resource Attributes ──
    echo "  $(dim "--- Resource Attributes ---")"
    check_log "Resource: service.name"               "service.name"            "$LOGS_FILE"
    check_log "Resource: deployment.environment.name"     "deployment.environment.name"  "$LOGS_FILE"

    [ "$OWN_LOG" = "1" ] && rm -f "$LOGS_FILE"
  fi
fi

# ── 4. Scout Dashboard Checklist ──────────────────────────────
echo ""
echo "$(cyan "=== 4. Scout Dashboard Checklist ===")"
echo "$(dim "    Open Base14 Scout and verify these manually:")"
echo ""
echo "  $(cyan "Trace Explorer:")"
echo "    [ ] Root HTTP span (POST /api/reports) parents the full pipeline"
echo "    [ ] Pipeline traces show nested spans: retrieve -> analyze -> generate -> format"
echo "    [ ] Each chat span has base14.report.stage attribute (analyze / generate)"
echo "    [ ] Database spans (db.reports.insert, db.reports.list) nested correctly"
echo "    [ ] chat spans are Client kind and HTTP spans are Server kind"
echo "    [ ] gen_ai.usage.input_tokens, output_tokens and base14.gen_ai.cost_usd on each chat span"
echo "    [ ] 400 and 404 responses leave their HTTP span with error status"
echo ""
echo "  $(cyan "HTTP Dashboard:")"
echo "    [ ] base14.http.request.duration shows p50/p99 latency"
echo "    [ ] Request breakdown by method + route"
echo "    [ ] Response status code distribution"
echo ""
echo "  $(cyan "Cost & Token Dashboard:")"
echo "    [ ] Total Cost is non-zero for priced models and 0 for local Ollama models"
echo "    [ ] Token Usage shows input vs output breakdown by model"
echo "    [ ] Cost broken down by base14.report.stage (analyze / generate)"
echo "    [ ] base14.gen_ai.retry.count, fallback.count and error.count visible on the error path"
echo ""
echo "  $(cyan "Report Pipeline Dashboard:")"
echo "    [ ] base14.report.generation.duration visible"
echo "    [ ] base14.report.data_points visible"
echo "    [ ] base14.report.sections visible"
echo "    [ ] Pipeline stage durations visible"
echo ""

# ── Summary ───────────────────────────────────────────────────
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
