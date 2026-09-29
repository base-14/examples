#!/usr/bin/env bash
# Runs the filing analyst scenarios against the running stack and checks each answer.
# Writes question IDs and results to .harness/last-run.json for scripts/verify-scout.sh.
# Needs curl, jq, docker compose, Ollama on the host with both models, and the stack started with
# FILING_FAULTS_ENABLED=true docker compose up -d --build.
#
# Usage: scripts/test-api.sh [scenario ...]
set -euo pipefail

cd "$(dirname "$0")/.."

BASE_URL="${API_URL:-http://localhost:8000}"
REQUEST_TIMEOUT="${REQUEST_TIMEOUT:-300}"
SLOW_MODEL_TIMEOUT_SECONDS=5
# FAULT_BLOCKED_BACKOFF_SECONDS in the SEC client, plus a margin.
BLOCKED_BACKOFF_WAIT_SECONDS=22
COLLECTOR_METRICS="${COLLECTOR_METRICS_URL:-http://localhost:8888/metrics}"
RESULTS_DIR=".harness"
RESULTS_FILE="${RESULTS_DIR}/last-run.json"
ACCESSION='^[0-9]{10}-[0-9]{2}-[0-9]{6}$'
RESTATED_VALUE=-47479000
RESTATED_ACCESSION="0001445305-22-000041"

BUSINESS="unknown_ticker single_figure ratio second_question trend restated ranking"
BUSINESS="${BUSINESS} outside_cache not_in_data"
TECHNICAL="sec_down sec_unreachable timeout ungrounded_answer model_unavailable tight_budget"
TECHNICAL="${TECHNICAL} bad_output sec_blocked"
ALL_SCENARIOS="${BUSINESS} ${TECHNICAL}"

green() { printf "\033[32m%s\033[0m" "$1"; }
red()   { printf "\033[31m%s\033[0m" "$1"; }
cyan()  { printf "\033[36m%s\033[0m" "$1"; }
dim()   { printf "\033[90m%s\033[0m" "$1"; }

FAILURES=""
QUESTION_IDS=""
HTTP_STATUS=""
HTTP_BODY="{}"
ASKED=" "

fail() {
  FAILURES="${FAILURES}${1}"$'\n'
  echo "    $(red "x") $1"
}

expect() {
  local label="$1" expected="$2" actual="$3"
  if [ "$actual" = "$expected" ]; then
    echo "    $(green "ok") ${label} = ${actual}"
  else
    fail "${label}: expected ${expected}, got ${actual}"
  fi
}

expect_true() {
  local label="$1" filter="$2"
  if [ "$(field "$filter")" = "true" ]; then
    echo "    $(green "ok") ${label}"
  else
    fail "${label}"
  fi
}

field() { echo "$HTTP_BODY" | jq -r "$1"; }

# ask TICKER QUESTION [EXTRA_JSON]
ask() {
  local body response extra="${3:-}"
  [ -n "$extra" ] || extra='{}'
  body=$(jq -n --arg ticker "$1" --arg question "$2" --argjson extra "$extra" \
    '{ticker: $ticker, question: $question} + $extra')
  response=$(curl -s --max-time "$REQUEST_TIMEOUT" -w $'\n%{http_code}' -X POST \
    "${BASE_URL}/questions" -H "Content-Type: application/json" -d "$body") \
    || response=$'{}\n000'
  HTTP_STATUS="${response##*$'\n'}"
  HTTP_BODY="${response%$'\n'*}"
  echo "$HTTP_BODY" | jq -e . >/dev/null 2>&1 || HTTP_BODY="{}"
  local question_id
  question_id=$(field '.question_id // empty')
  if [ -n "$question_id" ]; then
    QUESTION_IDS="${QUESTION_IDS}${question_id}"$'\n'
    echo "    $(dim "$1: $2 -> ${HTTP_STATUS} ${question_id}")"
  else
    echo "    $(dim "$1: $2 -> ${HTTP_STATUS}")"
  fi
  ASKED="${ASKED}${1} "
}

expect_answer() {
  expect "status" "$1" "$HTTP_STATUS"
  expect "outcome" "$2" "$(field '.outcome')"
}

expect_refusal() {
  expect "status" "$1" "$HTTP_STATUS"
  expect "outcome" "$2" "$(field '.outcome')"
  expect "reason" "$3" "$(field '.reason')"
}

# The newest fiscal year stored for a ticker and concept, from the facts endpoint.
latest_year() {
  curl -s --max-time 30 "${BASE_URL}/companies/$1/facts?concept=$2" | jq -r '.rows[0].fiscal_year // "none"'
}

expect_latest_years() {
  local ticker="$1" concept="$2" count="$3" latest
  latest=$(latest_year "$ticker" "$concept")
  expect "fiscal years" "$(jq -nc --argjson latest "$latest" --argjson count "$count" \
    '[range($latest - $count + 1; $latest + 1)]')" "$(field '[.figures[].fiscal_year] | unique | tostring')"
}

