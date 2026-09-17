#!/usr/bin/env bash

# ---------------------------------------------------------------------------
# verify-scout.sh - telemetry verification for the learning path planner.
#
# Drives two runs under trace ids the script chooses itself - one in-range topic
# that plans, one out-of-range topic that declines - then checks that the expected
# spans, attributes and metric points arrived. There are two sources of truth and
# the script uses both:
#
#   Local    the collector's `debug` exporter, on all three pipelines at detailed
#            verbosity. It shows what the app produced. Always checked.
#   Scout    the hosted backend, checked by hand from a printed checklist when
#            SCOUT_CLIENT_ID, SCOUT_CLIENT_SECRET and SCOUT_TOKEN_URL are all set.
#            The scout CLI is not installed or built by this script; the checklist
#            prints the command for a reader who has it.
#
# With those three unset the Scout section is skipped and the script still passes.
# A missing credential is not a build failure, and nothing above that section needs
# one: the whole verification runs against the local collector.
#
# The collector log is cumulative since the container started, so every check reads
# it through `docker compose logs --since <timestamp>`, scoped to the moment this
# run started. Without that, a check that greps the whole log keeps passing off an
# earlier run's spans even after the thing it is checking for was removed. The
# trailing Z on the timestamp matters too: without an explicit UTC marker,
# `docker compose logs --since` reads it in the daemon's local zone, which silently
# widens or narrows the window on any host that is not already on UTC.
#
# Span names come from a real collector log, not from the design. The AI SDK names its spans after the model, not the role: the lead's operation span
# is `invoke_agent qwen3.5:9B`, and a researcher's would be
# `invoke_agent gemma4:e2b`. The role is an attribute, base14.agent.role, so the role
# checks below read the attribute rather than the name. The HTTP server span is named
# `POST`, not `POST /plans`, because the http instrumentation has no route to work
# from; the path is on url.path.
#
# Takes about four minutes: two runs, then 30s for the span batch, then up to
# METRIC_WAIT_SECONDS for the metric reader's export period. Longer when the in-range
# run has to be driven again, which it is when the lead answers without calling a tool.
#
# Usage:
#   ./scripts/verify-scout.sh
#   SKIP_REQUESTS=1 ./scripts/verify-scout.sh        # re-check the last window
#   VERIFY_LOG_FILE=/tmp/captured.txt ./scripts/verify-scout.sh
#
# VERIFY_LOG_FILE reads a saved collector log instead of asking Compose for one. It
# implies SKIP_REQUESTS=1. It exists for the falsification pass: every check here
# reads that one file, so stripping a line out of a captured log and re-running is
# what proves a given check can go red. Trace ids and plan ids for a saved log come
# from TRACE_FILE, which a real run writes.
# ---------------------------------------------------------------------------

set -uo pipefail

# `docker compose logs` and dist/ both need the directory that holds compose.yaml,
# so this works the same whether it is called as ./scripts/verify-scout.sh or from
# inside scripts/.
cd "$(dirname "$0")/.." || exit 1

# shellcheck source=scripts/app-control.sh
. "$(dirname "$0")/app-control.sh"

API_URL="${API_URL:-http://localhost:3000}"
COLLECTOR_HEALTH="${COLLECTOR_HEALTH_URL:-http://localhost:13133}"
COMPOSE_SERVICE="${COLLECTOR_SERVICE:-otel-collector}"

# The Node metric reader exports on its default 60s period, so a plan's histogram
# points land up to a minute after the run finishes. Measured, not guessed.
METRIC_WAIT_SECONDS="${METRIC_WAIT_SECONDS:-120}"
SPAN_WAIT_SECONDS="${SPAN_WAIT_SECONDS:-30}"
PLAN_TIMEOUT_SECONDS="${PLAN_TIMEOUT_SECONDS:-600}"

IN_RANGE_TOPIC="${IN_RANGE_TOPIC:-OpenTelemetry tracing for Node.js services}"
OUT_OF_RANGE_TOPIC="${OUT_OF_RANGE_TOPIC:-medieval falconry}"

# How many chances the model gets to produce a fan-out run, and nothing else. A lead
# that answers in prose instead of calling a tool is refused by the SDK and the service
# reports it as failed with a no_tool_call gap; that is the model declining to
# cooperate on the first attempt rather than a defect, and it happened on about one run
# in ten while this was being written. Every other failure still fails immediately.
# What is asserted below does not move: a real fan-out run is still required, and the
# attempt count is printed so a reader sees how many it took.
PLAN_ATTEMPTS_MAX="${PLAN_ATTEMPTS_MAX:-3}"

# The texts the service writes for those gaps, read out of the source rather than copied
# into this script, so rewording one turns the retry off loudly instead of silently.
# src/plans/schema.ts holds both service reasons in SERVICE_GAP_REASONS and
# src/telemetry/metrics.ts tags the metric from the same object. Both are retried: they
# are the same class of thing, a model that did not do the work, and neither is a defect
# in the service.
RETRYABLE_GAP_REASONS=$(python3 - src/plans/schema.ts <<'REASON' 2>/dev/null
import re, sys

try:
    text = open(sys.argv[1]).read()
except OSError:
    text = ""
for key in ("no_tool_call", "no_research"):
    found = re.search(key + r':\s*"([^"]+)"', text)
    if found:
        print(found.group(1))
REASON
)

