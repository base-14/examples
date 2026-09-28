#!/usr/bin/env bash
# Sends a fixed set of chat turns to the OpenClaw gateway so the diagnostics-otel plugin has runs to export.
# Needs curl and jq. Writes .harness/last-run.json for scripts/verify-scout.sh.
#
# Usage: scripts/drive.sh
set -euo pipefail

cd "$(dirname "$0")/.."

GATEWAY="${GATEWAY_URL:-http://localhost:18789}"
TOKEN="${OPENCLAW_GATEWAY_TOKEN:-openclaw-rig-token}"
RUN_FILE=".harness/last-run.json"

mkdir -p .harness
started_at=$(date -u +%Y-%m-%dT%H:%M:%SZ)
run_id=$(date -u +%H%M%S)
results="[]"

turn() {
  local name="$1" session="$2" model="$3" prompt="$4"
  local body status
  body=$(jq -n --arg m "$model" --arg u "conv:${session}" --arg p "$prompt" \
    '{model: $m, user: $u, messages: [{role: "user", content: $p}]}')
  status=$(curl -s -o /tmp/openclaw-turn.json -w "%{http_code}" --max-time 600 \
    "${GATEWAY}/v1/chat/completions" \
    -H "Authorization: Bearer ${TOKEN}" -H "Content-Type: application/json" -d "$body") || status=000
  echo "  ${name}: HTTP ${status}"
  results=$(jq --arg n "$name" --arg s "$session" --arg c "$status" \
    '. + [{name: $n, session: $s, status: ($c | tonumber)}]' <<<"$results")
}

echo "Driving the gateway at ${GATEWAY}"
turn "plain answer" "rig-a-${run_id}" "openclaw/default" "In one sentence, what is OpenTelemetry?"
turn "second turn" "rig-a-${run_id}" "openclaw/default" "Now say the same thing in five words."
turn "tool call" "rig-b-${run_id}" "openclaw/default" "Use a tool to list the files in your workspace, then tell me how many there are."
turn "unknown agent" "rig-c-${run_id}" "openclaw/no-such-agent" "Hello."

jq -n --arg s "$started_at" --argjson r "$results" '{started_at: $s, turns: $r}' > "$RUN_FILE"
echo "Wrote ${RUN_FILE}"
