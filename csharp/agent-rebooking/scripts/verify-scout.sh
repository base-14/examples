#!/usr/bin/env bash

# ---------------------------------------------------------------------------
# verify-scout.sh - telemetry verification for the approval-gated rebooking agent.
#
# Drives one approval run with a trace id the script chooses itself, then checks that
# the expected spans and metrics arrived. There are two sources of truth and the
# script uses both:
#
#   Local    the collector's `debug` exporter, on all three pipelines at detailed
#            verbosity. It shows what the app produced. Always checked.
#   Scout    the hosted backend, checked by hand from a printed checklist when
#            SCOUT_CLIENT_ID, SCOUT_CLIENT_SECRET and SCOUT_TOKEN_URL are all set. The
#            scout CLI is not installed or built by this script; the checklist prints
#            the command for a reader who has it.
#
# With those three unset the Scout section is skipped and the script still passes. A
# missing credential is not a build failure.
#
# The span and metric names asserted below were read out of a real collector log on
# 2026-09-16, not copied from the design. Three of them are the traps this example
# exists to show:
#   - there is no `execute_tool handoff_to_1` span, because the injected handoff tool
#     is a declaration with no body, so nothing ever invokes it.
#   - `tools/call` appears once per call, as a server span. The MCP client attributes
#     land on the outer `execute_tool` span instead of a second client span.
#   - the post-approval pass parents to `base14.agent.run`, not to `base14.agent.resume`,
#     which is empty on a single-approval run.
#
# The collector log is cumulative since the container started, so every check below
# reads it through `docker compose logs --since <timestamp>`, scoped to the moment
# this run started. Without that, a check that greps the whole log would keep passing
# off an earlier run's spans even after the thing it is checking for was removed.
#
# Sections 2b and 3b are the error matrix: six deliberate failures driven inside the
# same window as the approval run, each checked on the span that actually carries the
# failure. Three of them restart the app service with one environment variable changed
# and one stops the postgres container; everything is put back by restore_stack, which
# runs from the EXIT trap as well. Ollama is never stopped: it runs on the host, and the
# model-unreachable row points the app at a port nothing listens on instead.
#
# Takes about eight minutes end to end: roughly five for the six failure scenarios and
# their app restarts, 30s for the span batch, then up to METRIC_WAIT_SECONDS (100s by
# default) for the .NET metric export period.
#
# Usage:
#   ./scripts/verify-scout.sh
#   SKIP_REQUESTS=1 ./scripts/verify-scout.sh   # re-check the log without a new run
# ---------------------------------------------------------------------------

set -uo pipefail

# `docker compose logs` needs the directory that holds compose.yaml, so the script
# works the same whether it is called as ./scripts/verify-scout.sh or from inside
# scripts/.
cd "$(dirname "$0")/.." || exit 1

API_URL="${API_URL:-http://localhost:8080}"
COLLECTOR_HEALTH="${COLLECTOR_HEALTH_URL:-http://localhost:13133}"
COMPOSE_SERVICE="${COLLECTOR_SERVICE:-otel-collector}"

# The .NET metric reader exports on its default 60s period, so the approval histogram
# point lands up to a minute after the decision. Measured, not guessed.
METRIC_WAIT_SECONDS="${METRIC_WAIT_SECONDS:-100}"
SPAN_WAIT_SECONDS="${SPAN_WAIT_SECONDS:-30}"

# Paid before every app restart in section 2b. The SDK's batch processors hold spans and
# log records for their scheduled delay, and restarting the container inside that window
# loses whatever has not gone out yet. Measured: a run-timeout scenario whose app was
# restarted two seconds later kept its span and lost its ERROR log record entirely.
EXPORT_SETTLE_SECONDS="${EXPORT_SETTLE_SECONDS:-10}"

# Persists the "since" timestamp across invocations, so `SKIP_REQUESTS=1` re-checks
# the same window a prior run of this script drove rather than the full cumulative
# log. Not cleaned up on exit: it is meant to outlive one invocation.
SINCE_FILE="/tmp/agent-rebooking-verify-since.txt"

# The trace ids sections 2 and 2b chose, for the same reason: SKIP_REQUESTS=1 re-checks
# the run and the six rows the last real invocation drove rather than losing them.
TRACE_FILE="/tmp/agent-rebooking-verify-traces.env"

PASS=0
FAIL=0
WARN=0

green()  { printf "\033[32m%s\033[0m" "$1"; }
red()    { printf "\033[31m%s\033[0m" "$1"; }
cyan()   { printf "\033[36m%s\033[0m" "$1"; }
yellow() { printf "\033[33m%s\033[0m" "$1"; }
dim()    { printf "\033[90m%s\033[0m" "$1"; }

heading() { printf '%s\n' "$(cyan "$1")"; }

ok()      { echo "  $(green "PASS") $1"; PASS=$((PASS + 1)); }
bad()     { echo "  $(red "FAIL") $1"; FAIL=$((FAIL + 1)); }
warn()    { echo "  $(yellow "WARN") $1"; WARN=$((WARN + 1)); }
skipped() { echo "  $(dim "SKIP") $1"; }

SPANS_FILE=""
SPANTREE_FILE=""
STATUSES_FILE=""
LOGS_FILE=""

# Set by capture_stack once section 2b has read the app's live settings; until then
# restore_stack does nothing. The trap is what keeps an interrupted run from leaving the
# app pointing at a dead port or the database stopped.
STACK_CAPTURED=0
APP_OLLAMA_BASE_URL=""
APP_RUN_TIMEOUT_SECONDS=""
APP_APPROVAL_TIMEOUT_SECONDS=""

cleanup() {
    if ! restore_stack; then
        echo ""
        echo "  THE STACK WAS NOT RESTORED. The app may still be pointing at a dead Ollama"
        echo "  port or running on a shortened timeout. Put it back with:"
        echo "      docker compose start postgres"
        echo "      docker compose up -d app"
    fi
    rm -f "$SPANS_FILE" "$STATUSES_FILE" "$SPANTREE_FILE" "$LOGS_FILE"
}
trap cleanup EXIT

# --- stack control for the error-matrix section ----------------------------
#
# Three of the six rows need one environment variable changed on the app, and one needs
# the database stopped. Ollama is never touched: it runs on the host, not in Compose,
# and a script that stops it has broken the machine for whoever runs it next. The dead
# port below is the substitute.

app_is_composed() {
    docker compose ps --status running --services 2>/dev/null | grep -qx app
}

# Read from the running container rather than assumed from compose.yaml, so a reader
# running with their own settings gets their own settings back.
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

