#!/usr/bin/env bash
# Checks the collector's debug output and self-metrics for the last scripts/drive.sh run.
# Needs curl, jq and docker compose. Do not restart the collector between the run and
# this script, because its self-metrics reset on restart.
#
# Usage: scripts/verify-scout.sh
set -euo pipefail

cd "$(dirname "$0")/.."

COLLECTOR_HEALTH="${COLLECTOR_HEALTH_URL:-http://localhost:${COLLECTOR_HEALTH_PORT:-13133}}"
COLLECTOR_METRICS="${COLLECTOR_METRICS_URL:-http://localhost:${COLLECTOR_METRICS_PORT:-8888}/metrics}"
RUN_FILE=".harness/last-run.json"
FLUSH_SECONDS="${FLUSH_SECONDS:-20}"

failures=0
pass() { printf "  \033[32mPASS\033[0m %s\n" "$1"; }
fail() { printf "  \033[31mFAIL\033[0m %s\n" "$1"; failures=$((failures + 1)); }
gap()  { printf "  \033[33mGAP\033[0m  %s\n" "$1"; }
stop() { fail "$1"; exit 2; }

echo "=== Prerequisites ==="
[ -s "$RUN_FILE" ] || stop "no ${RUN_FILE}; run scripts/drive.sh first"
total=$(jq '.turns | length' "$RUN_FILE")
completed=$(jq '[.turns[] | select(.exit == 0 and .completed)] | length' "$RUN_FILE")
[ "$completed" -eq "$total" ] && pass "${completed} of ${total} turns completed (Codex $(jq -r .codex_version "$RUN_FILE"))" \
  || fail "only ${completed} of ${total} turns completed"
[ "$(curl -s -o /dev/null -w "%{http_code}" "$COLLECTOR_HEALTH" || echo 000)" = "200" ] \
  && pass "collector healthy" || stop "collector not healthy at ${COLLECTOR_HEALTH}"

finished=$(stat -c %Y "$RUN_FILE" 2>/dev/null || stat -f %m "$RUN_FILE")
wait_seconds=$(( finished + FLUSH_SECONDS - $(date +%s) ))
[ "$wait_seconds" -gt 0 ] && sleep "$wait_seconds"

LOGS_FILE=$(mktemp /tmp/codex-collector-XXXXXX)
trap 'rm -f "$LOGS_FILE"' EXIT
docker compose logs otel-collector --no-log-prefix --since "$(jq -r .started_at "$RUN_FILE")" > "$LOGS_FILE" 2>/dev/null || true
[ -s "$LOGS_FILE" ] || stop "no collector debug output for the run"

