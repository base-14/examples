#!/usr/bin/env bash

# ---------------------------------------------------------------------------
# measure-catalogue.sh - what deferring the tool catalogue costs, measured.
#
# Runs the same request twice, once with TOOL_CATALOGUE=deferred and once with
# TOOL_CATALOGUE=full, and prints the input-token difference and the cost
# difference between them. TOOL_CATALOGUE is read at boot, so each half needs its
# own app start; both are undone by restore_app, which runs from an EXIT trap as
# well as at the end.
#
# Two different numbers get printed and they must not be conflated:
#
#   Input tokens      real counts, read from gen_ai.usage.input_tokens on the chat
#                     spans of each run. This is what the provider actually charged
#                     the context window for.
#   Definition tokens an estimate the service records itself, on
#                     base14.gen_ai.tool_definition.tokens. It is the JSON of the
#                     active tool definitions divided by four characters per token.
#                     That divisor is a stated convention, not a measurement, so
#                     anything quoting these numbers should quote the divisor too.
#
# The per-call figure is the one to quote. A run's total input tokens depend on how
# many steps the model took, which changes between runs; the first model call of each
# run is the same prompt with the same instructions and differs only in the tool list,
# which is the thing being measured.
#
# Needs a stack this script can restart, which means either a Compose app service or
# a host process started from dist/. Takes about five minutes: two runs plus two app
# starts plus one metric export period.
#
# Usage:
#   ./scripts/measure-catalogue.sh
#   TOPIC="..." ./scripts/measure-catalogue.sh
# ---------------------------------------------------------------------------

set -uo pipefail

cd "$(dirname "$0")/.." || exit 1

# shellcheck source=scripts/app-control.sh
. "$(dirname "$0")/app-control.sh"

API_URL="${API_URL:-http://localhost:3000}"
COMPOSE_SERVICE="${COLLECTOR_SERVICE:-otel-collector}"
TOPIC="${TOPIC:-OpenTelemetry tracing for Node.js services}"
PLAN_TIMEOUT_SECONDS="${PLAN_TIMEOUT_SECONDS:-600}"
SPAN_WAIT_SECONDS="${SPAN_WAIT_SECONDS:-30}"
METRIC_WAIT_SECONDS="${METRIC_WAIT_SECONDS:-120}"

LOGS_FILE=""
APP_RESTARTED=0

cleanup() {
    if [ "$APP_RESTARTED" = "1" ]; then
        echo ""
        echo "Restoring the app..."
        if ! restore_app; then
            echo "THE APP WAS NOT RESTORED. Put it back with 'make docker-up', or"
            echo "'make start' for a host run."
        fi
    fi
    rm -f "$LOGS_FILE"
}
trap cleanup EXIT

app_control_init

echo "=== tool catalogue measurement ==="
echo "Target: $API_URL"
echo "Topic: $TOPIC"
echo "App control: $(app_mode)"
echo ""

if ! app_can_restart; then
    echo "SKIP: this script cannot restart the app - docker compose has no app service"
    echo "      and there is no dist/ to launch - and TOOL_CATALOGUE is read at boot,"
    echo "      so there is no way to run the same request under both settings."
    exit 1
fi