# Persists the window across invocations, so SKIP_REQUESTS=1 re-checks the same
# window a prior run drove rather than the full cumulative log. Not cleaned up on
# exit: it is meant to outlive one invocation.
# Both are overridable so a saved log can be read back beside the trace ids that
# belong to it: VERIFY_LOG_FILE without a matching TRACE_FILE checks last night's
# log against this morning's trace ids.
SINCE_FILE="${SINCE_FILE:-/tmp/learning-path-planner-verify-since.txt}"
TRACE_FILE="${TRACE_FILE:-/tmp/learning-path-planner-verify-traces.env}"

if [ -n "${VERIFY_LOG_FILE:-}" ]; then
    SKIP_REQUESTS=1
fi

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

LOGS_FILE=""
SPANS_FILE=""
SPANTREE_FILE=""
STATUSES_FILE=""

APP_RESTARTED=0

cleanup() {
    if [ "$APP_RESTARTED" = "1" ]; then
        if ! restore_app; then
            echo ""
            echo "  THE APP WAS NOT RESTORED. It may still be running on the settings this"
            echo "  script changed. Put it back with 'make docker-up', or 'make start' for a"
            echo "  host run."
        fi
    fi
    rm -f "$SPANS_FILE" "$SPANTREE_FILE" "$STATUSES_FILE"
    if [ -z "${VERIFY_LOG_FILE:-}" ]; then
        rm -f "$LOGS_FILE"
    fi
}
trap cleanup EXIT

app_control_init

# --- parsers ---------------------------------------------------------------
#
# Three passes over the same detailed debug output, each pulling a different tuple.
# They are separate rather than one wider parser because each stops on a different
# line, and widening one would change what every check that reads it sees.

# (trace id, kind, name). The leading-arrow form of "Trace ID" inside a SpanLink
# block does not match, which is what keeps links from being counted as spans.
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

# (trace id, span id, parent id, name), so a check can say something about a span's
# parent rather than only about its presence. A root span prints an empty Parent ID.
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

# (trace id, status code, name, status message). Separate from read_spans because the
# status block sits below the Kind line that read_spans stops on.
read_span_statuses() {
    awk '
/^Span #/ { inspan = 1; tid = ""; name = ""; code = ""; next }
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

# --- span checks -----------------------------------------------------------

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

# Named spans are ambiguous here: the HTTP instrumentation names the server span for
# POST /plans and the client spans for each model call all `POST`. The kind separates
# them, so this asserts on both.
span_of_kind_in_trace() {
    local label="$1" trace="$2" kind="$3" prefix="$4"
    if awk -F'\t' -v t="$trace" -v k="$kind" -v p="$prefix" \
        '$1 == t && $2 == k && index($3, p) == 1 { found = 1 } END { exit found ? 0 : 1 }' \
        "$SPANS_FILE"; then
        ok "$label"
    else
        bad "$label - no $kind span starting '$prefix' on trace $trace"
    fi
}

# Asserts that some span named by the child prefix has a parent named by the parent
# prefix, inside one trace. Resolves the parent id against the same trace's spans, so
# a same-named span elsewhere in the window cannot satisfy it.
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

# Asserts the status message on one span, counting the matching spans rather than
# taking the first in log order: a prefix that matches two spans would otherwise
# resolve arbitrarily and pass or fail by luck.
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

# --- attribute checks ------------------------------------------------------
#
# The collector prints span attributes and metric data point tags in the same
# "key: Str(value)" form, so a plain grep for an attribute matches either and proves
# nothing about which. Both walkers below step through one span block at a time and
# only credit an attribute they find under a span's own Attributes, on a span whose
# name and trace id match.

span_attribute_in_trace() {
    local label="$1" trace="$2" prefix="$3" attribute="$4"
    if awk -v t="$trace" -v p="$prefix" -v a="$attribute" '
function reset() { name = ""; tid = ""; inattrs = 0 }
/^Span #/                       { inspan = 1; reset(); next }
/^Resource(Spans|Metrics|Logs)/ { inspan = 0; reset(); next }
/^Scope(Spans|Metrics|Logs)/    { inspan = 0; reset(); next }
inspan && /^[[:space:]]*Trace ID[[:space:]]*:/ { tid = $NF; next }
inspan && /^[[:space:]]*Name[[:space:]]*:/ {
    sub(/^[[:space:]]*Name[[:space:]]*:[[:space:]]*/, ""); name = $0; next
}
inspan && /^[[:space:]]*Attributes:/ { inattrs = 1; next }
inspan && inattrs && /^[[:space:]]*-> / {
    if (tid == t && index(name, p) == 1 && index($0, a) > 0) found = 1
    next
}
inspan && inattrs { inattrs = 0 }
END { exit found ? 0 : 1 }
' "$LOGS_FILE"; then
        ok "$label"
    else
        bad "$label - no span starting '$prefix' on trace $trace carries $attribute"
    fi
}

# Asserts a numeric span attribute is present and greater than zero. The collector
# prints numbers as Int(0) or Double(0.00034), so the value is read out of the
# parentheses rather than compared as text: a check for "not Int(0)" would be
# satisfied by Double(0.000000), which is the same zero written differently.
span_attribute_positive_in_trace() {
    local label="$1" trace="$2" prefix="$3" key="$4"
    local got
    got=$(awk -v t="$trace" -v p="$prefix" -v k="$key" '
function reset() { name = ""; tid = ""; inattrs = 0 }
/^Span #/                       { inspan = 1; reset(); next }
/^Resource(Spans|Metrics|Logs)/ { inspan = 0; reset(); next }
/^Scope(Spans|Metrics|Logs)/    { inspan = 0; reset(); next }
inspan && /^[[:space:]]*Trace ID[[:space:]]*:/ { tid = $NF; next }
inspan && /^[[:space:]]*Name[[:space:]]*:/ {
    sub(/^[[:space:]]*Name[[:space:]]*:[[:space:]]*/, ""); name = $0; next
}
inspan && /^[[:space:]]*Attributes:/ { inattrs = 1; next }
inspan && inattrs && /^[[:space:]]*-> / {
    if (tid == t && index(name, p) == 1 && index($0, k ":") > 0) {
        value = $0
        sub(/.*\(/, "", value)
        sub(/\).*/, "", value)
        if (value + 0 > best + 0) best = value
        seen = 1
    }
    next
}
inspan && inattrs { inattrs = 0 }
END { if (!seen) exit 2; print best + 0; exit best + 0 > 0 ? 0 : 1 }
' "$LOGS_FILE")
    case "$?" in
        0) ok "$label (largest value $got)" ;;
        1) bad "$label - $key is on the span but every value is zero. A local model has no price row, so cost stays zero unless PRICE_MODEL names a row to borrow rates from." ;;
        *) bad "$label - no span starting '$prefix' on trace $trace carries $key" ;;
    esac
}