# Every variable passed explicitly, so this does not depend on what happens to be
# exported in the caller's shell.
restart_app() {
    local ollama="$1" run_timeout="$2" approval_timeout="$3"
    env OLLAMA_BASE_URL="$ollama" \
        RUN_TIMEOUT_SECONDS="$run_timeout" \
        APPROVAL_TIMEOUT_SECONDS="$approval_timeout" \
        docker compose up -d app >/dev/null 2>&1
    for _ in $(seq 1 40); do
        if curl -sf "$API_URL/health" >/dev/null 2>&1; then
            return 0
        fi
        sleep 3
    done
    return 1
}

# Returns non-zero when the app did not come back. STACK_CAPTURED is cleared only after
# the restart has reported healthy, so an interrupt partway through, including one during
# restart_app's two minute health poll, leaves the flag set and the EXIT trap tries again
# rather than treating the work as already done. The caller decides what to say about a
# failure: the normal path reads the settings back and fails the check, the trap prints
# the commands to run by hand.
restore_stack() {
    if [ "$STACK_CAPTURED" != "1" ]; then
        return 0
    fi
    docker compose start postgres >/dev/null 2>&1 || true
    if ! restart_app "$APP_OLLAMA_BASE_URL" "$APP_RUN_TIMEOUT_SECONDS" "$APP_APPROVAL_TIMEOUT_SECONDS"; then
        return 1
    fi
    STACK_CAPTURED=0
    return 0
}

# Starts one run under a trace id the caller chose and polls until it leaves the states
# given. Prints the run id. Used by the error-matrix section; section 2 keeps its own
# inline version because it also has to answer an approval halfway through.
drive_run() {
    local trace="$1" message="$2"
    shift 2

    local run_id
    run_id=$(curl -s -X POST "$API_URL/runs" \
        -H 'content-type: application/json' \
        -H "traceparent: 00-$trace-$(python3 -c 'import secrets; print(secrets.token_hex(8))')-01" \
        -d "$(python3 -c 'import json,sys; print(json.dumps({"message": sys.argv[1]}))' "$message")" \
        | python3 -c 'import json,sys; print(json.load(sys.stdin).get("runId",""))' 2>/dev/null)

    if [ -z "$run_id" ]; then
        echo ""
        return 1
    fi

    local state
    for _ in $(seq 1 150); do
        state=$(curl -s "$API_URL/runs/$run_id" \
            | python3 -c 'import json,sys; print(json.load(sys.stdin).get("state",""))' 2>/dev/null)
        local waiting=0
        for want in "$@"; do
            [ "$state" = "$want" ] && waiting=1
        done
        [ "$waiting" -eq 0 ] && break
        sleep 2
    done

    echo "$run_id"
}

# Pulls (trace id, kind, name) out of the collector's detailed debug output. The
# leading-arrow form of "Trace ID" inside a SpanLink block does not match, which is
# what keeps links from being counted as spans.
read_spans() {
    awk '
/^Span #/ { inspan = 1; tid = ""; name = ""; next }
inspan && /^[[:space:]]*Trace ID[[:space:]]*:/ { tid = $NF; next }
inspan && /^[[:space:]]*Name[[:space:]]*:/ {
    sub(/^[[:space:]]*Name[[:space:]]*:[[:space:]]*/, ""); name = $0; next
}
inspan && /^[[:space:]]*Kind[[:space:]]*:/ {
    if (name != "" && tid != "") print tid "\t" $NF "\t" name
    inspan = 0
    next
}
' "$1"
}

# Pulls (trace id, span id, parent id, name) out of the same debug output, so a check can
# say something about a span's parent rather than only about its presence. A root span
# prints an empty Parent ID.
read_span_tree() {
    awk '
/^Span #/ { inspan = 1; tid = ""; pid = ""; sid = ""; name = ""; seenparent = 0; next }
inspan && /^[[:space:]]*Trace ID[[:space:]]*:/ { tid = $NF; next }
inspan && /^[[:space:]]*Parent ID[[:space:]]*:/ {
    sub(/^[[:space:]]*Parent ID[[:space:]]*:[[:space:]]*/, ""); pid = $0; seenparent = 1; next
}
inspan && seenparent && /^[[:space:]]*ID[[:space:]]*:/ { sid = $NF; next }
inspan && /^[[:space:]]*Name[[:space:]]*:/ {
    sub(/^[[:space:]]*Name[[:space:]]*:[[:space:]]*/, ""); name = $0; next
}
inspan && /^[[:space:]]*Kind[[:space:]]*:/ {
    if (name != "" && tid != "" && sid != "") print tid "\t" sid "\t" pid "\t" name
    inspan = 0
    next
}
' "$1"
}

# Pulls (trace id, name, status code) out of the same debug output. Separate from
# read_spans because the status block sits below the Kind line that read_spans stops on,
# and widening that parser would change what every existing check reads.
read_span_statuses() {
    awk '
/^Span #/ { inspan = 1; tid = ""; name = ""; next }
inspan && /^[[:space:]]*Trace ID[[:space:]]*:/ { tid = $NF; next }
inspan && /^[[:space:]]*Name[[:space:]]*:/ {
    sub(/^[[:space:]]*Name[[:space:]]*:[[:space:]]*/, ""); name = $0; next
}
inspan && /^[[:space:]]*Status code[[:space:]]*:/ {
    sub(/^[[:space:]]*Status code[[:space:]]*:[[:space:]]*/, ""); code = $0; next
}
inspan && code != "" && /^[[:space:]]*Status message[[:space:]]*:/ {
    sub(/^[[:space:]]*Status message[[:space:]]*:[[:space:]]*/, "")
    if (name != "" && tid != "") print tid "\t" code "\t" name "\t" $0
    inspan = 0; code = ""
    next
}
' "$1"
}

# True when the collector's approval-decided span, wherever it is, carries a
# SpanLink pointing at the given trace id. Parses one span block at a time so the
# link found has to sit on that span, not just appear somewhere in the log.
decided_span_links_to() {
    awk -v want="$1" '
function flush() {
    if (name == "base14.approval.decided rebook" && linktrace == want) found = 1
    name = ""; linktrace = ""; capturing = 0
}
/^Span #/       { if (inspan) flush(); inspan = 1; next }
/^ScopeSpans/   { if (inspan) flush(); inspan = 0; next }
/^ResourceSpans/{ if (inspan) flush(); inspan = 0; next }
inspan && /^[[:space:]]*Name[[:space:]]*:/ {
    sub(/^[[:space:]]*Name[[:space:]]*:[[:space:]]*/, ""); name = $0; next
}
inspan && /^SpanLink #/ { capturing = 1; next }
inspan && capturing && /^[[:space:]]*->[[:space:]]*Trace ID[[:space:]]*:/ {
    sub(/^[[:space:]]*->[[:space:]]*Trace ID[[:space:]]*:[[:space:]]*/, "")
    if ($0 == want) linktrace = want
    capturing = 0
    next
}
END { if (inspan) flush(); exit found ? 0 : 1 }
' "$2"
}