has() { grep -qE -- "$1" "$LOGS_FILE"; }
# One line per span: name, trace id, and parent id or "-" for a root span.
SPANS=$(awk '
  /^Span #/ {trace=""; parent="-"}
  /^ +Trace ID +: / {trace=$NF}
  /^ +Parent ID +: / {parent=($NF == ":" ? "-" : $NF)}
  /^ +Name +: / {print $NF, trace, parent}' "$LOGS_FILE")
count_spans() { awk -v n="$1" '$1 == n' <<<"$SPANS" | grep -c . || true; }
# One line per log record: its event.name.
EVENTS=$(awk '/^LogRecord #/ {inlog=1} /^(Span|Metric) #/ {inlog=0}
  inlog && /^ +-> event.name: Str\(/ {gsub(/.*Str\(|\)$/, ""); print}' "$LOGS_FILE")
count_events() { grep -cx -- "$1" <<<"$EVENTS" || true; }

echo "=== Traces ==="
for span in turn/start codex.exec session_task.turn run_sampling_request handle_responses exec_command; do
  [ "$(count_spans "$span")" -gt 0 ] && pass "span ${span}" || fail "span ${span} missing"
done
turns=$(count_spans turn/start)
[ "$turns" -ge "$total" ] && pass "${turns} turn/start spans for ${total} turns" \
  || fail "${turns} turn/start spans for ${total} turns"
has "^ +-> gen_ai.usage.input_tokens: " && pass "gen_ai.usage.* on handle_responses" || fail "no gen_ai.usage.* on spans"
has "^ +-> codex.turn.token_usage.total_tokens: " \
  && pass "codex.turn.token_usage.* on session_task.turn" || fail "no turn token usage on spans"
parent_trace=$(jq -r .parent_trace "$RUN_FILE")
awk -v t="$parent_trace" '$1 == "turn/start" && $2 == t' <<<"$SPANS" | grep -q . \
  && pass "the turn run with TRACEPARENT joined that trace" || fail "no turn/start span in trace ${parent_trace}"
roots=$(awk '$3 == "-"' <<<"$SPANS" | grep -c . || true)
gap "${roots} root spans for ${total} turns; each turn is several traces, and auth and file reads are their own"
has "^ +-> gen_ai.operation.name: " \
  && pass "gen_ai.operation.name present" || gap "no gen_ai.operation.name; spans are named after internal functions"
has "^ +-> gen_ai.request.model: " \
  && pass "gen_ai.request.model present" || gap "the model is in the model attribute, not gen_ai.request.model"
has "^ +-> gen_ai.provider.name: " && pass "gen_ai.provider.name present" || gap "no gen_ai.provider.name"
has "^ +Status code +: Error" && pass "a span has status Error" || gap "no span has status Error, including the failed command"

echo "=== Metrics ==="
for metric in codex.api_request codex.api_request.duration_ms codex.turn.e2e_duration_ms codex.turn.ttft.duration_ms \
  codex.turn.token_usage codex.tool.call codex.tool.call.duration_ms codex.conversation.turn.count codex.thread.started; do
  has "^\s+-> Name: ${metric}$" && pass "metric ${metric}" || fail "metric ${metric} missing"
done
for token_type in input output cached_input; do
  has "-> token_type: Str\(${token_type}\)" && pass "token type ${token_type}" || fail "token type ${token_type} missing"
done
has "^\s+-> Name: gen_ai\.client\." && pass "gen_ai.client.* metrics present" || gap "no gen_ai.client.* metrics"

echo "=== Logs ==="
for event in codex.conversation_starts codex.user_prompt codex.api_request codex.tool_decision codex.tool_result \
  codex.sandbox_outcome; do
  [ "$(count_events "$event")" -gt 0 ] && pass "event ${event}" || fail "event ${event} missing"
done
has "-> prompt: Str\(\[REDACTED\]\)" && pass "prompt text redacted by default" || fail "prompt not redacted"
has "-> outcome: Str\(denied\)" && pass "sandbox denial recorded" || fail "no sandbox_outcome with outcome denied"
has "-> conversation.id: Str\($(jq -r '.turns[0].thread_id' "$RUN_FILE")\)" \
  && pass "conversation.id of the first thread present" || fail "conversation.id of the first thread not found"
stream_events=$(count_events codex.sse_event)
responses=$(grep -c -- "-> event.kind: Str(response.completed)" "$LOGS_FILE" || true)
[ "$stream_events" -gt 0 ] && [ "$stream_events" -eq "$responses" ] \
  && pass "${stream_events} codex.sse_event records, all response.completed" \
  || fail "${stream_events} codex.sse_event records, ${responses} response.completed; the collector filter is not applied"
has "-> input_token_count: " && pass "token counts on response.completed" || fail "no token counts on sse events"
# The success value of the tool_result for the command that exits non-zero.
failed_command=$(awk '/^LogRecord #/ {success=""; hit=0}
  /^ +-> success: Str\(/ {gsub(/.*Str\(|\)$/, ""); success=$0}
  /^ +-> arguments: Str\(.*missing\.txt/ {hit=1}
  /^Trace ID:/ {if (hit && success != "") print success; hit=0}' "$LOGS_FILE" | head -1)
case "$failed_command" in
  false) pass "tool_result reports failure for the command that exited non-zero" ;;
  true) gap "tool_result reports success for the command that exited non-zero" ;;
  *) gap "the failed-tool turn did not run its command, so tool_result was not checked" ;;
esac
correlated=$(grep -cE "^Trace ID: [0-9a-f]{32}$" "$LOGS_FILE" || true)
[ "$correlated" -gt 0 ] && pass "${correlated} log records carry a trace id" || fail "no log record carries a trace id"

echo "=== Scout exporter ==="
self_metrics=$(curl -sf "$COLLECTOR_METRICS") || stop "collector self-metrics not reachable at ${COLLECTOR_METRICS}"
for signal in spans metric_points log_records; do
  sent=$(awk -v m="otelcol_exporter_sent_${signal}" '$0 ~ "^"m"\\{exporter=\"otlp_http/b14\"" {s+=$NF} END {print s+0}' <<<"$self_metrics")
  failed=$(awk -v m="otelcol_exporter_send_failed_${signal}" '$0 ~ "^"m"\\{exporter=\"otlp_http/b14\"" {s+=$NF} END {print s+0}' <<<"$self_metrics")
  [ "$sent" -gt 0 ] && [ "$failed" -eq 0 ] && pass "${signal}: ${sent} sent, none failed" \
    || fail "${signal}: ${sent} sent, ${failed} failed"
done

echo ""
[ "$failures" -eq 0 ] && echo "All checks passed." || { echo "${failures} checks failed."; exit 1; }
