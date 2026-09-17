#!/bin/bash

# Shebang matches the other test-api.sh scripts in this repo. verify-scout.sh uses
# #!/usr/bin/env bash instead, matching the other verify-scout.sh scripts.

# ---------------------------------------------------------------------------
# test-api.sh - end-to-end API check for the learning path planner.
#
# Three sections against a live stack with Ollama on the host.
#
# Section 1, the four endpoints:
#   GET  /health         the liveness answer.
#   GET  /corpus/stats   the indexed corpus the plans are built from.
#   POST /plans          an in-range topic, which streams NDJSON and ends planned.
#   GET  /plans/{id}     the same run read back.
#
# Section 2, the 422 and 404 paths:
#   POST /plans          a topic the corpus has no coverage of. 422, and it still
#                        streams both lines, ending declined with one gap.
#   GET  /plans/{id}     an id that was never issued. 404.
#   POST /plans          three malformed bodies. 400, and no stream at all.
#
# Section 3, one deliberate failure: the app restarted against a port nothing
# listens on, so the model call fails after the stream has opened. The HTTP status
# is already on the wire by then, so the only signal left is the terminal NDJSON
# line, and that is what is asserted. The restart is undone by restore_app, which
# runs from an EXIT trap as well as at the end of the section, so an interrupted
# run does not leave the app pointing at a dead port. Ollama itself is never
# touched: it runs on the host, not in Compose, and stopping it would break the
# machine for whoever runs this next.
#
# Section 3 needs a stack this script can restart, which means either a Compose app
# service or a host process started from dist/. Without one the section is skipped
# rather than failed, so API_URL pointed at a deployment somewhere else still gets
# sections 1 and 2.
#
# POST /plans streams newline-delimited JSON. The first line is
# {"event":"accepted",...} and the last is either {"event":"plan",...} or
# {"event":"error",...}. Every assertion below keys on "event" and never on the
# presence of a field: a run that fails mid-stream still carries an id, but which
# fields a line has is exactly what changes between the two terminal shapes.
#
# Assertions are on status codes, the event names and the plan's structure, never
# on the plan's wording: the model writes that and it changes between runs.
#
# Measured on an M-series Mac, 12 cores, qwen3.5:9b on host Ollama, 2026-09-17: one
# in-range plan takes 90 to 95 seconds. The declined and malformed paths never reach
# the model and answer immediately. Budget more on a slower machine.
#
# Usage:
#   ./scripts/test-api.sh
#   API_URL=http://localhost:3000 ./scripts/test-api.sh
#   SKIP_FAILURE_CASE=1 ./scripts/test-api.sh   # sections 1 and 2 only
# ---------------------------------------------------------------------------

set -eu

# docker compose and dist/ both need the directory holding compose.yaml, so this
# works the same whether it is called as ./scripts/test-api.sh or from inside
# scripts/.
cd "$(dirname "$0")/.."

# shellcheck source=scripts/app-control.sh
. "$(dirname "$0")/app-control.sh"