# Asserts that a data point of one named metric carries one attribute. The collector
# prints span attributes and metric data point attributes in the same "key: Str(value)"
# form, so a plain grep for an outcome tag matches the decided span and proves nothing
# about the metric. This walks the metric block and only credits a tag it finds under
# "Data point attributes" of the metric asked for.
metric_point_tagged() {
    local label="$1" metric="$2" attribute="$3"
    if awk -v m="$metric" -v a="$attribute" '
/^Metric #/     { name = ""; indesc = 0; indp = 0; next }
/^Descriptor:/  { indesc = 1; next }
indesc && /^[[:space:]]*->[[:space:]]*Name[[:space:]]*:/ {
    sub(/^[[:space:]]*->[[:space:]]*Name[[:space:]]*:[[:space:]]*/, ""); name = $0; indesc = 0; next
}
/Data point attributes:/ { indp = 1; next }
indp && /^[[:space:]]*-> / { if (name == m && index($0, a) > 0) found = 1; next }
indp { indp = 0 }
END { exit found ? 0 : 1 }
' "$LOGS_FILE"; then
        ok "$label"
    else
        bad "$label - no data point on $metric tagged $attribute"
    fi
}

# Asserts a span name inside one trace id. Prefix match, so `chat ` covers any model.
span_in_trace() {
    local label="$1" trace="$2" prefix="$3"
    if awk -F'\t' -v t="$trace" -v p="$prefix" \
        '$1 == t && index($3, p) == 1 { found = 1 } END { exit found ? 0 : 1 }' "$SPANS_FILE"; then
        ok "$label"
    else
        bad "$label - no span starting '$prefix' on trace $trace"
    fi
}

span_absent_in_trace() {
    local label="$1" trace="$2" prefix="$3"
    if awk -F'\t' -v t="$trace" -v p="$prefix" \
        '$1 == t && index($3, p) == 1 { found = 1 } END { exit found ? 0 : 1 }' "$SPANS_FILE"; then
        bad "$label - a span starting '$prefix' is present and should not be"
    else
        ok "$label"
    fi
}

span_anywhere() {
    local label="$1" kind="$2" prefix="$3"
    if awk -F'\t' -v k="$kind" -v p="$prefix" \
        '$2 == k && index($3, p) == 1 { found = 1 } END { exit found ? 0 : 1 }' "$SPANS_FILE"; then
        ok "$label"
    else
        bad "$label - no $kind span starting '$prefix'"
    fi
}

# Asserts that some span named by the child prefix has a parent named by the parent
# prefix, inside one trace. Resolves the parent id against the same trace's spans, so a
# same-named span elsewhere in the window cannot satisfy it.
span_parent_in_trace() {
    local label="$1" trace="$2" child="$3" parent="$4"
    if awk -F'\t' -v t="$trace" -v c="$child" -v par="$parent" '
$1 == t { name[$2] = $4; parent_of[$2] = $3; ids[++n] = $2 }
END {
    for (i = 1; i <= n; i++) {
        id = ids[i]
        if (index(name[id], c) != 1) continue
        pid = parent_of[id]
        if (pid != "" && index(name[pid], par) == 1) { found = 1; break }
    }
    exit found ? 0 : 1
}' "$SPANTREE_FILE"; then
        ok "$label"
    else
        bad "$label - no span starting '$child' in trace $trace has a parent starting '$parent'"
    fi
}

