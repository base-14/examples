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
echo "$(cyan "  AI Customer Support")"
echo "$(cyan "=============================================")"

# Prerequisites
echo ""
echo "$(cyan "=== 1. Prerequisites ===")"
echo ""

if [ -n "${COLLECTOR_LOG:-}" ]; then
  echo "  $(dim "Reading the saved collector log ${COLLECTOR_LOG}, skipping the live checks")"
  SKIP_LOG_CHECK=0
  SKIP_REQUESTS=1
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

# Generate telemetry
if [ "${SKIP_REQUESTS:-}" != "1" ]; then
  echo ""
  echo "$(cyan "=== 2. Running Customer Support Pipeline ===")"
  echo ""

  echo "  $(dim "Sending test messages...")"
  curl -s -o /dev/null -X POST "${BASE_URL}/api/chat" \
    -H "Content-Type: application/json" \
    -d '{"message":"What is the status of order ORD-10001?"}' || true
  curl -s -o /dev/null -X POST "${BASE_URL}/api/chat" \
    -H "Content-Type: application/json" \
    -d '{"message":"I want to return my headphones"}' || true
  curl -s -o /dev/null -X POST "${BASE_URL}/api/chat" \
    -H "Content-Type: application/json" \
    -d '{"message":"What products do you have in the audio category?"}' || true
  echo "  $(green "sent") 3 chat messages"

  # Hit GET endpoints for HTTP span coverage
  echo "  $(dim "Hitting GET endpoints...")"
  curl -s -o /dev/null "${BASE_URL}/api/products" || true
  curl -s -o /dev/null "${BASE_URL}/api/conversations" || true
  echo "  $(green "sent") 2 GET requests"

  # Trigger error cases
  echo "  $(dim "Triggering error spans...")"
  curl -s -o /dev/null -X POST "${BASE_URL}/api/chat" \
    -H "Content-Type: application/json" \
    -d '{"message":""}' || true
  echo "  $(green "sent") empty message (400)"

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

  LOGS_FILE="${COLLECTOR_LOG:-}"
  CLEANUP_LOGS=0
  if [ -z "$LOGS_FILE" ]; then
    LOGS_FILE=$(mktemp /tmp/otel-logs-XXXXXX.txt)
    CLEANUP_LOGS=1
    docker compose logs otel-collector --since=15m --no-log-prefix >"$LOGS_FILE" 2>/dev/null || true
  fi

  if [ ! -s "$LOGS_FILE" ]; then
    echo "  $(yellow "WARN: Could not read collector logs")"
    if [ "$CLEANUP_LOGS" = "1" ]; then
      rm -f "$LOGS_FILE"
    fi
  else
    # HTTP Spans (auto-instrumented by Java Agent)
    echo "  $(dim "--- HTTP Spans ---")"
    check_log "Span: POST /api/chat"                "POST /api/chat"          "$LOGS_FILE"
    check_log "Span: GET /api/products"             "GET /api/products"       "$LOGS_FILE"
    warn_log  "Attr: http.request.method"           "http.request.method"     "$LOGS_FILE"
    warn_log  "Attr: http.response.status_code"     "http.response.status_code" "$LOGS_FILE"
    warn_log  "Attr: url.scheme"                    "url.scheme"              "$LOGS_FILE"

    # HTTP Metrics
    echo "  $(dim "--- HTTP Metrics ---")"
    warn_log  "Metric: http.server.request.duration"    "http.server.request.duration"    "$LOGS_FILE"

    # Database Spans (auto-instrumented by Java Agent)
    echo "  $(dim "--- Database Spans ---")"
    warn_log  "Span: SELECT support.*"               "SELECT support\."        "$LOGS_FILE"
    warn_log  "Span: INSERT support.*"               "INSERT support\."        "$LOGS_FILE"
    warn_log  "Span: UPDATE support.*"               "UPDATE support\."        "$LOGS_FILE"
    warn_log  "Attr: db.system"                     "db.system"               "$LOGS_FILE"

    # GenAI Spans (Spring AI observations, bridged to the Java agent)
    echo "  $(dim "--- GenAI Spans ---")"
    check_log "Span: chat {model}"                  "Name *: chat "           "$LOGS_FILE"
    check_log "Span kind: Client on chat spans"     "Kind *: Client"          "$LOGS_FILE"
    warn_log  "Span: embeddings {model}"            "Name *: embeddings "     "$LOGS_FILE"
    warn_log  "Span: execute_tool {tool_name}"      "Name *: execute_tool "   "$LOGS_FILE"
    warn_log  "Span: retrieval kb_articles"         "Name *: retrieval kb_articles" "$LOGS_FILE"

    # The deprecated chat span name and provider attribute must be gone.
    echo "  $(dim "--- Removed GenAI Names (should be absent) ---")"
    NAMES_CLEAN=1
    for removed in "Name *: gen_ai.chat" "gen_ai.system:" "Name *: rag_retrieval" "support.conversation_id"; do
      if grep -q "$removed" "$LOGS_FILE" 2>/dev/null; then
        echo "  $(red "FAIL") Removed name still emitted: ${removed}"
        FAIL=$((FAIL + 1))
        NAMES_CLEAN=0
      fi
    done
    if [ "$NAMES_CLEAN" = "1" ]; then
      echo "  $(green "PASS") The removed span and attribute names are absent"
      PASS=$((PASS + 1))
    fi

    # Required GenAI Span Attributes
    echo "  $(dim "--- Required GenAI Span Attributes ---")"
    warn_log  "Attr: gen_ai.operation.name"         "gen_ai.operation.name"   "$LOGS_FILE"
    warn_log  "Attr: gen_ai.provider.name"          "gen_ai.provider.name"    "$LOGS_FILE"
    warn_log  "Attr: gen_ai.request.model"          "gen_ai.request.model"    "$LOGS_FILE"
    warn_log  "Attr: gen_ai.tool.name"              "gen_ai.tool.name"        "$LOGS_FILE"
    warn_log  "Attr: gen_ai.data_source.id"         "gen_ai.data_source.id"   "$LOGS_FILE"

    # Recommended GenAI Span Attributes
    echo "  $(dim "--- Recommended GenAI Span Attributes ---")"
    warn_log  "Attr: server.address"                "server.address"          "$LOGS_FILE"
    warn_log  "Attr: server.port"                   "server.port"             "$LOGS_FILE"
    warn_log  "Attr: gen_ai.request.temperature"    "gen_ai.request.temperature" "$LOGS_FILE"
    warn_log  "Attr: gen_ai.request.max_tokens"     "gen_ai.request.max_tokens"  "$LOGS_FILE"
    warn_log  "Attr: gen_ai.response.model"         "gen_ai.response.model"   "$LOGS_FILE"
    warn_log  "Attr: gen_ai.response.finish_reasons" "gen_ai.response.finish_reasons" "$LOGS_FILE"
    warn_log  "Attr: gen_ai.usage.input_tokens"     "gen_ai.usage.input_tokens"  "$LOGS_FILE"
    warn_log  "Attr: gen_ai.usage.output_tokens"    "gen_ai.usage.output_tokens" "$LOGS_FILE"
    warn_log  "Attr: base14.gen_ai.cost_usd"        "base14.gen_ai.cost_usd"  "$LOGS_FILE"

    # Business Context Attributes
    echo "  $(dim "--- Business Context Attributes ---")"
    warn_log  "Attr: gen_ai.agent.name"             "gen_ai.agent.name"       "$LOGS_FILE"
    warn_log  "Attr: gen_ai.conversation.id"        "gen_ai.conversation.id"  "$LOGS_FILE"

    # Pipeline stage spans (manual)
    echo "  $(dim "--- Pipeline Stage Spans ---")"
    check_log "Span: support_conversation"          "support_conversation"    "$LOGS_FILE"
    warn_log  "Stage span: classify"                "Str(classify)"           "$LOGS_FILE"
    warn_log  "Stage span: generate"                "Str(generate)"           "$LOGS_FILE"
    warn_log  "Stage span: route"                   "Str(route)"              "$LOGS_FILE"

    # Span Events
    # The inference event only appears when content capture is switched on, so
    # its absence is expected here. The two removed message events must be gone.
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
    warn_log  "Event: gen_ai.evaluation.result"     "gen_ai.evaluation.result" "$LOGS_FILE"
    warn_log  "Event: provider_fallback"             "provider_fallback"       "$LOGS_FILE"
    warn_log  "Event: tool_execution_failed"         "tool_execution_failed"   "$LOGS_FILE"
    warn_log  "Event: rag_retrieval_degraded"        "rag_retrieval_degraded"  "$LOGS_FILE"
    if [ "${OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT:-false}" = "true" ]; then
      warn_log  "Event: gen_ai.client.inference.operation.details" \
                "gen_ai.client.inference.operation.details" "$LOGS_FILE"
    else
      echo "  $(dim "SKIP") Inference details event gated by OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT (default: false)"
    fi

    # Error telemetry
    echo "  $(dim "--- Error Telemetry ---")"
    warn_log  "Attr: error.type (on error spans)"   "error.type"              "$LOGS_FILE"

    # GenAI Metrics
    echo "  $(dim "--- GenAI Metrics ---")"
    warn_log  "Metric: gen_ai.client.token.usage"        "gen_ai.client.token.usage"        "$LOGS_FILE"
    warn_log  "Metric: gen_ai.client.operation.duration" "gen_ai.client.operation.duration" "$LOGS_FILE"
    warn_log  "Metric: base14.gen_ai.cost"               "Name *: base14.gen_ai.cost"       "$LOGS_FILE"
    warn_log  "Metric: base14.gen_ai.retry.count"        "base14.gen_ai.retry.count"        "$LOGS_FILE"
    warn_log  "Metric: base14.gen_ai.fallback.count"     "base14.gen_ai.fallback.count"     "$LOGS_FILE"
    warn_log  "Metric: base14.gen_ai.error.count"        "base14.gen_ai.error.count"        "$LOGS_FILE"

    # Domain Metrics
    echo "  $(dim "--- Domain Metrics ---")"
    warn_log  "Metric: base14.support.conversation.duration" "base14.support.conversation.duration" "$LOGS_FILE"
    warn_log  "Metric: base14.support.conversation.turns"    "base14.support.conversation.turns"    "$LOGS_FILE"
    warn_log  "Metric: base14.support.escalation.count"      "base14.support.escalation.count"      "$LOGS_FILE"
    warn_log  "Metric: base14.support.tool_calls"            "base14.support.tool_calls"            "$LOGS_FILE"
    warn_log  "Metric: base14.support.rag.similarity"        "base14.support.rag.similarity"        "$LOGS_FILE"

    # Resource Attributes
    echo "  $(dim "--- Resource Attributes ---")"
    warn_log  "Resource: service.name"              "service.name"            "$LOGS_FILE"

    if [ "$CLEANUP_LOGS" = "1" ]; then
      rm -f "$LOGS_FILE"
    fi
  fi
