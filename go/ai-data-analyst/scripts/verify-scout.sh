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
echo "$(cyan "  AI Data Analyst")"
echo "$(cyan "=============================================")"

# Prerequisites
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

# Generate telemetry
if [ "${SKIP_REQUESTS:-}" != "1" ]; then
  echo ""
  echo "$(cyan "=== 2. Running Data Analyst Pipeline ===")"
  echo ""

  SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
  QUESTIONS_FILE="${SCRIPT_DIR}/../data/sample-questions.txt"

  if [ -f "$QUESTIONS_FILE" ]; then
    count=0
    while IFS= read -r question && [ $count -lt 3 ]; do
      [ -z "$question" ] && continue
      echo "  $(dim "Asking: ${question}")"
      curl -s -o /dev/null -X POST "${BASE_URL}/api/ask" \
        -H "Content-Type: application/json" \
        -d "{\"question\":\"${question}\"}" || true
      count=$((count + 1))
    done < "$QUESTIONS_FILE"
    echo "  $(green "sent") ${count} questions"
  else
    echo "  $(dim "Asking sample questions...")"
    curl -s -o /dev/null -X POST "${BASE_URL}/api/ask" \
      -H "Content-Type: application/json" \
      -d '{"question":"Top 5 countries by GDP growth in 2023"}' || true
    curl -s -o /dev/null -X POST "${BASE_URL}/api/ask" \
      -H "Content-Type: application/json" \
      -d '{"question":"Compare life expectancy between Japan and Nigeria"}' || true
    echo "  $(green "sent") 2 questions"
  fi

  # Hit GET endpoints for HTTP span coverage
  echo "  $(dim "Hitting GET endpoints...")"
  curl -s -o /dev/null "${BASE_URL}/api/schema" || true
  curl -s -o /dev/null "${BASE_URL}/api/indicators" || true
  curl -s -o /dev/null "${BASE_URL}/api/history" || true
  echo "  $(green "sent") 3 GET requests"

  # Trigger error cases
  echo "  $(dim "Triggering error spans...")"
  curl -s -o /dev/null -X POST "${BASE_URL}/api/ask" \
    -H "Content-Type: application/json" \
    -d '{"question":""}' || true
  echo "  $(green "sent") empty question (400)"

  echo ""
  echo "  $(dim "Waiting 30s for batch export to collector...")"
  sleep 30
fi