# Drives one run under a trace id the caller chose, leaving the NDJSON in $2.
drive_plan() {
    local trace="$1" out="$2"
    curl -s --max-time "$PLAN_TIMEOUT_SECONDS" -X POST "$API_URL/plans" \
        -H 'content-type: application/json' \
        -H "traceparent: 00-$trace-$(python3 -c 'import secrets; print(secrets.token_hex(8))')-01" \
        -d "$(python3 -c 'import json,sys; print(json.dumps({"topic": sys.argv[1]}))' "$TOPIC")" \
        -o "$out" 2>/dev/null
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

run_one() {
    local catalogue="$1" trace="$2"
    echo "  $catalogue: restarting the app..."
    APP_RESTARTED=1
    if ! restart_app "TOOL_CATALOGUE=$catalogue"; then
        echo "  ERROR: the app did not come back up with TOOL_CATALOGUE=$catalogue"
        return 1
    fi
    local body
    body=$(mktemp /tmp/learning-path-planner-measure-XXXXXX.ndjson)
    local started
    started=$(date +%s)
    echo "  $catalogue: planning, trace $trace..."
    drive_plan "$trace" "$body"
    local outcome
    outcome=$(plan_outcome "$body")
    echo "  $catalogue: ended '$outcome' after $(( $(date +%s) - started ))s"
    rm -f "$body"
    if [ "$outcome" != "planned" ]; then
        echo "  ERROR: the $catalogue run did not plan, so there is nothing to compare"
        return 1
    fi
    return 0
}

SINCE_TS=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
DEFERRED_TRACE=$(python3 -c 'import secrets; print(secrets.token_hex(16))')
FULL_TRACE=$(python3 -c 'import secrets; print(secrets.token_hex(16))')

run_one deferred "$DEFERRED_TRACE" || exit 1
run_one full "$FULL_TRACE" || exit 1

echo ""
echo "Restoring the app..."
restore_app
APP_RESTARTED=0

echo "  waiting ${SPAN_WAIT_SECONDS}s for the span batch..."
sleep "$SPAN_WAIT_SECONDS"

LOGS_FILE=$(mktemp /tmp/learning-path-planner-measure-log-XXXXXX.txt)
echo "  waiting up to ${METRIC_WAIT_SECONDS}s for the metric export period..."
DEADLINE=$(( $(date +%s) + METRIC_WAIT_SECONDS ))
while [ "$(date +%s)" -lt "$DEADLINE" ]; do
    docker compose logs "$COMPOSE_SERVICE" --no-log-prefix --since "$SINCE_TS" >"$LOGS_FILE" 2>/dev/null
    if grep -qF "catalogue: Str(full)" "$LOGS_FILE"; then
        break
    fi
    sleep 5
done

echo ""
python3 - "$LOGS_FILE" "$DEFERRED_TRACE" "$FULL_TRACE" <<'PYTHON'
import re
import sys

log_path, deferred_trace, full_trace = sys.argv[1], sys.argv[2], sys.argv[3]
text = open(log_path, encoding="utf-8", errors="replace").read()

TRACE = re.compile(r"Trace ID\s+:\s*(\S+)")
NAME = re.compile(r"\n\s+Name\s+:\s*(.+)")
ATTR = re.compile(r"->\s*([\w.]+):\s*\w+\(([^)]*)\)")


def spans(blob):
    for block in blob.split("Span #")[1:]:
        trace = TRACE.search(block)
        name = NAME.search(block)
        if not trace or not name:
            continue
        attrs = dict(ATTR.findall(block.split("Attributes:", 1)[-1]))
        yield trace.group(1), name.group(1).strip(), attrs


def measure(trace_id):
    chat_inputs, chat_outputs, agent_costs = [], [], []
    for trace, name, attrs in spans(text):
        if trace != trace_id:
            continue
        if name.startswith("chat "):
            if "gen_ai.usage.input_tokens" in attrs:
                chat_inputs.append(int(attrs["gen_ai.usage.input_tokens"]))
            if "gen_ai.usage.output_tokens" in attrs:
                chat_outputs.append(int(attrs["gen_ai.usage.output_tokens"]))
        elif name.startswith("invoke_agent ") and "base14.gen_ai.cost" in attrs:
            agent_costs.append(float(attrs["base14.gen_ai.cost"]))
    return {
        "calls": len(chat_inputs),
        "first_call_input": chat_inputs[0] if chat_inputs else None,
        "total_input": sum(chat_inputs),
        "total_output": sum(chat_outputs),
        "cost": sum(agent_costs),
    }


def definition_tokens():
    out = {}
    for block in text.split("Metric #")[1:]:
        if "Name: base14.gen_ai.tool_definition.tokens" not in block:
            continue
        for point in block.split("HistogramDataPoints #")[1:]:
            role = re.search(r"->\s*role:\s*\w+\(([^)]*)\)", point)
            catalogue = re.search(r"->\s*catalogue:\s*\w+\(([^)]*)\)", point)
            value = re.search(r"\n\s*Max:\s*([0-9.]+)", point)
            if role and catalogue and value:
                out[(catalogue.group(1), role.group(1))] = int(float(value.group(1)))
    return out


deferred = measure(deferred_trace)
full = measure(full_trace)
defs = definition_tokens()

if deferred["first_call_input"] is None or full["first_call_input"] is None:
    print("Could not read input tokens for both runs from the collector log.")
    print("  deferred trace:", deferred_trace, deferred)
    print("  full trace:    ", full_trace, full)
    sys.exit(1)

print("=== Input tokens, real counts from gen_ai.usage.input_tokens ===")
print()
print(f"{'':<22}{'deferred':>12}{'full':>12}{'difference':>14}")
first_diff = full["first_call_input"] - deferred["first_call_input"]
print(f"{'first model call':<22}{deferred['first_call_input']:>12}"
      f"{full['first_call_input']:>12}{first_diff:>+14}")
total_diff = full["total_input"] - deferred["total_input"]
print(f"{'whole run':<22}{deferred['total_input']:>12}"
      f"{full['total_input']:>12}{total_diff:>+14}")
print(f"{'model calls in the run':<22}{deferred['calls']:>12}{full['calls']:>12}")
print(f"{'output tokens':<22}{deferred['total_output']:>12}"
      f"{full['total_output']:>12}{full['total_output'] - deferred['total_output']:>+14}")
print()
print("The first-call figure is the one to quote. The whole-run total also carries")
print("however many steps the model happened to take, which is not the catalogue's")
print("doing, and the output column is there because it moves the cost below far more")
print("than the catalogue does.")
print()

print("=== Cost, summed over the run's invoke_agent spans ===")
print()
cost_diff = full["cost"] - deferred["cost"]
print(f"{'':<22}{'deferred':>14}{'full':>14}{'difference':>16}")
print(f"{'USD':<22}{deferred['cost']:>14.8f}{full['cost']:>14.8f}{cost_diff:>+16.8f}")
print()
if deferred["cost"] == 0 and full["cost"] == 0:
    print("Both runs cost zero. A local model has no price row of its own, so cost stays")
    print("zero unless PRICE_MODEL names a row to borrow rates from.")
else:
    print("Every figure here is simulated: base14.gen_ai.cost.simulated is true on every")
    print("span of a local run, because the rate is borrowed from PRICE_MODEL rather than")
    print("charged by anyone.")
    print()
    print("Read the sign before the number. Output tokens are priced several times higher")
    print("than input tokens on every row in _shared/pricing.json, and how many the model")
    print("writes varies far more between two runs than the tool catalogue changes the")
    print("input. A single pair of runs can and does come out with the full catalogue")
    print("cheaper. The input-token difference above is the measurement; this cost")
    print("difference is one sample of a noisy quantity.")
print()

print("=== Definition tokens, the service's own four-characters-per-token estimate ===")
print()
if defs:
    print(f"{'':<22}{'deferred':>12}{'full':>12}")
    for role in ("lead", "researcher"):
        left = defs.get(("deferred", role))
        right = defs.get(("full", role))
        print(f"{role:<22}{left if left is not None else '-':>12}"
              f"{right if right is not None else '-':>12}")
    print()
    print("These are base14.gen_ai.tool_definition.tokens, a character estimate of the")
    print("active tool definitions at four characters per token. They are not token")
    print("counts and do not have to match the input-token difference above.")
else:
    print("No base14.gen_ai.tool_definition.tokens points landed in this window.")
PYTHON
