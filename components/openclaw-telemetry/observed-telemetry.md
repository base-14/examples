# observed-telemetry.md - openclaw

live-captured 2026-09-28T05:10Z, from an empty state volume

## Run context

- **Monitored software**: `ghcr.io/openclaw/openclaw:2026.9.6` (OpenClaw 2026.9.6, `eb377ac`), gateway mode,
  Node.js 24.19.0. The bundled `diagnostics-otel` plugin exports over OTLP/HTTP (protobuf) to the collector at
  `otel-collector:4318`, with `sampleRate` 1.0, `flushIntervalMs` 10000 and `captureContent` off.
  `OTEL_SEMCONV_STABILITY_OPT_IN=gen_ai_latest_experimental` is set.
- **Model**: local Ollama `qwen3.5:9B` over the native `/api/chat` API, `num_ctx` 32768. The agent prompt is about
  12K tokens (38K characters of system prompt and 12 tool definitions), so Ollama's default 4096 context fails
  every turn with a context overflow.
- **Collector**: `otel/opentelemetry-collector-contrib:0.161.0`, OTLP receiver, debug exporter (verbosity detailed)
  and `otlp_http/b14` to Scout with `oauth2client`.
- **Traffic driver**: `scripts/drive.sh`, four turns on the gateway's OpenAI-compatible `/v1/chat/completions`:
  two turns in one session (`user: conv:rig-a-<run>`), one turn that calls the `ls` tool, and one to an unknown agent,
  which returns 400 before any run starts.

## Traces

One trace per turn, rooted at `openclaw.harness.run`:

```text
openclaw.harness.run                  INTERNAL
└─ openclaw.run                       INTERNAL  openclaw.outcome, openclaw.channel=webchat, openclaw.trigger=user
   ├─ openclaw.context.assembled      INTERNAL
   ├─ chat qwen3.5:9B                 CLIENT    one per model call
   └─ openclaw.tool.execution         INTERNAL  one per tool call
```

- `chat {model}` carries `gen_ai.operation.name`, `gen_ai.provider.name`, `gen_ai.request.model`,
  `gen_ai.usage.input_tokens`, `gen_ai.usage.output_tokens`, `gen_ai.usage.cache_read.input_tokens` and
  `gen_ai.usage.cache_creation.input_tokens`, plus `openclaw.model_call.*` prompt sizes, request and response
  bytes, and time to first byte.
- `openclaw.tool.execution` carries `gen_ai.operation.name=execute_tool`, `gen_ai.tool.name`,
  `gen_ai.tool.call.id` and `openclaw.tool.source`.
- `openclaw.model.usage` is emitted once per run as its own root trace, not under `openclaw.harness.run`.
- `openclaw.diagnostic.phase` spans are separate root traces for gateway startup phases, with `openclaw.phase`
  naming the phase and `openclaw.phase.cpu_*` attributes.
- No span carries `gen_ai.operation.name=invoke_agent`; the agent run is `openclaw.run` with `openclaw.*`
  attributes only, and there is no `gen_ai.agent.name`.

## Metrics

All metrics are cumulative and re-exported on every flush, including while the gateway is idle.

| Metric | Type | Attributes |
| --- | --- | --- |
| `gen_ai.client.token.usage` | Histogram | `gen_ai.operation.name`, `gen_ai.provider.name`, `gen_ai.request.model`, `gen_ai.token.type` |
| `gen_ai.client.operation.duration` | Histogram | `gen_ai.operation.name`, `gen_ai.provider.name`, `gen_ai.request.model` |
| `openclaw.tokens` | Sum | `openclaw.token` (input, output, prompt, total, cache_read), `openclaw.agent`, `openclaw.channel`, `openclaw.model`, `openclaw.provider` |
| `openclaw.run.duration_ms` | Histogram | `openclaw.agent`, `openclaw.channel`, `openclaw.model`, `openclaw.outcome`, `openclaw.provider` |
| `openclaw.harness.duration_ms` | Histogram | `openclaw.channel`, `openclaw.harness.id`, `openclaw.harness.plugin`, `openclaw.model`, `openclaw.outcome`, `openclaw.provider` |
| `openclaw.context.tokens` | Histogram | `openclaw.context` (used, limit), `openclaw.agent`, `openclaw.channel`, `openclaw.model`, `openclaw.provider` |
| `openclaw.model_call.duration_ms` | Histogram | `openclaw.api`, `openclaw.transport`, `openclaw.model`, `openclaw.provider`, `openclaw.model_call.observation_unit` |
| `openclaw.model_call.time_to_first_byte_ms` | Histogram | as `openclaw.model_call.duration_ms` |
| `openclaw.model_call.request_bytes` | Histogram | as `openclaw.model_call.duration_ms` |
| `openclaw.model_call.response_bytes` | Histogram | as `openclaw.model_call.duration_ms` |
| `openclaw.tool.execution.duration_ms` | Histogram | `gen_ai.tool.name`, `openclaw.tool.source`, `openclaw.tool.params.kind` |
| `openclaw.queue.depth` | Histogram | `openclaw.lane` (main, session), `openclaw.channel` |
| `openclaw.queue.wait_ms` | Histogram | `openclaw.lane` |
| `openclaw.queue.lane.enqueue` | Sum | `openclaw.lane` |
| `openclaw.queue.lane.dequeue` | Sum | `openclaw.lane` |
| `openclaw.session.state` | Sum | `openclaw.state` (processing, idle), `openclaw.reason` (run_started, run_completed) |
| `openclaw.gateway.event_loop.delay_max_ms` | Histogram | none |
| `openclaw.gateway.event_loop.observed_ms` | Sum | none |
| `openclaw.memory.rss_bytes` | Histogram | none |
| `openclaw.memory.heap_used_bytes` | Histogram | none |
| `openclaw.memory.heap_total_bytes` | Histogram | none |
| `openclaw.memory.external_bytes` | Histogram | none |
| `openclaw.memory.array_buffers_bytes` | Histogram | none |
| `openclaw.gc.duration_ms` | Histogram | none |
| `openclaw.telemetry.exporter.events` | Sum | `openclaw.exporter`, `openclaw.signal`, `openclaw.status`, `openclaw.reason` |

Model-usage metrics carry `openclaw.agent=unknown` for turns that arrive on the OpenAI-compatible endpoint.

## Logs

Gateway log lines are exported as OTLP log records. The body is the constant string `log`; the message fields are
attributes (`openclaw.subsystem`, `openclaw.log.level`, `openclaw.error` and others, plus `code.function` and
`code.lineno`). Records written during a run carry that run's trace id and span id, so they correlate with the
trace in Scout. Records written outside a run carry no trace id.

## Gaps on 2026.9.6

- No session or conversation id on any exported span, metric or log. The gateway derives a session key from the
  request's `user` field, but the plugin does not export it, so `gen_ai.conversation.id` is absent.
- `openclaw agent exec` runs export nothing (issue #128806, open). Not exercised by this rig, which drives the
  gateway.
- No `gen_ai.response.*` attributes on `chat {model}` spans.
- The OpenAI-compatible HTTP endpoint ignores an incoming `traceparent`: a turn sent with one starts a new trace.
  OpenClaw's docs describe per-request `traceparent` on the gateway WebSocket protocol only; this rig does not
  exercise it.

## Scout export

All three signals reached Scout through `otlp_http/b14` with no send failures: 29 spans, 126 metric points and
21 log records at the time `scripts/verify-scout.sh` ran.
