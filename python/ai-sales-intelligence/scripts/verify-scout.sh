#!/usr/bin/env bash
set -euo pipefail 2>/dev/null || set -eu

# ---------------------------------------------------------------------------
# verify-scout.sh - End-to-end telemetry verification
#
# Runs the full sales intelligence pipeline (campaign → import → run),
# then inspects OTel Collector debug logs to verify GenAI semconv spans,
# attributes, metrics, and events arrived correctly.
#
# Prerequisites:
#   docker compose up -d
#   (wait for app + collector to be healthy)
#
# Usage:
#   ./scripts/verify-scout.sh              # full verification
#   SKIP_REQUESTS=1 ./scripts/verify-scout.sh  # only check logs (re-run)
#   COLLECTOR_LOG=/tmp/collector.log ./scripts/verify-scout.sh  # check a saved log
# ---------------------------------------------------------------------------

BASE_URL="${API_URL:-http://localhost:8000}"
COLLECTOR_HEALTH="${COLLECTOR_HEALTH_URL:-http://localhost:13133}"
COMPOSE_PROJECT="ai-sales-intelligence"
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

echo ""
echo "$(cyan "=============================================")"
echo "$(cyan "  Telemetry Verification - Base14 Scout")"
echo "$(cyan "  AI Sales Intelligence")"
echo "$(cyan "=============================================")"

# ---------------------------------------------------------------------------
# 1. Prerequisites
# ---------------------------------------------------------------------------
echo ""
echo "$(cyan "=== 1. Prerequisites ===")"
echo ""

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
    SKIP_LOG_CHECK=1
  else
    SKIP_LOG_CHECK=0
  fi
fi

# ---------------------------------------------------------------------------
# 2. Run the pipeline (telemetry-generating requests)
# ---------------------------------------------------------------------------
if [ "${SKIP_REQUESTS:-}" != "1" ] && [ -z "${COLLECTOR_LOG:-}" ]; then
  echo ""
  echo "$(cyan "=== 2. Running Sales Intelligence Pipeline ===")"
  echo ""

  SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
  DATA_DIR="$(cd "${SCRIPT_DIR}/../data" && pwd)"

  # Create campaign
  echo "  $(dim "Creating campaign...")"
  CAMPAIGN=$(curl -s -X POST "${BASE_URL}/campaigns" \
    -H "Content-Type: application/json" \
    -d '{
      "name": "Telemetry Verify Campaign",
      "target_keywords": ["SaaS", "AI", "Cloud"],
      "target_titles": ["CTO", "VP Engineering", "Head of Platform"]
    }')
  CAMPAIGN_ID=$(echo "$CAMPAIGN" | python3 -c "import sys,json; print(json.load(sys.stdin)['id'])" 2>/dev/null || echo "")
  if [ -z "$CAMPAIGN_ID" ]; then
    echo "  $(red "FAIL: Could not create campaign. Response: $CAMPAIGN")"
    exit 1
  fi
  echo "  $(green "created") campaign id=${CAMPAIGN_ID}"

  # Import connections
  echo "  $(dim "Importing connections from sample CSV...")"
  IMPORT_RESULT=$(curl -s -X POST "${BASE_URL}/campaigns/${CAMPAIGN_ID}/connections/import" \
    -F "file=@${DATA_DIR}/sample-connections-verify-scout.csv")
  IMPORTED=$(echo "$IMPORT_RESULT" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('imported', '?'))" 2>/dev/null || echo "?")
  SKIPPED=$(echo "$IMPORT_RESULT" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('skipped', 0))" 2>/dev/null || echo "0")
  echo "  $(green "imported") ${IMPORTED} connections (${SKIPPED} duplicates skipped)"

  # Run pipeline - triggers enrich → score → draft → evaluate agents
  echo "  $(dim "Running pipeline (LLM calls for all agents)...")"
  echo "  $(dim "  enrich + draft → capable model")"
  echo "  $(dim "  score + evaluate → fast model")"
  PIPELINE_RESULT=$(curl -s -X POST "${BASE_URL}/campaigns/${CAMPAIGN_ID}/run" \
    -H "Content-Type: application/json" \
    -d '{"score_threshold": 50, "quality_threshold": 60}')

  # --- Pipeline Summary ---
  echo ""
  echo "  $(cyan "--- Pipeline Results ---")"
  FOUND=$(echo "$PIPELINE_RESULT" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('prospects_found', '?'))" 2>/dev/null || echo "?")
  SCORED=$(echo "$PIPELINE_RESULT" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('prospects_scored', '?'))" 2>/dev/null || echo "?")
  DRAFTED=$(echo "$PIPELINE_RESULT" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('drafts_generated', '?'))" 2>/dev/null || echo "?")
  PASSED=$(echo "$PIPELINE_RESULT" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('drafts_passed', '?'))" 2>/dev/null || echo "?")
  ERRORS=$(echo "$PIPELINE_RESULT" | python3 -c "import sys,json; d=json.load(sys.stdin); errs=d.get('errors',[]); print(len(errs))" 2>/dev/null || echo "?")

  echo "  research   → prospects found:   ${FOUND}"
  echo "  score      → passed threshold:  ${SCORED} (score_threshold=50)"
  echo "  draft      → emails generated:  ${DRAFTED}"
  echo "  evaluate   → quality passed:    ${PASSED} (quality_threshold=60)"
  if [ "$ERRORS" != "0" ] && [ "$ERRORS" != "?" ]; then
    echo "  $(yellow "errors") → ${ERRORS} error(s) during pipeline"
    echo "$PIPELINE_RESULT" | python3 -c "
