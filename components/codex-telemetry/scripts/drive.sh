#!/usr/bin/env bash
# Runs Codex headless on a few small tasks with telemetry on, on a local Ollama model.
# Needs npx (or a codex binary), jq and perl. Writes .harness/last-run.json for
# scripts/verify-scout.sh.
#
# Usage: scripts/drive.sh
#   CODEX_CMD        command that runs Codex (default: npx -y @openai/codex@0.160.0)
#   TURN_TIMEOUT     seconds before a turn is stopped (default 300)
set -euo pipefail

cd "$(dirname "$0")/.."

RIG="$PWD"
WORKSPACE="$RIG/.harness/workspace"
RUN_FILE="$RIG/.harness/last-run.json"
OUT_FILE="$RIG/.harness/turn.jsonl"
RUN_CODEX="${CODEX_CMD:-npx -y @openai/codex@0.160.0}"
TURN_TIMEOUT="${TURN_TIMEOUT:-300}"
PARENT_TRACE="4bf92f3577b34da6a3ce929d0e0e4736"

# The run must not inherit provider keys or telemetry settings from the calling shell, and it
# keeps its config and sessions out of ~/.codex. No OPENAI_API_KEY means no hosted calls.
rig_env() {
  local name
  for name in $(compgen -e | grep -E '^(OPENAI_|CODEX_|OTEL_|TRACEPARENT$|TRACESTATE$)'); do unset "$name"; done
  export CODEX_HOME="$RIG/.harness/codex-home"
}

# Stops the turn and its children when it overruns.
with_timeout() {
  perl -e 'my $s = shift; my $pid = fork; if (!$pid) { setpgrp(0, 0); exec @ARGV }
    $SIG{ALRM} = sub { kill "TERM", -$pid; exit 124 }; alarm $s; waitpid($pid, 0);
    exit($? & 127 ? 128 + ($? & 127) : $? >> 8)' "$@"
}

rm -rf "$WORKSPACE" "$RIG/.harness/codex-home"
mkdir -p "$WORKSPACE" "$RIG/.harness/codex-home"
cp "$RIG/config/config.toml" "$RIG/.harness/codex-home/config.toml"
printf 'greeting = "hello"\nprint(greeting)\n' > "$WORKSPACE/app.py"
printf 'Rig workspace for Codex telemetry runs.\n' > "$WORKSPACE/notes.txt"

started_at=$(date -u +%Y-%m-%dT%H:%M:%SZ)
# shellcheck disable=SC2086
codex_version=$(rig_env; $RUN_CODEX --version | awk '{print $NF}')
results="[]"
thread=""

turn() {
  local name="$1" prompt="$2"
  shift 2
  local status=0
  (
    rig_env
    cd "$WORKSPACE"
    # shellcheck disable=SC2086
    with_timeout "$TURN_TIMEOUT" env "$@" $RUN_CODEX exec $EXEC_ARGS --skip-git-repo-check --json "$prompt" < /dev/null
  ) > "$OUT_FILE" 2>/dev/null || status=$?
  thread=$(jq -r 'select(.type == "thread.started") | .thread_id' "$OUT_FILE" 2>/dev/null | head -1 || true)
  local completed commands
  completed=$(jq -s '[.[] | select(.type == "turn.completed")] | length' "$OUT_FILE" 2>/dev/null || echo 0)
  commands=$(jq -s '[.[] | select(.type == "item.completed" and .item.type == "command_execution")] | length' "$OUT_FILE" 2>/dev/null || echo 0)
  echo "  ${name}: exit ${status}, ${commands} commands"
  results=$(jq --arg n "$name" --argjson e "$status" --arg t "$thread" --argjson c "$completed" --argjson k "$commands" \
    '. + [{name: $n, exit: $e, thread_id: $t, completed: ($c > 0), commands: $k}]' <<<"$results")
}

echo "Driving Codex ${codex_version} on the model in config/config.toml"
EXEC_ARGS=""
turn "plain answer" "In one sentence, what is OpenTelemetry?"
[ -n "$thread" ] || { echo "the first turn started no thread; is Ollama running with the configured model?" >&2; exit 1; }
EXEC_ARGS="resume $thread"
turn "second turn" "Now say the same thing in five words."
EXEC_ARGS=""
turn "tool call" "Run ls, then tell me how many files are in this directory."
turn "file edit" "In app.py, change the greeting from hello to hi."
turn "failed tool" "Run the command cat missing.txt and tell me what it printed."
EXEC_ARGS="--sandbox read-only"
turn "sandbox denial" "Run the command touch denied.txt and tell me if it worked."
EXEC_ARGS=""
turn "trace parent" "Reply with the single word ok." "TRACEPARENT=00-${PARENT_TRACE}-00f067aa0ba902b7-01"

jq -n --arg s "$started_at" --arg v "$codex_version" --arg p "$PARENT_TRACE" --argjson r "$results" \
  '{started_at: $s, codex_version: $v, parent_trace: $p, turns: $r}' > "$RUN_FILE"
rm -f "$OUT_FILE"
echo "Wrote ${RUN_FILE}"
