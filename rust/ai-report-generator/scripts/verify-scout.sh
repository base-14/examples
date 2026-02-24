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
    echo "  $(red "FAIL") ${label} — pattern not found: ${pattern}"
    FAIL=$((FAIL + 1))
  fi
}

warn_log() {
  local label="$1" pattern="$2" file="$3"
  if grep -q "$pattern" "$file" 2>/dev/null; then
    echo "  $(green "PASS") ${label}"
    PASS=$((PASS + 1))
  else
    echo "  $(yellow "WARN") ${label} — pattern not found: ${pattern}"
    WARN=$((WARN + 1))
  fi
}

echo ""
echo "$(cyan "=============================================")"
echo "$(cyan "  Telemetry Verification — Base14 Scout")"
echo "$(cyan "  AI Report Generator")"
echo "$(cyan "=============================================")"

# ── 1. Prerequisites ──────────────────────────────────────────
echo ""
echo "$(cyan "=== 1. Prerequisites ===")"
echo ""

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
  echo "  $(yellow "WARN: Collector not reachable — telemetry log verification will be skipped")"
  SKIP_LOG_CHECK=1
else
  SKIP_LOG_CHECK=0
fi

# ── 2. Generate Traffic ───────────────────────────────────────
if [ "${SKIP_REQUESTS:-}" != "1" ]; then
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
    echo "  $(green "sent") POST /api/test/llm-error — error path exercised"
  else
    echo "  $(yellow "warn") POST /api/test/llm-error — unexpected response: ${LLM_ERR}"
  fi

  echo ""
  echo "  $(dim "Waiting 15s for batch export to collector...")"
  sleep 15
fi

