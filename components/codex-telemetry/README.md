# Codex Telemetry

Runnable example that exports traces, metrics and logs from the OpenAI Codex
CLI 0.160.0 to an OpenTelemetry Collector, which ships them to base14 Scout.
The model runs on local Ollama.

Codex does all the instrumentation. The rig only sets the `[otel]` table in
`config/config.toml` and runs a few headless turns.

## Architecture

```text
  scripts/drive.sh
       |   codex exec, seven headless turns
       v
  Codex CLI (on the host, CODEX_HOME=.harness/codex-home)
       |   OTLP/HTTP protobuf to localhost:4318
       |   model calls to Ollama on the host (Responses API)
       v
  otel-collector (otel/opentelemetry-collector-contrib:0.161.0)
       |   otlp receiver -> processors[memory_limiter, filter, attributes, batch]
       |   -> exporters[otlp_http/b14, debug]
       v
   base14 Scout
```

## Prerequisites

- Docker with Compose v2.
- Node.js with `npx`, which fetches `@openai/codex@0.160.0`. Set `CODEX_CMD`
  to use an installed `codex` binary.
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
- `jq` and `perl`.

## Quick start

```bash
cd components/codex-telemetry
docker compose up -d
scripts/drive.sh
scripts/verify-scout.sh
```

`drive.sh` runs seven headless turns in a scratch workspace under
`.harness/`: two in one thread, one that runs a shell command, one that edits
a file, one whose command exits non-zero, one whose command the read-only
sandbox denies, and one started with `TRACEPARENT` set. It writes
`.harness/last-run.json`.

`verify-scout.sh` reads the collector's debug output and self-metrics for
that run. It checks the expected spans, metrics and log events, checks that
the turn with `TRACEPARENT` joined that trace, checks that the Scout exporter
sent all three signals with no failures, and lists the known gaps.

The run does not use your Codex config or sessions. `drive.sh` clears the
`OPENAI_*`, `CODEX_*` and `OTEL_*` variables of the calling shell and sets
`CODEX_HOME` to `.harness/codex-home`, with a copy of `config/config.toml`.
With no `OPENAI_API_KEY`, Codex cannot call a hosted model.

## What you'll see

- Several traces per turn. The main one is rooted at `turn/start`, with
  `session_task.turn`, a `run_sampling_request` per model request and an
  `exec_command` per shell command under it. Span names are Codex's internal
  function names.
- Over 40 `codex.*` metrics, including `codex.turn.token_usage`,
  `codex.turn.e2e_duration_ms`, `codex.api_request` and `codex.tool.call`.
- One log record per event, such as `codex.api_request` and
  `codex.tool_result`, carrying `conversation.id` and the trace id of its
  turn.

Codex writes one `codex.sse_event` record per stream chunk. The collector's
`filter/codex_stream_events` processor keeps only the `response.completed`
records. Codex writes two per model request, and one has the token counts.

`codex.tool_result` records include the command line and the command's
output. Do not point the rig at a workspace with content you would not
export.

`observed-telemetry.md` has the full capture from live runs, including the
gaps.

## Troubleshooting

### Codex starts downloading a model

Do not pass `--oss`. With it, Codex ignores `model` in the config and pulls
`gpt-oss:20b` into Ollama. The rig selects Ollama with
`model_provider = "ollama"` in `config/config.toml`.

### Turns return garbled or empty answers

Check `ollama ps` for the context size of the loaded model. Codex's prompt
and tool definitions need more than Ollama's default context. The rig runs
`qwen3.5-32k`, built from `config/Modelfile` with `num_ctx` 32768.

### A turn never finishes

`drive.sh` stops a turn after `TURN_TIMEOUT` seconds, 300 by default, and
records it as failed. Check that Ollama answers on `localhost:11434`.

### A port is already taken

Set `COLLECTOR_OTLP_HTTP_PORT`, `COLLECTOR_OTLP_GRPC_PORT`,
`COLLECTOR_HEALTH_PORT` and `COLLECTOR_METRICS_PORT` for
`docker compose up`. If you move the OTLP port, change the three endpoints in
`config/config.toml` to match. Pass the health and metrics ports to
`verify-scout.sh` as well.

### Scout exporter checks fail

Run `docker compose logs otel-collector` and look for `oauth2client` or
`otlp_http/b14` errors. Confirm the five `SCOUT_*` variables were exported
before `docker compose up`, then recreate the collector.

## Files

| File | Purpose |
| --- | --- |
| `compose.yaml` | The collector, with OTLP published on loopback. |
| `config/config.toml` | Codex model, provider and the `[otel]` exporters. |
| `config/otel-collector.yaml` | OTLP receiver, the stream event filter, debug exporter and the Scout exporter. |
| `config/Modelfile` | The Ollama model tag with a 32768-token context. |
| `scripts/drive.sh` | Runs the headless turns and records the run. |
| `scripts/verify-scout.sh` | Checks the run's telemetry and the Scout export. |
| `observed-telemetry.md` | Span tree, metrics, log events and gaps from live runs. |

## Clean up

```bash
docker compose down -v
ollama rm qwen3.5-32k
rm -rf .harness
```