import sys, json
d = json.load(sys.stdin)
for e in d.get('errors', []):
    print(f'    ⚠ {e}')
" 2>/dev/null || true
  fi

  # --- Step skip reasons ---
  if [ "$FOUND" = "0" ]; then
    echo "  $(yellow "NOTE") research found 0 prospects - all downstream steps skipped"
  elif [ "$SCORED" = "0" ]; then
    echo "  $(yellow "NOTE") no prospects passed score threshold - draft + evaluate skipped"
  elif [ "$DRAFTED" = "0" ]; then
    echo "  $(yellow "NOTE") no drafts generated - evaluate skipped"
  elif [ "$PASSED" = "0" ] && [ "$DRAFTED" != "0" ]; then
    echo "  $(yellow "NOTE") all drafts failed quality threshold"
  fi

  # --- Per-Prospect Outcomes ---
  echo ""
  echo "  $(cyan "--- Prospect Outcomes ---")"
  PROSPECTS=$(curl -s "${BASE_URL}/campaigns/${CAMPAIGN_ID}/prospects")
  echo "$PROSPECTS" | python3 "${SCRIPT_DIR}/print-prospects.py" 2>/dev/null || echo "  $(dim "Could not parse prospect data")"
  echo ""

  # Error case: non-existent campaign → 404
  echo "  $(dim "Triggering 404 error span...")"
  curl -s -o /dev/null "${BASE_URL}/campaigns/00000000-0000-0000-0000-000000000000" || true
  echo "  $(green "sent") GET /campaigns/nonexistent (404)"

  # Error case: invalid payload → 422
  echo "  $(dim "Triggering 422 validation error span...")"
  curl -s -o /dev/null -X POST "${BASE_URL}/campaigns" \
    -H "Content-Type: application/json" \
    -d '{"target_keywords": "not-a-list"}' || true
  echo "  $(green "sent") POST /campaigns (invalid - 422)"

  echo ""
  echo "  $(dim "Waiting 60s for pipeline LLM calls and batch export to collector...")"
  sleep 60
fi

