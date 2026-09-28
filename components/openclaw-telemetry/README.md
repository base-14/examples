# OpenClaw Telemetry

Runnable example that exports traces, metrics and logs from an OpenClaw 2026.9.6
gateway through its bundled `diagnostics-otel` plugin to an OpenTelemetry
Collector, which ships them to base14 Scout. The agent's model runs on local
Ollama.

The plugin does all the instrumentation. The rig only turns it on in
`config/openclaw.json` and drives a few chat turns through the gateway.

## Architecture

```text
  scripts/drive.sh
       |   POST /v1/chat/completions on 127.0.0.1:18789
       v
  openclaw-gateway (ghcr.io/openclaw/openclaw:2026.9.6)
       |   diagnostics-otel plugin, OTLP/HTTP protobuf
       |   model calls to Ollama on the host (native /api/chat)
       v
  otel-collector (otel/opentelemetry-collector-contrib:0.161.0)
       |   otlp receiver -> processors[memory_limiter, attributes, batch]
       |   -> exporters[otlp_http/b14, debug]
       v
   base14 Scout
```

## Prerequisites

- Docker with Compose v2.
- Ollama on the host with `qwen3.5:9B` pulled: `ollama pull qwen3.5:9B`.
- Scout credentials exported in the shell: `SCOUT_CLIENT_ID`,
  `SCOUT_CLIENT_SECRET`, `SCOUT_TOKEN_URL`, `SCOUT_ENDPOINT` and
  `SCOUT_ENVIRONMENT`. Without them the collector still prints everything
  to its debug output, but the Scout export fails.
- `curl` and `jq`.

## Quick start

```bash
cd components/openclaw-telemetry
docker compose up -d
docker compose ps          # wait for openclaw-gateway to be healthy
scripts/drive.sh
scripts/verify-scout.sh
```

`drive.sh` sends four turns to the gateway's OpenAI-compatible endpoint: two
in one session, one that calls a tool, and one to an agent that does not
exist. It writes `.harness/last-run.json`.

`verify-scout.sh` reads the collector's debug output and self-metrics for
that run. It checks the expected spans, metrics and log records, checks that
the Scout exporter sent all three signals with no failures, and lists the
known gaps.

The gateway listens on `127.0.0.1` only. Its token defaults to
`openclaw-rig-token`; set `OPENCLAW_GATEWAY_TOKEN` for both
`docker compose up` and `drive.sh` to change it.

## What you'll see

- One trace per turn: `openclaw.harness.run`, then `openclaw.run`, with a
  `chat {model}` span per model call and an `openclaw.tool.execution` span
  per tool call under it.
- `gen_ai.*` attributes on model calls and tool calls, and the
  `gen_ai.client.token.usage` and `gen_ai.client.operation.duration`
  metrics. The rest of the metrics use the `openclaw.*` prefix.
- Gateway log records, carrying the trace id of the run they were written in.

`observed-telemetry.md` has the full capture from a live run, including the
gaps: no session or conversation id, and no `invoke_agent` span.

## Troubleshooting

### Every turn returns HTTP 500

Check `docker compose logs openclaw-gateway` for `Context overflow`. The
agent prompt is about 12K tokens, and Ollama's default context of 4096
tokens rejects it. The model entry in `config/openclaw.json` sets `num_ctx`
to 32768; keep it if you change the model.

### A port is already taken

Set `COLLECTOR_HEALTH_PORT` and `COLLECTOR_METRICS_PORT` for both
`docker compose up` and `verify-scout.sh` to move the collector's health
check (13133) and self-metrics (8888).

### Scout exporter checks fail

Run `docker compose logs otel-collector` and look for `oauth2client` or
`otlp_http/b14` errors. Confirm the five `SCOUT_*` variables were exported
before `docker compose up`, then recreate the collector.

## Files

| File | Purpose |
| --- | --- |
| `compose.yaml` | Collector, a one-shot config copy into the state volume, and the gateway. |
| `config/openclaw.json` | Gateway, Ollama provider, the `diagnostics-otel` plugin and its `diagnostics.otel` settings. |
| `config/otel-collector.yaml` | OTLP receiver, debug exporter and the Scout exporter. |
| `scripts/drive.sh` | Sends the four turns and records the run. |
| `scripts/verify-scout.sh` | Checks the run's telemetry and the Scout export. |
| `observed-telemetry.md` | Span tree, metrics, log shape and gaps from a live run. |

## Clean up

```bash
docker compose down -v
```

`-v` also removes the gateway's state volume, which holds its sessions.
