# Claude Code Telemetry

Runnable example that exports traces, metrics and logs from Claude Code
2.1.289 and the Claude Agent SDK 0.2.163 to an OpenTelemetry Collector, which
ships them to base14 Scout.

Claude Code does all the instrumentation. The rig only sets the telemetry
variables in `config/telemetry.env`, runs a few headless turns, and runs one
Agent SDK query under a parent span.

## Architecture

```text
  scripts/drive.sh
       |   claude -p, six headless turns
       |   scripts/sdk-trace.py, one Agent SDK query with TRACEPARENT
       v
  Claude Code CLI (on the host)
       |   OTLP/HTTP protobuf to localhost:4318
       |   model calls to Ollama on the host, or to Anthropic's API
       v
  otel-collector (otel/opentelemetry-collector-contrib:0.161.0)
       |   otlp receiver -> processors[memory_limiter, attributes, batch]
       |   -> exporters[otlp_http/b14, debug]
       v
   base14 Scout
```

## Prerequisites

- Docker with Compose v2.
- Claude Code on the host: `claude --version`.
- Ollama on the host with `qwen3.5:9B` pulled, and the larger-context tag
  the rig uses:

  ```bash
  ollama pull qwen3.5:9B
  ollama create qwen3.5-32k -f config/Modelfile
  ```

- Scout credentials exported in the shell: `SCOUT_CLIENT_ID`,
  `SCOUT_CLIENT_SECRET`, `SCOUT_TOKEN_URL`, `SCOUT_ENDPOINT` and
  `SCOUT_ENVIRONMENT`. Without them the collector still prints everything
  to its debug output, but the Scout export fails.
- `uv`, `jq` and `uuidgen`.

## Quick start

```bash
cd components/claude-code-telemetry
docker compose up -d
scripts/drive.sh
scripts/verify-scout.sh
```

`drive.sh` runs six headless turns in a scratch workspace under `.harness/`:
two in one session, one that runs a shell command, one that edits a file, one
whose tool call is denied, and one whose tool call fails. It then runs
`scripts/sdk-trace.py`, which starts a span and runs one Agent SDK query under
it. It writes `.harness/last-run.json`.

`verify-scout.sh` reads the collector's debug output and self-metrics for
that run. It checks the expected spans, metrics and log events, checks that
the Agent SDK query joined its parent trace, checks that the Scout exporter
sent all three signals with no failures, and lists the known gaps.

The run does not use your Claude Code settings or sessions. `drive.sh` clears
the `CLAUDE*`, `OTEL_*` and `ANTHROPIC_*` variables of the calling shell, sets
`CLAUDE_CONFIG_DIR` to `.harness/claude-config`, and starts the CLI with
`--bare`.

## Running against Anthropic's API

```bash
export ANTHROPIC_API_KEY=...
scripts/drive.sh hosted
scripts/verify-scout.sh
```

A hosted run spends tokens on `claude-haiku-4-5-20251001`, capped per turn by
`CLAUDE_RIG_TURN_BUDGET_USD`. Set `CLAUDE_RIG_MODEL` to use another model in
either mode.

On Anthropic's API, `verify-scout.sh` fails its trace structure checks with
Claude Code 2.1.289: after the first prompt, runs export no
`claude_code.interaction` span, and the other spans arrive as separate
traces. Metrics and events pass. `observed-telemetry.md` has the detail.

## What you'll see

- On Ollama, one trace per prompt: `claude_code.interaction`, with a
  `claude_code.llm_request` span per model request and a `claude_code.tool`
  span per tool call. The tool span has `claude_code.tool.blocked_on_user`
  and `claude_code.tool.execution` children.
- The Agent SDK query's `claude_code.interaction` under the script's
  `summarise_notes` span, in one trace.
- Six `claude_code.*` metrics, including `claude_code.token.usage` and
  `claude_code.cost.usage`.
- One log record per event, such as `claude_code.api_request` and
  `claude_code.tool_result`, carrying the trace id of its prompt.

`observed-telemetry.md` has the full capture from live runs, including the
gaps.

## Troubleshooting

### The Agent SDK query never finishes on Ollama

An Agent SDK session sends a second request that asks the model for a session
title. Uncapped, it asks for up to 32000 output tokens, and Ollama serves one
request at a time, so the query waits behind it. `drive.sh` sets
`CLAUDE_CODE_MAX_OUTPUT_TOKENS` to 1024 on Ollama runs. Set
`CLAUDE_RIG_LOCAL_OUTPUT_TOKENS` to change the cap.

### Turns return garbled or empty answers on Ollama

Check `ollama ps` for the context size of the loaded model. Claude Code's
prompt and tool definitions need more than Ollama's default context. The rig
runs `qwen3.5-32k`, built from `config/Modelfile` with `num_ctx` 32768.

### A port is already taken

Set `COLLECTOR_OTLP_HTTP_PORT`, `COLLECTOR_OTLP_GRPC_PORT`,
`COLLECTOR_HEALTH_PORT` and `COLLECTOR_METRICS_PORT` for
`docker compose up`. If you move the OTLP port, change
`OTEL_EXPORTER_OTLP_ENDPOINT` in `config/telemetry.env` to match. Pass the
health and metrics ports to `verify-scout.sh` as well.

### Scout exporter checks fail

Run `docker compose logs otel-collector` and look for `oauth2client` or
`otlp_http/b14` errors. Confirm the five `SCOUT_*` variables were exported
before `docker compose up`, then recreate the collector.

## Files

| File | Purpose |
| --- | --- |
| `compose.yaml` | The collector, with OTLP published on loopback. |
| `config/telemetry.env` | The Claude Code telemetry variables. |
| `config/otel-collector.yaml` | OTLP receiver, debug exporter and the Scout exporter. |
| `config/Modelfile` | The Ollama model tag with a 32768-token context. |
| `scripts/drive.sh` | Runs the headless turns and the Agent SDK query, and records the run. |
| `scripts/sdk-trace.py` | One Agent SDK query under a parent span, with pinned dependencies. |
| `scripts/verify-scout.sh` | Checks the run's telemetry and the Scout export. |
| `observed-telemetry.md` | Span tree, metrics, log events and gaps from live runs. |

## Clean up

```bash
docker compose down -v
ollama rm qwen3.5-32k
rm -rf .harness
```