expect_cited_figures() {
  expect "figures" "$1" "$(field '.figures | length')"
  expect_true "every figure cites a 10-K accession number" \
    "all(.figures[]; (.accession | test(\"${ACCESSION}\")) and (.form | startswith(\"10-K\")))"
}

# --- scenarios ---

scenario_unknown_ticker() {
  ask ZZZZQ "What was revenue for the latest fiscal year?"
  expect_refusal 404 rejected unknown_ticker
}

scenario_single_figure() {
  ask KVYO "What was Klaviyo's revenue for its latest fiscal year?"
  expect_answer 200 answered
  expect_cited_figures 1
  expect_latest_years KVYO revenue 1
  expect "facts source" cache "$(field '.facts_source')"
}

scenario_ratio() {
  ask FRSH "What was Freshworks' net margin for its latest fiscal year?"
  expect_answer 200 answered
  expect "ratio" net_margin "$(field '.ratios[0].name')"
  expect "ratio accession numbers" 2 "$(field '.ratios[0].accessions | length')"
  expect "ratio fiscal year" "$(latest_year FRSH revenue)" "$(field '.ratios[0].fiscal_year')"
}

scenario_second_question() {
  case "$ASKED" in
    *" FRSH "*) ;;
    *) ask FRSH "What was Freshworks' net income for its latest fiscal year?" ;;
  esac
  ask FRSH "What was Freshworks' revenue for its latest fiscal year?"
  expect_answer 200 answered
  expect_latest_years FRSH revenue 1
  expect "facts source" stored "$(field '.facts_source')"
  expect "SEC calls" 0 "$(field '.sec_calls')"
}

scenario_trend() {
  ask WK "What was Workiva's revenue for each of its last three fiscal years?"
  expect_answer 200 answered
  expect_cited_figures 3
  expect_latest_years WK revenue 3
}

scenario_restated() {
  ask WK "What was Workiva's net income for fiscal year 2019?"
  expect_answer 200 answered
  expect_true "the restated value ${RESTATED_VALUE} from ${RESTATED_ACCESSION}" \
    "any(.figures[]; .value == ${RESTATED_VALUE} and .accession == \"${RESTATED_ACCESSION}\")"
}

scenario_ranking() {
  ask ABNB "How did Airbnb's net income for 2025 rank among all SEC filers?"
  expect_answer 200 answered
  expect_true "the ranking agent placed the company" \
    'any(.rankings[]; .rank != null and .filer_count > 0)'
  expect_true "the answer or a caveat names the frame" \
    '([.answer, .caveats[]] | join(" ") | ascii_downcase) | test("cy20[0-9]{2}|calendar")'
}

scenario_outside_cache() {
  ask KLTR "What was Kaltura's revenue for its latest fiscal year?"
  expect_answer 200 answered
  expect_cited_figures 1
  expect_latest_years KLTR revenue 1
  expect "facts source" sec "$(field '.facts_source')"
}

scenario_not_in_data() {
  ask AMPL "What was Amplitude's headcount by region?"
  expect_answer 200 not_available
  expect "figures" 0 "$(field '.figures | length')"
  expect_true "a caveat says what was searched" '.caveats | length > 0'
}

scenario_sec_down() {
  ask YEXT "What was Yext's revenue for its latest fiscal year?" '{"fault": "sec_down"}'
  expect_answer 200 answered
  expect "facts source" sec "$(field '.facts_source')"
}

scenario_sec_unreachable() {
  ask ABNB "How did Airbnb's net income for 2025 rank among all SEC filers?" \
    '{"fault": "sec_unreachable"}'
  expect "status" 200 "$HTTP_STATUS"
  expect "rankings" 0 "$(field '.rankings | length')"
  expect_true "a caveat says the frames fetch failed" \
    '.caveats | any(test("SEC frames data could not be fetched"))'
  expect_true "the answer says the ranking could not be fetched" \
    '.answer | test("unavailable|could not be fetched"; "i")'
}

scenario_timeout() {
  ask WK "What was Workiva's revenue for its latest fiscal year?" \
    "{\"fault\": \"slow_model\", \"timeout_seconds\": ${SLOW_MODEL_TIMEOUT_SECONDS}}"
  expect_refusal 504 timeout timeout
}

scenario_ungrounded_answer() {
  ask WK "What was Workiva's net income for fiscal year 2019?" '{"fault": "ungrounded_answer"}'
  expect_refusal 502 ungrounded ungrounded
}

scenario_model_unavailable() {
  ask WK "What was Workiva's revenue for its latest fiscal year?" '{"fault": "model_unavailable"}'
  expect_refusal 502 error model_unavailable
}

scenario_tight_budget() {
  ask FRSH "What was Freshworks' net margin for its latest fiscal year?" '{"fault": "tight_budget"}'
  expect_refusal 504 budget budget
}

scenario_bad_output() {
  ask WK "What was Workiva's revenue for its latest fiscal year?" '{"fault": "bad_output"}'
  expect_refusal 502 error bad_output
}