# Asserts one span's status inside one trace. Reads $STATUSES_FILE, which is built from
# the same window-scoped log as $SPANS_FILE, so a check here cannot be satisfied by an
# earlier run's span any more than the checks above can.
#
# When several spans in the trace share the prefix, every distinct status they carry is
# collected rather than the first one in log order. Two spans with the same prefix and
# different statuses therefore produce something like "Error,Unset", which matches no
# expected value and fails with both printed. Taking the first match would have resolved
# that case by whichever span the collector happened to flush first.
span_status_in_trace() {
    local label="$1" trace="$2" prefix="$3" want="$4"
    local got
    got=$(awk -F'\t' -v t="$trace" -v p="$prefix" \
        '$1 == t && index($3, p) == 1 { seen[$2] = 1 }
         END { out = ""; for (s in seen) { out = (out == "" ? s : out "," s) } print out }' \
        "$STATUSES_FILE")
    if [ -z "$got" ]; then
        bad "$label - no span starting '$prefix' on trace $trace"
    elif [ "$got" = "$want" ]; then
        ok "$label"
    elif [ "$got" != "${got%,*}" ]; then
        bad "$label - several spans starting '$prefix' on trace $trace, carrying $got between them; expected one status, $want"
    else
        bad "$label - span '$prefix' on trace $trace is $got, expected $want"
    fi
}

# Asserts that nothing in one trace is in error. The point of the rows where a tool
# fails and the agent recovers: the failure is on the tool spans and must not spread to
# the run. Fails loudly when the trace has no spans at all, so a mistyped trace id reads
# as a failure rather than as a clean bill of health.
no_error_span_in_trace() {
    local label="$1" trace="$2"
    local total errors
    total=$(awk -F'\t' -v t="$trace" '$1 == t { n++ } END { print n + 0 }' "$STATUSES_FILE")
    errors=$(awk -F'\t' -v t="$trace" '$1 == t && $2 == "Error" { print $3 }' "$STATUSES_FILE" | sort -u | tr '\n' ' ')
    if [ "$total" -eq 0 ]; then
        bad "$label - no spans at all on trace $trace"
    elif [ -z "$errors" ]; then
        ok "$label"
    else
        bad "$label - these spans on trace $trace are in error: $errors"
    fi
}

# Asserts the status message on one span. Only the first line of it: the agent
# framework puts a whole stack trace in there when an executor fails, and a multi-line
# status message is itself worth knowing about, which is why the matrix says so.
#
# Counts the matching spans rather than taking the first in log order. A prefix that
# matches two spans would otherwise resolve arbitrarily and pass or fail by luck. The
# sibling helper compares a set of statuses instead, which will not work here: a status
# message can contain any punctuation, so there is no separator to join them on.
span_status_message_in_trace() {
    local label="$1" trace="$2" prefix="$3" want="$4"
    local matches got
    matches=$(awk -F'\t' -v t="$trace" -v p="$prefix" \
        '$1 == t && index($3, p) == 1 { n++ } END { print n + 0 }' "$STATUSES_FILE")
    if [ "$matches" -gt 1 ]; then
        bad "$label - $matches spans on this trace start '$prefix', so the status message is ambiguous"
        return
    fi
    got=$(awk -F'\t' -v t="$trace" -v p="$prefix" \
        '$1 == t && index($3, p) == 1 { print $4 }' "$STATUSES_FILE")
    if [ "$got" = "$want" ]; then
        ok "$label"
    else
        bad "$label - the status message on '$prefix' is '${got:-(none)}', expected '$want'"
    fi
}

# Asserts one attribute sits on a span with the given name. Walks a span block at a
# time, so an attribute that appears elsewhere in the window - on another span, or as a
# metric data point tag, which the collector prints in the same key: Str(value) form -
# does not satisfy it.
span_attribute_anywhere() {
    local label="$1" prefix="$2" attribute="$3"
    if awk -v p="$prefix" -v a="$attribute" '
function flush() { name = ""; inattrs = 0 }
/^Span #/        { inspan = 1; flush(); next }
/^Resource(Spans|Metrics|Logs)/ { inspan = 0; flush(); next }
/^Scope(Spans|Metrics|Logs)/    { inspan = 0; flush(); next }
inspan && /^[[:space:]]*Name[[:space:]]*:/ {
    sub(/^[[:space:]]*Name[[:space:]]*:[[:space:]]*/, ""); name = $0; next
}
inspan && /^[[:space:]]*Attributes:/ { inattrs = 1; next }
inspan && inattrs && /^[[:space:]]*-> / {
    if (index(name, p) == 1 && index($0, a) > 0) found = 1
    next
}
inspan && inattrs { inattrs = 0 }
END { exit found ? 0 : 1 }
' "$LOGS_FILE"; then
        ok "$label"
    else
        bad "$label - no span starting '$prefix' carries $attribute"
    fi
}

# The database-unreachable row lands on whichever Npgsql span the failure reached, and
# which one that is depends on the pool. With a connection already open when the database
# goes away, the command span `postgresql` carries it, as 57P01. With the pool empty, which
# is the normal case when the script stops postgres before driving the run, there is no
# command span at all and the error lands on `CONNECT {database}`. Both are measured and
# both are in the README. Naming one span made this row fail on the arm it did not name, so
# the assertion is on the layer: there must be at least one Npgsql span on the trace, and
# every one of them must be Error.
npgsql_error_in_trace() {
    local label="$1" trace="$2"
    local got
    got=$(awk -F'\t' -v t="$trace" \
        '$1 == t && ($3 == "postgresql" || index($3, "CONNECT ") == 1) { seen[$2] = 1 }
         END { out = ""; for (s in seen) { out = (out == "" ? s : out "," s) } print out }' \
        "$STATUSES_FILE")
    if [ -z "$got" ]; then
        bad "$label - no Npgsql span, postgresql or CONNECT, on trace $trace"
    elif [ "$got" = "Error" ]; then
        ok "$label"
    else
        bad "$label - the Npgsql spans on trace $trace carry $got between them, expected Error"
    fi
}

# Asserts an ERROR-severity log record whose body contains the text. Walks the record
# so the severity and the body have to belong together; a grep for the text alone would
# also match the same words sitting in a span's status message.
log_record_at_error() {
    local label="$1" needle="$2"
    if awk -v n="$needle" '
/^SeverityText:/ { severity = $2; next }
/^Body:/ { if (severity == "ERROR" && index($0, n) > 0) found = 1; severity = ""; next }
END { exit found ? 0 : 1 }
' "$LOGS_FILE"; then
        ok "$label"
    else
        bad "$label - no ERROR log record containing: $needle"
    fi
}

log_has() {
    local label="$1" pattern="$2"
    if grep -qF -- "$pattern" "$LOGS_FILE"; then
        ok "$label"
    else
        bad "$label - not found: $pattern"
    fi
}

log_warn_if_missing() {
    local label="$1" pattern="$2"
    if grep -qF -- "$pattern" "$LOGS_FILE"; then
        ok "$label"
    else
        warn "$label - not found: $pattern"
    fi
}

# Fetches the collector log into $LOGS_FILE, scoped to $SINCE_TS when one is set.
# Every check below reads through this file, so scoping it here is what keeps a
# check from passing off a previous run's spans or metrics.
fetch_logs() {
    if [ -n "${SINCE_TS:-}" ]; then
        docker compose logs "$COMPOSE_SERVICE" --no-log-prefix --since "$SINCE_TS" >"$LOGS_FILE" 2>/dev/null
    else
        docker compose logs "$COMPOSE_SERVICE" --no-log-prefix >"$LOGS_FILE" 2>/dev/null
    fi
}

heading "============================================="
heading "  Telemetry verification - agent-rebooking"
heading "============================================="

# --- 1. Prerequisites ------------------------------------------------------
echo ""
heading "=== 1. Prerequisites ==="
echo ""

APP_STATUS=$(curl -s -o /dev/null -w "%{http_code}" "$API_URL/health" 2>/dev/null || echo "000")
if [ "$APP_STATUS" = "200" ]; then
    ok "app is healthy ($API_URL/health)"
else
    bad "app is not healthy ($API_URL/health returned $APP_STATUS)"
    echo ""
    echo "  Start the stack with 'make up', then run this again."
    exit 1
fi

COLLECTOR_STATUS=$(curl -s -o /dev/null -w "%{http_code}" "$COLLECTOR_HEALTH" 2>/dev/null || echo "000")
if [ "$COLLECTOR_STATUS" = "200" ]; then
    ok "collector is healthy ($COLLECTOR_HEALTH)"
else
    bad "collector is not healthy ($COLLECTOR_HEALTH returned $COLLECTOR_STATUS)"
    echo ""
    echo "  The collector exits at startup when SCOUT_CLIENT_ID is empty: its oauth2client"
    echo "  extension requires a client id even when nothing is being exported. Check with"
    echo "  'docker compose logs otel-collector'. Without the collector there is no debug"
    echo "  output to verify against."
    exit 1
fi

# --- 2. Drive one approval run --------------------------------------------
#
# BK-1002 is the over-limit booking: every alternative is above APPROVAL_LIMIT, so the
# run always parks on an approval and always produces the approval span pair and a
# point on the wait histogram. The traceparent is generated here so the checks below
# can name one exact trace id instead of guessing which trace was the run.
TRACE_ID=""
SINCE_TS=""

if [ "${SKIP_REQUESTS:-}" != "1" ]; then
    echo ""
    heading "=== 2. Driving one approval run (BK-1002) ==="
    echo ""

    # Captured before anything is driven, so `--since` below excludes every span and
    # metric this script did not just produce. The trailing Z matters: without an
    # explicit UTC marker, `docker compose logs --since` reads the timestamp in the
    # daemon's local zone, which silently widens or narrows the window on any host
    # that is not already on UTC.
    SINCE_TS=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
    echo "$SINCE_TS" >"$SINCE_FILE"

    TRACE_ID=$(python3 -c 'import secrets; print(secrets.token_hex(16))')
    PARENT_SPAN_ID=$(python3 -c 'import secrets; print(secrets.token_hex(8))')
    echo "  $(dim "trace id: $TRACE_ID")"

    RUN_ID=$(curl -s -X POST "$API_URL/runs" \
        -H 'content-type: application/json' \
        -H "traceparent: 00-$TRACE_ID-$PARENT_SPAN_ID-01" \
        -d '{"message":"My flight on booking BK-1002 to New York was cancelled. Please rebook me onto the cheapest alternative on the same date."}' \
        | python3 -c 'import json,sys; print(json.load(sys.stdin).get("runId",""))' 2>/dev/null)

    if [ -z "$RUN_ID" ]; then
        bad "could not start a run"
        exit 1
    fi
    echo "  $(dim "run id: $RUN_ID")"

    echo "  $(dim "waiting for the run to park on an approval...")"
    APPROVAL_ID=""
    for _ in $(seq 1 150); do
        STATE=$(curl -s "$API_URL/runs/$RUN_ID" \
            | python3 -c 'import json,sys; print(json.load(sys.stdin).get("state",""))' 2>/dev/null)
        if [ "$STATE" = "pending_approval" ]; then
            APPROVAL_ID=$(curl -s "$API_URL/runs/$RUN_ID" | python3 -c '
import json, sys
run = json.load(sys.stdin)
pending = run.get("pendingApproval") or {}
print(pending.get("approvalId", ""))
' 2>/dev/null)
            break
        fi
        if [ "$STATE" != "running" ]; then
            break
        fi
        sleep 2
    done

    if [ -z "$APPROVAL_ID" ]; then
        bad "the run never parked on an approval (last state: ${STATE:-unknown})"
        exit 1
    fi
    ok "run parked on approval $APPROVAL_ID"

    curl -s -X POST "$API_URL/approvals/$APPROVAL_ID" \
        -H 'content-type: application/json' -d '{"approved":true}' >/dev/null
    ok "approval answered"

    echo "  $(dim "waiting for the run to finish...")"
    for _ in $(seq 1 150); do
        STATE=$(curl -s "$API_URL/runs/$RUN_ID" \
            | python3 -c 'import json,sys; print(json.load(sys.stdin).get("state",""))' 2>/dev/null)
        case "$STATE" in
            running|pending_approval) sleep 2 ;;
            *) break ;;
        esac
    done
    ok "run reached state $STATE"

    # --- 2b. Drive the six failure scenarios ------------------------------
    #
    # All six inside the same window as the approval run above, so one log read covers
    # everything and the waits are paid once rather than six times.
    echo ""
    heading "=== 2b. Driving the six failure scenarios ==="
    echo ""

    if ! app_is_composed; then
        skipped "docker compose has no running app service, so the failure scenarios cannot be driven"
    elif ! capture_stack; then
        skipped "could not read the app's OLLAMA_BASE_URL, RUN_TIMEOUT_SECONDS and APPROVAL_TIMEOUT_SECONDS, so there is nothing safe to restore to"
    else
        echo "  $(dim "the app is restarted three times and postgres is stopped once, then the app is")"
        echo "  $(dim "restarted once more to put it back. That happens from an interrupt as well.")"
        echo "  $(dim "About five minutes.")"
        echo ""

        ERR_TRACE_UNKNOWN=$(python3 -c 'import secrets; print(secrets.token_hex(16))')
        ERR_TRACE_REJECTED=$(python3 -c 'import secrets; print(secrets.token_hex(16))')
        ERR_TRACE_DB=$(python3 -c 'import secrets; print(secrets.token_hex(16))')
        ERR_TRACE_TIMEOUT=$(python3 -c 'import secrets; print(secrets.token_hex(16))')
        ERR_TRACE_MODEL=$(python3 -c 'import secrets; print(secrets.token_hex(16))')
        ERR_TRACE_EXPIRED=$(python3 -c 'import secrets; print(secrets.token_hex(16))')

        echo "  $(dim "BK-9999, a booking reference that does not exist...")"
        drive_run "$ERR_TRACE_UNKNOWN" \
            "My flight on booking BK-9999 to Berlin was cancelled. Please rebook me onto the cheapest alternative on the same date." \
            running >/dev/null

        echo "  $(dim "BK-1002 declined by a human...")"
        REJECTED_RUN=$(drive_run "$ERR_TRACE_REJECTED" \
            "My flight on booking BK-1002 to New York was cancelled. Please rebook me onto the cheapest alternative on the same date." \
            running)
        REJECTED_APPROVAL=$(curl -s "$API_URL/runs/$REJECTED_RUN" | python3 -c '
import json, sys
run = json.load(sys.stdin)
print((run.get("pendingApproval") or {}).get("approvalId", ""))
' 2>/dev/null)
        if [ -n "$REJECTED_APPROVAL" ]; then
            curl -s -X POST "$API_URL/approvals/$REJECTED_APPROVAL" \
                -H 'content-type: application/json' -d '{"approved":false}' >/dev/null
            for _ in $(seq 1 150); do
                STATE=$(curl -s "$API_URL/runs/$REJECTED_RUN" \
                    | python3 -c 'import json,sys; print(json.load(sys.stdin).get("state",""))' 2>/dev/null)
                case "$STATE" in running|pending_approval) sleep 2 ;; *) break ;; esac
            done
        else
            warn "the rejected-approval run never parked, so its row below will fail"
        fi

        echo "  $(dim "the database stopped...")"
        docker compose stop postgres >/dev/null 2>&1
        drive_run "$ERR_TRACE_DB" \
            "My flight on booking BK-1001 to Berlin was cancelled. Please rebook me onto the cheapest alternative on the same date." \
            running >/dev/null
        docker compose start postgres >/dev/null 2>&1
        for _ in $(seq 1 30); do
            docker compose exec -T postgres pg_isready -U postgres -d agentrebooking >/dev/null 2>&1 && break
            sleep 2
        done

        echo "  $(dim "a five second run budget...")"
        sleep "$EXPORT_SETTLE_SECONDS"
        restart_app "$APP_OLLAMA_BASE_URL" 5 "$APP_APPROVAL_TIMEOUT_SECONDS"
        drive_run "$ERR_TRACE_TIMEOUT" \
            "My flight on booking BK-1001 to Berlin was cancelled. Please rebook me onto the cheapest alternative on the same date." \
            running >/dev/null

        echo "  $(dim "an approval nobody answers...")"
        sleep "$EXPORT_SETTLE_SECONDS"
        restart_app "$APP_OLLAMA_BASE_URL" "$APP_RUN_TIMEOUT_SECONDS" 10
        drive_run "$ERR_TRACE_EXPIRED" \
            "My flight on booking BK-1002 to New York was cancelled. Please rebook me onto the cheapest alternative on the same date." \
            running pending_approval >/dev/null

        # Last, and then waited on. base14.gen_ai.error.count is a cumulative counter
        # held in the app's own meter, so restarting the app before the metric reader's
        # 60s period elapses throws the only measurement of it away and the check in
        # section 4 fails for a reason that has nothing to do with the code.
        echo "  $(dim "the model unreachable, on a port nothing listens on...")"
        sleep "$EXPORT_SETTLE_SECONDS"
        restart_app "http://host.docker.internal:11435" "$APP_RUN_TIMEOUT_SECONDS" "$APP_APPROVAL_TIMEOUT_SECONDS"
        drive_run "$ERR_TRACE_MODEL" \
            "My flight on booking BK-1001 to Berlin was cancelled. Please rebook me onto the cheapest alternative on the same date." \
            running >/dev/null

        echo "  $(dim "waiting for the failed provider call to reach the metric export period...")"
        DEADLINE=$(( $(date +%s) + METRIC_WAIT_SECONDS ))
        while [ "$(date +%s)" -lt "$DEADLINE" ]; do
            if docker compose logs "$COMPOSE_SERVICE" --no-log-prefix --since "$SINCE_TS" 2>/dev/null \
                | grep -qF "base14.gen_ai.error.count"; then
                break
            fi
            sleep 5
        done

        sleep "$EXPORT_SETTLE_SECONDS"
        restore_stack

        # Read back rather than assumed. restore_stack does return non-zero on a failed
        # restart now, but its own report is the app answering about itself; reading the
        # three settings out of the container is independent of it. Leaving the app on a
        # dead port is the worst thing this section could do to the machine.
        RESTORED=$(docker compose exec -T app printenv OLLAMA_BASE_URL 2>/dev/null || echo "")
        RESTORED_RUN=$(docker compose exec -T app printenv RUN_TIMEOUT_SECONDS 2>/dev/null || echo "")
        RESTORED_APPROVAL=$(docker compose exec -T app printenv APPROVAL_TIMEOUT_SECONDS 2>/dev/null || echo "")
        if [ "$RESTORED" = "$APP_OLLAMA_BASE_URL" ] \
            && [ "$RESTORED_RUN" = "$APP_RUN_TIMEOUT_SECONDS" ] \
            && [ "$RESTORED_APPROVAL" = "$APP_APPROVAL_TIMEOUT_SECONDS" ]; then
            ok "the stack is back on the settings it started with"
        else
            bad "the stack did not come back: OLLAMA_BASE_URL is '$RESTORED', RUN_TIMEOUT_SECONDS is '$RESTORED_RUN', APPROVAL_TIMEOUT_SECONDS is '$RESTORED_APPROVAL'"
        fi

        # The happy-path trace from section 2 goes in as well, so SKIP_REQUESTS=1 can
        # re-check its two trace-scoped span checks instead of failing them against a
        # freshly generated id that was never driven.
        cat >"$TRACE_FILE" <<TRACES
