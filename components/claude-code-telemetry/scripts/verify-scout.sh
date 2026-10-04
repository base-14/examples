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
mode=$(jq -r .mode "$RUN_FILE")
completed=$(jq '[.turns[] | select(.exit == 0 and .is_error == false)] | length' "$RUN_FILE")
total=$(jq '.turns | length' "$RUN_FILE")
[ "$completed" -ge $((total - 1)) ] && pass "${completed} of ${total} turns completed (${mode}, $(jq -r .model "$RUN_FILE"))" \
  || fail "only ${completed} of ${total} turns completed"
[ "$(curl -s -o /dev/null -w "%{http_code}" "$COLLECTOR_HEALTH" || echo 000)" = "200" ] \
  && pass "collector healthy" || stop "collector not healthy at ${COLLECTOR_HEALTH}"

finished=$(stat -c %Y "$RUN_FILE" 2>/dev/null || stat -f %m "$RUN_FILE")
wait_seconds=$(( finished + FLUSH_SECONDS - $(date +%s) ))
[ "$wait_seconds" -gt 0 ] && sleep "$wait_seconds"

LOGS_FILE=$(mktemp /tmp/claude-code-collector-XXXXXX)
trap 'rm -f "$LOGS_FILE"' EXIT
docker compose logs otel-collector --no-log-prefix --since "$(jq -r .started_at "$RUN_FILE")" > "$LOGS_FILE" 2>/dev/null || true
[ -s "$LOGS_FILE" ] || stop "no collector debug output for the run"

has() { grep -qE -- "$1" "$LOGS_FILE"; }
# Prints one line per span: name, trace id, and parent id or "-" for a root span.
SPANS=$(awk '
  /^Span #/ {trace=""; parent="-"}
  /^ +Trace ID +: / {trace=$NF}
  /^ +Parent ID +: / {parent=($NF == ":" ? "-" : $NF)}
  /^ +Name +: / {print $NF, trace, parent}' "$LOGS_FILE")
count_spans() { awk -v n="$1" '$1 == n' <<<"$SPANS" | grep -c . || true; }
spans_in_trace() { awk -v t="$1" '$2 == t {print $1}' <<<"$SPANS"; }

echo "=== Traces ==="
for span in claude_code.interaction claude_code.llm_request claude_code.tool claude_code.tool.execution; do
  [ "$(count_spans "$span")" -gt 0 ] && pass "span ${span}" || fail "span ${span} missing"
done
prompts=$(( $(jq '[.turns[] | select(.exit == 0)] | length' "$RUN_FILE") + $(jq 'if .sdk.trace_id then 1 else 0 end' "$RUN_FILE") ))
interactions=$(count_spans claude_code.interaction)
[ "$interactions" -ge "$prompts" ] && pass "${interactions} interaction spans for ${prompts} prompts" \
  || fail "${interactions} interaction spans for ${prompts} prompts"
orphans=$(awk '($1 == "claude_code.llm_request" || $1 == "claude_code.tool") && $3 == "-"' <<<"$SPANS" | grep -c . || true)
[ "$orphans" -eq 0 ] && pass "every model request and tool span has a parent" \
  || fail "${orphans} model request or tool spans arrived as trace roots"
has "-> session.id: Str\($(jq -r '.turns[0].session_id' "$RUN_FILE")\)" \
  && pass "session.id of the first turn present" || fail "session.id of the first turn not found"
if has "-> cache_read_tokens: Int\([1-9]"; then
  pass "cache read tokens on model requests"
else
  gap "no cache read tokens in this run"
fi
has "-> stop_reason: Str\(tool_use\)" && pass "stop_reason on model requests" || fail "no tool_use stop_reason"
has "-> input_tokens: Int\([1-9]" && pass "token counts on model requests" || fail "no input_tokens on model requests"
has "-> gen_ai.tool.call.id: Str\(" && pass "gen_ai.tool.call.id on tool spans" || fail "gen_ai.tool.call.id missing"
has "-> gen_ai.provider.name: " \
  && pass "gen_ai.provider.name present" || gap "model requests carry gen_ai.system, not gen_ai.provider.name"
has "-> gen_ai.operation.name: " \
  && pass "gen_ai.operation.name present" || gap "no gen_ai.operation.name; spans are named claude_code.*"
has "-> gen_ai.usage.input_tokens: " \
  && pass "gen_ai.usage.* present" || gap "token counts are input_tokens and output_tokens, not gen_ai.usage.*"
has "-> gen_ai.conversation.id: " \
  && pass "gen_ai.conversation.id present" || gap "no gen_ai.conversation.id; group by session.id"
if [ "$mode" = ollama ]; then
  has "-> gen_ai.system: Str\(anthropic\)" && gap "gen_ai.system reads anthropic on a local model"
fi

echo "=== Agent SDK trace ==="
sdk_trace=$(jq -r '.sdk.trace_id // empty' "$RUN_FILE")
if [ -z "$sdk_trace" ]; then
  fail "the Agent SDK query did not run"
else
  names=$(spans_in_trace "$sdk_trace")
  grep -qx "summarise_notes" <<<"$names" && pass "host span summarise_notes" || fail "host span missing from ${sdk_trace}"
  grep -qx "claude_code.interaction" <<<"$names" \
    && pass "claude_code.interaction joined the host trace" || fail "no claude_code.interaction in ${sdk_trace}"
  has "-> parent.source: Str\(env\)" && pass "parent.source is env" || fail "no interaction with parent.source env"
  has "-> app.entrypoint: Str\(sdk-py\)" && pass "app.entrypoint is sdk-py" || fail "no sdk-py entrypoint"
fi

echo "=== Metrics ==="
for metric in claude_code.session.count claude_code.token.usage claude_code.cost.usage claude_code.active_time.total \
  claude_code.lines_of_code.count claude_code.code_edit_tool.decision; do
  has "^\s+-> Name: ${metric}$" && pass "metric ${metric}" || fail "metric ${metric} missing"
done
for token_type in input output; do
  has "-> type: Str\(${token_type}\)" && pass "token type ${token_type}" || fail "token type ${token_type} missing"
done
has "-> start_type: Str\(resume\)" && pass "resumed session counted" || fail "no session with start_type resume"

echo "=== Logs ==="
for event in user_prompt api_request assistant_response tool_decision tool_result; do
  has "^Body: Str\(claude_code\.${event}\)$" && pass "event ${event}" || fail "event ${event} missing"
done
has "-> prompt: Str\(<REDACTED>\)" && pass "prompt text redacted by default" || fail "prompt not redacted"
has "-> decision: Str\(reject\)" && pass "rejected tool decision" || fail "no rejected tool decision"
has "-> success: Str\(false\)" && pass "failed tool result" || fail "no failed tool result"
has "-> cost_usd: Double\(" && pass "cost_usd on api_request" || fail "no cost_usd on api_request"
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