scenario_sec_blocked() {
  ask BOX "What was Box's revenue for its latest fiscal year?" '{"fault": "sec_blocked"}'
  expect_refusal 502 error sec_unavailable
  ask ASAN "What was Asana's revenue for its latest fiscal year?"
  expect_refusal 503 error sec_backoff
  echo "    $(dim "waiting ${BLOCKED_BACKOFF_WAIT_SECONDS}s for the back-off to end")"
  sleep "$BLOCKED_BACKOFF_WAIT_SECONDS"
}

# --- run ---

run_scenario() {
  local name="$1" started finished passed
  FAILURES=""
  QUESTION_IDS=""
  echo ""
  cyan "--- ${name} ---"; echo
  started=$(date +%s)
  "scenario_${name}"
  finished=$(date +%s)
  passed=$([ -z "$FAILURES" ] && echo true || echo false)
  jq -n \
    --arg scenario "$name" \
    --argjson passed "$passed" \
    --argjson seconds "$(( finished - started ))" \
    --arg question_ids "$QUESTION_IDS" \
    --arg status "$HTTP_STATUS" \
    --argjson body "$HTTP_BODY" \
    --arg failures "$FAILURES" \
    '{scenario: $scenario, passed: $passed, seconds: $seconds,
      question_ids: ($question_ids | split("\n") | map(select(length > 0))),
      status: ($status | tonumber? // null), outcome: $body.outcome, reason: $body.reason,
      figures: ($body.figures // [] | length), answer: $body.answer,
      failures: ($failures | split("\n") | map(select(length > 0)))}' >> "$RUN_LINES"
}

main() {
  local scenarios="$*" name
  [ -n "$scenarios" ] || scenarios="$ALL_SCENARIOS"
  for name in $scenarios; do
    if ! echo " ${ALL_SCENARIOS} " | grep -q " ${name} "; then
      echo "unknown scenario: ${name}"
      echo "scenarios: ${ALL_SCENARIOS}"
      exit 2
    fi
  done

  if ! curl -sf --max-time 10 "${BASE_URL}/health" >/dev/null; then
    red "API not reachable at ${BASE_URL}; start the stack with FILING_FAULTS_ENABLED=true docker compose up -d --build"
    echo
    exit 2
  fi

  # First questions must load their company, so every run starts with no facts on file.
  docker compose exec -T postgres psql -q -U filing -d filing -c "TRUNCATE facts, fact_loads" >/dev/null

  # verify-scout.sh subtracts these from the collector's cumulative exporter counters.
  local collector_metrics self_metrics_at_start="" self_metrics_recorded=false
  if collector_metrics=$(curl -sf --max-time 10 "$COLLECTOR_METRICS"); then
    self_metrics_at_start=$(printf '%s\n' "$collector_metrics" | grep '^otelcol_exporter_' || true)
    self_metrics_recorded=true
  else
    echo "  collector self-metrics not reachable at ${COLLECTOR_METRICS}; verify-scout.sh will fail the send counts"
  fi

  local framework
  framework=$(curl -sf --max-time 10 "${BASE_URL}/health" | jq -r '.framework // "strands"')
  echo "  $(dim "framework: ${framework}")"

  mkdir -p "$RESULTS_DIR"
  RUN_LINES=$(mktemp)
  local run_started run_started_at
  run_started=$(date +%s)
  run_started_at=$(date -u +%Y-%m-%dT%H:%M:%SZ)

  for name in $scenarios; do
    run_scenario "$name"
  done

  local total_seconds=$(( $(date +%s) - run_started ))
  jq -s \
    --arg started_at "$run_started_at" \
    --arg self_metrics_at_start "$self_metrics_at_start" \
    --argjson self_metrics_recorded "$self_metrics_recorded" \
    --argjson total_seconds "$total_seconds" \
    --arg framework "$framework" \
    --arg analyst_model "$(docker compose exec -T api printenv ANALYST_MODEL 2>/dev/null || true)" \
    --arg ranking_model "$(docker compose exec -T api printenv RANKING_MODEL 2>/dev/null || true)" \
    '{started_at: $started_at, total_seconds: $total_seconds, framework: $framework,
      collector_self_metrics_at_start: (if $self_metrics_recorded then $self_metrics_at_start else null end),
      analyst_model: ($analyst_model | rtrimstr("\r")), ranking_model: ($ranking_model | rtrimstr("\r")),
      passed: all(.[]; .passed), scenarios: .}' "$RUN_LINES" > "$RESULTS_FILE"
  rm -f "$RUN_LINES"

  echo ""
  cyan "=== Summary ==="; echo
  jq -r '.scenarios[] | "\(if .passed then "PASS" else "FAIL" end)  \(.scenario)  \(.status)  \(.outcome // "-")  \(.question_ids | join(","))  \(.seconds)s"' \
    "$RESULTS_FILE" | column -t
  echo ""
  echo "Total ${total_seconds}s. Question IDs written to ${RESULTS_FILE}."
  if [ "$(jq -r .passed "$RESULTS_FILE")" != "true" ]; then
    red "Some scenarios failed."; echo
    exit 1
  fi
  green "All scenarios passed."; echo
}

main "$@"