TRACE_ID=$TRACE_ID
ERR_TRACE_UNKNOWN=$ERR_TRACE_UNKNOWN
ERR_TRACE_REJECTED=$ERR_TRACE_REJECTED
ERR_TRACE_DB=$ERR_TRACE_DB
ERR_TRACE_TIMEOUT=$ERR_TRACE_TIMEOUT
ERR_TRACE_MODEL=$ERR_TRACE_MODEL
ERR_TRACE_EXPIRED=$ERR_TRACE_EXPIRED
TRACES
    fi

    echo "  $(dim "waiting ${SPAN_WAIT_SECONDS}s for the span batch to reach the collector...")"
    sleep "$SPAN_WAIT_SECONDS"
else
    if [ -f "$SINCE_FILE" ]; then
        SINCE_TS=$(cat "$SINCE_FILE")
        echo "  $(dim "SKIP_REQUESTS=1: re-checking the log since $SINCE_TS (from the last driven run)")"
        if [ -f "$TRACE_FILE" ]; then
            # shellcheck disable=SC1090
            . "$TRACE_FILE"
        fi
    else
        echo "  $(dim "SKIP_REQUESTS=1 with no timestamp from a prior run: checking the full collector log")"
    fi
fi

# --- 3. Local verification against the collector debug exporter ------------
echo ""
heading "=== 3. Collector debug output ==="
echo ""

