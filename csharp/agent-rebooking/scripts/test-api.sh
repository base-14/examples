#!/bin/bash

# Shebang matches the other test-api.sh scripts in this repo. verify-scout.sh uses
# #!/usr/bin/env bash instead, matching the other verify-scout.sh scripts.

# ---------------------------------------------------------------------------
# test-api.sh - end-to-end API check for the approval-gated rebooking agent.
#
# Eight cases against a live stack with Ollama on the host, in three sections.
#
# Section 1 and 2, the happy path:
#   BK-1001  under the limit, the gate auto-approves, the run completes on its own.
#   BK-1002  over the limit, the run parks on pending_approval, a human approves,
#            the run completes.
#
# Section 3, six deliberate failures, one per row of the error matrix. Four of them
# need the stack changed under the app. Three restart the app service with one
# environment variable overridden; the fourth restarts it once more to undo the
# previous case's dead port and then stops the postgres container. That is four
# restarts inside the section, plus one at the end to put the app back. Both kinds of
# change are undone by restore_stack, which runs from an EXIT trap as well as at the
# end, so an interrupted run does not leave the app pointing at a dead port. Ollama
# itself is never touched: it runs on the host, not in Compose, and stopping it would
# break the machine for whoever runs this next.
#
# Section 3 needs a local Compose stack. When docker compose cannot see a running app
# service the whole section is skipped rather than failed, so API_URL pointed at a
# remote deployment still gets sections 1 and 2.
#
# Assertions are on run state and the tool log only, never on reply text: the model
# writes the reply and its wording changes between runs. On failure the run's tool
# log is printed.
#
# On an M-series Mac, 12 cores, qwen3.5:9b on host Ollama: BK-1001 takes 34-46s and
# BK-1002 27-32s. BK-1001 is the slower of the two because
# it runs the whole loop to a final reply in one pass, while BK-1002 splits across the
# approval. Budget more on a slower machine or a larger model.
#
# The model does not always call the tool on its first pass. Roughly one run in nine,
# BK-1001 completes without calling rebook and this script retries it, which takes the
# case to about 200s. That is the model wandering, not a broken stack, and the retry
# exists for it.
#
# Usage:
#   ./scripts/test-api.sh
#   API_URL=http://localhost:8080 ./scripts/test-api.sh
#   SKIP_FAILURE_CASES=1 ./scripts/test-api.sh   # sections 1 and 2 only, about 80s
#
# Section 3 costs about four and a half minutes and restarts the app service, so
# SKIP_FAILURE_CASES=1 is the way to run the happy path on its own. Without it the
# section runs whenever docker compose can see a running app service.
# ---------------------------------------------------------------------------

set -eu

# docker compose needs the directory holding compose.yaml, so section 3 works the same
# whether this is called as ./scripts/test-api.sh or from inside scripts/.
cd "$(dirname "$0")/.."

