#!/usr/bin/env bash
# Runs the KYC scenarios against the running stack and checks each case's outcome.
# Writes results to .harness/last-run.json for scripts/verify-scout.sh.
# Needs curl, jq, docker compose, and the stack started with
# KYC_FAULTS_ENABLED=true docker compose up -d --build.
#
# Usage: scripts/test-api.sh [scenario ...]
set -euo pipefail

cd "$(dirname "$0")/.."

BASE_URL="${API_URL:-http://localhost:8000}"
CASE_TIMEOUT="${CASE_TIMEOUT:-600}"
DOCUMENT_DEADLINE_SECONDS="${DOCUMENT_DEADLINE_SECONDS:-5}"
CRASH_TARGET="${CRASH_TARGET:-kyc-assessment__model_request}"
COLLECTOR_METRICS="${COLLECTOR_METRICS_URL:-http://localhost:8888/metrics}"
# The SDK default OTEL_BSP_SCHEDULE_DELAY, which the worker does not override.
BSP_SCHEDULE_DELAY_MS=5000
SPAN_EXPORT_MARGIN_SECONDS=2
RESULTS_DIR=".harness"
RESULTS_FILE="${RESULTS_DIR}/last-run.json"
POLL_INTERVAL=2

ALL_SCENARIOS="auto_approved approved_after_resubmission approved_by_reviewer rejected_by_reviewer"
ALL_SCENARIOS="${ALL_SCENARIOS} rejected_automatically expired worker_crash model_unavailable"
ALL_SCENARIOS="${ALL_SCENARIOS} sanctions_down tight_budget bad_output"

green() { printf "\033[32m%s\033[0m" "$1"; }
red()   { printf "\033[31m%s\033[0m" "$1"; }
cyan()  { printf "\033[36m%s\033[0m" "$1"; }
dim()   { printf "\033[90m%s\033[0m" "$1"; }

log() { echo "    $(dim "$1")"; }

CASE_ID=""
VIEW="{}"
FAILURES=""
NOTES=""
CRASHED_ACTIVITY="null"
DOCUMENTS_SENT=0

fail() {
  FAILURES="${FAILURES}${1}"$'\n'
  echo "    $(red "x") $1"
}

note() {
  NOTES="${NOTES}${1}"$'\n'
  log "$1"
}

expect() {
  local label="$1" expected="$2" actual="$3"
  if [ "$actual" = "$expected" ]; then
    echo "    $(green "ok") ${label} = ${actual}"
  else
    fail "${label}: expected ${expected}, got ${actual}"
  fi
}

view_field() { echo "$VIEW" | jq -r "$1"; }

# --- API calls ---

HTTP_STATUS=""
HTTP_BODY=""

request() {
  local method="$1" path="$2" body="${3:-}"
  local response
  if [ -n "$body" ]; then
    response=$(curl -s --max-time 30 -w $'\n%{http_code}' -X "$method" "${BASE_URL}${path}" \
      -H "Content-Type: application/json" -d "$body") || response=$'\n000'
  else
    response=$(curl -s --max-time 30 -w $'\n%{http_code}' -X "$method" "${BASE_URL}${path}") \
      || response=$'\n000'
  fi
  HTTP_STATUS="${response##*$'\n'}"
  HTTP_BODY="${response%$'\n'*}"
}

create_case() {
  local name="$1" country="$2" account_type="$3" overrides="${4:-}"
  if [ -z "$overrides" ]; then
    overrides="{}"
  fi
  local body
  body=$(jq -nc --arg name "$name" --arg country "$country" --arg account_type "$account_type" \
    --argjson overrides "$overrides" \
    '{name: $name, country: $country, account_type: $account_type} + $overrides')
  request POST /cases "$body"
  if [ "$HTTP_STATUS" != "201" ]; then
    red "POST /cases returned ${HTTP_STATUS}: ${HTTP_BODY}"; echo
    if [ "$HTTP_STATUS" = "422" ] && [ "$overrides" != "{}" ]; then
      red "Restart the stack with KYC_FAULTS_ENABLED=true docker compose up -d"; echo
    fi
    exit 2
  fi
  CASE_ID=$(echo "$HTTP_BODY" | jq -r .case_id)
  VIEW="$HTTP_BODY"
  log "case ${CASE_ID}"
}