# ---------------------------------------------------------------------------
# 3. Verify Collector debug logs
# ---------------------------------------------------------------------------
if [ "${SKIP_LOG_CHECK:-0}" = "0" ]; then
  echo ""
  echo "$(cyan "=== 3. Collector Debug Log Verification ===")"
  echo "$(dim "    Checking last 15 minutes of collector logs for expected telemetry")"
  echo ""

  LOGS_FILE="${COLLECTOR_LOG:-}"
  CLEANUP_LOGS=0
  if [ -z "$LOGS_FILE" ]; then
    LOGS_FILE=$(mktemp /tmp/otel-logs-XXXXXX.txt)
    CLEANUP_LOGS=1
    docker compose logs otel-collector --since=15m --no-log-prefix >"$LOGS_FILE" 2>/dev/null || true
  fi

  if [ ! -s "$LOGS_FILE" ]; then
    echo "  $(yellow "WARN: Could not read collector logs. Are you in the project directory?")"
    echo "  $(dim  "       Try: cd $(pwd) && docker compose logs otel-collector --since=15m")"
    [ "$CLEANUP_LOGS" = "1" ] && rm -f "$LOGS_FILE"
  else

    # --- Trace Spans ---
    echo "  $(dim "--- Trace Spans ---")"
    check_log "Span: chat {model}"                  "Name *: chat "           "$LOGS_FILE"
    check_log "Span kind: Client on chat spans"     "Kind *: Client"          "$LOGS_FILE"
    warn_log  "Span: retrieval prospects_fts"       "Name *: retrieval prospects_fts" "$LOGS_FILE"

    # --- Required GenAI Span Attributes ---
    echo "  $(dim "--- Required GenAI Span Attributes ---")"
    warn_log  "Attr: gen_ai.operation.name"         "gen_ai.operation.name"   "$LOGS_FILE"
    warn_log  "Attr: gen_ai.provider.name"          "gen_ai.provider.name"    "$LOGS_FILE"
    warn_log  "Attr: gen_ai.request.model"          "gen_ai.request.model"    "$LOGS_FILE"
    warn_log  "Attr: gen_ai.data_source.id"         "gen_ai.data_source.id"   "$LOGS_FILE"

    # --- Recommended GenAI Span Attributes ---
    echo "  $(dim "--- Recommended GenAI Span Attributes ---")"
    warn_log  "Attr: server.address"                "server.address"          "$LOGS_FILE"
    warn_log  "Attr: server.port"                   "server.port"             "$LOGS_FILE"
    warn_log  "Attr: gen_ai.request.temperature"    "gen_ai.request.temperature" "$LOGS_FILE"
    warn_log  "Attr: gen_ai.request.max_tokens"     "gen_ai.request.max_tokens"  "$LOGS_FILE"
    warn_log  "Attr: gen_ai.response.model"         "gen_ai.response.model"   "$LOGS_FILE"
    warn_log  "Attr: gen_ai.usage.input_tokens"     "gen_ai.usage.input_tokens"  "$LOGS_FILE"
    warn_log  "Attr: gen_ai.usage.output_tokens"    "gen_ai.usage.output_tokens" "$LOGS_FILE"
    warn_log  "Attr: base14.gen_ai.cost_usd"        "base14.gen_ai.cost_usd"  "$LOGS_FILE"

    # --- Business Context Attributes ---
    echo "  $(dim "--- Business Context Attributes ---")"
    warn_log  "Attr: gen_ai.agent.name"             "gen_ai.agent.name"       "$LOGS_FILE"
    warn_log  "Attr: base14.campaign_id"            "base14.campaign_id"      "$LOGS_FILE"

    # --- Per-Agent Span Verification ---
    echo "  $(dim "--- Per-Agent Spans ---")"
    warn_log  "Agent span: enrich"                  "Str(enrich)"             "$LOGS_FILE"
    warn_log  "Agent span: score"                   "Str(score)"              "$LOGS_FILE"
    warn_log  "Agent span: draft"                   "Str(draft)"              "$LOGS_FILE"
    warn_log  "Agent span: evaluate"                "Str(evaluate)"           "$LOGS_FILE"

    # --- Span Events ---
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

    # --- Error Telemetry ---
    echo "  $(dim "--- Error Telemetry ---")"
    warn_log  "Attr: error.type (on error spans)"   "error.type"              "$LOGS_FILE"

    # --- PII Scrubbing (emails from sample CSV must NOT appear) ---
    echo "  $(dim "--- PII Scrubbing (should be absent) ---")"
    PII_CLEAN=1
    for email in "alex.chen@techwave.io" "sarah.kumar@cloudnative.dev" "marcus@dataforge.ai" "emily.r@scalepeak.com"; do
      if grep -q "$email" "$LOGS_FILE" 2>/dev/null; then
        echo "  $(red "FAIL") PII leak: ${email} found in collector logs"
        FAIL=$((FAIL + 1))
        PII_CLEAN=0
      fi
    done
    if [ "$PII_CLEAN" = "1" ]; then
      echo "  $(green "PASS") No PII leak: prospect emails absent from collector logs"
      PASS=$((PASS + 1))
    fi

    # --- Metrics ---
    echo "  $(dim "--- Metrics ---")"
    warn_log  "Metric: gen_ai.client.token.usage"        "gen_ai.client.token.usage"        "$LOGS_FILE"
    warn_log  "Metric: gen_ai.client.operation.duration" "gen_ai.client.operation.duration"  "$LOGS_FILE"
    warn_log  "Metric: base14.gen_ai.cost"               "Name: base14.gen_ai.cost"         "$LOGS_FILE"
    warn_log  "Metric: base14.gen_ai.retry.count"        "base14.gen_ai.retry.count"        "$LOGS_FILE"
    warn_log  "Metric: base14.gen_ai.fallback.count"     "base14.gen_ai.fallback.count"     "$LOGS_FILE"
    warn_log  "Metric: base14.gen_ai.error.count"        "base14.gen_ai.error.count"        "$LOGS_FILE"
    warn_log  "Metric: base14.gen_ai.evaluation.score"   "base14.gen_ai.evaluation.score"   "$LOGS_FILE"
    warn_log  "Metric: http.server.request.duration"     "http.server.request.duration"     "$LOGS_FILE"

    # --- Resource Attributes ---
    echo "  $(dim "--- Resource Attributes ---")"
    warn_log  "Resource: service.name"              "service.name"            "$LOGS_FILE"
    warn_log  "Resource: deployment.environment"    "deployment.environment"  "$LOGS_FILE"
    [ "$CLEANUP_LOGS" = "1" ] && rm -f "$LOGS_FILE"
  fi
