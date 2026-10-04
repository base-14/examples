#!/usr/bin/env bash
# Runs Claude Code headless on a few small tasks with telemetry on, then one Claude Agent SDK
# query under a parent span. Needs claude, uv, jq and uuidgen. Writes .harness/last-run.json
# for scripts/verify-scout.sh.
#
# Usage: scripts/drive.sh [ollama|hosted]
#   ollama  local model through Ollama's Anthropic-compatible endpoint (default); output
#           tokens per request capped by CLAUDE_RIG_LOCAL_OUTPUT_TOKENS (default 1024)
#   hosted  Anthropic's API; needs ANTHROPIC_API_KEY and spends tokens, capped per turn
#           by CLAUDE_RIG_TURN_BUDGET_USD (default 0.25)
set -euo pipefail

cd "$(dirname "$0")/.."

MODE="${1:-ollama}"
RIG="$PWD"
WORKSPACE="$RIG/.harness/workspace"
RUN_FILE="$RIG/.harness/last-run.json"
OUT_FILE="$RIG/.harness/turn.json"
HOSTED_KEY="${ANTHROPIC_API_KEY:-}"
TURN_BUDGET_USD="${CLAUDE_RIG_TURN_BUDGET_USD:-0.25}"
LOCAL_OUTPUT_TOKENS="${CLAUDE_RIG_LOCAL_OUTPUT_TOKENS:-1024}"
BUDGET=()

case "$MODE" in
  ollama) MODEL="${CLAUDE_RIG_MODEL:-qwen3.5-32k}" ;;
  hosted)
    MODEL="${CLAUDE_RIG_MODEL:-claude-haiku-4-5-20251001}"
    BUDGET=(--max-budget-usd "$TURN_BUDGET_USD")
    [ -n "$HOSTED_KEY" ] || { echo "hosted mode needs ANTHROPIC_API_KEY" >&2; exit 2; }
    ;;
  *) echo "usage: scripts/drive.sh [ollama|hosted]" >&2; exit 2 ;;
esac

# The run must not inherit telemetry, provider or session settings from the calling shell,
# and it keeps its sessions out of ~/.claude.
rig_env() {
  local name
  for name in $(compgen -e | grep -E '^(CLAUDE|OTEL_|ANTHROPIC_|ENABLE_|BETA_TRACING_|TRACEPARENT$|TRACESTATE$)'); do unset "$name"; done
  set -a
  # shellcheck disable=SC1091
  . "$RIG/config/telemetry.env"
  set +a
  export CLAUDE_CONFIG_DIR="$RIG/.harness/claude-config"
  export CLAUDE_RIG_MODEL="$MODEL" CLAUDE_RIG_WORKSPACE="$WORKSPACE" CLAUDE_RIG_TURN_BUDGET_USD="$TURN_BUDGET_USD"
  if [ "$MODE" = ollama ]; then
    export ANTHROPIC_BASE_URL="${OLLAMA_URL:-http://localhost:11434}" ANTHROPIC_API_KEY=ollama
    # Agent SDK sessions also request a session title. Uncapped, that request asks a local
    # model for up to 32000 tokens and holds Ollama's one slot while the query waits.
    export CLAUDE_CODE_MAX_OUTPUT_TOKENS="$LOCAL_OUTPUT_TOKENS"
  else
    export ANTHROPIC_API_KEY="$HOSTED_KEY"
  fi
}

rm -rf "$WORKSPACE"
mkdir -p "$WORKSPACE" "$RIG/.harness/claude-config"
printf 'greeting = "hello"\nprint(greeting)\n' > "$WORKSPACE/app.py"
printf 'Rig workspace for Claude Code telemetry runs.\n' > "$WORKSPACE/notes.txt"

started_at=$(date -u +%Y-%m-%dT%H:%M:%SZ)
cli_version=$(claude --version | awk '{print $1}')
results="[]"

turn() {
  local name="$1" prompt="$2"
  shift 2
  local status=0
  (
    rig_env
    cd "$WORKSPACE"
    claude -p "$prompt" --bare --model "$MODEL" --tools "Bash,Read,Edit" --output-format json ${BUDGET[@]+"${BUDGET[@]}"} "$@"
  ) > "$OUT_FILE" 2>/dev/null || status=$?
  jq -e . "$OUT_FILE" >/dev/null 2>&1 || echo '{}' > "$OUT_FILE"
  echo "  ${name}: exit ${status}, $(jq -r '"\(.num_turns // 0) model turns, \(.permission_denials // [] | length) denials"' "$OUT_FILE")"
  results=$(jq --arg n "$name" --argjson e "$status" --slurpfile o "$OUT_FILE" \
    '. + [{name: $n, exit: $e, session_id: $o[0].session_id, is_error: ($o[0].is_error != false),
           num_turns: ($o[0].num_turns // 0), cost_usd: ($o[0].total_cost_usd // 0),
           denials: ($o[0].permission_denials // [] | length)}]' <<<"$results")
}

echo "Driving Claude Code ${cli_version} on ${MODEL} (${MODE})"
session=$(uuidgen | tr '[:upper:]' '[:lower:]')
turn "plain answer" "In one sentence, what is OpenTelemetry?" --session-id "$session"
turn "second turn" "Now say the same thing in five words." --resume "$session"
turn "tool call" "Run ls with the Bash tool, then tell me how many files are in this directory." \
  --allowedTools "Bash(ls:*)"
turn "file edit" "In app.py, change the greeting from hello to hi. Read the file first, then use the Edit tool." \
  --permission-mode acceptEdits
turn "denied tool" "Run the command touch denied.txt with the Bash tool and tell me if it worked." \
  --permission-prompts none
turn "failed tool" "Read the file missing.txt with the Read tool and tell me what it says."

echo "Running the Agent SDK query"
sdk="{}"
sdk=$(rig_env; uv run --quiet "$RIG/scripts/sdk-trace.py" 2>"$RIG/.harness/sdk-stderr.log") \
  || { echo "  agent sdk: failed, see .harness/sdk-stderr.log"; sdk="{}"; }
echo "  agent sdk: trace $(jq -r '.trace_id // "none"' <<<"$sdk")"

jq -n --arg s "$started_at" --arg mode "$MODE" --arg model "$MODEL" --arg v "$cli_version" \
  --argjson r "$results" --argjson sdk "$sdk" \
  '{started_at: $s, mode: $mode, model: $model, cli_version: $v, turns: $r, sdk: $sdk}' > "$RUN_FILE"
rm -f "$OUT_FILE"
echo "Wrote ${RUN_FILE}"
