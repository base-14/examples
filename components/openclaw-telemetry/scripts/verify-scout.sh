#!/usr/bin/env bash
# Checks the collector's debug output and self-metrics for the last scripts/drive.sh run.
# Needs curl, jq and docker compose. Do not restart the collector between the run and
# this script, because its self-metrics reset on restart.
#
# Usage: scripts/verify-scout.sh
set -euo pipefail

cd "$(dirname "$0")/.."

GATEWAY="${GATEWAY_URL:-http://localhost:18789}"
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
answered=$(jq '[.turns[] | select(.status == 200)] | length' "$RUN_FILE")
[ "$answered" -ge 3 ] && pass "${answered} turns answered" || fail "only ${answered} turns answered"

[ "$(curl -s -o /dev/null -w "%{http_code}" "${GATEWAY}/healthz" || echo 000)" = "200" ] \
  && pass "gateway healthy" || stop "gateway not healthy at ${GATEWAY}/healthz"
[ "$(curl -s -o /dev/null -w "%{http_code}" "$COLLECTOR_HEALTH" || echo 000)" = "200" ] \
  && pass "collector healthy" || stop "collector not healthy at ${COLLECTOR_HEALTH}"

finished=$(stat -c %Y "$RUN_FILE" 2>/dev/null || stat -f %m "$RUN_FILE")
wait_seconds=$(( finished + FLUSH_SECONDS - $(date +%s) ))
[ "$wait_seconds" -gt 0 ] && sleep "$wait_seconds"

LOGS_FILE=$(mktemp /tmp/openclaw-collector-XXXXXX)
trap 'rm -f "$LOGS_FILE"' EXIT
docker compose logs otel-collector --no-log-prefix --since "$(jq -r .started_at "$RUN_FILE")" > "$LOGS_FILE" 2>/dev/null
[ -s "$LOGS_FILE" ] || stop "no collector debug output for the run"

echo "=== Traces ==="
for span in openclaw.harness.run openclaw.run openclaw.context.assembled openclaw.tool.execution; do
  grep -qE "^\s+Name\s+: ${span}$" "$LOGS_FILE" && pass "span ${span}" || fail "span ${span} missing"
done
grep -qE "^\s+Name\s+: chat " "$LOGS_FILE" && pass "span chat {model}, CLIENT" || fail "no chat {model} span"
grep -q "gen_ai.provider.name: Str(ollama)" "$LOGS_FILE" \
  && pass "gen_ai.provider.name on model calls" || fail "gen_ai.provider.name missing"
grep -q "gen_ai.usage.input_tokens" "$LOGS_FILE" && pass "gen_ai.usage.* on model calls" || fail "gen_ai.usage.* missing"
grep -q "gen_ai.operation.name: Str(execute_tool)" "$LOGS_FILE" \
  && pass "execute_tool on tool spans" || fail "execute_tool missing"
grep -q "gen_ai.operation.name: Str(invoke_agent)" "$LOGS_FILE" \
  && pass "invoke_agent span present" || gap "no invoke_agent span; agent runs are openclaw.run only"
grep -q "gen_ai.conversation.id" "$LOGS_FILE" \
  && pass "gen_ai.conversation.id present" || gap "no session or conversation id on spans"

echo "=== Metrics ==="
for metric in gen_ai.client.token.usage gen_ai.client.operation.duration openclaw.tokens openclaw.run.duration_ms \
  openclaw.model_call.duration_ms openclaw.tool.execution.duration_ms openclaw.queue.depth openclaw.session.state; do
  grep -qE "^\s+-> Name: ${metric}$" "$LOGS_FILE" && pass "metric ${metric}" || fail "metric ${metric} missing"
done

echo "=== Logs ==="
records=$(grep -c "LogRecord #" "$LOGS_FILE" || true)
correlated=$(grep -cE "^Trace ID: [0-9a-f]{32}$" "$LOGS_FILE" || true)
[ "$records" -gt 0 ] && pass "${records} log records" || fail "no log records"
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