fi

# ---------------------------------------------------------------------------
# 4. Scout Dashboard Checklist
# ---------------------------------------------------------------------------
echo ""
echo "$(cyan "=== 4. Scout Dashboard Checklist ===")"
echo "$(dim "    Open Base14 Scout and verify these manually:")"
echo ""
echo "  $(cyan "Trace Explorer:")"
echo "    [ ] Pipeline traces show nested spans per agent: research → enrich → score → draft → evaluate"
echo "    [ ] Each chat span has gen_ai.agent.name attribute (enrich / score / draft / evaluate)"
echo "    [ ] enrich + draft spans use the capable model (LLM_MODEL_CAPABLE)"
echo "    [ ] score + evaluate spans use the fast model (LLM_MODEL_FAST)"
echo "    [ ] base14.campaign_id attribute present on all agent spans"
echo "    [ ] retrieval prospects_fts span wraps the Postgres FTS query"
echo "    [ ] gen_ai.usage.input_tokens, output_tokens and base14.gen_ai.cost_usd on each chat span"
echo "    [ ] 404 and 422 traces have error status on the HTTP span"
echo ""
echo "  $(cyan "Cost & Token Dashboard:")"
echo "    [ ] Total Cost is non-zero for priced models and 0 for local Ollama models"
echo "    [ ] Token Usage shows input vs output breakdown by model"
echo "    [ ] Cost broken down by gen_ai.agent.name"
echo "    [ ] Cost broken down by base14.campaign_id"
echo ""
echo "  $(cyan "Error & Retry Dashboard:")"
echo "    [ ] base14.gen_ai.retry.count visible (may be zero if no transient errors)"
echo "    [ ] base14.gen_ai.fallback.count visible (may be zero if the primary provider is healthy)"
echo "    [ ] base14.gen_ai.error.count visible on error conditions"
echo ""
echo "  $(cyan "Logs:")"
echo "    [ ] Log records include trace_id and span_id correlation"
echo "    [ ] LLM response length logged for each agent call"
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