API_URL=${API_URL:-http://localhost:3000}

# This script's own budget for one POST /plans, not a setting of the app's. A plan
# that reaches the model takes about 95 seconds; a stalled Ollama can take much
# longer, and waiting is better than reporting a failure the stack did not have.
PLAN_TIMEOUT_SECONDS=${PLAN_TIMEOUT_SECONDS:-600}

IN_RANGE_TOPIC=${IN_RANGE_TOPIC:-"OpenTelemetry tracing for Node.js services"}
# Every token of this has to be absent from every title, keyword, description and
# heading in the corpus, or the run plans instead of declining. Checked against the
# committed artifact, not guessed.
OUT_OF_RANGE_TOPIC=${OUT_OF_RANGE_TOPIC:-"medieval falconry"}

PASSED=0
FAILED=0

# Set by http_request: the response body goes to a file rather than a variable, so a
# body containing a literal newline - which every NDJSON response does - cannot be
# confused with the status code curl reports alongside it.
HTTP_STATUS=""
HTTP_BODY_FILE=$(mktemp /tmp/learning-path-planner-http-XXXXXX.json)
HTTP_HEADER_FILE=$(mktemp /tmp/learning-path-planner-hdr-XXXXXX.txt)

APP_RESTARTED=0

cleanup() {
    rm -f "$HTTP_BODY_FILE" "$HTTP_HEADER_FILE"
    if [ "$APP_RESTARTED" = "1" ]; then
        echo ""
        echo "Restoring the app..."
        if ! restore_app; then
            echo "THE APP WAS NOT RESTORED. It may still be pointing at a dead Ollama port."
            echo "Put it back with 'make docker-up', or 'make start' for a host run."
        fi
    fi
}
trap cleanup EXIT

app_control_init

echo "=== ai-learning-path-planner API test ==="
echo "Target: $API_URL"
echo "Plan budget: ${PLAN_TIMEOUT_SECONDS}s per run"
echo "App control: $(app_mode)"
echo ""

pass() {
    echo "[PASS] $1"
    PASSED=$((PASSED + 1))
}

fail() {
    echo "[FAIL] $1"
    FAILED=$((FAILED + 1))
}

check_status() {
    local label="$1" want="$2"
    if [ "$HTTP_STATUS" = "$want" ]; then
        pass "$label"
    else
        fail "$label - expected HTTP $want, got $HTTP_STATUS"
        head -c 300 "$HTTP_BODY_FILE"
        echo ""
    fi
}

# curl writes 000 into %{http_code} itself when it cannot reach the host, so an
# `|| echo 000` on the end of this appends a second one and reports 000000.
http_request() {
    HTTP_STATUS=$(curl -s -o "$HTTP_BODY_FILE" -D "$HTTP_HEADER_FILE" -w "%{http_code}" \
        --max-time "$PLAN_TIMEOUT_SECONDS" "$@" 2>/dev/null)
    HTTP_STATUS=${HTTP_STATUS:-000}
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

# Reads one value out of the NDJSON line at the given index: 0 is the first line,
# -1 the last. Keyed on position rather than on a field, so the terminal line is
# found the same way whether it is a plan or an error.
ndget() {
    local index="$1"
    shift
    python3 -c '
import json, sys
lines = [l for l in sys.stdin.read().splitlines() if l.strip()]
index = int(sys.argv[1])
try:
    doc = json.loads(lines[index])
except (IndexError, ValueError):
    print("")
    sys.exit()
for key in sys.argv[2:]:
    if doc is None:
        break
    doc = doc.get(key) if isinstance(doc, dict) else None
print("" if doc is None else doc)
' "$index" "$@" 2>/dev/null || echo ""
}

ndlines() {
    python3 -c '
import sys
print(len([l for l in sys.stdin.read().splitlines() if l.strip()]))
' 2>/dev/null || echo 0
}

# Number of gaps on the plan carried by the NDJSON line at the given index. Prints
# an empty string when that line has no plan, so a caller can tell "no gaps" from
# "no plan".
ndgapcount() {
    local index="$1"
    python3 -c '
import json, sys
lines = [l for l in sys.stdin.read().splitlines() if l.strip()]
try:
    doc = json.loads(lines[int(sys.argv[1])])
except (IndexError, ValueError):
    print("")
    sys.exit()
plan = doc.get("plan")
print("" if not isinstance(plan, dict) else len(plan.get("gaps") or []))
' "$index" 2>/dev/null || echo ""
}

post_plan() {
    local topic="$1"
    http_request -X POST "$API_URL/plans" \
        -H 'content-type: application/json' \
        -d "$(python3 -c 'import json,sys; print(json.dumps({"topic": sys.argv[1]}))' "$topic")"
}

wait_for_app() {
    echo "Waiting for the app to become healthy..."
    if app_wait_healthy; then
        echo "App ready."
        echo ""
        return 0
    fi
    echo "ERROR: $API_URL/health did not answer within 120 seconds."
    echo "Start the stack with 'make docker-up', or 'make start' for a host run."
    exit 1
}

# --- Section 1: the four endpoints ----------------------------------------
echo "--- Section 1: the four endpoints ---"
wait_for_app

http_request "$API_URL/health"
check_status "GET /health" "200"
if [ "$(jget status <"$HTTP_BODY_FILE")" = "ok" ]; then
    pass "GET /health reports status ok"
else
    fail "GET /health did not report status ok, got: $(head -c 120 "$HTTP_BODY_FILE")"
fi

http_request "$API_URL/corpus/stats"
check_status "GET /corpus/stats" "200"
CORPUS_DOCUMENTS=$(jget documents <"$HTTP_BODY_FILE")
if [ -n "$CORPUS_DOCUMENTS" ] && [ "$CORPUS_DOCUMENTS" -gt 0 ] 2>/dev/null; then
    pass "GET /corpus/stats reports $CORPUS_DOCUMENTS indexed documents"
else
    fail "GET /corpus/stats reports no indexed documents; the artifact is empty or missing"
    head -c 300 "$HTTP_BODY_FILE"
    echo ""
fi

echo "  planning '$IN_RANGE_TOPIC', about 95s..."
PLAN_START=$(date +%s)
post_plan "$IN_RANGE_TOPIC"
echo "  wall clock: $(( $(date +%s) - PLAN_START ))s"
check_status "POST /plans with an in-range topic" "200"

if grep -qi '^content-type:[[:space:]]*application/x-ndjson' "$HTTP_HEADER_FILE"; then
    pass "POST /plans answers application/x-ndjson"
else
    fail "POST /plans did not answer application/x-ndjson, got: $(grep -i '^content-type:' "$HTTP_HEADER_FILE" | tr -d '\r')"
fi

PLAN_LINES=$(ndlines <"$HTTP_BODY_FILE")
PLAN_ID=$(ndget 0 id <"$HTTP_BODY_FILE")
if [ "$(ndget 0 event <"$HTTP_BODY_FILE")" = "accepted" ] \
    && [ "$(ndget 0 topic <"$HTTP_BODY_FILE")" = "$IN_RANGE_TOPIC" ] \
    && [ -n "$PLAN_ID" ]; then
    pass "the first line is event=accepted, echoing the topic and an id"
else
    fail "the first line is not an accepted event for this topic: $(head -1 "$HTTP_BODY_FILE" | head -c 200)"
fi

PLAN_EVENT=$(ndget -1 event <"$HTTP_BODY_FILE")
PLAN_STATUS=$(ndget -1 status <"$HTTP_BODY_FILE")
if [ "$PLAN_LINES" = "2" ] && [ "$PLAN_EVENT" = "plan" ] && [ "$PLAN_STATUS" = "planned" ]; then
    pass "the run streams two lines and ends event=plan status=planned"
else
    fail "the run ended with $PLAN_LINES line(s), event '$PLAN_EVENT', status '$PLAN_STATUS'"
    tail -1 "$HTTP_BODY_FILE" | head -c 300
    echo ""
fi

if [ -z "$PLAN_ID" ]; then
    fail "GET /plans/{id} - the accepted line carried no id to read back"
else
    http_request "$API_URL/plans/$PLAN_ID"
    check_status "GET /plans/$PLAN_ID" "200"
    READ_BACK=$(jget status <"$HTTP_BODY_FILE")
    READ_BACK_TOPIC=$(jget plan topic <"$HTTP_BODY_FILE")
    if [ "$READ_BACK" = "$PLAN_STATUS" ] && [ "$READ_BACK_TOPIC" = "$IN_RANGE_TOPIC" ]; then
        pass "GET /plans/{id} returns the same status the stream ended on, for the same topic"
    else
        fail "GET /plans/{id} reports status '$READ_BACK' topic '$READ_BACK_TOPIC', the stream said '$PLAN_STATUS' / '$IN_RANGE_TOPIC'"
    fi
fi
echo ""

# --- Section 2: the 422 and 404 paths -------------------------------------
echo "--- Section 2: the 422 and 404 paths ---"

post_plan "$OUT_OF_RANGE_TOPIC"
check_status "POST /plans with a topic the corpus does not cover" "422"

DECLINED_ID=$(ndget 0 id <"$HTTP_BODY_FILE")
DECLINED_LINES=$(ndlines <"$HTTP_BODY_FILE")
DECLINED_STATUS=$(ndget -1 status <"$HTTP_BODY_FILE")
if [ "$DECLINED_LINES" = "2" ] && [ "$DECLINED_STATUS" = "declined" ]; then
    pass "a 422 still streams both lines, ending status=declined"
else
    fail "the declined run streamed $DECLINED_LINES line(s) ending status '$DECLINED_STATUS'"
    head -c 300 "$HTTP_BODY_FILE"
    echo ""
fi

DECLINED_GAPS=$(ndgapcount -1 <"$HTTP_BODY_FILE")
if [ "$DECLINED_GAPS" = "1" ]; then
    pass "the declined plan records one gap"
else
    fail "the declined plan records ${DECLINED_GAPS:-no} gap(s); a decline should record exactly one"
fi

if [ -z "$DECLINED_ID" ]; then
    fail "GET /plans/{id} for the declined run - no id was issued"
else
    http_request "$API_URL/plans/$DECLINED_ID"
    check_status "GET /plans/$DECLINED_ID" "200"
    if [ "$(jget status <"$HTTP_BODY_FILE")" = "declined" ]; then
        pass "GET /plans/{id} reports the declined run as declined"
    else
        fail "GET /plans/{id} does not report the declined run as declined: $(head -c 200 "$HTTP_BODY_FILE")"
    fi
fi

http_request "$API_URL/plans/00000000-0000-0000-0000-000000000000"
check_status "GET /plans/{id} for an id that was never issued" "404"

http_request -X POST "$API_URL/plans" -H 'content-type: application/json' -d 'not json at all'
check_status "POST /plans with a body that is not JSON" "400"
if [ "$(ndlines <"$HTTP_BODY_FILE")" = "1" ] && [ -z "$(ndget 0 event <"$HTTP_BODY_FILE")" ]; then
    pass "the 400 answers a JSON error object, not a stream"
else
    fail "the 400 answered something with an event field; a malformed body should not open a stream"
fi

http_request -X POST "$API_URL/plans" -H 'content-type: application/json' -d '{}'
check_status "POST /plans with no topic" "400"

http_request -X POST "$API_URL/plans" -H 'content-type: application/json' -d '{"topic":123}'
check_status "POST /plans with a topic that is not a string" "400"

http_request -X POST "$API_URL/plans" -H 'content-type: application/json' -d '{"topic":"   "}'
check_status "POST /plans with a blank topic" "400"
echo ""

# --- Section 3: the model unreachable --------------------------------------
#
# Pointed at a port nothing listens on rather than stopping Ollama, which runs on
# the host and belongs to whoever is at the keyboard.
echo "--- Section 3: the model unreachable ---"
if [ "${SKIP_FAILURE_CASE:-}" = "1" ]; then
    echo "  SKIP: SKIP_FAILURE_CASE=1. Sections 1 and 2 above still ran."
elif ! app_can_restart; then
    echo "  SKIP: this script cannot restart the app - docker compose has no app service"
    echo "        and there is no dist/ to launch - so there is nothing safe to change"
    echo "        and put back. Sections 1 and 2 above still ran."
else
    APP_RESTARTED=1
    if ! restart_app "OLLAMA_BASE_URL=http://localhost:11435/api"; then
        fail "the app did not come back up pointing at the dead port"
    else
        post_plan "$IN_RANGE_TOPIC"
        # 200, not 5xx. The status is decided and sent before the stream opens, so a
        # failure after that point cannot change it. This is the assertion that says
        # the terminal line is the only signal a client has left.
        check_status "POST /plans still answers 200 when the model is unreachable" "200"
        if [ "$(ndget -1 event <"$HTTP_BODY_FILE")" = "error" ]; then
            pass "the run ends event=error rather than stopping silently"
        else
            fail "the run ended event '$(ndget -1 event <"$HTTP_BODY_FILE")', expected error"
            tail -1 "$HTTP_BODY_FILE" | head -c 300
            echo ""
        fi
    fi

    echo ""
    echo "Restoring the app..."
    if restore_app; then
        APP_RESTARTED=0
        # Read back out of the running app, not out of what this script asked for.
        # restore_app reporting success is the app answering about itself; this is not.
        RESTORED=$(app_setting OLLAMA_BASE_URL)
        if [ "$RESTORED" = "$(app_baseline_setting OLLAMA_BASE_URL)" ]; then
            pass "the app is back on the OLLAMA_BASE_URL it started with"
        else
            fail "the app came back on OLLAMA_BASE_URL '$RESTORED'"
        fi
    else
        fail "the app did not come back up"
    fi
fi
echo ""

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
