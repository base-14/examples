# AI Runbook Assistant

An SRE incident-diagnosis service built on a LangChain tool-calling agent (RAG over a
runbook corpus, plus fixture-backed metric, log, and status tools), instrumented end to
end with OpenTelemetry and viewable in [Base14 Scout](https://base14.io).

The focus is how you instrument LangChain with OpenTelemetry using the official
OpenTelemetry GenAI instrumentation, and what to add to it.

## How to instrument LangChain with OpenTelemetry

1. Install `opentelemetry-api`, `opentelemetry-sdk`, `opentelemetry-exporter-otlp-proto-http`,
   `opentelemetry-instrumentation-fastapi`, `opentelemetry-instrumentation-sqlalchemy`,
   `opentelemetry-instrumentation-httpx`, `opentelemetry-instrumentation-logging` and
   `opentelemetry-instrumentation-genai-langchain` from `pyproject.toml`.
2. Call `setup_telemetry(engine=engine)` from `src/runbook_assistant/telemetry/setup.py` in
   the FastAPI lifespan. It registers OTLP trace, metric and log exporters, the span
   processor and exporter from `telemetry/genai_spans.py`, the httpx, logging and SQLAlchemy
   instrumentors, and `LangChainInstrumentor().instrument()`. `instrument_fastapi(app)` then
   calls `FastAPIInstrumentor.instrument_app(app, excluded_urls="healthz,readyz")`.
3. Set `OTEL_SERVICE_NAME=ai-runbook-assistant`,
   `OTEL_EXPORTER_OTLP_ENDPOINT=http://otel-collector:4318` and
   `OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT=no_content` as in `.env.example` and
   `compose.yaml`.

The LangChain instrumentation creates the `invoke_agent`, `chat`, `execute_tool` and
`retrieval` spans and the `gen_ai.client.token.usage` and `gen_ai.client.operation.duration`
histograms from LangChain's callbacks. This example adds the conversation ID, the data source
and the cost to those spans, PII scrubbing of captured content, an
`embeddings` span, the `base14.gen_ai.cost`, `.retry.count`, `.fallback.count` and
`.error.count` counters, and OTLP logs correlated with the active trace. The full guide is
[LangChain OpenTelemetry Instrumentation](https://docs.base14.io/instrument/apps/auto-instrumentation/langchain/).

## What you will learn

- What the official LangChain instrumentation records for a `create_agent` agent, and what
  it leaves to you.
- How to add application context, cost and PII scrubbing to the instrumentation's spans
  with a span processor and a span exporter.
- How to retry and fall back between models with `create_agent` middleware, so every
  attempt is one span.
- How to keep an LLM trace joined to the rest of your stack, so the HTTP span, the agent,
  the tool calls, the vector search, and the database write all land in one trace.

## Stack

- Python 3.14, FastAPI, async SQLAlchemy 2.0.
- LangChain 1.x `create_agent` (LangGraph-backed).
- PostgreSQL 18 + pgvector for the runbook vector store.
- Ollama (`qwen3.5:9B` chat, `embeddinggemma` embeddings) by default, so no API key and
  no per-run cost. Anthropic, OpenAI, and Google are drop-in alternatives.
- Tenacity retries and a configurable fallback provider around every model call.
- OpenTelemetry SDK over OTLP/HTTP to an OpenTelemetry Collector, then to Scout.

## Prerequisites

- Docker with Compose.
- [uv](https://docs.astral.sh/uv/) for local development.
- [Ollama](https://ollama.com) on the host, with the models pulled:

  ```bash
  ollama pull qwen3.5:9B      # tool-capable chat model
  ollama pull embeddinggemma  # 768-dim embeddings
  ```

  Ollama stays on the host rather than in Compose to keep the image small and reuse your
  model cache. The container reaches it through `host.docker.internal`. If you would rather
  run it in Compose, start the bundled service with `docker compose --profile ollama up -d`
  and pull the two models inside that container.

## Quick start

```bash
cp .env.example .env
docker compose up -d --build
# wait for http://localhost:8000/healthz to return 200, then:
./scripts/test-api.sh
./scripts/verify-scout.sh
```

The collector exports to both Scout and a debug exporter. With the `SCOUT_*` values blank
the Scout export fails and is dropped, and everything still prints to the collector log, so
this works without credentials. Fill in `SCOUT_CLIENT_ID`, `SCOUT_CLIENT_SECRET`,
`SCOUT_TOKEN_URL` and `SCOUT_ENDPOINT` in `.env` to export for real.

`verify-scout.sh` drives a diagnosis and asserts against the collector output: span tree
shape, GenAI attributes, token and cost values, the in-trace database span, and the
resource attributes. Use it to confirm a change has not dropped a signal.

Set `OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT=span_only` for the stack and the
script to check content capture and scrubbing:

```bash
OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT=span_only docker compose up -d --build
OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT=span_only ./scripts/verify-scout.sh
```

## Agent workflow

`POST /api/v1/diagnose` hands the incident question to one tool-calling agent built with
LangChain `create_agent`. The model decides which tool to call next, reads the result,
and repeats until it answers without a tool call. The system prompt tells it to start
with a runbook and then follow that runbook's diagnostic steps.

```mermaid
flowchart TD
    req([POST /api/v1/diagnose]) --> llm
    llm{"chat model<br/>tool call or answer?"}
    llm -->|tool call| tools
    subgraph tools [Tools]
        search_runbooks["search_runbooks<br/>pgvector over 12 runbooks"]
        query_metrics["query_metrics"]
        search_logs["search_logs"]
        get_service_status["get_service_status"]
    end
    tools -->|tool result| llm
    llm -->|final answer| save[(diagnoses table)]
    save --> resp([diagnosis + trace_id])

    fixtures[/data/fixtures/services.json/] -.-> query_metrics & search_logs & get_service_status
```

- **search_runbooks** embeds the question with `embeddinggemma` and returns the closest
  runbooks from pgvector, such as `container-oom` or `p99-latency`.
- **query_metrics**, **search_logs** and **get_service_status** return a metric value,
  matching log lines and replica or deploy status for a service. They read fixed data
  from `services.json`, so runs are repeatable.
- The final **chat** call writes the root cause and remediation and cites the runbooks it
  used. The answer is saved with the request's `trace_id`.

Every model call goes through the retry and fallback middleware in `llm.py`.

## What gets instrumented

One `POST /api/v1/diagnose` produces a single trace spanning HTTP, agent, LLM, tools,
vector search, and the database write:

```text
POST /api/v1/diagnose                 (FastAPI HTTP span)
└─ invoke_agent runbook_assistant     (agent root)
   ├─ chat qwen3.5:9B                 (LLM: decide which tool to call)
   ├─ execute_tool search_runbooks
   │  └─ retrieval runbooks           (pgvector)
   │     └─ embeddings embeddinggemma (Ollama embedding call)
   ├─ execute_tool query_metrics
   ├─ execute_tool search_logs
   ├─ chat qwen3.5:9B                 (LLM: synthesize the diagnosis)
   └─ ...
   INSERT INTO diagnoses              (SQLAlchemy span, same trace)
```

The example emits all three signals:

| Signal | Source | What you get |
|---|---|---|
| Traces | LangChain, FastAPI, SQLAlchemy and HTTPX instrumentation, enriched by `telemetry/genai_spans.py` | The tree above, with tokens and cost on every `chat` span |
| Metrics | the LangChain instrumentation and `telemetry/metrics.py` | `gen_ai.client.token.usage` and `gen_ai.client.operation.duration` from the instrumentation; `base14.gen_ai.cost`, `.retry.count`, `.fallback.count` and `.error.count` from the example |
| Logs | `LoggerProvider` + `LoggingHandler` in `telemetry/setup.py` | OTLP log records carrying `trace_id` and `span_id`, so logs correlate with their trace |

The persisted `diagnoses` row also stores the `trace_id`, so a saved diagnosis links back
to the trace that produced it.

## What the instrumentation records

`LangChainInstrumentor` adds a callback handler to every LangChain callback manager, so it
sees each run of the agent, its model, its tools and its retriever:

| Span | Kind | What the instrumentation sets | What `telemetry/genai_spans.py` adds |
|---|---|---|---|
| `invoke_agent runbook_assistant` | `INTERNAL` | `gen_ai.operation.name`, `gen_ai.agent.name` from `create_agent(name=...)`, `gen_ai.conversation.id` | |
| `chat {model}` | `CLIENT` | `gen_ai.provider.name`, `gen_ai.request.model`, `gen_ai.response.model`, `gen_ai.request.temperature`, `gen_ai.request.max_tokens`, `gen_ai.usage.input_tokens`, `gen_ai.usage.output_tokens`, `gen_ai.response.finish_reasons` | `gen_ai.conversation.id`, `base14.gen_ai.cost_usd` |
| `execute_tool {name}` | `INTERNAL` | `gen_ai.tool.name`, `gen_ai.tool.type`, `gen_ai.tool.call.id`, `gen_ai.tool.description` | `gen_ai.conversation.id` |
| `retrieval` | `CLIENT` | `gen_ai.provider.name` (the vector store class, `PGVector`) | `gen_ai.data_source.id`, `server.address`, `server.port` |

The conversation ID is passed in the run's metadata, `config={"metadata":
{"conversation_id": ...}}`, which the instrumentation reads for agent and `chat` spans. The
span processor puts it on the others. The agent name comes from `create_agent(name=...)`. The agent runs on sync `invoke`, so the httpx, SQLAlchemy
and embeddings spans nest under the instrumentation's spans. LangChain's async API does not
propagate context into the run.

Embeddings have no LangChain callback, so `src/runbook_assistant/embeddings.py` wraps the
vector store's embedding client and emits the `embeddings {model}` span itself, under the
retrieval span.

The instrumentation reports `gen_ai.response.finish_reasons` as `["error"]` for successful
Ollama calls. It reads `finish_reason` or `stop_reason`, and `ChatOllama` reports
`done_reason`.

To write your own callback handler instead, for chains the instrumentation does not cover,
see the [LangChain callback handler guide](https://docs.base14.io/guides/ai-observability/langchain-callback-handler/).

## Retry, fallback and errors

`src/runbook_assistant/llm.py` gives the agent a `ResilienceMiddleware` through
`create_agent(middleware=[...])`. Its `wrap_model_call` hook retries a call three times with
exponential backoff from 1 s to 10 s, then switches to `FALLBACK_PROVIDER` / `FALLBACK_MODEL`
with `request.override(model=...)`. Every attempt runs the real chat model, so the trace
holds one `chat` span per attempt, named after the model that ran:

- A failed attempt's span is marked `ERROR` with the exception recorded. A retry increments
  `base14.gen_ai.retry.count` with `gen_ai.provider.name`, `error.type` and the attempt
  number.
- A switch to the fallback adds a `provider_fallback` event and
  `gen_ai.fallback.triggered=true` to the `invoke_agent` span, and increments
  `base14.gen_ai.fallback.count` and `base14.gen_ai.error.count`. The agent span is not
  marked failed, because the request succeeded.
- A call that fails outright increments `base14.gen_ai.error.count`.

The chat models are built with `max_retries=0` where the provider integration has one, so
the middleware is the only retry layer. LangChain also ships `ModelRetryMiddleware` and
`ModelFallbackMiddleware`; this example uses its own to record the counters.

On the HTTP edge, `src/runbook_assistant/errors.py` registers an exception handler that
records an unhandled error on the active span and returns a 500, and a middleware that
marks the server span `ERROR` for any response of 400 or above.

## GenAI semantic conventions

- Spans are named `{operation} {target}`: `invoke_agent`, `chat`, `execute_tool`,
  `retrieval`, `embeddings`. No `gen_ai.` prefix on the operation inside the span name.
- Metrics: `gen_ai.client.token.usage` (histogram, split by `gen_ai.token.type`) and
  `gen_ai.client.operation.duration` (histogram, seconds) keep their semconv names.
  Everything the conventions do not define carries a `base14.` prefix:
  `base14.gen_ai.cost` (counter, USD), `base14.gen_ai.retry.count`,
  `base14.gen_ai.fallback.count` and `base14.gen_ai.error.count`.
- Cost is computed locally in `src/runbook_assistant/cost.py` from `_shared/pricing.json`
  and attached as `base14.gen_ai.cost_usd` by the span exporter. Compose mounts `_shared/` read-only into the
  container. Unknown models, Ollama included, cost 0.
- `LLM_PROVIDER=google` selects Gemini, matching the gateway contract's provider key. The
  emitted `gen_ai.provider.name` is `gcp.gemini`, which is the semantic convention value.
- Resource carries the dual-key environment: `deployment.environment.name` plus
  lowercase `environment`, which is what Scout filters on. Set on the resource and
  upserted by the collector.
- The LangChain instrumentation always emits the latest experimental GenAI conventions
  and does not read `OTEL_SEMCONV_STABILITY_OPT_IN`.

Companion guide:
[LangChain auto-instrumentation](https://docs.base14.io/instrument/apps/auto-instrumentation/langchain).

## Prompt and completion capture

Content capture is **off by default**. Prompts and completions often carry incident detail,
hostnames, and customer identifiers, and once exported they follow your telemetry backend's
retention and access rules.

`OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT` takes `no_content` (the default),
`span_only`, `event_only` or `span_and_event`. `true` and `false` are not valid; the
instrumentation logs a warning and captures nothing. With `span_only`, `chat` spans carry
`gen_ai.input.messages`, `gen_ai.output.messages`, `gen_ai.system_instructions` and
`gen_ai.tool.definitions`, `execute_tool` spans carry the call arguments and result, and
`retrieval` spans carry the query and the retrieved document IDs. The span exporter in
`telemetry/genai_spans.py` scrubs them with `src/runbook_assistant/pii.py` (emails, IPv4,
bearer tokens, API keys) before export. `event_only` and `span_and_event` also emit log
events, which this example does not scrub.

The instrumentation reads the variable once, when it is instrumented.

The scrubber is a backstop, not a compliance control. Decide what may leave your boundary
before enabling capture in production.

## Configuration

| Variable | Default | Purpose |
|---|---|---|
| `LLM_PROVIDER` | `ollama` | `ollama`, `anthropic`, `openai`, `google` |
| `LLM_MODEL` | `qwen3.5:9B` | Must be tool-capable |
| `FALLBACK_PROVIDER` | `ollama` | Used after the primary exhausts its retries |
| `FALLBACK_MODEL` | `qwen3.5:9B` | Model for the fallback provider |
| `OLLAMA_BASE_URL` | `http://host.docker.internal:11434` | `http://localhost:11434` when running the app directly on the host |
| `ANTHROPIC_API_KEY` / `OPENAI_API_KEY` / `GOOGLE_API_KEY` | empty | Required only for that provider |
| `EMBEDDING_MODEL` | `embeddinggemma` | Vector store embeddings, 768-dim |
| `DATABASE_URL` | local Postgres | pgvector-enabled PostgreSQL |
| `OTEL_ENABLED` | `true` | Set `false` to disable telemetry entirely |
| `OTEL_SERVICE_NAME` | `ai-runbook-assistant` | Becomes `service.name` |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | `http://localhost:4318` | OTLP/HTTP collector endpoint |
| `SCOUT_ENVIRONMENT` | empty | Written to both environment resource keys |
| `OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT` | `no_content` | `no_content`, `span_only`, `event_only` or `span_and_event` |
| `SCOUT_CLIENT_ID` / `SCOUT_CLIENT_SECRET` / `SCOUT_TOKEN_URL` / `SCOUT_ENDPOINT` | empty | Collector to Scout OAuth, leave blank for local runs |

## API

| Method | Path | Body | Response |
|---|---|---|---|
| `POST` | `/api/v1/diagnose` | `{"question": "..."}` | `{"answer": "...", "diagnosis_id": "..."}` |
| `GET` | `/healthz` | - | `{"status": "ok"}` |
| `GET` | `/readyz` | - | `{"status": "ready"}` |

```bash
curl -X POST http://localhost:8000/api/v1/diagnose \
  -H 'content-type: application/json' \
  -d '{"question": "checkout pods are being OOMKilled, what do I do?"}'
```

Health endpoints are excluded from HTTP tracing, so probe traffic produces no spans.

## Viewing telemetry in Scout

With `SCOUT_*` set, open Scout and look at:

- A diagnosis trace: `invoke_agent` to `chat`, `execute_tool`, `retrieval` and
  `embeddings`, with the `diagnoses` INSERT span in the same trace.
- Tokens and cost per `chat` span, and the `gen_ai.client.*` and `base14.gen_ai.*` metrics
  over time.
- Logs filtered by `trace_id` to sit alongside the request that emitted them.

Two dashboards ship under `dashboards/`, with the panel-by-panel rationale in
`dashboards/DESIGN.md`:

- `operational.json` - token throughput, cost rate, tool and retrieval activity, errors,
  retries and fallbacks.
- `strategic.json` - cost and usage trends by model and provider.

## Project layout

```text
src/runbook_assistant/
├── telemetry/
│   ├── setup.py         # providers, OTLP exporters, resource, instrumentation
│   ├── genai_spans.py   # agent, conversation, data source, cost and scrubbing on spans
│   └── metrics.py       # gen_ai.client.* and base14.gen_ai.* instruments
├── agent.py             # create_agent, system prompt, invocation
├── llm.py               # chat model factory, retry and fallback middleware
├── providers.py         # provider semconv names and server endpoints
├── embeddings.py        # instrumented embedding client
├── tools.py             # search_runbooks, query_metrics, search_logs, get_service_status
├── retriever.py         # pgvector store + runbook seeding
├── cost.py              # token -> USD from _shared/pricing.json
├── pii.py               # scrubbing for opt-in content capture
├── errors.py            # exception handler + HTTP span status
├── db.py                # async SQLAlchemy, diagnoses table
└── main.py              # FastAPI app, per-request conversation ID
```

Reading order for the instrumentation: `setup.py`, then `genai_spans.py`, then `llm.py`.

## Testing

```bash
uv sync --extra dev
uv run pytest -m "not integration"   # unit tests, no external services
uv run pytest -m integration         # needs Docker (pgvector) and Ollama
make check                           # ruff + mypy --strict + unit tests
```

The telemetry tests assert on exported spans through an in-memory exporter, so span
names, attributes, and parenting are covered without a running collector. This catches
instrumentation regressions in CI rather than in a dashboard.

## Troubleshooting

**No spans in the collector.** Confirm `OTEL_EXPORTER_OTLP_ENDPOINT` points at the
collector's OTLP/HTTP port (`4318`, not `4317`) and includes no path. The exporters
append `/v1/traces`, `/v1/metrics`, and `/v1/logs` themselves. Check `OTEL_ENABLED`.

**Spans arrive but no `chat` spans.** `LangChainInstrumentor().instrument()` did not run,
or ran before the tracer provider was set. Check the order in `telemetry/setup.py`. The
instrumentation also checks that the `langchain` package is installed, and instruments
nothing if it is not.

**Two `chat` spans per model call, one inside the other.** A chat model wraps another chat
model. The instrumentation traces both, so tokens count twice. Use `create_agent`
middleware for retries and fallbacks instead of a wrapper model.

**`gen_ai.response.finish_reasons` is `["error"]` on a successful call.** Expected on
Ollama. The instrumentation does not read `ChatOllama`'s `done_reason`.

**No content on spans with capture set to `true`.** Use `span_only`. The instrumentation
accepts `no_content`, `span_only`, `event_only` and `span_and_event` only.

**Tool calls never happen.** The model must support tool calling. Smaller local models
often accept the request and answer without calling a tool. Stay on a tool-capable model
such as `qwen3.5:9B`.

**Ollama connection refused from the container.** Use
`OLLAMA_BASE_URL=http://host.docker.internal:11434`. Inside the container, `localhost` is
the container itself.

**Cost is always 0.** The model is not a key in `_shared/pricing.json`, which is expected
for Ollama. Local inference has no per-token price.

**Collector cannot authenticate to Scout.** All four `SCOUT_*` values must be set for the
OAuth extension in `otel-collector-config.yaml`. The collector log names the missing or
rejected credential.

## Adapting this to your own LangChain app

1. Copy `telemetry/setup.py` and adjust the resource attributes and OTLP endpoint.
2. Install `opentelemetry-instrumentation-genai-langchain` and call
   `LangChainInstrumentor().instrument()` after the tracer provider is set.
3. Copy `telemetry/genai_spans.py` for the attributes your traces need: agent name,
   conversation ID, data source, cost, scrubbing.
4. Name the agent with `create_agent(name=...)`, pass a conversation ID in the run's
   metadata, and keep content capture at `no_content` by default.
5. Add span assertions to your test suite using an in-memory exporter, so a refactor that
   drops an attribute fails CI.

## References

- [OTel GenAI semantic conventions](https://github.com/open-telemetry/semantic-conventions/tree/main/docs/gen-ai)
- [LangChain callbacks](https://python.langchain.com/docs/concepts/callbacks/)
- [OpenTelemetry GenAI instrumentation for Python](https://github.com/open-telemetry/opentelemetry-python-genai)
- [Base14 Scout docs](https://docs.base14.io)