LOGS_FILE=$(mktemp /tmp/agent-rebooking-otel-XXXXXX.txt)
SPANS_FILE=$(mktemp /tmp/agent-rebooking-spans-XXXXXX.tsv)
fetch_logs

if [ ! -s "$LOGS_FILE" ]; then
    bad "could not read collector logs since $SINCE_TS - run this from csharp/agent-rebooking"
    exit 1
fi

read_spans "$LOGS_FILE" >"$SPANS_FILE"

STATUSES_FILE=$(mktemp /tmp/agent-rebooking-statuses-XXXXXX.tsv)
read_span_statuses "$LOGS_FILE" >"$STATUSES_FILE"

SPANTREE_FILE=$(mktemp /tmp/agent-rebooking-spantree-XXXXXX.tsv)
read_span_tree "$LOGS_FILE" >"$SPANTREE_FILE"

# Without a run of our own, fall back to the most recent trace that has a resume span.
# Only an approval run produces one, so it identifies the right trace unambiguously.
if [ -z "$TRACE_ID" ]; then
    TRACE_ID=$(awk -F'\t' '$3 == "base14.agent.resume" { print $1 }' "$SPANS_FILE" | tail -1)
    if [ -z "$TRACE_ID" ]; then
        bad "no trace with a base14.agent.resume span in the collector log since $SINCE_TS"
        exit 1
    fi
    echo "  $(dim "using the most recent approval trace: $TRACE_ID")"
fi

echo "  $(dim "--- the run trace, all on $TRACE_ID ---")"
# POST /runs is not asserted as the trace root: this script sets its own traceparent on
# the request, so the server span has a remote parent that is never exported. What the
# example actually claims is the shape below it, and that is asserted.
span_in_trace "POST /runs, the run's server span"             "$TRACE_ID" "POST /runs"
span_parent_in_trace "base14.agent.run sits under POST /runs" "$TRACE_ID" "base14.agent.run" "POST /runs"
span_in_trace "base14.agent.run"                              "$TRACE_ID" "base14.agent.run"
span_in_trace "base14.agent.resume"                           "$TRACE_ID" "base14.agent.resume"
span_in_trace "invoke_agent triage(triage)"                   "$TRACE_ID" "invoke_agent triage(triage)"
span_in_trace "invoke_agent rebooking(rebooking)"             "$TRACE_ID" "invoke_agent rebooking(rebooking)"
span_in_trace "chat {model}"                                  "$TRACE_ID" "chat "
span_in_trace "execute_tool lookup_booking"                   "$TRACE_ID" "execute_tool lookup_booking"
span_in_trace "tools/call lookup_booking (MCP server span)"   "$TRACE_ID" "tools/call lookup_booking"
span_in_trace "execute_tool rebook"                           "$TRACE_ID" "execute_tool rebook"
span_in_trace "tools/call rebook (MCP server span)"           "$TRACE_ID" "tools/call rebook"
span_in_trace "base14.approval.requested rebook"              "$TRACE_ID" "base14.approval.requested rebook"
span_parent_in_trace "postgresql (Npgsql, under the tool spans)" "$TRACE_ID" "postgresql" "tools/call"