fi

# Dashboard checklist
echo ""
echo "$(cyan "=== 4. Scout Dashboard Checklist ===")"
echo "$(dim "    Open Base14 Scout and verify these manually:")"
echo ""
echo "  $(cyan "Trace Explorer:")"
echo "    [ ] Root HTTP span (POST /api/chat) parents the full pipeline"
echo "    [ ] Pipeline traces show nested spans: classify → retrieve → generate → route"
echo "    [ ] Exactly one chat span per LLM call, named chat {model}, kind Client"
echo "    [ ] Each chat span carries gen_ai.conversation.id and gen_ai.agent.name"
echo "    [ ] Database spans nested under tool/repository calls"
echo "    [ ] classify spans use the fast model, generate spans use the capable model"
echo "    [ ] gen_ai.usage.input_tokens, output_tokens and base14.gen_ai.cost_usd on each chat span"
echo "    [ ] retrieval kb_articles span shows app.retrieval.matches and app.retrieval.top_similarity"
echo "    [ ] execute_tool {tool_name} spans wrap each tool call"
echo "    [ ] escalation_check span carries a gen_ai.evaluation.result event"
echo ""
echo "  $(cyan "HTTP Dashboard:")"
echo "    [ ] http.server.request.duration shows p50/p99 latency"
echo "    [ ] Request breakdown by method + route (POST /api/chat, GET /api/products, etc.)"
echo "    [ ] Response status code distribution"
echo ""
echo "  $(cyan "Database Dashboard:")"
echo "    [ ] SQL operation breakdown (SELECT, INSERT, UPDATE)"
echo "    [ ] Connection pool behavior visible"
echo ""
echo "  $(cyan "Cost & Token Dashboard:")"
echo "    [ ] Total Cost is non-zero for priced models and 0 for local Ollama models"
echo "    [ ] Token Usage shows input vs output breakdown by model"
echo "    [ ] Cost broken down by gen_ai.request.model"
echo ""
echo "  $(cyan "Support-Specific Dashboard:")"
echo "    [ ] base14.support.conversation.turns visible"
echo "    [ ] base14.support.escalation.count visible"
echo "    [ ] base14.support.rag.similarity visible"
echo "    [ ] Intent distribution visible"
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