send_document() {
  local file="$1"
  local body
  body=$(jq -nc --arg document_type "$(basename "$file" .txt)" --rawfile raw_text "$file" \
    '{document_type: $document_type, raw_text: $raw_text}')
  request POST "/cases/${CASE_ID}/documents" "$body"
  expect "POST documents $(basename "$file" .txt)" 202 "$HTTP_STATUS"
  if [ "$HTTP_STATUS" = "202" ]; then
    DOCUMENTS_SENT=$(( DOCUMENTS_SENT + 1 ))
  fi
}

send_fixture_set() {
  local file
  for file in "fixtures/$1"/*.txt; do
    send_document "$file"
  done
}

# Resends each missing document from the first fixture set that has it.
resend_missing() {
  local document_type set_name
  for document_type in $(view_field '.missing_documents[]'); do
    for set_name in "$@"; do
      if [ -f "fixtures/${set_name}/${document_type}.txt" ]; then
        log "resending ${document_type} from ${set_name}"
        send_document "fixtures/${set_name}/${document_type}.txt"
        break
      fi
    done
  done
}

review() {
  local decision="$1"
  request POST "/cases/${CASE_ID}/review" \
    "$(jq -nc --arg decision "$decision" '{decision: $decision, reviewer: "harness"}')"
  expect "POST review ${decision}" 200 "$HTTP_STATUS"
  if [ "$HTTP_STATUS" = "200" ]; then
    VIEW="$HTTP_BODY"
  fi
}

# A case waiting for documents in a later round than this will never get them.
EXPECTED_ROUNDS=0

settled_state() {
  echo "(.outcome != null) or (.status == \"awaiting_review\")
    or (.status == \"awaiting_documents\" and .resubmission_round > ${EXPECTED_ROUNDS})"
}

case_state() {
  view_field '"status=\(.status) round=\(.resubmission_round) outcome=\(.outcome) escalation=\(.escalation_reason)"'
}

# Records a failure and returns 0 when the case is stuck in a state it cannot leave on its own.
stopped_unexpectedly() {
  local waiting_for="$1"
  if [ "$(echo "$VIEW" | jq -r "$(settled_state)")" = "true" ]; then
    fail "case reached $(case_state), which the scenario did not expect, while waiting for ${waiting_for}"
    return 0
  fi
  return 1
}

# Retries non-200 responses, which the API returns while the worker is down.
wait_for() {
  local predicate="$1" description="$2" timeout="${3:-$CASE_TIMEOUT}"
  local deadline=$(( $(date +%s) + timeout ))
  while [ "$(date +%s)" -lt "$deadline" ]; do
    request GET "/cases/${CASE_ID}"
    if [ "$HTTP_STATUS" = "200" ]; then
      VIEW="$HTTP_BODY"
      if [ "$(echo "$VIEW" | jq -r "$predicate")" = "true" ]; then
        log "$(view_field '"status=\(.status) round=\(.resubmission_round) escalation=\(.escalation_reason)"')"
        return 0
      fi
      if stopped_unexpectedly "$description"; then
        return 0
      fi
    fi
    sleep "$POLL_INTERVAL"
  done
  fail "timed out after ${timeout}s waiting for ${description} (last status $(view_field .status))"
}

wait_until_settled() {
  local round="$1"
  wait_for "(.outcome != null) or (.status == \"awaiting_review\")
    or (.status == \"awaiting_documents\" and .resubmission_round > ${round})" \
    "the case to settle after round ${round}"
}

# --- Temporal activity history ---

case_activities() {
  docker compose exec -T api python - "$1" "$CASE_ID" < scripts/case_activities.py
}

ACTIVITIES="[]"

load_activities() {
  ACTIVITIES=$(case_activities history) || ACTIVITIES="[]"
}

count_activities() {
  echo "$ACTIVITIES" | jq "[.[] | select($1)] | length"
}

# --- Scenarios: business outcomes ---

scenario_auto_approved() {
  create_case "Maria Elena Gonzalez" IE personal
  send_fixture_set clean_personal
  wait_until_settled 0
  expect outcome approved "$(view_field .outcome)"
  expect escalation_reason null "$(view_field .escalation_reason)"
  expect resubmission_round 0 "$(view_field .resubmission_round)"
  expect review null "$(view_field .review)"
}

scenario_approved_after_resubmission() {
  EXPECTED_ROUNDS=1
  create_case "Priya Chandrasekaran" CA personal
  send_fixture_set address_mismatch
  wait_until_settled 0
  expect status awaiting_documents "$(view_field .status)"
  expect resubmission_round 1 "$(view_field .resubmission_round)"
  resend_missing corrected_address address_mismatch
  wait_until_settled 1
  expect outcome approved "$(view_field .outcome)"
  expect resubmission_round 1 "$(view_field .resubmission_round)"
  expect escalation_reason null "$(view_field .escalation_reason)"
}

reviewed_partial_sanctions_match() {
  local decision="$1" expected_outcome="$2"
  create_case "Alexander Petrov Volkov" GB personal
  send_fixture_set partial_sanctions_match
  wait_until_settled 0
  expect status awaiting_review "$(view_field .status)"
  expect escalation_reason risk "$(view_field .escalation_reason)"
  if [ "$(view_field .status)" = "awaiting_review" ]; then
    review "$decision"
  fi
  wait_for '.outcome != null' "the reviewer's decision to close the case" 60
  expect outcome "$expected_outcome" "$(view_field .outcome)"
  expect escalation_reason risk "$(view_field .escalation_reason)"
  expect review.decision "$decision" "$(view_field .review.decision)"
}

scenario_approved_by_reviewer() { reviewed_partial_sanctions_match approve approved; }

scenario_rejected_by_reviewer() { reviewed_partial_sanctions_match reject rejected; }

scenario_rejected_automatically() {
  EXPECTED_ROUNDS=2
  create_case "Fatima Zahra Bensalem" FR personal
  send_fixture_set expired_id
  local round=0 settled_round
  while true; do
    wait_until_settled "$round"
    settled_round=$(view_field .resubmission_round)
    if [ "$(view_field .status)" != "awaiting_documents" ] || [ "$settled_round" -le "$round" ]; then
      break
    fi
    round="$settled_round"
    resend_missing expired_id
  done
  expect outcome rejected "$(view_field .outcome)"
  expect resubmission_round 2 "$(view_field .resubmission_round)"
  expect escalation_reason null "$(view_field .escalation_reason)"
  expect review null "$(view_field .review)"
}

scenario_expired() {
  create_case "Tomasz Wright" PL personal \
    "{\"document_deadline_seconds\": ${DOCUMENT_DEADLINE_SECONDS}}"
  wait_for '.outcome != null' "the document deadline" $(( DOCUMENT_DEADLINE_SECONDS + 60 ))
  expect outcome expired "$(view_field .outcome)"
  expect missing_documents "id,proof_of_address" "$(view_field '.missing_documents | join(",")')"
}

# --- Scenarios: technical failures ---

# A SIGKILL loses spans still waiting out the batch span processor's delay, so the kill waits past it.
extraction_spans_exported_at() {
  load_activities
  echo "$ACTIVITIES" | jq --argjson delay_ms "$BSP_SCHEDULE_DELAY_MS" --argjson margin "$SPAN_EXPORT_MARGIN_SECONDS" \
    --argjson now "$(date +%s)" \
    '[.[] | select(.agent == "kyc-extraction" and .outcome == "completed") | .closed_at]
      | (max // $now) + $delay_ms / 1000 + $margin | ceil'
}

# Temporal retries the killed attempt only after its 30s heartbeat timeout.
scenario_worker_crash() {
  create_case "Daniel Otieno Mwangi" ZA business
  send_fixture_set clean_business

  local in_flight="" exported_at="" deadline=$(( $(date +%s) + CASE_TIMEOUT ))
  while [ -z "$in_flight" ] && [ "$(date +%s)" -lt "$deadline" ]; do
    request GET "/cases/${CASE_ID}"
    if [ "$HTTP_STATUS" = "200" ]; then
      VIEW="$HTTP_BODY"
      if stopped_unexpectedly "a ${CRASH_TARGET} activity to kill"; then
        return
      fi
    fi
    in_flight=$(case_activities pending | jq -c --arg target "$CRASH_TARGET" \
      'map(select(.state == "PENDING_ACTIVITY_STATE_STARTED" and (.activity_type | contains($target)))) | first // empty') \
      || in_flight=""
    if [ -n "$in_flight" ] && [ -z "$exported_at" ]; then
      exported_at=$(extraction_spans_exported_at)
      log "extraction spans exported by $(( exported_at - $(date +%s) ))s from now, waiting to kill"
    fi
    if [ -n "$in_flight" ] && [ "$(date +%s)" -lt "$exported_at" ]; then
      in_flight=""
      sleep 1
    fi
  done
  if [ -z "$in_flight" ]; then
    fail "no ${CRASH_TARGET} activity was seen running after the extraction spans were exported"
    return
  fi

  docker compose kill -s SIGKILL worker >/dev/null 2>&1
  local killed_id killed_attempt
  killed_id=$(echo "$in_flight" | jq -r .activity_id)
  killed_attempt=$(echo "$in_flight" | jq -r .attempt)
  CRASHED_ACTIVITY=$(echo "$in_flight" | jq -c '{activity_id, activity_type, attempt}')
  note "killed the worker during activity ${killed_id} ($(echo "$in_flight" | jq -r .activity_type)), attempt ${killed_attempt}"

  local still_pending
  still_pending=$(case_activities pending | jq --arg id "$killed_id" 'any(.activity_id == $id)')
  expect "activity ${killed_id} still in flight after the kill" true "$still_pending"

  sleep 3
  docker compose start worker >/dev/null 2>&1
  log "worker restarted"

  wait_for '.outcome != null or .status == "awaiting_review"' "the case to finish after the restart"
  expect outcome approved "$(view_field .outcome)"
  expect escalation_reason null "$(view_field .escalation_reason)"

  load_activities
  local retried
  retried=$(echo "$ACTIVITIES" | jq -r --arg id "$killed_id" \
    'map(select(.activity_id == $id)) | first | "\(.attempt) \(.outcome)"')
  expect "activity ${killed_id} attempt and outcome" "$(( killed_attempt + 1 )) completed" "$retried"
}

scenario_model_unavailable() {
  create_case "Maria Elena Gonzalez" IE personal '{"fault": "model_unavailable"}'
  send_fixture_set clean_personal
  wait_until_settled 0
  expect outcome approved "$(view_field .outcome)"
  expect escalation_reason null "$(view_field .escalation_reason)"
  load_activities
  expect "first model request, completed on attempt 3 after two connection errors" \
    '{"attempt":3,"outcome":"completed","unreachable":true}' \
    "$(echo "$ACTIVITIES" | jq -c '[.[] | select(.kind == "model_request")] | first
      | {attempt, outcome, unreachable: (.last_failure // "" | contains("ollama unreachable"))}')"
  expect "later model requests that needed a retry" 0 \
    "$(echo "$ACTIVITIES" | jq '[.[] | select(.kind == "model_request")] | .[1:]
      | map(select(.attempt != 1)) | length')"
}

scenario_sanctions_down() {
  create_case "Maria Elena Gonzalez" IE personal '{"fault": "sanctions_down"}'
  send_fixture_set clean_personal
  wait_until_settled 0
  expect outcome approved "$(view_field .outcome)"
  expect escalation_reason null "$(view_field .escalation_reason)"
  load_activities
  local screenings
  screenings=$(count_activities '.tool == "screen_sanctions"')
  if [ "$screenings" -eq 0 ]; then
    fail "the assessment agent never called screen_sanctions"
  fi
  expect "screen_sanctions calls that succeeded on attempt 4 after three failures" "$screenings" \
    "$(count_activities '.tool == "screen_sanctions" and .attempt == 4 and .outcome == "completed" and (.last_failure // "" | contains("sanctions service unreachable"))')"
}

scenario_tight_budget() {
  create_case "Maria Elena Gonzalez" IE personal '{"fault": "tight_budget"}'
  send_fixture_set clean_personal
  wait_until_settled 0
  expect status awaiting_review "$(view_field .status)"
  expect escalation_reason budget "$(view_field .escalation_reason)"
  expect decisions "[]" "$(view_field '.decisions | tojson')"
  load_activities
  expect "assessment model requests" 1 \
    "$(count_activities '.agent == "kyc-assessment" and .kind == "model_request"')"
  if [ "$(view_field .status)" = "awaiting_review" ]; then
    review approve
  fi
  wait_for '.outcome != null' "the reviewer's decision to close the case" 60
  expect outcome approved "$(view_field .outcome)"
}

scenario_bad_output() {
  create_case "Maria Elena Gonzalez" IE personal '{"fault": "bad_output"}'
  send_fixture_set clean_personal
  wait_until_settled 0
  expect outcome approved "$(view_field .outcome)"
  expect escalation_reason null "$(view_field .escalation_reason)"
  load_activities
  expect "extraction model requests (two documents plus one retry)" 3 \
    "$(count_activities '.agent == "kyc-extraction" and .kind == "model_request"')"
  expect "extraction requests carrying a retry prompt" 1 \
    "$(count_activities '.agent == "kyc-extraction" and .has_retry_prompt')"
}

# --- Runner ---

activity_summary() {
  echo "$ACTIVITIES" | jq -c '{
    extraction_requests: [.[] | select(.agent == "kyc-extraction" and .kind == "model_request")] | length,
    assessment_requests: [.[] | select(.agent == "kyc-assessment" and .kind == "model_request")] | length,
    tool_calls: [.[] | select(.kind == "call_tool") | .tool],
    retry_prompts: [.[] | select(.has_retry_prompt) | .agent],
    retried_activities: [.[] | select((.attempt // 1) > 1) | {activity_id, activity_type, tool, attempt}]
  }'
}

# Closing a stranded case ends its workflow span, so the trace exports whole.
close_stranded_review() {
  if [ -z "$FAILURES" ] || [ -z "$CASE_ID" ] || [ "$(view_field .status)" != "awaiting_review" ]; then
    return
  fi
  request POST "/cases/${CASE_ID}/review" '{"decision": "reject", "reviewer": "harness-cleanup"}'
  note "rejected the stranded review so the case closes (HTTP ${HTTP_STATUS})"
}

run_scenario() {
  local name="$1"
  CASE_ID=""
  VIEW="{}"
  FAILURES=""
  NOTES=""
  CRASHED_ACTIVITY="null"
  DOCUMENTS_SENT=0
  EXPECTED_ROUNDS=0
  ACTIVITIES="[]"
  echo ""
  cyan "=== ${name} ==="; echo
  local started finished
  started=$(date +%s)
  "scenario_${name}"
  finished=$(date +%s)
  if [ "$ACTIVITIES" = "[]" ] && [ -n "$CASE_ID" ]; then
    load_activities
  fi
  close_stranded_review

  local passed=true verdict
  verdict="$(green PASS)"
  if [ -n "$FAILURES" ]; then
    passed=false
    verdict="$(red FAIL)"
  fi
  echo "  ${verdict} ${name} case=${CASE_ID} outcome=$(view_field .outcome) $(( finished - started ))s"

  jq -nc \
    --arg scenario "$name" \
    --arg case_id "$CASE_ID" \
    --argjson passed "$passed" \
    --argjson seconds "$(( finished - started ))" \
    --argjson view "$VIEW" \
    --argjson activities "$(activity_summary)" \
    --arg failures "$FAILURES" \
    --arg notes "$NOTES" \
    --argjson crashed_activity "$CRASHED_ACTIVITY" \
    --argjson documents_sent "$DOCUMENTS_SENT" \
    '{scenario: $scenario, case_id: $case_id, passed: $passed, seconds: $seconds,
      status: $view.status, outcome: $view.outcome, escalation_reason: $view.escalation_reason,
      resubmission_round: $view.resubmission_round, decisions: $view.decisions,
      documents_sent: $documents_sent, activities: $activities,
      crashed_activity: $crashed_activity,
      failures: ($failures | split("\n") | map(select(length > 0))),
      notes: ($notes | split("\n") | map(select(length > 0)))}' >> "$RUN_LINES"
}

main() {
  local scenarios="$*"
  if [ -z "$scenarios" ]; then
    scenarios="$ALL_SCENARIOS"
  fi
  local name
  for name in $scenarios; do
    if ! echo " ${ALL_SCENARIOS} " | grep -q " ${name} "; then
      echo "unknown scenario: ${name}"
      echo "scenarios: ${ALL_SCENARIOS}"
      exit 2
    fi
  done

  request GET /health
  if [ "$HTTP_STATUS" != "200" ]; then
    red "API not reachable at ${BASE_URL}; start the stack with KYC_FAULTS_ENABLED=true docker compose up -d --build"; echo
    exit 2
  fi

  # verify-scout.sh subtracts these from the collector's cumulative exporter counters.
  local collector_metrics self_metrics_at_start="" self_metrics_recorded=false
  if collector_metrics=$(curl -sf --max-time 10 "$COLLECTOR_METRICS"); then
    self_metrics_at_start=$(printf '%s\n' "$collector_metrics" | grep '^otelcol_exporter_' || true)
    self_metrics_recorded=true
  else
    log "collector self-metrics not reachable at ${COLLECTOR_METRICS}; verify-scout.sh will fail the send counts"
  fi

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
    --argjson total_seconds "$total_seconds" \
    --arg extraction_model "$(docker compose exec -T worker printenv EXTRACTION_MODEL 2>/dev/null || true)" \
    --arg assessment_model "$(docker compose exec -T worker printenv ASSESSMENT_MODEL 2>/dev/null || true)" \
    --arg self_metrics_at_start "$self_metrics_at_start" \
    --argjson self_metrics_recorded "$self_metrics_recorded" \
    '{started_at: $started_at, total_seconds: $total_seconds,
      extraction_model: $extraction_model, assessment_model: $assessment_model,
      collector_self_metrics_at_start: (if $self_metrics_recorded then $self_metrics_at_start else null end),
      passed: all(.[]; .passed), scenarios: .}' "$RUN_LINES" > "$RESULTS_FILE"
  rm -f "$RUN_LINES"

  echo ""
  cyan "=== Summary ==="; echo
  jq -r '.scenarios[] | "\(if .passed then "PASS" else "FAIL" end)  \(.scenario)  \(.case_id)  \(.outcome)  \(.seconds)s"' \
    "$RESULTS_FILE" | column -t
  echo ""
  echo "Total ${total_seconds}s. Case IDs written to ${RESULTS_FILE}."
  if [ "$(jq -r .passed "$RESULTS_FILE")" != "true" ]; then
    red "Some scenarios failed."; echo
    exit 1
  fi
  green "All scenarios passed."; echo
}

main "$@"