echo "  $(dim "--- the traps, asserted as absences ---")"
span_absent_in_trace "no execute_tool span for the handoff tool" "$TRACE_ID" "execute_tool handoff_to_"
if awk -F'\t' -v t="$TRACE_ID" \
    '$1 == t && $2 == "Client" && index($3, "tools/call") == 1 { found = 1 } END { exit found ? 0 : 1 }' \
    "$SPANS_FILE"; then
    bad "a client-side tools/call span appeared; the mcp.* attributes should land on execute_tool instead"
else
    ok "no client-side tools/call span; the mcp.* attributes land on execute_tool"
fi

log_has "the handoff tool is visible in gen_ai.tool.definitions" "handoff_to_1"

echo "  $(dim "--- content capture, off by default ---")"
if grep -qF "was cancelled. Please rebook me" "$LOGS_FILE"; then
    bad "the traveller's message is in the span data; OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT should be false by default"
else
    ok "no message content in the spans; set OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT=true to capture it"
fi

echo "  $(dim "--- the approval decision, in the approver's trace ---")"
span_anywhere "POST /approvals/{approvalId}"          "Server"   "POST /approvals/"
span_anywhere "base14.approval.decided rebook"        "Internal" "base14.approval.decided rebook"
if decided_span_links_to "$TRACE_ID" "$LOGS_FILE"; then
    ok "the decided span carries a link back to trace $TRACE_ID"
else
    bad "the decided span has no SpanLink to trace $TRACE_ID; the run trace and the decision are not connected"
fi

# The MCP handshake happens once per app start, and section 2b restarts the app four
# times inside this window, so these four read the same window-scoped spans as every
# other check. They were once read from the full collector log, which meant they kept
# passing off a startup from hours earlier even with the source registration removed.
# If the window holds no app start, these fail, which is the honest answer.
echo "  $(dim "--- MCP startup trace, from the app restarts in this window ---")"
span_anywhere "server/discover (MCP client span)" "Client" "server/discover"
span_anywhere "server/discover (MCP server span)" "Server" "server/discover"
span_anywhere "tools/list (MCP client span)"      "Client" "tools/list"
span_anywhere "tools/list (MCP server span)"      "Server" "tools/list"

# Four of these are plain greps because the attribute appears on no metric data point,
# so nothing but a span can satisfy them. The other four do sit on metric data points,
# which the collector prints in the same key: Str(value) form, so they go through
# span_attribute_anywhere and have to be found inside a named span block.
echo "  $(dim "--- span attributes ---")"
span_attribute_anywhere "gen_ai.tool.name on the tool span" "execute_tool " "gen_ai.tool.name"
log_has "base14.run.id"              "base14.run.id"
span_attribute_anywhere "base14.approval.outcome on the decided span" \
    "base14.approval.decided " "base14.approval.outcome"
log_has "base14.approval.amount"     "base14.approval.amount"
log_has "base14.approval.limit"      "base14.approval.limit"
log_has "base14.approval.wait_seconds" "base14.approval.wait_seconds"
span_attribute_anywhere "mcp.method.name on the tool span" "execute_tool " "mcp.method.name"
span_attribute_anywhere "mcp.session.id on the tool span"  "execute_tool " "mcp.session.id"

# --- 3b. The error matrix --------------------------------------------------
#
# One block per row. The rows differ in which span carries the failure, and that is the
# whole point of them, so each block asserts the status on a named span rather than
# grepping for the word Error anywhere in the window.
echo ""
heading "=== 3b. The error matrix ==="
echo ""

if [ -z "${ERR_TRACE_UNKNOWN:-}" ]; then
    skipped "no failure scenarios were driven, so there is nothing to check here"
    echo ""
    echo "  $(dim "Run without SKIP_REQUESTS=1 to drive them.")"
else
    echo "  $(dim "--- row: unknown booking, a failed tool call inside a run that succeeds ---")"
    span_status_in_trace "tools/call lookup_booking is Error" \
        "$ERR_TRACE_UNKNOWN" "tools/call lookup_booking" "Error"
    span_status_in_trace "execute_tool lookup_booking is Error" \
        "$ERR_TRACE_UNKNOWN" "execute_tool lookup_booking" "Error"
    span_status_in_trace "base14.agent.run stays Unset; the agent read the error and answered" \
        "$ERR_TRACE_UNKNOWN" "base14.agent.run" "Unset"

    echo "  $(dim "--- row: approval rejected, the gate working rather than failing ---")"
    # The absence checks below only mean something once a rebook was actually asked for.
    # On a run where the model never proposed the tool they would both pass for the wrong
    # reason, so this positive check goes first.
    span_in_trace "a rebook was requested on this trace" \
        "$ERR_TRACE_REJECTED" "base14.approval.requested rebook"
    span_absent_in_trace "no execute_tool rebook span; the tool never ran" \
        "$ERR_TRACE_REJECTED" "execute_tool rebook"
    span_absent_in_trace "no tools/call rebook span either" \
        "$ERR_TRACE_REJECTED" "tools/call rebook"
    no_error_span_in_trace "nothing in the rejected run is in error" "$ERR_TRACE_REJECTED"

    echo "  $(dim "--- row: approval expired, the same shape with nobody answering ---")"
    span_in_trace "a rebook was requested on this trace too" \
        "$ERR_TRACE_EXPIRED" "base14.approval.requested rebook"
    span_absent_in_trace "no execute_tool rebook span on the expired run" \
        "$ERR_TRACE_EXPIRED" "execute_tool rebook"
    no_error_span_in_trace "nothing in the expired run is in error" "$ERR_TRACE_EXPIRED"
    span_attribute_anywhere "a base14.approval.decided span carries outcome expired" \
        "base14.approval.decided" "base14.approval.outcome: Str(expired)"

    echo "  $(dim "--- row: database unreachable ---")"
    npgsql_error_in_trace "the Npgsql span is Error" "$ERR_TRACE_DB"
    span_status_in_trace "execute_tool lookup_booking is Error" \
        "$ERR_TRACE_DB" "execute_tool lookup_booking" "Error"
    span_status_in_trace "base14.agent.run stays Unset here too" \
        "$ERR_TRACE_DB" "base14.agent.run" "Unset"

    echo "  $(dim "--- row: run timeout, the one failure the app itself records ---")"
    span_status_in_trace "base14.agent.run is Error" \
        "$ERR_TRACE_TIMEOUT" "base14.agent.run" "Error"
    span_status_message_in_trace "and carries the reason as its status message" \
        "$ERR_TRACE_TIMEOUT" "base14.agent.run" "the run exceeded RUN_TIMEOUT_SECONDS"
    log_record_at_error "an ERROR log record names the run and the reason" \
        "failed: the run exceeded RUN_TIMEOUT_SECONDS"

    echo "  $(dim "--- row: model unreachable ---")"
    span_status_in_trace "chat {model} is Error" \
        "$ERR_TRACE_MODEL" "chat " "Error"
    span_status_in_trace "invoke_agent triage(triage) is Error" \
        "$ERR_TRACE_MODEL" "invoke_agent triage(triage)" "Error"
    span_status_in_trace "base14.agent.run is Error" \
        "$ERR_TRACE_MODEL" "base14.agent.run" "Error"