# ── 3. Collector Debug Log Verification ───────────────────────
if [ "${SKIP_LOG_CHECK:-0}" = "0" ]; then
  echo ""
  echo "$(cyan "=== 3. Collector Debug Log Verification ===")"
  echo "$(dim "    Checking last 15 minutes of collector logs")"
  echo ""

  LOGS_FILE=$(mktemp /tmp/otel-logs-XXXXXX.txt)
  docker compose logs otel-collector --since=15m --no-log-prefix >"$LOGS_FILE" 2>/dev/null || true

  if [ ! -s "$LOGS_FILE" ]; then
    echo "  $(yellow "WARN: Could not read collector logs")"
    rm -f "$LOGS_FILE"
  else

    # ── GenAI Spans ──
    echo "  $(dim "--- GenAI Spans ---")"
    check_log "Span: gen_ai.chat (semconv name)"    "gen_ai.chat"             "$LOGS_FILE"
    check_log "Attr: gen_ai.operation.name"          "gen_ai.operation.name"   "$LOGS_FILE"
    check_log "Attr: gen_ai.provider.name"           "gen_ai.provider.name"    "$LOGS_FILE"
    check_log "Attr: gen_ai.request.model"           "gen_ai.request.model"    "$LOGS_FILE"
    check_log "Attr: gen_ai.usage.input_tokens"      "gen_ai.usage.input_tokens"  "$LOGS_FILE"
    check_log "Attr: gen_ai.usage.output_tokens"     "gen_ai.usage.output_tokens" "$LOGS_FILE"

    # ── GenAI Span Events ──
    echo "  $(dim "--- GenAI Span Events ---")"
    check_log "Event: gen_ai.user.message"           "gen_ai.user.message"     "$LOGS_FILE"
    check_log "Event: gen_ai.assistant.message"      "gen_ai.assistant.message" "$LOGS_FILE"

    # ── Recommended GenAI Span Attributes ──
    echo "  $(dim "--- Recommended GenAI Span Attributes ---")"
    check_log "Attr: server.address"                 "server.address"          "$LOGS_FILE"
    check_log "Attr: server.port"                    "server.port"             "$LOGS_FILE"
    check_log "Attr: gen_ai.request.temperature"     "gen_ai.request.temperature" "$LOGS_FILE"
    check_log "Attr: gen_ai.request.max_tokens"      "gen_ai.request.max_tokens"  "$LOGS_FILE"
    check_log "Attr: gen_ai.response.model"          "gen_ai.response.model"   "$LOGS_FILE"
    check_log "Attr: gen_ai.usage.cost_usd"          "gen_ai.usage.cost_usd"   "$LOGS_FILE"

    # ── Pipeline Stage Spans ──
    echo "  $(dim "--- Pipeline Stage Spans ---")"
    check_log "Stage span: retrieve"                 "pipeline_stage retrieve" "$LOGS_FILE"
    check_log "Stage span: analyze"                  "pipeline_stage analyze"  "$LOGS_FILE"
    check_log "Stage span: generate"                 "pipeline_stage generate" "$LOGS_FILE"
    check_log "Stage span: format"                   "pipeline_stage format"   "$LOGS_FILE"
    check_log "Attr: pipeline.stage = retrieve"      "Str(retrieve)"          "$LOGS_FILE"
    check_log "Attr: pipeline.stage = analyze"       "Str(analyze)"           "$LOGS_FILE"
    check_log "Attr: pipeline.stage = generate"      "Str(generate)"          "$LOGS_FILE"
    check_log "Attr: pipeline.stage = format"        "Str(format)"            "$LOGS_FILE"
    check_log "Root span: pipeline report"           "pipeline report"        "$LOGS_FILE"

    # ── HTTP Spans ──
    echo "  $(dim "--- HTTP Spans ---")"
    check_log "Span: POST /api/reports"              "POST /api/reports"       "$LOGS_FILE"
    check_log "Span: GET /api/indicators"            "GET /api/indicators"     "$LOGS_FILE"
    warn_log  "Attr: http.request.method"            "http.request.method"     "$LOGS_FILE"
    check_log "Attr: http.response.status_code"      "http.response.status_code" "$LOGS_FILE"

    # ── Error Telemetry ──
    echo "  $(dim "--- Error Telemetry ---")"
    check_log "HTTP 400 in traces"                    "400"                     "$LOGS_FILE"
    check_log "HTTP 404 in traces"                    "404"                     "$LOGS_FILE"
    check_log "Attr: error.type (on LLM error spans)" "error.type"             "$LOGS_FILE"

    # ── GenAI Metrics (6 required) ──
    echo "  $(dim "--- GenAI Metrics ---")"
    check_log "Metric: gen_ai.client.token.usage"        "gen_ai.client.token.usage"        "$LOGS_FILE"
    check_log "Metric: gen_ai.client.operation.duration"  "gen_ai.client.operation.duration" "$LOGS_FILE"
    check_log "Metric: gen_ai.client.cost"               "gen_ai.client.cost"               "$LOGS_FILE"
    check_log "Metric: gen_ai.client.retry.count"        "gen_ai.client.retry.count"        "$LOGS_FILE"
    warn_log  "Metric: gen_ai.client.fallback.count"     "gen_ai.client.fallback.count"     "$LOGS_FILE"
    check_log "Metric: gen_ai.client.error.count"        "gen_ai.client.error.count"        "$LOGS_FILE"
    echo "  $(dim "(fallback.count only emits when fallback provider is configured and triggered)")"

    # ── Domain Metrics ──
    echo "  $(dim "--- Domain Metrics ---")"
    check_log "Metric: report.generation.duration"       "report.generation.duration"       "$LOGS_FILE"
    check_log "Metric: report.data_points"               "report.data_points"               "$LOGS_FILE"
    check_log "Metric: report.sections"                  "report.sections"                  "$LOGS_FILE"

    # ── HTTP Metrics ──
    echo "  $(dim "--- HTTP Metrics ---")"
    check_log "Metric: http.requests.total"              "http.requests.total"              "$LOGS_FILE"
    check_log "Metric: http.request.duration"            "http.request.duration"            "$LOGS_FILE"

    # ── Resource Attributes ──
    echo "  $(dim "--- Resource Attributes ---")"
    check_log "Resource: service.name"               "service.name"            "$LOGS_FILE"
    check_log "Resource: deployment.environment"     "deployment.environment"  "$LOGS_FILE"

    rm -f "$LOGS_FILE"
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
echo "    [ ] Each gen_ai.chat span has report.stage attribute (analyze / generate)"
echo "    [ ] Database spans (db.reports.insert, db.reports.list) nested correctly"
echo "    [ ] gen_ai.user.message / gen_ai.assistant.message events on chat spans"
echo "    [ ] gen_ai.usage.input_tokens, output_tokens, cost_usd on each span"
echo ""
echo "  $(cyan "HTTP Dashboard:")"
echo "    [ ] http.request.duration shows p50/p99 latency"
echo "    [ ] Request breakdown by method + route"
echo "    [ ] Response status code distribution"
echo ""
echo "  $(cyan "Cost & Token Dashboard:")"
echo "    [ ] Total Cost shows non-zero value"
echo "    [ ] Token Usage shows input vs output breakdown by model"
echo "    [ ] Cost broken down by report.stage (analyze / generate)"
echo ""
echo "  $(cyan "Report Pipeline Dashboard:")"
echo "    [ ] report.generation.duration visible"
echo "    [ ] report.data_points visible"
echo "    [ ] report.sections visible"
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