API_URL=${API_URL:-http://localhost:8080}

# This script's own polling budget per run, not the app's RUN_TIMEOUT_SECONDS. Section 3
# passes the app's value to one `docker compose up` invocation only, so the two never
# collide even though they share a name.
RUN_TIMEOUT_SECONDS=${RUN_TIMEOUT_SECONDS:-300}
POLL_INTERVAL_SECONDS=${POLL_INTERVAL_SECONDS:-2}

PASSED=0
FAILED=0
RUN_BODY=""
RUN_STATE=""

# Set by http_request: the response body goes to this file rather than a variable,
# so a body containing a literal newline cannot be confused with the status code
# curl reports alongside it.
HTTP_STATUS=""
HTTP_BODY_FILE=$(mktemp /tmp/agent-rebooking-http-XXXXXX.json)

# restore_stack is a no-op until section 3 has captured what to restore to.
trap 'rm -f "$HTTP_BODY_FILE"; restore_stack' EXIT

# --- section 3 stack control ----------------------------------------------
#
# Captured from the running container before anything is changed, and put back from
# here. Reading the live values rather than assuming the compose defaults means a
# reader who runs with their own OLLAMA_BASE_URL or APPROVAL_LIMIT gets their own
# settings back, not the file's.
STACK_CAPTURED=0
APP_OLLAMA_BASE_URL=""
APP_RUN_TIMEOUT_SECONDS=""
APP_APPROVAL_TIMEOUT_SECONDS=""

app_is_composed() {
    docker compose ps --status running --services 2>/dev/null | grep -qx app
}

capture_stack() {
    APP_OLLAMA_BASE_URL=$(docker compose exec -T app printenv OLLAMA_BASE_URL 2>/dev/null || echo "")
    APP_RUN_TIMEOUT_SECONDS=$(docker compose exec -T app printenv RUN_TIMEOUT_SECONDS 2>/dev/null || echo "")
    APP_APPROVAL_TIMEOUT_SECONDS=$(docker compose exec -T app printenv APPROVAL_TIMEOUT_SECONDS 2>/dev/null || echo "")
    if [ -z "$APP_OLLAMA_BASE_URL" ] || [ -z "$APP_RUN_TIMEOUT_SECONDS" ] || [ -z "$APP_APPROVAL_TIMEOUT_SECONDS" ]; then
        return 1
    fi
    STACK_CAPTURED=1
    return 0
}

# Brings the app back up with one setting overridden and the other two at the values
# captured above. Every variable is passed explicitly, so this does not depend on what
# happens to be exported in the caller's shell.
restart_app() {
    local ollama="$1" run_timeout="$2" approval_timeout="$3"
    env OLLAMA_BASE_URL="$ollama" \
        RUN_TIMEOUT_SECONDS="$run_timeout" \
        APPROVAL_TIMEOUT_SECONDS="$approval_timeout" \
        docker compose up -d app >/dev/null 2>&1
    wait_for_services
}

# Runs from the EXIT trap as well as at the end of section 3, so an interrupt does not
# leave the app pointing at a dead port or the database stopped. Silent when section 3
# never started. STACK_CAPTURED is cleared only after the app has reported healthy, so
# an interrupt partway through leaves the flag set and the trap tries again rather than
# treating the work as already done. A restore that cannot bring the app back exits
# through wait_for_services, which says so and returns 1.
restore_stack() {
    if [ "$STACK_CAPTURED" != "1" ]; then
        return 0
    fi
    echo ""
    echo "Restoring the stack..."
    docker compose start postgres >/dev/null 2>&1 || true
    restart_app "$APP_OLLAMA_BASE_URL" "$APP_RUN_TIMEOUT_SECONDS" "$APP_APPROVAL_TIMEOUT_SECONDS"
    STACK_CAPTURED=0
}

echo "=== agent-rebooking API test ==="
echo "Target: $API_URL"
echo "Run budget: ${RUN_TIMEOUT_SECONDS}s per run"
echo ""

pass() {
    echo "[PASS] $1"
    PASSED=$((PASSED + 1))
}

fail() {
    echo "[FAIL] $1"
    FAILED=$((FAILED + 1))
}

# Reads one value out of a JSON document on stdin. Prints nothing and succeeds when
# the path is missing, so a caller can test for an empty string.
jget() {
    python3 -c '
import json, sys
doc = json.load(sys.stdin)
for key in sys.argv[1:]:
    if doc is None:
        break
    doc = doc.get(key) if isinstance(doc, dict) else None
print("" if doc is None else doc)
' "$@" 2>/dev/null || echo ""
}

# Runs curl, writes the response body to $HTTP_BODY_FILE and sets HTTP_STATUS to the
# response code, or "000" when curl itself could not reach the server.
http_request() {
    HTTP_STATUS=$(curl -s -o "$HTTP_BODY_FILE" -w "%{http_code}" "$@" 2>/dev/null || echo "000")
}

print_tool_log() {
    local body="$1"
    echo "  --- tool log ---"
    echo "$body" | python3 -c '
import json, sys
try:
    run = json.load(sys.stdin)
except ValueError:
    print("  (no run body)")
    sys.exit()
print("  state={0} outcome={1} error={2}".format(
    run.get("state"), run.get("outcome"), run.get("error")))
calls = run.get("toolCalls") or []
for call in calls:
    print("  tool {0} {1}".format(call["tool"], call["arguments"]))
if not calls:
    print("  (no tool calls)")
for approval in run.get("approvals") or []:
    print("  approval {0} {1} amount={2} limit={3} outcome={4}".format(
        approval["approvalId"], approval["tool"],
        approval["amount"], approval["limit"], approval["outcome"]))
' 2>/dev/null || echo "  (could not parse run body)"
    echo "  ----------------"
}

# Every approval entry's outcome on the run, one per line. The gate records an entry for
# each priceable tool call it decides, so an empty result means the gate never ran.
approval_outcomes() {
    echo "$1" | python3 -c '
import json, sys
run = json.load(sys.stdin)
for entry in run.get("approvals") or []:
    print(entry.get("outcome"))
' 2>/dev/null
}

tool_was_called() {
    echo "$1" | python3 -c '
import json, sys
run = json.load(sys.stdin)
calls = [c["tool"] for c in (run.get("toolCalls") or [])]
sys.exit(0 if sys.argv[1] in calls else 1)
' "$2" 2>/dev/null
}

wait_for_services() {
    echo "Waiting for the app to become healthy..."
    local retries=60
    while [ $retries -gt 0 ]; do
        if curl -sf "$API_URL/health" > /dev/null 2>&1; then
            echo "App ready."
            echo ""
            return 0
        fi
        retries=$((retries - 1))
        sleep 2
    done
    echo "ERROR: $API_URL/health did not answer within 120 seconds. Start the stack with 'make up'."
    exit 1
}

start_run() {
    local message="$1"
    http_request -X POST "$API_URL/runs" \
        -H "Content-Type: application/json" \
        -d "{\"message\":$(python3 -c 'import json,sys; print(json.dumps(sys.argv[1]))' "$message")}"
    if [ "$HTTP_STATUS" != "202" ]; then
        echo "  POST /runs returned HTTP $HTTP_STATUS, expected 202" >&2
        return 0
    fi
    jget runId <"$HTTP_BODY_FILE"
}

# Polls GET /runs/{id} until the state leaves the set of states given as arguments,
# or the budget runs out. Sets RUN_STATE and RUN_BODY rather than printing them: a
# command substitution would run this in a subshell and throw the body away, and the
# body is what the failure output needs.
poll_until_not() {
    local run_id="$1"
    shift
    local deadline=$(( $(date +%s) + RUN_TIMEOUT_SECONDS ))

    RUN_BODY=""
    RUN_STATE=""

    while [ "$(date +%s)" -lt "$deadline" ]; do
        http_request "$API_URL/runs/$run_id"
        if [ "$HTTP_STATUS" != "200" ]; then
            echo "  GET /runs/$run_id returned HTTP $HTTP_STATUS, retrying..." >&2
            sleep "$POLL_INTERVAL_SECONDS"
            continue
        fi
        RUN_BODY=$(cat "$HTTP_BODY_FILE")
        RUN_STATE=$(jget state <"$HTTP_BODY_FILE")
        if [ -z "$RUN_STATE" ]; then
            echo "  could not read run state from the last response, retrying..." >&2
            sleep "$POLL_INTERVAL_SECONDS"
            continue
        fi
        local still_waiting=0
        for waiting_state in "$@"; do
            if [ "$RUN_STATE" = "$waiting_state" ]; then
                still_waiting=1
            fi
        done
        if [ "$still_waiting" -eq 0 ]; then
            return 0
        fi
        sleep "$POLL_INTERVAL_SECONDS"
    done

    return 1
}

# --- Case 1: BK-1001, under the limit -------------------------------------
#
# The model reaches `rebook` in roughly eight runs of nine, so a single miss is the model
# wandering rather than the app breaking. One retry before this is called a failure.
run_under_limit_case() {
    local attempt="$1"
    local run_id
    run_id=$(start_run "My flight on booking BK-1001 to Berlin was cancelled. Please rebook me onto the cheapest alternative on the same date.")

    if [ -z "$run_id" ]; then
        echo "  could not start a run"
        return 1
    fi
    echo "  attempt $attempt, run $run_id"

    if ! poll_until_not "$run_id" running; then
        echo "  run did not reach a terminal state within ${RUN_TIMEOUT_SECONDS}s (last state: $RUN_STATE)"
        return 1
    fi

    if [ "$RUN_STATE" != "completed" ]; then
        echo "  expected completed, got $RUN_STATE"
        return 1
    fi
    if ! tool_was_called "$RUN_BODY" rebook; then
        echo "  the run completed without calling rebook"
        return 1
    fi
    # Asserted on the approval entries, not on pendingApproval: the server computes that
    # property as null for any state other than pending_approval, and the completed check
    # above has already run, so reading it here could not fail.
    local outcomes
    outcomes=$(approval_outcomes "$RUN_BODY")
    if [ -z "$outcomes" ]; then
        echo "  the gate recorded no approval entry; an under-limit rebook should leave one"
        return 1
    fi
    if echo "$outcomes" | grep -vqx auto; then
        echo "  every approval entry should be auto, got: $(echo "$outcomes" | tr '\n' ' ')"
        return 1
    fi
    local outcome
    outcome=$(echo "$RUN_BODY" | jget outcome)
    if [ "$outcome" != "auto" ]; then
        echo "  expected outcome auto, got '$outcome'"
        return 1
    fi
    return 0
}

echo "--- Case 1: BK-1001, under the limit, auto-approved ---"
wait_for_services

CASE1_START=$(date +%s)
if run_under_limit_case 1; then
    pass "BK-1001 completed with a rebook call and no approval"
elif run_under_limit_case 2; then
    pass "BK-1001 completed with a rebook call and no approval (second attempt)"
else
    fail "BK-1001 did not complete with a rebook call in two attempts"
    print_tool_log "$RUN_BODY"
fi
echo "  case 1 wall clock: $(( $(date +%s) - CASE1_START ))s"
echo ""

# --- Case 2: BK-1002, over the limit, human approves ----------------------
echo "--- Case 2: BK-1002, over the limit, approved by a human ---"

CASE2_START=$(date +%s)
RUN_ID=$(start_run "My flight on booking BK-1002 to New York was cancelled. Please rebook me onto the cheapest alternative on the same date.")

if [ -z "$RUN_ID" ]; then
    fail "BK-1002 run did not start"
else
    echo "  run $RUN_ID"
    poll_until_not "$RUN_ID" running || true

    if [ "$RUN_STATE" != "pending_approval" ]; then
        fail "BK-1002 should park on pending_approval, got '$RUN_STATE'"
        print_tool_log "$RUN_BODY"
    else
        pass "BK-1002 parked on pending_approval after $(( $(date +%s) - CASE2_START ))s"

        http_request "$API_URL/approvals"
        if [ "$HTTP_STATUS" != "200" ]; then
            fail "GET /approvals returned HTTP $HTTP_STATUS, expected 200"
        fi
        APPROVALS=$(cat "$HTTP_BODY_FILE")
        APPROVAL_ID=$(echo "$APPROVALS" | python3 -c '
import json, sys
for approval in json.load(sys.stdin):
    if approval["runId"] == sys.argv[1]:
        print(approval["approvalId"])
        break
' "$RUN_ID" 2>/dev/null || echo "")

        OVER_LIMIT=$(echo "$APPROVALS" | python3 -c '
import json, sys
for approval in json.load(sys.stdin):
    if approval["runId"] == sys.argv[1]:
        amount, limit = approval.get("amount"), approval.get("limit")
        print("yes" if amount is not None and limit is not None and amount > limit else "no")
        break
' "$RUN_ID" 2>/dev/null || echo "no")

        if [ -z "$APPROVAL_ID" ]; then
            fail "the pending approval for $RUN_ID is not in GET /approvals"
            print_tool_log "$RUN_BODY"
        else
            pass "the approval is listed in GET /approvals"

            if [ "$OVER_LIMIT" = "yes" ]; then
                pass "the listed approval carries an amount over the limit"
            else
                fail "the listed approval does not carry an amount over the limit"
                echo "$APPROVALS" | head -1
            fi

            http_request -X POST "$API_URL/approvals/$APPROVAL_ID" \
                -H "Content-Type: application/json" -d '{"approved":true}'
            if [ "$HTTP_STATUS" != "200" ]; then
                fail "POST /approvals/$APPROVAL_ID returned HTTP $HTTP_STATUS, expected 200"
            fi
            ANSWER=$(cat "$HTTP_BODY_FILE")
            ANSWER_OUTCOME=$(jget outcome <"$HTTP_BODY_FILE")

            if [ "$ANSWER_OUTCOME" = "approved" ]; then
                pass "POST /approvals/$APPROVAL_ID recorded the approval"
            else
                fail "approving returned outcome '$ANSWER_OUTCOME'"
                echo "$ANSWER" | head -1
            fi

            poll_until_not "$RUN_ID" running pending_approval || true

            RUN_OUTCOME=$(echo "$RUN_BODY" | jget outcome)
            if [ "$RUN_STATE" = "completed" ] && [ "$RUN_OUTCOME" = "approved" ] && tool_was_called "$RUN_BODY" rebook; then
                pass "BK-1002 completed after the approval with a rebook call and outcome=approved"
            else
                fail "BK-1002 did not complete as approved with a rebook call (state: $RUN_STATE, outcome: $RUN_OUTCOME)"
                print_tool_log "$RUN_BODY"
            fi
        fi
    fi
fi
echo "  case 2 wall clock: $(( $(date +%s) - CASE2_START ))s"
echo ""

# --- Section 3: the error matrix ------------------------------------------
#
# One case per row. Each is a named function that returns 0 when the row behaved as
# the matrix says it should, and prints why when it did not. The telemetry side of
# each row is asserted by verify-scout.sh; what is checked here is what the API shows.

# Runs to a terminal or parked state and leaves the answer in RUN_STATE and RUN_BODY.
# Returns 1 when the run never left the states given, so a case can report a stall
# rather than asserting against an empty body.
drive() {
    local message="$1"
    shift
    local run_id
    run_id=$(start_run "$message")
    if [ -z "$run_id" ]; then
        echo "  could not start a run"
        return 1
    fi
    echo "  run $run_id"
    if ! poll_until_not "$run_id" "$@"; then
        echo "  run did not leave ${*} within ${RUN_TIMEOUT_SECONDS}s (last state: $RUN_STATE)"
        return 1
    fi
    LAST_RUN_ID="$run_id"
    return 0
}

LAST_RUN_ID=""

# Row 1. An unknown booking reference. The tool call fails and the agent recovers from
# it, so the run completes: the failure is visible on the tool spans, not on the run.
# rebook is never reached because there is no booking to rebook.
case_unknown_booking() {
    drive "My flight on booking BK-9999 to Berlin was cancelled. Please rebook me onto the cheapest alternative on the same date." running || return 1

    if [ "$RUN_STATE" != "completed" ]; then
        echo "  expected completed, got $RUN_STATE"
        return 1
    fi
    if ! tool_was_called "$RUN_BODY" lookup_booking; then
        echo "  the run never called lookup_booking, so nothing exercised the failure"
        return 1
    fi
    if tool_was_called "$RUN_BODY" rebook; then
        echo "  rebook was called for a booking reference that does not exist"
        return 1
    fi
    return 0
}

# Row 5. A human declining. Not an error: the run completes, outcome rejected, and the
# tool never runs. The absence of the execute_tool span is asserted in verify-scout.sh;
# what the API shows is the outcome on both the answer and the run.
case_approval_rejected() {
    drive "My flight on booking BK-1002 to New York was cancelled. Please rebook me onto the cheapest alternative on the same date." running || return 1

    if [ "$RUN_STATE" != "pending_approval" ]; then
        echo "  BK-1002 should park on pending_approval, got '$RUN_STATE'"
        return 1
    fi

    local approval_id
    approval_id=$(echo "$RUN_BODY" | python3 -c '
import json, sys
run = json.load(sys.stdin)
print((run.get("pendingApproval") or {}).get("approvalId", ""))
' 2>/dev/null || echo "")
    if [ -z "$approval_id" ]; then
        echo "  the parked run carries no pending approval id"
        return 1
    fi

    http_request -X POST "$API_URL/approvals/$approval_id" \
        -H "Content-Type: application/json" -d '{"approved":false}'
    if [ "$HTTP_STATUS" != "200" ]; then
        echo "  POST /approvals/$approval_id returned HTTP $HTTP_STATUS, expected 200"
        return 1
    fi
    if [ "$(jget outcome <"$HTTP_BODY_FILE")" != "rejected" ]; then
        echo "  rejecting did not return outcome rejected"
        return 1
    fi
    if [ "$(jget runFailed <"$HTTP_BODY_FILE")" != "False" ]; then
        echo "  rejecting reported runFailed true; declining is not a failure"
        return 1
    fi

    poll_until_not "$LAST_RUN_ID" running pending_approval || true
    if [ "$RUN_STATE" != "completed" ] || [ "$(echo "$RUN_BODY" | jget outcome)" != "rejected" ]; then
        echo "  expected completed with outcome rejected, got $RUN_STATE / $(echo "$RUN_BODY" | jget outcome)"
        return 1
    fi
    return 0
}

# Row 6. Nobody answers. The sweep expires the request, which the workflow cannot tell
# apart from a rejection, so the run completes with outcome expired. Also not an error.
case_approval_expired() {
    restart_app "$APP_OLLAMA_BASE_URL" "$APP_RUN_TIMEOUT_SECONDS" 10
    drive "My flight on booking BK-1002 to New York was cancelled. Please rebook me onto the cheapest alternative on the same date." running pending_approval || return 1

    if [ "$RUN_STATE" != "completed" ]; then
        echo "  expected completed, got $RUN_STATE"
        return 1
    fi
    if [ "$(echo "$RUN_BODY" | jget outcome)" != "expired" ]; then
        echo "  expected outcome expired, got '$(echo "$RUN_BODY" | jget outcome)'"
        return 1
    fi

    local entry_outcome
    entry_outcome=$(echo "$RUN_BODY" | python3 -c '
import json, sys
run = json.load(sys.stdin)
approvals = run.get("approvals") or []
print(approvals[-1]["outcome"] if approvals else "")
' 2>/dev/null || echo "")
    if [ "$entry_outcome" != "expired" ]; then
        echo "  the approval entry says '$entry_outcome', not expired"
        return 1
    fi
    return 0
}

# Row 1 of the error half. The run outlives its budget and the sweep fails it. This is
# the one case where the app itself sets error status, on base14.agent.run.
case_run_timeout() {
    restart_app "$APP_OLLAMA_BASE_URL" 5 "$APP_APPROVAL_TIMEOUT_SECONDS"
    drive "My flight on booking BK-1001 to Berlin was cancelled. Please rebook me onto the cheapest alternative on the same date." running || return 1

    if [ "$RUN_STATE" != "failed" ]; then
        echo "  expected failed, got $RUN_STATE"
        return 1
    fi
    local error
    error=$(echo "$RUN_BODY" | jget error)
    if [ "$error" != "the run exceeded RUN_TIMEOUT_SECONDS" ]; then
        echo "  expected the run timeout message, got '$error'"
        return 1
    fi
    return 0
}

# Row 3. The model is gone. Pointed at a port nothing listens on rather than stopping
# Ollama, which runs on the host and belongs to whoever is at the keyboard.
case_model_unreachable() {
    restart_app "http://host.docker.internal:11435" "$APP_RUN_TIMEOUT_SECONDS" "$APP_APPROVAL_TIMEOUT_SECONDS"
    drive "My flight on booking BK-1001 to Berlin was cancelled. Please rebook me onto the cheapest alternative on the same date." running || return 1

    if [ "$RUN_STATE" != "failed" ]; then
        echo "  expected failed, got $RUN_STATE"
        return 1
    fi
    case "$(echo "$RUN_BODY" | jget error)" in
        *"executor 'triage_triage' failed"*) return 0 ;;
        *) echo "  the run failed for some reason other than the executor: $(echo "$RUN_BODY" | jget error | head -c 120)"
           return 1 ;;
    esac
}

# Row 4. The database is gone. Every tool reads from it, so the tool calls fail, but
# the agent recovers the same way it does from an unknown booking and the run still
# completes. No approval is ever asked for, because nothing could be priced.
case_database_unreachable() {
    restart_app "$APP_OLLAMA_BASE_URL" "$APP_RUN_TIMEOUT_SECONDS" "$APP_APPROVAL_TIMEOUT_SECONDS"
    docker compose stop postgres >/dev/null 2>&1

    local result=0
    if drive "My flight on booking BK-1001 to Berlin was cancelled. Please rebook me onto the cheapest alternative on the same date." running; then
        if ! tool_was_called "$RUN_BODY" lookup_booking; then
            echo "  the run never called lookup_booking, so nothing reached the database"
            result=1
        elif [ -n "$(echo "$RUN_BODY" | jget outcome)" ]; then
            echo "  an approval was decided with no database to price against"
            result=1
        fi
    else
        result=1
    fi

    docker compose start postgres >/dev/null 2>&1
    echo "  waiting for postgres to come back..."
    local retries=30
    while [ $retries -gt 0 ]; do
        if docker compose exec -T postgres pg_isready -U postgres -d agentrebooking >/dev/null 2>&1; then
            return $result
        fi
        retries=$((retries - 1))
        sleep 2
    done
    echo "  postgres did not become ready again"
    return 1
}

run_case() {
    local label="$1" fn="$2"
    local started
    started=$(date +%s)
    echo "--- $label ---"
    if "$fn"; then
        pass "$label"
    else
        fail "$label"
        print_tool_log "$RUN_BODY"
    fi
    echo "  wall clock: $(( $(date +%s) - started ))s"
    echo ""
}

echo "--- Section 3: the error matrix ---"
if [ "${SKIP_FAILURE_CASES:-}" = "1" ]; then
    echo "  SKIP: SKIP_FAILURE_CASES=1. Sections 1 and 2 above still ran."
    echo ""
elif ! app_is_composed; then
    echo "  SKIP: docker compose has no running app service, so the six failure cases"
    echo "        cannot change the stack under it. Sections 1 and 2 above still ran."
    echo ""
elif ! capture_stack; then
    echo "  SKIP: could not read OLLAMA_BASE_URL, RUN_TIMEOUT_SECONDS and"
    echo "        APPROVAL_TIMEOUT_SECONDS from the app container, so there is nothing"
    echo "        safe to restore to afterwards."
    echo ""
else
    echo "  The app is restarted four times and postgres is stopped once. Everything is"
    echo "  put back at the end, and from an interrupt as well. Budget about five minutes."
    echo ""
    run_case "Case 3: BK-9999, unknown booking, the tool fails and the run recovers" case_unknown_booking
    run_case "Case 4: BK-1002, a human declines" case_approval_rejected
    run_case "Case 5: BK-1002, nobody answers and the approval expires" case_approval_expired
    run_case "Case 6: BK-1001 with a five second run budget" case_run_timeout
    run_case "Case 7: BK-1001 with the model unreachable" case_model_unreachable
    run_case "Case 8: BK-1001 with the database stopped" case_database_unreachable
    restore_stack
    echo ""
fi

TOTAL=$((PASSED + FAILED))
echo "=== Results ==="
echo "Passed: $PASSED / $TOTAL"
echo "Failed: $FAILED / $TOTAL"

if [ "$FAILED" -gt 0 ]; then
    echo ""
    echo "SOME CHECKS FAILED"
    exit 1
fi

echo ""
echo "ALL CHECKS PASSED"