fi

# --- 4. Metrics ------------------------------------------------------------
#
# The wait histogram is recorded when the decision is taken, but the .NET metric reader
# exports on a 60s period, so it shows up in the collector log up to a minute later.
echo ""
heading "=== 4. Metrics ==="
echo ""

if [ "${SKIP_REQUESTS:-}" != "1" ]; then
    echo "  $(dim "waiting up to ${METRIC_WAIT_SECONDS}s for the metric export period...")"
    DEADLINE=$(( $(date +%s) + METRIC_WAIT_SECONDS ))
    while [ "$(date +%s)" -lt "$DEADLINE" ]; do
        fetch_logs
        if grep -qF "base14.agent.approval.wait.duration" "$LOGS_FILE"; then
            break
        fi
        sleep 5
    done
fi

log_has "base14.agent.approval.wait.duration"  "Name: base14.agent.approval.wait.duration"
log_has "base14.agent.approval.count"          "Name: base14.agent.approval.count"
log_has "gen_ai.client.token.usage"            "Name: gen_ai.client.token.usage"
log_has "gen_ai.client.operation.duration"     "Name: gen_ai.client.operation.duration"
log_has "mcp.client.operation.duration"        "Name: mcp.client.operation.duration"
log_has "mcp.server.operation.duration"        "Name: mcp.server.operation.duration"
metric_point_tagged "a wait histogram point tagged outcome=approved" \
    "base14.agent.approval.wait.duration" "base14.approval.outcome: Str(approved)"

if [ -n "${ERR_TRACE_UNKNOWN:-}" ]; then
    # Keyed on error.type rather than on the provider name. HttpRequestException is what
    # the dead-port row produces and nothing else here does, so a regression that started
    # counting the run-timeout row's cancelled stream would not satisfy this. The provider
    # tag would have been satisfied by any counted error at all.
    metric_point_tagged "base14.gen_ai.error.count tagged error.type=HttpRequestException" \
        "base14.gen_ai.error.count" "error.type: Str(HttpRequestException)"
    metric_point_tagged "a wait histogram point tagged outcome=rejected" \
        "base14.agent.approval.wait.duration" "base14.approval.outcome: Str(rejected)"
    metric_point_tagged "a wait histogram point tagged outcome=expired" \
        "base14.agent.approval.wait.duration" "base14.approval.outcome: Str(expired)"
fi

# --- 5. Scout ---------------------------------------------------------------
echo ""
heading "=== 5. base14 Scout ==="
echo ""
# Scout is checked only when all three credentials are present. A reader without a
# Scout account gets everything above and a clean exit here: a missing credential is
# not a failure.
if [ -z "${SCOUT_CLIENT_ID:-}" ] || [ -z "${SCOUT_CLIENT_SECRET:-}" ] || [ -z "${SCOUT_TOKEN_URL:-}" ]; then
    skipped "Scout checks skipped: SCOUT_CLIENT_ID, SCOUT_CLIENT_SECRET and SCOUT_TOKEN_URL are not all set."
    echo ""
    echo "  $(dim "Everything above came from the collector's local debug exporter, so the")"
    echo "  $(dim "example is fully verifiable without a Scout account. To check the hosted")"
    echo "  $(dim "side as well, set those three plus SCOUT_ENDPOINT and run this again.")"
else
    # No automated query here: the scout CLI is not installed on any machine this
    # example is tested on, and is not to be installed or built by this script. An
    # automated branch would ship inside documentation having never run once, so this
    # is the manual checklist instead, the same shape the other verify-scout.sh
    # scripts in this repo use for their Scout section.
    SCOUT_SERVICE="${OTEL_SERVICE_NAME:-agent-rebooking}"
    skipped "SCOUT_* is set. The hosted side is a manual check from here; the checklist below covers it."
    echo ""
    echo "  $(dim "If the scout CLI is installed, this trace's own query is:")"
    echo ""
    echo "    scout traces $SCOUT_SERVICE --id $TRACE_ID --since 30m --raw"
    echo ""
    echo "  $(dim "--id drills into one trace. --since 30m is valid here even though the flag's")"
    echo "  $(dim "help says 15m, because querying by id raises the cap to 60 minutes. --raw prints")"
    echo "  $(dim "the trace as a JSON object with a trace_id field and a spans array.")"
    echo ""
    echo "  $(dim "In the Scout UI, or in that JSON, this run should show:")"
    echo "    [ ] base14.agent.run and base14.agent.resume as siblings on one trace rooted at POST /runs."
    echo "    [ ] the post-approval invoke_agent under base14.agent.run, not under base14.agent.resume."
    echo "    [ ] invoke_agent triage(triage) and invoke_agent rebooking(rebooking)."
    echo "    [ ] execute_tool rebook and tools/call rebook."
    echo "    [ ] base14.approval.requested rebook, and base14.run.id on the approval spans."
    echo "    [ ] base14.approval.decided in the POST /approvals trace, linked to the requested span."
    echo "    [ ] a point on base14.agent.approval.wait.duration tagged outcome=approved."
fi

# --- Summary ---------------------------------------------------------------
echo ""
heading "=== Summary ==="
echo ""
TOTAL=$((PASS + FAIL + WARN))
if [ "$FAIL" -eq 0 ] && [ "$WARN" -eq 0 ]; then
    echo "  $(green "all $TOTAL checks passed")"
elif [ "$FAIL" -eq 0 ]; then
    echo "  $(green "$PASS passed"), $(yellow "$WARN warnings")"
else
    echo "  $(green "$PASS passed"), $(red "$FAIL failed"), $(yellow "$WARN warnings")"
fi
echo ""

[ "$FAIL" -eq 0 ]