# --- metric checks ---------------------------------------------------------

# Credits a tag only when it sits under "Data point attributes" of the metric asked
# for, for the reason above: a plain grep for outcome=planned also matches the span
# that carries it.
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

# Asserts the Sum of the one histogram data point carrying a given tag. Used for the
# declined run, which has to record a fan-out of zero rather than no fan-out at all:
# metric_point_tagged alone would pass on a declined run that reported three.
metric_point_sum() {
    local label="$1" metric="$2" attribute="$3" want="$4"
    local got
    got=$(awk -v m="$metric" -v a="$attribute" '
/^Metric #/     { name = ""; indesc = 0; next }
/^Descriptor:/  { indesc = 1; next }
indesc && /^[[:space:]]*->[[:space:]]*Name[[:space:]]*:/ {
    sub(/^[[:space:]]*->[[:space:]]*Name[[:space:]]*:[[:space:]]*/, ""); name = $0; indesc = 0; next
}
/DataPoints #/           { tagged = 0; next }
/Data point attributes:/ { indp = 1; next }
indp && /^[[:space:]]*-> / { if (name == m && index($0, a) > 0) tagged = 1; next }
indp { indp = 0 }
tagged && /^Sum:/ { sub(/^Sum:[[:space:]]*/, ""); print $0 + 0; tagged = 0; next }
' "$LOGS_FILE" | tail -1)
    if [ -z "$got" ]; then
        bad "$label - no data point on $metric tagged $attribute"
    elif [ "$got" = "$want" ]; then
        ok "$label"
    else
        bad "$label - the $attribute point on $metric sums to $got, expected $want"
    fi
}

# Asserts a histogram's explicit bucket boundaries, given as a comma separated list.
# The SDK's defaults start at 0 and jump to 5, which would put every cost and every
# duration this service produces into one bucket; the instruments set their own. That
# is a claim about the instrument definition, and this is what makes it falsifiable.
#
# The boundaries belong to a data point, not to the metric, and the collector prints
# the full list under every one. A histogram with two series therefore prints them
# twice per export and the window usually holds several exports, so collecting them
# all produced the same list repeated and matched nothing. Each data point is closed
# off on its own and the last complete list wins.
metric_bounds() {
    local label="$1" metric="$2" want="$3"
    local got
    got=$(awk -v m="$metric" '
function close_point() {
    if (name == m && current != "") last = current
    current = ""
}
/^Metric #/     { close_point(); name = ""; indesc = 0; next }
/DataPoints #/  { close_point(); next }
/^Descriptor:/  { indesc = 1; next }
indesc && /^[[:space:]]*->[[:space:]]*Name[[:space:]]*:/ {
    sub(/^[[:space:]]*->[[:space:]]*Name[[:space:]]*:[[:space:]]*/, ""); name = $0; indesc = 0; next
}
name == m && /^ExplicitBounds #/ {
    sub(/^ExplicitBounds #[0-9]+:[[:space:]]*/, "")
    current = (current == "" ? "" : current ",") ($0 + 0)
    next
}
END { close_point(); print last }
' "$LOGS_FILE")
    if [ -z "$got" ]; then
        bad "$label - $metric has no explicit bucket boundaries in this window"
    elif [ "$got" = "$want" ]; then
        ok "$label"
    else
        bad "$label - $metric boundaries are $got, expected $want"
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

log_lacks() {
    local label="$1" pattern="$2"
    if grep -qF -- "$pattern" "$LOGS_FILE"; then
        bad "$label - present in the window: $pattern"
    else
        ok "$label"
    fi
}

fetch_logs() {
    if [ -n "${VERIFY_LOG_FILE:-}" ]; then
        return 0
    fi
    if [ -n "${SINCE_TS:-}" ]; then
        docker compose logs "$COMPOSE_SERVICE" --no-log-prefix --since "$SINCE_TS" >"$LOGS_FILE" 2>/dev/null
    else
        docker compose logs "$COMPOSE_SERVICE" --no-log-prefix >"$LOGS_FILE" 2>/dev/null
    fi
}

# Drives one POST /plans under a trace id the caller chose, and prints the plan id
# the service minted. Keyed on the event name, never on the presence of a field: the
# terminal line is {"event":"plan",...} or {"event":"error",...} and both carry an id.
drive_plan() {
    local trace="$1" topic="$2" out="$3"
    curl -s --max-time "$PLAN_TIMEOUT_SECONDS" -X POST "$API_URL/plans" \
        -H 'content-type: application/json' \
        -H "traceparent: 00-$trace-$(python3 -c 'import secrets; print(secrets.token_hex(8))')-01" \
        -d "$(python3 -c 'import json,sys; print(json.dumps({"topic": sys.argv[1]}))' "$topic")" \
        -o "$out" 2>/dev/null
    python3 -c '
import json, sys
for line in open(sys.argv[1]):
    if not line.strip():
        continue
    doc = json.loads(line)
    if doc.get("event") == "accepted":
        print(doc.get("id", ""))
        break
' "$out" 2>/dev/null
}

plan_outcome() {
    python3 -c '
import json, sys
last = None
for line in open(sys.argv[1]):
    if line.strip():
        last = json.loads(line)
print("" if last is None else (last.get("status") or last.get("event") or ""))
' "$1" 2>/dev/null
}

# True only when the terminal line is a failed plan carrying one of the gaps the service
# writes when the model did not do the work: the lead answered without calling a tool, or
# it finished without researching a subtopic. Those two are retried. Anything else - an
# outage, a connection refused, a schema violation - returns false here and fails the
# check above on the spot.
plan_failed_without_doing_the_work() {
    if [ -z "${RETRYABLE_GAP_REASONS:-}" ]; then
        return 1
    fi
    python3 -c '
import json, sys

last = None
for line in open(sys.argv[1]):
    if line.strip():
        last = json.loads(line)
if last is None or last.get("event") != "plan" or last.get("status") != "failed":
    sys.exit(1)
retryable = {line for line in sys.argv[2].splitlines() if line}
gaps = (last.get("plan") or {}).get("gaps") or []
sys.exit(0 if any(gap.get("reason") in retryable for gap in gaps) else 1)
' "$1" "$RETRYABLE_GAP_REASONS" 2>/dev/null
}

collector_lines_since() {
    docker compose logs "$COMPOSE_SERVICE" --no-log-prefix --since "$1" 2>/dev/null | wc -l | tr -d ' '
}

# Waits for the collector to stop writing, then returns. The restart in section 2 stops
# the outgoing app process with SIGTERM, which flushes its pending spans and its cumulative
# metric points, and that flush reaches the collector's log a second or two after the
# new process is already answering /health. A window opened at that moment contains the
# previous run's points, and every metric check below reads the whole window: the wait
# loop in section 4 ends on the stale export and the tag checks then pass or fail
# against data from a run nobody is looking at. Five quiet seconds put the flush behind
# the window instead of inside it. An idle collector writes nothing, so this returns as
# soon as the flush has landed.
wait_for_collector_quiet() {
    local from="$1" deadline last seen quiet=0
    deadline=$(( $(date +%s) + 60 ))
    last=$(collector_lines_since "$from")
    while [ "$(date +%s)" -lt "$deadline" ]; do
        sleep 1
        seen=$(collector_lines_since "$from")
        if [ "$seen" = "$last" ]; then
            quiet=$((quiet + 1))
            if [ "$quiet" -ge 5 ]; then
                return 0
            fi
        else
            quiet=0
            last="$seen"
        fi
    done
    return 1
}

heading "================================================="
heading "  Telemetry verification - learning path planner"
heading "================================================="

# --- 1. Prerequisites ------------------------------------------------------
echo ""
heading "=== 1. Prerequisites ==="
echo ""

if [ -n "${VERIFY_LOG_FILE:-}" ]; then
    if [ -s "$VERIFY_LOG_FILE" ]; then
        ok "reading a saved collector log: $VERIFY_LOG_FILE"
    else
        bad "VERIFY_LOG_FILE is set to $VERIFY_LOG_FILE, which is empty or missing"
        exit 1
    fi
else
    # curl writes 000 into %{http_code} itself when it cannot reach the host, so an
    # `|| echo 000` on the end of this appends a second one and prints 000000.
    APP_STATUS=$(curl -s -o /dev/null -w "%{http_code}" "$API_URL/health" 2>/dev/null)
    APP_STATUS=${APP_STATUS:-000}
    if [ "$APP_STATUS" = "200" ]; then
        ok "app is healthy ($API_URL/health)"
    else
        bad "app is not healthy ($API_URL/health returned $APP_STATUS)"
        echo ""
        echo "  Start the stack with 'make docker-up', or 'make start' for a host run,"
        echo "  then run this again."
        exit 1
    fi

    COLLECTOR_STATUS=$(curl -s -o /dev/null -w "%{http_code}" "$COLLECTOR_HEALTH" 2>/dev/null)
    COLLECTOR_STATUS=${COLLECTOR_STATUS:-000}
    if [ "$COLLECTOR_STATUS" = "200" ]; then
        ok "collector is healthy ($COLLECTOR_HEALTH)"
    else
        bad "collector is not healthy ($COLLECTOR_HEALTH returned $COLLECTOR_STATUS)"
        echo ""
        echo "  Check with 'docker compose logs otel-collector'. Without the collector there"
        echo "  is no debug output to verify against."
        exit 1
    fi
fi

# --- 2. Drive the runs -----------------------------------------------------
PLAN_TRACE=""
DECLINED_TRACE=""
PLAN_ID=""
DECLINED_ID=""
SINCE_TS=""

if [ "${SKIP_REQUESTS:-}" != "1" ]; then
    echo ""
    heading "=== 2. Driving one planned run and one declined run ==="
    echo ""

    # A local model has no price row of its own, so base14.gen_ai.cost is zero unless
    # PRICE_MODEL names a row to borrow rates from. The cost check below asserts a
    # non-zero number, so the app is restarted with one. Every cost produced this way
    # carries base14.gen_ai.cost.simulated=true: it is a stand-in, not a bill.
    RESTART_TS=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
    if app_can_restart; then
        echo "  $(dim "restarting the app with PRICE_MODEL=$(app_baseline_setting PRICE_MODEL) so cost is a real number...")"
        APP_RESTARTED=1
        if ! restart_app; then
            bad "the app did not come back up after the restart"
            exit 1
        fi
        echo "  $(dim "waiting for the outgoing process's final export to land before opening the window...")"
        if ! wait_for_collector_quiet "$RESTART_TS"; then
            warn "the collector was still writing after 60s, so the window may still hold points from before this run"
        fi
    else
        warn "this script cannot restart the app, so it runs on whatever PRICE_MODEL is already set. With none, every cost is zero and the cost check below fails."
    fi

    # Captured after the restart, after that restart's flush has landed, and before
    # anything is driven, so --since excludes every span and metric this script did not
    # just produce.
    SINCE_TS=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
    echo "$SINCE_TS" >"$SINCE_FILE"

    DECLINED_TRACE=$(python3 -c 'import secrets; print(secrets.token_hex(16))')

    PLAN_BODY=$(mktemp /tmp/learning-path-planner-plan-XXXXXX.ndjson)
    DECLINED_BODY=$(mktemp /tmp/learning-path-planner-declined-XXXXXX.ndjson)

    if [ -z "$RETRYABLE_GAP_REASONS" ]; then
        warn "could not read the retryable gap reasons out of src/plans/schema.ts, so a lead that does no work fails this run instead of being retried"
    fi

    # A fresh trace per attempt: the span checks below all read the trace this loop
    # ends on, so a retried attempt is left out of them entirely rather than mixed in.
    PLAN_ATTEMPT=0
    while : ; do
        PLAN_ATTEMPT=$((PLAN_ATTEMPT + 1))
        PLAN_TRACE=$(python3 -c 'import secrets; print(secrets.token_hex(16))')
        echo "  $(dim "planned run, attempt $PLAN_ATTEMPT of $PLAN_ATTEMPTS_MAX, trace $PLAN_TRACE, about 95s...")"
        PLAN_ID=$(drive_plan "$PLAN_TRACE" "$IN_RANGE_TOPIC" "$PLAN_BODY")
        if [ -z "$PLAN_ID" ]; then
            bad "the planned run never returned an accepted line"
            exit 1
        fi
        PLAN_RESULT=$(plan_outcome "$PLAN_BODY")
        if [ "$PLAN_RESULT" = "planned" ] || [ "$PLAN_ATTEMPT" -ge "$PLAN_ATTEMPTS_MAX" ]; then
            break
        fi
        if ! plan_failed_without_doing_the_work "$PLAN_BODY"; then
            break
        fi
        echo "  $(dim "attempt $PLAN_ATTEMPT ended failed: the lead did no research. Retrying.")"
    done

    if [ "$PLAN_RESULT" = "planned" ]; then
        ok "planned run $PLAN_ID finished planned on attempt $PLAN_ATTEMPT of $PLAN_ATTEMPTS_MAX"
    else
        bad "the in-range run ended '$PLAN_RESULT' on attempt $PLAN_ATTEMPT of $PLAN_ATTEMPTS_MAX, not planned; every span check below is against a run that did not happen"
        tail -1 "$PLAN_BODY" | head -c 300
        echo ""
    fi

    echo "  $(dim "declined run, trace $DECLINED_TRACE...")"
    DECLINED_ID=$(drive_plan "$DECLINED_TRACE" "$OUT_OF_RANGE_TOPIC" "$DECLINED_BODY")
    DECLINED_RESULT=$(plan_outcome "$DECLINED_BODY")
    if [ "$DECLINED_RESULT" = "declined" ]; then
        ok "declined run $DECLINED_ID finished declined"
    else
        bad "the out-of-range run ended '$DECLINED_RESULT', not declined; '$OUT_OF_RANGE_TOPIC' is apparently covered by this corpus"
    fi
    rm -f "$PLAN_BODY" "$DECLINED_BODY"

    # Captured a second past the end of both runs, so the wait in section 4 can only be
    # satisfied by an export the metric reader produced with this run's points already
    # in it. Waiting on the whole window instead let a partial export end the wait: one
    # taken between the two runs, or the outgoing process's own flush, carries the
    # instrument names without carrying what the checks are about to read.
    METRIC_SINCE_TS=$(python3 -c '
import datetime

now = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(seconds=1)
print(now.strftime("%Y-%m-%dT%H:%M:%SZ"))
')

    cat >"$TRACE_FILE" <<TRACES
PLAN_TRACE=$PLAN_TRACE
DECLINED_TRACE=$DECLINED_TRACE
PLAN_ID=$PLAN_ID
DECLINED_ID=$DECLINED_ID
TRACES

    echo "  $(dim "waiting ${SPAN_WAIT_SECONDS}s for the span batch to reach the collector...")"
    sleep "$SPAN_WAIT_SECONDS"
else
    if [ -f "$TRACE_FILE" ]; then
        # shellcheck disable=SC1090
        . "$TRACE_FILE"
    fi
    if [ -n "${VERIFY_LOG_FILE:-}" ]; then
        echo "  $(dim "VERIFY_LOG_FILE is set: checking $VERIFY_LOG_FILE, traces from $TRACE_FILE")"
    elif [ -f "$SINCE_FILE" ]; then
        SINCE_TS=$(cat "$SINCE_FILE")
        echo "  $(dim "SKIP_REQUESTS=1: re-checking the log since $SINCE_TS (from the last driven run)")"
    else
        echo "  $(dim "SKIP_REQUESTS=1 with no timestamp from a prior run: checking the full collector log")"
    fi
fi

if [ -z "$PLAN_TRACE" ] || [ -z "$DECLINED_TRACE" ]; then
    bad "no trace ids to check against. Run this without SKIP_REQUESTS=1 to drive them."
    exit 1
fi

# --- 3. Local verification against the collector debug exporter ------------
echo ""
heading "=== 3. Collector debug output ==="
echo ""

if [ -n "${VERIFY_LOG_FILE:-}" ]; then
    LOGS_FILE="$VERIFY_LOG_FILE"
else
    LOGS_FILE=$(mktemp /tmp/learning-path-planner-otel-XXXXXX.txt)
fi
fetch_logs

if [ ! -s "$LOGS_FILE" ]; then
    bad "could not read collector logs since $SINCE_TS - run this from nodejs/ai-learning-path-planner"
    exit 1
fi

SPANS_FILE=$(mktemp /tmp/learning-path-planner-spans-XXXXXX.tsv)
SPANTREE_FILE=$(mktemp /tmp/learning-path-planner-spantree-XXXXXX.tsv)
STATUSES_FILE=$(mktemp /tmp/learning-path-planner-statuses-XXXXXX.tsv)
read_spans "$LOGS_FILE" >"$SPANS_FILE"
read_span_tree "$LOGS_FILE" >"$SPANTREE_FILE"
read_span_statuses "$LOGS_FILE" >"$STATUSES_FILE"

echo "  $(dim "--- the planned run, all on $PLAN_TRACE ---")"
# POST /plans is not asserted as the trace root: this script sets its own traceparent
# on the request, so the server span has a remote parent that is never exported. What
# the example claims is the shape below it, and that is what is asserted.
span_of_kind_in_trace "POST /plans, the run's server span" "$PLAN_TRACE" "Server" "POST"
span_in_trace         "invoke_agent, the lead's operation span" "$PLAN_TRACE" "invoke_agent "
span_in_trace         "step, one per model call"                "$PLAN_TRACE" "step "
span_in_trace         "chat, the model call itself"             "$PLAN_TRACE" "chat "
span_parent_in_trace  "invoke_agent sits under the server span" "$PLAN_TRACE" "invoke_agent " "POST"
span_parent_in_trace  "step sits under invoke_agent"            "$PLAN_TRACE" "step " "invoke_agent "
span_parent_in_trace  "chat sits under step"                    "$PLAN_TRACE" "chat " "step "
span_status_in_trace  "the lead's operation span is not in error" "$PLAN_TRACE" "invoke_agent " "Unset"

echo "  $(dim "--- gen_ai.* on the model calls ---")"
span_attribute_in_trace "gen_ai.operation.name on the chat span"  "$PLAN_TRACE" "chat " "gen_ai.operation.name: Str(chat)"
span_attribute_in_trace "gen_ai.request.model on the chat span"   "$PLAN_TRACE" "chat " "gen_ai.request.model"
span_attribute_in_trace "gen_ai.response.model on the chat span"  "$PLAN_TRACE" "chat " "gen_ai.response.model"
span_attribute_in_trace "gen_ai.usage.input_tokens on the chat span"  "$PLAN_TRACE" "chat " "gen_ai.usage.input_tokens"
span_attribute_in_trace "gen_ai.usage.output_tokens on the chat span" "$PLAN_TRACE" "chat " "gen_ai.usage.output_tokens"
span_attribute_in_trace "gen_ai.agent.name on the operation span" "$PLAN_TRACE" "invoke_agent " "gen_ai.agent.name: Str(lead)"
span_attribute_in_trace "gen_ai.usage.input_tokens on the operation span too" "$PLAN_TRACE" "invoke_agent " "gen_ai.usage.input_tokens"

echo "  $(dim "--- the base14.* attributes ---")"
span_attribute_in_trace "base14.plan.id on the operation span, matching the run"  "$PLAN_TRACE" "invoke_agent " "base14.plan.id: Str($PLAN_ID)"
span_attribute_in_trace "base14.plan.id on the step span"                         "$PLAN_TRACE" "step "         "base14.plan.id: Str($PLAN_ID)"
span_attribute_in_trace "base14.plan.id on the chat span"                         "$PLAN_TRACE" "chat "         "base14.plan.id: Str($PLAN_ID)"
span_attribute_in_trace "base14.agent.role is lead on the operation span"         "$PLAN_TRACE" "invoke_agent " "base14.agent.role: Str(lead)"
span_attribute_in_trace "base14.tool.catalogue on the chat span"                  "$PLAN_TRACE" "chat "         "base14.tool.catalogue: Str($(app_baseline_setting TOOL_CATALOGUE))"
span_attribute_positive_in_trace "base14.gen_ai.cost is non-zero on the chat span"      "$PLAN_TRACE" "chat "         "base14.gen_ai.cost"
span_attribute_positive_in_trace "base14.gen_ai.cost is non-zero on the operation span" "$PLAN_TRACE" "invoke_agent " "base14.gen_ai.cost"
span_attribute_in_trace "base14.gen_ai.cost.simulated is true on the chat span"   "$PLAN_TRACE" "chat "         "base14.gen_ai.cost.simulated: Bool(true)"

echo "  $(dim "--- the fan-out: researcher spans and tool spans ---")"
# The lead reaches a researcher only by calling research_subtopic, so the tool span
# comes first and the researcher's own operation span hangs under it. Asserted in that
# order so a failure says which half is missing.
span_in_trace         "execute_tool research_subtopic, the fan-out itself" "$PLAN_TRACE" "execute_tool research_subtopic"
span_parent_in_trace  "execute_tool sits under a step"                     "$PLAN_TRACE" "execute_tool " "step "
span_attribute_in_trace "a researcher operation span, by base14.agent.role" "$PLAN_TRACE" "invoke_agent " "base14.agent.role: Str(researcher)"
span_attribute_in_trace "base14.subtopic on a researcher span"              "$PLAN_TRACE" "invoke_agent " "base14.subtopic"
span_parent_in_trace  "the researcher's operation span sits under the tool span" "$PLAN_TRACE" "invoke_agent " "execute_tool research_subtopic"
span_in_trace         "execute_tool search_docs, a researcher's own tool"   "$PLAN_TRACE" "execute_tool search_docs"

echo "  $(dim "--- the declined run, all on $DECLINED_TRACE ---")"
span_of_kind_in_trace "POST /plans answered 422 and still produced a server span" "$DECLINED_TRACE" "Server" "POST"
span_absent_in_trace  "no invoke_agent span; a decline spends no tokens"          "$DECLINED_TRACE" "invoke_agent "
span_absent_in_trace  "no chat span either"                                       "$DECLINED_TRACE" "chat "

echo "  $(dim "--- the noise filter, which only the collector can confirm ---")"
# The healthcheck fires every ten seconds and this script curls /health itself, so the
# window always contains the traffic. If filter/noisy is working, none of it reaches the
# exporter. This asserts on the span data rather than on the collector config because the
# defect it exists to catch was a condition that parsed, loaded and matched nothing: it
# read the span name, and the server span is named POST or GET with the path on url.path.
# A YAML assertion cannot tell a condition that works from one that never fires.
log_lacks "no /health span reached the exporter; filter/noisy dropped them" "url.path: Str(/health)"

echo "  $(dim "--- content capture, off by default ---")"
# base14.subtopic is excluded, and only that. It is an attribute this service records on
# purpose, asserted present a few checks above, and its value is a subtopic the lead model
# chose - which for this topic came back as "OpenTelemetry tracing for Node.js services
# setup", the whole topic with a word after it. Matching that as captured prompt content
# made this check fail on a run where nothing was captured at all. Everything else in the
# span data is still matched.
if grep -F "$IN_RANGE_TOPIC" "$LOGS_FILE" | grep -qv "base14.subtopic:"; then
    bad "the requested topic is in the span data; OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT should be false by default"
else
    ok "no prompt content in the spans; set OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT=true to capture it"
fi

# --- 4. Metrics ------------------------------------------------------------
#
# Six instruments, one point each, tagged. The Node metric reader exports on a 60s
# period, so these land up to a minute after the runs finish.
echo ""
heading "=== 4. Metrics ==="
echo ""

if [ "${SKIP_REQUESTS:-}" != "1" ]; then
    echo "  $(dim "waiting up to ${METRIC_WAIT_SECONDS}s for an export taken after both runs...")"
    DEADLINE=$(( $(date +%s) + METRIC_WAIT_SECONDS ))
    while [ "$(date +%s)" -lt "$DEADLINE" ]; do
        if docker compose logs "$COMPOSE_SERVICE" --no-log-prefix --since "$METRIC_SINCE_TS" 2>/dev/null \
            | grep -qF "Name: base14.plan.gap.count"; then
            break
        fi
        sleep 5
    done
    fetch_logs
fi

log_has "base14.plan.cost"                    "Name: base14.plan.cost"
log_has "base14.plan.fanout"                  "Name: base14.plan.fanout"
log_has "base14.plan.duration"                "Name: base14.plan.duration"
log_has "base14.plan.gap.count"               "Name: base14.plan.gap.count"
log_has "base14.plan.escalation.count"        "Name: base14.plan.escalation.count"
log_has "base14.gen_ai.tool_definition.tokens" "Name: base14.gen_ai.tool_definition.tokens"

echo "  $(dim "--- the tags ---")"
metric_point_tagged "base14.plan.cost tagged catalogue"        "base14.plan.cost" "catalogue: Str($(app_baseline_setting TOOL_CATALOGUE))"
metric_point_tagged "base14.plan.cost tagged fanout_bucket"    "base14.plan.cost" "fanout_bucket: Str("
metric_point_tagged "base14.plan.cost tagged outcome=planned"   "base14.plan.cost" "outcome: Str(planned)"
metric_point_tagged "base14.plan.fanout tagged outcome=planned"   "base14.plan.fanout"   "outcome: Str(planned)"
metric_point_tagged "base14.plan.fanout tagged outcome=declined"  "base14.plan.fanout"   "outcome: Str(declined)"
metric_point_tagged "base14.plan.duration tagged outcome=planned" "base14.plan.duration" "outcome: Str(planned)"
metric_point_tagged "base14.plan.gap.count tagged reason=topic_out_of_range" \
    "base14.plan.gap.count" "reason: Str(topic_out_of_range)"
metric_point_tagged "base14.plan.escalation.count tagged trigger=low_confidence" \
    "base14.plan.escalation.count" "trigger: Str(low_confidence)"
metric_point_tagged "base14.gen_ai.tool_definition.tokens tagged role=lead" \
    "base14.gen_ai.tool_definition.tokens" "role: Str(lead)"
metric_point_tagged "base14.gen_ai.tool_definition.tokens tagged role=researcher" \
    "base14.gen_ai.tool_definition.tokens" "role: Str(researcher)"

echo "  $(dim "--- the values the tags are there to separate ---")"
# A decline researches nothing, so its fan-out is zero rather than absent. Asserted on
# the sum of that one series: the tag check above passes on a declined run that
# reported three subtopics, and this one does not.
metric_point_sum "the declined run recorded a fan-out of zero" \
    "base14.plan.fanout" "outcome: Str(declined)" "0"

echo "  $(dim "--- the bucket boundaries, which are not the SDK defaults ---")"
metric_bounds "base14.plan.cost boundaries"     "base14.plan.cost"     "0.0001,0.0003,0.001,0.003,0.01,0.03,0.1,0.3,1"
metric_bounds "base14.plan.fanout boundaries"   "base14.plan.fanout"   "0,1,2,3,4,5,6,8"
# Anchored on the planned-run band, not the SDK defaults. See src/telemetry/metrics.ts and
# tests/telemetry/metrics.test.ts.
metric_bounds "base14.plan.duration boundaries" "base14.plan.duration" "0.1,1,10,30,60,90,120,150,180,240,300"

# --- 5. Scout ---------------------------------------------------------------
echo ""
heading "=== 5. base14 Scout ==="
echo ""
# Scout is checked only when all three credentials are present. A reader without a
# Scout account gets everything above and a clean exit here: a missing credential is
# not a failure, and nothing above this line needed one.
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
    SCOUT_SERVICE="${OTEL_SERVICE_NAME:-ai-learning-path-planner}"
    skipped "SCOUT_* is set. The hosted side is a manual check from here; the checklist below covers it."
    echo ""
    echo "  $(dim "If the scout CLI is installed, this trace's own query is:")"
    echo ""
    echo "    scout traces $SCOUT_SERVICE --id $PLAN_TRACE --since 30m --raw"
    echo ""
    echo "  $(dim "--id drills into one trace. --since 30m is valid here even though the flag's")"
    echo "  $(dim "help says 15m, because querying by id raises the cap to 60 minutes. --raw prints")"
    echo "  $(dim "the trace as a JSON object with a trace_id field and a spans array.")"
    echo ""
    echo "  $(dim "In the Scout UI, or in that JSON, this run should show:")"
    echo "    [ ] one trace rooted at the POST /plans server span."
    echo "    [ ] invoke_agent under it, step under invoke_agent, chat under step."
    echo "    [ ] base14.plan.id equal to $PLAN_ID on every agent span."
    echo "    [ ] base14.agent.role lead on the lead spans, researcher on the fan-out."
    echo "    [ ] base14.gen_ai.cost with base14.gen_ai.cost.simulated true."
    echo "    [ ] points on all six base14.plan.* and base14.gen_ai.* instruments."
    echo "    [ ] the declined run on trace $DECLINED_TRACE, with a fan-out of zero."
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