# Verify collector logs
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
    # HTTP Spans
    echo "  $(dim "--- HTTP Spans ---")"
    check_log "Span: POST /api/ask"                 "POST /api/ask"           "$LOGS_FILE"
    check_log "Span: GET /api/schema"               "GET /api/schema"         "$LOGS_FILE"
    check_log "Span: GET /api/indicators"           "GET /api/indicators"     "$LOGS_FILE"
    warn_log  "Attr: http.request.method"           "http.request.method"     "$LOGS_FILE"
    warn_log  "Attr: http.response.status_code"     "http.response.status_code" "$LOGS_FILE"
    warn_log  "Attr: url.scheme"                    "url.scheme"              "$LOGS_FILE"

    # HTTP Metrics
    echo "  $(dim "--- HTTP Metrics ---")"
    warn_log  "Metric: http.server.request.duration"    "http.server.request.duration"    "$LOGS_FILE"
    warn_log  "Metric: http.server.request.body.size"   "http.server.request.body.size"   "$LOGS_FILE"
    warn_log  "Metric: http.server.response.body.size"  "http.server.response.body.size"  "$LOGS_FILE"

    # Database Spans
    echo "  $(dim "--- Database Spans ---")"
    check_log "Span: data_analyst SELECT"           "data_analyst SELECT"     "$LOGS_FILE"
    check_log "Span: data_analyst SET"              "data_analyst SET"        "$LOGS_FILE"
    check_log "Span: data_analyst INSERT"           "data_analyst INSERT"     "$LOGS_FILE"
    warn_log  "Span: pool.acquire"                  "pool.acquire"            "$LOGS_FILE"
    warn_log  "Attr: db.system (postgresql)"        "db.system"               "$LOGS_FILE"
    warn_log  "Attr: db.name"                       "db.name"                 "$LOGS_FILE"

    # GenAI Spans
    echo "  $(dim "--- GenAI Spans ---")"
    check_log "Span: gen_ai.chat (semconv name)"    "gen_ai.chat"             "$LOGS_FILE"

    # Required GenAI Span Attributes
    echo "  $(dim "--- Required GenAI Span Attributes ---")"
    warn_log  "Attr: gen_ai.operation.name"         "gen_ai.operation.name"   "$LOGS_FILE"
    warn_log  "Attr: gen_ai.provider.name"          "gen_ai.provider.name"    "$LOGS_FILE"
    warn_log  "Attr: gen_ai.request.model"          "gen_ai.request.model"    "$LOGS_FILE"

    # Recommended GenAI Span Attributes
    echo "  $(dim "--- Recommended GenAI Span Attributes ---")"
    warn_log  "Attr: server.address"                "server.address"          "$LOGS_FILE"
    warn_log  "Attr: server.port"                   "server.port"             "$LOGS_FILE"
    warn_log  "Attr: gen_ai.request.temperature"    "gen_ai.request.temperature" "$LOGS_FILE"
    warn_log  "Attr: gen_ai.request.max_tokens"     "gen_ai.request.max_tokens"  "$LOGS_FILE"
    warn_log  "Attr: gen_ai.response.model"         "gen_ai.response.model"   "$LOGS_FILE"
    warn_log  "Attr: gen_ai.usage.input_tokens"     "gen_ai.usage.input_tokens"  "$LOGS_FILE"
    warn_log  "Attr: gen_ai.usage.output_tokens"    "gen_ai.usage.output_tokens" "$LOGS_FILE"
    warn_log  "Attr: gen_ai.usage.cost_usd"         "gen_ai.usage.cost_usd"   "$LOGS_FILE"

    # Pipeline stage spans
    echo "  $(dim "--- Pipeline Stage Spans ---")"
    warn_log  "Stage span: generate"                "Str(generate)"           "$LOGS_FILE"
    warn_log  "Stage span: explain"                 "Str(explain)"            "$LOGS_FILE"
    warn_log  "Stage span: parse"                   "Str(parse)"              "$LOGS_FILE"
    warn_log  "Stage span: validate"                "Str(validate)"           "$LOGS_FILE"
    warn_log  "Stage span: execute"                 "Str(execute)"            "$LOGS_FILE"

    # Span Events
    echo "  $(dim "--- Span Events ---")"
    warn_log  "Event: gen_ai.user.message"          "gen_ai.user.message"     "$LOGS_FILE"
    warn_log  "Event: gen_ai.assistant.message"     "gen_ai.assistant.message" "$LOGS_FILE"

    # Error telemetry
    echo "  $(dim "--- Error Telemetry ---")"
    warn_log  "Attr: error.type (on error spans)"   "error.type"              "$LOGS_FILE"

    # Metrics
    echo "  $(dim "--- Metrics ---")"
    warn_log  "Metric: gen_ai.client.token.usage"        "gen_ai.client.token.usage"        "$LOGS_FILE"
    warn_log  "Metric: gen_ai.client.operation.duration" "gen_ai.client.operation.duration"  "$LOGS_FILE"
    warn_log  "Metric: gen_ai.client.cost"               "gen_ai.client.cost"               "$LOGS_FILE"
    warn_log  "Metric: gen_ai.client.retry.count"        "gen_ai.client.retry.count"        "$LOGS_FILE"
    warn_log  "Metric: gen_ai.client.fallback.count"     "gen_ai.client.fallback.count"     "$LOGS_FILE"
    warn_log  "Metric: gen_ai.client.error.count"        "gen_ai.client.error.count"        "$LOGS_FILE"

    # Domain Metrics
    echo "  $(dim "--- Domain Metrics ---")"
    warn_log  "Metric: nlsql.question.duration"         "nlsql.question.duration"         "$LOGS_FILE"
    warn_log  "Metric: nlsql.sql.valid"                 "nlsql.sql.valid"                 "$LOGS_FILE"
    warn_log  "Metric: nlsql.query.rows"                "nlsql.query.rows"                "$LOGS_FILE"
    warn_log  "Metric: nlsql.query.execution_time"      "nlsql.query.execution_time"      "$LOGS_FILE"
    warn_log  "Metric: nlsql.confidence"                "nlsql.confidence"                "$LOGS_FILE"

    # Resource Attributes
    echo "  $(dim "--- Resource Attributes ---")"
    warn_log  "Resource: service.name"              "service.name"            "$LOGS_FILE"
    warn_log  "Resource: deployment.environment"    "deployment.environment"  "$LOGS_FILE"

    rm -f "$LOGS_FILE"
  fi
fi

# Dashboard checklist
echo ""
echo "$(cyan "=== 4. Scout Dashboard Checklist ===")"
echo "$(dim "    Open Base14 Scout and verify these manually:")"
echo ""
echo "  $(cyan "Trace Explorer:")"
echo "    [ ] Root HTTP span (POST /api/ask) parents the full pipeline"
echo "    [ ] Pipeline traces show nested spans: parse → generate → validate → execute → explain"
echo "    [ ] Each gen_ai.chat span has nlsql.stage attribute (generate / explain)"
echo "    [ ] Database spans (data_analyst SELECT/SET/INSERT) nested under execute stage"
echo "    [ ] generate spans use capable model (gpt-4.1 or configured)"
echo "    [ ] explain spans use fast model (gpt-4.1-mini or configured)"
echo "    [ ] gen_ai.user.message / gen_ai.assistant.message events on chat spans"
echo "    [ ] gen_ai.usage.input_tokens, output_tokens, cost_usd on each span"
echo ""
echo "  $(cyan "HTTP Dashboard:")"
echo "    [ ] http.server.request.duration shows p50/p99 latency"
echo "    [ ] Request breakdown by method + route (POST /api/ask, GET /api/schema, etc.)"
echo "    [ ] Response status code distribution"
echo ""
echo "  $(cyan "Database Dashboard:")"
echo "    [ ] SQL operation breakdown (SELECT, SET, INSERT)"
echo "    [ ] Query execution time visible"
echo "    [ ] pool.acquire spans show connection pool behavior"
echo ""
echo "  $(cyan "Cost & Token Dashboard:")"
echo "    [ ] Total Cost shows non-zero value"
echo "    [ ] Token Usage shows input vs output breakdown by model"
echo "    [ ] Cost broken down by nlsql.stage (generate / explain)"
echo ""
echo "  $(cyan "Query Health Dashboard:")"
echo "    [ ] nlsql.confidence visible"
echo "    [ ] nlsql.query.rows visible"
echo "    [ ] nlsql.query.execution_time visible"
echo "    [ ] Pipeline stage durations visible"
echo ""

# Summary
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
