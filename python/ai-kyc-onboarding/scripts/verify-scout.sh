#!/usr/bin/env bash
# Checks the collector's debug output and self-metrics for the last scripts/test-api.sh run.
# Needs curl, jq, uv and docker compose. Do not restart the collector between the run and
# this script, because its self-metrics reset on restart.
#
# Usage: scripts/verify-scout.sh [--allow-partial]
#        COLLECTOR_LOG=/tmp/collector.log scripts/verify-scout.sh
set -euo pipefail

cd "$(dirname "$0")/.."

BASE_URL="${API_URL:-http://localhost:8000}"
COLLECTOR_HEALTH="${COLLECTOR_HEALTH_URL:-http://localhost:13133}"
COLLECTOR_METRICS="${COLLECTOR_METRICS_URL:-http://localhost:8888/metrics}"
RUN_FILE=".harness/last-run.json"
FLUSH_SECONDS="${FLUSH_SECONDS:-30}"

green() { printf "\033[32m%s\033[0m" "$1"; }
red()   { printf "\033[31m%s\033[0m" "$1"; }
cyan()  { printf "\033[36m%s\033[0m" "$1"; }
dim()   { printf "\033[90m%s\033[0m" "$1"; }

stop() {
  echo "  $(red "FAIL") $1"
  exit 2
}

echo ""
cyan "=== Prerequisites ==="; echo

if [ ! -s "$RUN_FILE" ]; then
  stop "no ${RUN_FILE}; run scripts/test-api.sh first"
fi
echo "  $(dim "run started $(jq -r .started_at "$RUN_FILE"), $(jq '.scenarios | length' "$RUN_FILE") scenarios, harness passed=$(jq -r .passed "$RUN_FILE")")"

LOGS_FILE=$(mktemp /tmp/kyc-collector-XXXXXX)
METRICS_FILE=$(mktemp /tmp/kyc-collector-metrics-XXXXXX)
trap 'rm -f "$LOGS_FILE" "$METRICS_FILE"' EXIT

if [ -n "${COLLECTOR_LOG:-}" ]; then
  echo "  $(dim "reading the saved collector output ${COLLECTOR_LOG}; skipping the live checks")"
  cp "$COLLECTOR_LOG" "$LOGS_FILE"
else
  status=$(curl -s -o /dev/null -w "%{http_code}" "${BASE_URL}/health" || echo 000)
  [ "$status" = "200" ] || stop "API not healthy at ${BASE_URL}/health (${status})"
  echo "  $(green "PASS") API healthy"
  status=$(curl -s -o /dev/null -w "%{http_code}" "$COLLECTOR_HEALTH" || echo 000)
  [ "$status" = "200" ] || stop "collector not healthy at ${COLLECTOR_HEALTH} (${status})"
  echo "  $(green "PASS") collector healthy"

  finished=$(stat -f %m "$RUN_FILE" 2>/dev/null || stat -c %Y "$RUN_FILE")
  wait_seconds=$(( finished + FLUSH_SECONDS - $(date +%s) ))
  if [ "$wait_seconds" -gt 0 ]; then
    echo "  $(dim "waiting ${wait_seconds}s for the last batches to reach the collector")"
    sleep "$wait_seconds"
  fi

  docker compose logs otel-collector --no-log-prefix --since "$(jq -r .started_at "$RUN_FILE")" \
    > "$LOGS_FILE" 2>/dev/null
  curl -sf "$COLLECTOR_METRICS" > "$METRICS_FILE" \
    || stop "collector self-metrics not reachable at ${COLLECTOR_METRICS}"
fi
[ -s "$LOGS_FILE" ] || stop "no collector debug output for the run"
echo "  $(dim "collector debug output: $(wc -c < "$LOGS_FILE" | tr -d ' ') bytes")"

set +e
uv run --quiet python -m scripts.verify_cases "$@" "$RUN_FILE" "$LOGS_FILE" "$METRICS_FILE" \
  | sed -e "s/^  PASS /  $(green PASS) /" -e "s/^  FAIL /  $(red FAIL) /" \
        -e "s/^\(=== .* ===\)$/$(printf '\033[36m')\1$(printf '\033[0m')/"
result=${PIPESTATUS[0]}
set -e
exit "$result"
