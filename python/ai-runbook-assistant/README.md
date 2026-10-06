# AI Runbook Assistant

An SRE incident-diagnosis service built on a LangChain tool-calling agent (RAG over a
runbook corpus, plus fixture-backed metric, log, and status tools), instrumented with
OpenTelemetry and exporting to [Base14 Scout](https://base14.io).

It shows how to instrument LangChain with the official OpenTelemetry GenAI
instrumentation, and what to add to it. The full guide is
[LangChain OpenTelemetry Instrumentation](https://docs.base14.io/instrument/apps/auto-instrumentation/langchain/).

## How to instrument LangChain with OpenTelemetry

1. The dependencies are pinned in `pyproject.toml`: the OpenTelemetry SDK and OTLP HTTP
   exporter, the FastAPI, SQLAlchemy, httpx and logging instrumentations, and
   `opentelemetry-instrumentation-genai-langchain`.
2. `setup_telemetry(engine=engine)` in `src/runbook_assistant/telemetry/setup.py` runs in the
   FastAPI lifespan. It registers OTLP trace, metric and log exporters, the span processor
   and exporter from `telemetry/genai_spans.py`, the httpx, logging and SQLAlchemy
   instrumentors, and `LangChainInstrumentor().instrument()`. `instrument_fastapi(app)` runs
   when the app is created and calls
   `FastAPIInstrumentor.instrument_app(app, excluded_urls="healthz,readyz")`.
3. `OTEL_SERVICE_NAME=ai-runbook-assistant`,
   `OTEL_EXPORTER_OTLP_ENDPOINT=http://otel-collector:4318` and
   `OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT=no_content` are set in `.env.example`
   and `compose.yaml`.

The LangChain instrumentation creates the `invoke_agent`, `chat`, `execute_tool` and
`retrieval` spans and the `gen_ai.client.token.usage` and `gen_ai.client.operation.duration`
histograms from LangChain's callbacks. This example adds the conversation ID, the data source
and the cost to those spans, PII scrubbing of captured content, an `embeddings` span, the
`base14.gen_ai.cost`, `.retry.count`, `.fallback.count` and `.error.count` counters, and OTLP
logs correlated with the active trace.

## Stack

- Python 3.14, FastAPI, async SQLAlchemy 2.0.
- LangChain 1.3 `create_agent` (LangGraph-backed).
- PostgreSQL 18 + pgvector for the runbook vector store.
- Ollama (`qwen3.5:9B` chat, `embeddinggemma` embeddings) by default, which runs locally
  without an API key. Anthropic, OpenAI, and Google are configurable alternatives.
- Retries and a configurable fallback model around every model call.
- OpenTelemetry SDK over OTLP/HTTP to an OpenTelemetry Collector, then to Scout.

## Prerequisites

- Docker with Compose.
- [uv](https://docs.astral.sh/uv/), for the tests and for running the app on the host.
- [Ollama](https://ollama.com) on the host, with the models pulled:

  ```bash
  ollama pull qwen3.5:9B      # tool-capable chat model
  ollama pull embeddinggemma  # 768-dim embeddings
  ```

  The app container reaches Ollama on the host through `host.docker.internal`. To run Ollama
  in Compose instead, start it with `docker compose --profile ollama up -d`, set
  `OLLAMA_BASE_URL=http://ollama:11434` in `.env`, and pull the two models inside that
  container.
- Base14 Scout credentials, to export to Scout: `SCOUT_CLIENT_ID`, `SCOUT_CLIENT_SECRET`,
  `SCOUT_TOKEN_URL` and `SCOUT_ENDPOINT`. Without them the example still runs and prints
  telemetry to the collector log.

## Quick start

```bash
cp .env.example .env
docker compose up -d --build
# wait for http://localhost:8000/healthz to return 200, then:
./scripts/test-api.sh
./scripts/verify-scout.sh
```

The collector exports to both Scout and a debug exporter. With the `SCOUT_*` values blank
the Scout export fails and is dropped, and everything still prints to the collector log.
Fill in the four `SCOUT_*` values in `.env` to export to Scout.

`verify-scout.sh` drives a diagnosis and checks the collector output: the span tree, that
every `chat` span comes from the LangChain instrumentation and none is nested in another,
the GenAI attributes, token and cost values, the in-trace database span, and the resource
attributes.

To check content capture and scrubbing, set
`OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT=span_only` for both the stack and the
script:

```bash
OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT=span_only docker compose up -d --build
OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT=span_only ./scripts/verify-scout.sh
```

### Run on the host

To run the app with `uv` instead of in a container, start only Postgres and the collector,
then `make run`:

```bash
cp .env.example .env
docker compose up -d postgres otel-collector
make run
```

`make run` points the app at the published Postgres port `5433`, the collector on
`localhost:4318` and Ollama on `localhost:11434`, and passes `--env-file .env` to uvicorn so
that the GenAI instrumentation reads `.env` too.

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
    save --> resp([answer + diagnosis_id])

    fixtures[/data/fixtures/services.json/] -.-> query_metrics & search_logs & get_service_status
```

- **search_runbooks** embeds the question with `embeddinggemma` and returns the closest
  runbooks from pgvector, such as `container-oom` or `p99-latency`.
- **query_metrics**, **search_logs** and **get_service_status** return a metric value,
  matching log lines and replica or deploy status for a service. They read fixed data
  from `services.json`, so runs are repeatable.
- The final **chat** call writes the root cause and remediation and cites the runbooks it
  used. The answer is saved with the request's `trace_id`, and the response returns the
  answer and the diagnosis ID.

Every model call goes through the retry and fallback middleware in `llm.py`.

The `/diagnose` route is `async`, and the agent runs on LangChain's sync `invoke`, which
blocks the event loop for the length of the run. The sync call keeps the trace nested (see
below). A service with concurrent requests would run it in a worker thread with the
context copied.

## What gets instrumented

One `POST /api/v1/diagnose` produces a single trace spanning HTTP, agent, LLM, tools,
vector search, and the database write:

```text
POST /api/v1/diagnose                 (FastAPI HTTP span)
├─ invoke_agent runbook_assistant     (agent root)
│  ├─ chat qwen3.5:9B                 (LLM: decide which tool to call)
│  ├─ execute_tool search_runbooks
│  │  └─ retrieval                    (pgvector)
│  │     ├─ embeddings embeddinggemma (Ollama embedding call)
│  │     └─ SELECT runbooks           (SQLAlchemy)
│  ├─ execute_tool query_metrics
│  ├─ execute_tool search_logs
│  ├─ chat qwen3.5:9B                 (LLM: synthesize the diagnosis)
│  └─ ...
└─ INSERT                             (SQLAlchemy, the saved diagnosis)
```

The example emits all three signals:

| Signal | Source | What you get |
| --- | --- | --- |
| Traces | LangChain, FastAPI, SQLAlchemy and HTTPX instrumentation, enriched by `telemetry/genai_spans.py` | The tree above, with tokens and cost on every `chat` span |
| Metrics | The LangChain instrumentation and `telemetry/metrics.py` | `gen_ai.client.token.usage` and `gen_ai.client.operation.duration` for chat calls from the instrumentation; `gen_ai.client.operation.duration` for embeddings and the `base14.gen_ai.cost`, `.retry.count`, `.fallback.count` and `.error.count` counters from the example |
| Logs | `LoggerProvider` + `LoggingHandler` in `telemetry/setup.py` | OTLP log records carrying `trace_id` and `span_id` |

The persisted `diagnoses` row also stores the `trace_id`, so a saved diagnosis links back
to the trace that produced it.

## What the instrumentation records

`LangChainInstrumentor` adds a callback handler to every LangChain callback manager, so it
sees each run of the agent, its model, its tools and its retriever:

| Span | Kind | What the instrumentation sets | What the example adds |
| --- | --- | --- | --- |
| `invoke_agent runbook_assistant` | `INTERNAL` | `gen_ai.operation.name`, `gen_ai.agent.name` from `create_agent(name=...)`, `gen_ai.conversation.id` | |
| `chat {model}` | `CLIENT` | `gen_ai.provider.name`, `gen_ai.request.model`, `gen_ai.response.model`, `gen_ai.request.temperature`, `gen_ai.usage.input_tokens`, `gen_ai.usage.output_tokens`, `gen_ai.response.finish_reasons`, `gen_ai.conversation.id` | `base14.gen_ai.cost_usd` |
| `execute_tool {name}` | `INTERNAL` | `gen_ai.tool.name`, `gen_ai.tool.type`, `gen_ai.tool.call.id`, `gen_ai.tool.description`, `gen_ai.agent.name` | `gen_ai.conversation.id` |
| `retrieval` | `CLIENT` | `gen_ai.provider.name` (the vector store class, `PGVector`) | `gen_ai.data_source.id`, `server.address`, `server.port`, `gen_ai.conversation.id`, `app.retrieval.chunk_count` |

The conversation ID is passed in the run's metadata, `config={"metadata":
{"conversation_id": ...}}`, which the instrumentation reads for agent and `chat` spans. The
span processor in `telemetry/genai_spans.py` puts it on tool and retrieval spans, and adds
the data source. `retriever.py` sets `app.retrieval.chunk_count` on the retrieval span,
which is current while the retriever runs. The span exporter adds the cost.

The agent runs on sync `invoke`, so the httpx, SQLAlchemy and embeddings spans nest under
the instrumentation's spans. LangChain's async API does not propagate context into the
run.

Embeddings have no LangChain callback, so `src/runbook_assistant/embeddings.py` wraps the
vector store's embedding client and emits the `embeddings {model}` span itself, under the
retrieval span.

The instrumentation reports `gen_ai.response.finish_reasons` as `["error"]` for successful
Ollama calls. It reads `finish_reason` or `stop_reason`, and `ChatOllama` reports
`done_reason`. It does not set `gen_ai.request.max_tokens` or `server.address` for
`ChatOllama` either.

To write your own callback handler instead, for chains the instrumentation does not cover,
see the [LangChain callback handler guide](https://docs.base14.io/guides/ai-observability/langchain-callback-handler/).

## Retry, fallback and errors

`src/runbook_assistant/llm.py` gives the agent a `ResilienceMiddleware` through
`create_agent(middleware=[...])`. Its `wrap_model_call` hook tries a call up to three times,
with exponential backoff from 1 s to 10 s between attempts. When those fail, it switches to
`FALLBACK_PROVIDER` / `FALLBACK_MODEL` with `request.override(model=...)` and tries that up
to three times. Every attempt runs the real chat model, so the trace holds one `chat` span
per attempt, named after the model that ran:

- A failed attempt's span is marked `ERROR` with the exception recorded. A retry increments
  `base14.gen_ai.retry.count` with `gen_ai.provider.name`, `error.type` and the attempt
  number.
- A switch to the fallback adds a `provider_fallback` event and
  `gen_ai.fallback.triggered=true` to the `invoke_agent` span, and increments
  `base14.gen_ai.fallback.count` and `base14.gen_ai.error.count`. The agent span is not
  marked failed when the fallback answers.
- A call that fails with no fallback increments `base14.gen_ai.error.count`.

With the defaults, the fallback is the same Ollama model as the primary, so no fallback
model is built and a switch never happens. Set `FALLBACK_PROVIDER` or `FALLBACK_MODEL` to
something different to see it.

The chat models are built with `max_retries=0` where the provider integration has one, so
the middleware is the only retry layer. LangChain also ships `ModelRetryMiddleware` and
`ModelFallbackMiddleware`; this example uses its own to record the counters.

On the HTTP edge, `src/runbook_assistant/errors.py` registers an exception handler that
records an unhandled error on the active span and returns a 500, and a middleware that
marks the server span `ERROR` for any response of 400 or above.

## GenAI semantic conventions

- Spans are named `{operation} {target}`: `invoke_agent runbook_assistant`, `chat {model}`,
  `execute_tool {name}`, `embeddings {model}`. The retrieval span is named `retrieval`, with
  no target, because the instrumentation does not know the data source.
- Metrics: `gen_ai.client.token.usage` (histogram, split by `gen_ai.token.type`) and
  `gen_ai.client.operation.duration` (histogram, seconds) keep their semconv names.
  Everything the conventions do not define carries a `base14.` prefix:
  `base14.gen_ai.cost` (counter, USD), `base14.gen_ai.retry.count`,
  `base14.gen_ai.fallback.count` and `base14.gen_ai.error.count`.
- Cost is computed in `src/runbook_assistant/cost.py` from `_shared/pricing.json` at the
  repository root, which Compose mounts read-only into the container, and attached as
  `base14.gen_ai.cost_usd` by the span exporter. Unknown models, Ollama included, cost 0.
- `LLM_PROVIDER=google` selects Gemini. The emitted `gen_ai.provider.name` is `gcp.gemini`,
  the semantic convention value.
- The resource carries both `deployment.environment.name` and lowercase `environment`,
  which is what Scout filters on. The collector upserts both.

## Prompt and completion capture

Content capture is off by default.

`OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT` takes `no_content` (the default),
`span_only`, `event_only` or `span_and_event`. With `span_only`, `chat` spans carry
`gen_ai.input.messages`, `gen_ai.output.messages`, `gen_ai.system_instructions` and
`gen_ai.tool.definitions`, `execute_tool` spans carry the call arguments and result, and
`retrieval` spans carry the query and the retrieved document IDs. The span exporter in
`telemetry/genai_spans.py` scrubs them with `src/runbook_assistant/pii.py` before export.
`event_only` and `span_and_event` send content as log events, which this example does not
scrub.

The instrumentation reads the variable once, when it is instrumented.

The scrubber replaces emails, IPv4 addresses, bearer tokens and API keys only. Check what your
prompts and tool results contain before enabling capture in production.

## Configuration

The Default column shows the app's default. Where `compose.yaml` or `make run` sets a
different value, the Notes column says so.

| Variable | Default | Notes |
| --- | --- | --- |
| `LLM_PROVIDER` | `ollama` | `ollama`, `anthropic`, `openai`, `google` |
| `LLM_MODEL` | `qwen3.5:9B` | Must be tool-capable |
| `FALLBACK_PROVIDER` | `ollama` | Used after the primary exhausts its attempts; no fallback is built when provider and model match the primary |
| `FALLBACK_MODEL` | `qwen3.5:9B` | Model for the fallback provider |
| `OLLAMA_BASE_URL` | `http://localhost:11434` | Compose sets `http://host.docker.internal:11434` |
| `OLLAMA_REASONING` | `false` | Lets a thinking model such as `qwen3.5` reason before answering |
| `ANTHROPIC_API_KEY` / `OPENAI_API_KEY` / `GOOGLE_API_KEY` | empty | Required only for that provider |
| `EMBEDDING_MODEL` | `embeddinggemma` | Vector store embeddings, 768-dim |
| `DATA_SOURCE_ID` | `runbooks` | Becomes `gen_ai.data_source.id` on retrieval spans |
| `DATABASE_URL` | `postgresql+asyncpg://postgres:postgres@localhost:5432/runbooks` | Compose uses `postgres:5432`; `make run` uses `localhost:5433` |
| `DEFAULT_TEMPERATURE` / `DEFAULT_MAX_TOKENS` | `0.0` / `4096` | Passed to every chat model |
| `LOG_LEVEL` | `INFO` | Root logger level |
| `OTEL_ENABLED` | `true` | Set `false` to disable telemetry |
| `OTEL_SERVICE_NAME` | `ai-runbook-assistant` | Becomes `service.name` |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | `http://localhost:4318` | Compose sets `http://otel-collector:4318` |
| `SCOUT_ENVIRONMENT` | `development` | Written to both environment resource keys |
| `OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT` | `no_content` | `no_content`, `span_only`, `event_only` or `span_and_event` |
| `SCOUT_CLIENT_ID` / `SCOUT_CLIENT_SECRET` / `SCOUT_TOKEN_URL` / `SCOUT_ENDPOINT` | empty | Collector to Scout OAuth; leave blank for local runs |

## API

| Method | Path | Body | Response |
| --- | --- | --- | --- |
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
  `embeddings`, with the saved diagnosis's `INSERT` span in the same trace.
- Tokens and cost per `chat` span, and the `gen_ai.client.*` and `base14.gen_ai.*` metrics
  over time.
- Logs filtered by `trace_id`.

Two dashboards ship under `dashboards/`, with the panel-by-panel notes in
`dashboards/DESIGN.md`:

- `operational.json` - token throughput, cost rate, tool and retrieval activity, errors,
  retries and fallbacks.
- `strategic.json` - cost and usage trends by model and provider.

## Project layout

```text
src/runbook_assistant/
├── telemetry/
│   ├── setup.py         # providers, OTLP exporters, resource, instrumentation
│   ├── genai_spans.py   # conversation ID, data source, cost and scrubbing on spans
│   └── metrics.py       # embeddings duration and base14.gen_ai.* counters
├── agent.py             # create_agent, system prompt, conversation ID, invocation
├── llm.py               # chat model factory, retry and fallback middleware
├── providers.py         # provider semconv names and server endpoints
├── embeddings.py        # instrumented embedding client
├── tools.py             # search_runbooks, query_metrics, search_logs, get_service_status
├── retriever.py         # pgvector store, runbook seeding, chunk count on the retrieval span
├── cost.py              # token -> USD from _shared/pricing.json
├── pii.py               # scrubbing for opt-in content capture
├── errors.py            # exception handler + HTTP span status
├── db.py                # async SQLAlchemy, diagnoses table
└── main.py              # FastAPI app, per-request conversation ID
```

Reading order for the instrumentation: `telemetry/setup.py`, `agent.py`,
`telemetry/genai_spans.py`, then `llm.py`.

## Testing

```bash
uv sync --extra dev
make test               # unit tests, no external services
make test-integration   # needs Docker (pgvector) and Ollama
make check              # ruff + mypy --strict + unit tests
```

The telemetry tests assert on exported spans through an in-memory exporter, so span
names, attributes, and parenting are covered without a running collector.

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
accepts `no_content`, `span_only`, `event_only` and `span_and_event` only, and logs a
warning for any other value. On the host, run the app with `make run`, which exports `.env`
to the process.

**Tool calls never happen.** The model must support tool calling. A model without it can
accept the request and answer without calling a tool. Use a tool-capable model, such as the
default `qwen3.5:9B`.

**Ollama connection refused from the container.** Use
`OLLAMA_BASE_URL=http://host.docker.internal:11434`. Inside the container, `localhost` is
the container itself.

**Cost is always 0.** The model is not a key in `_shared/pricing.json`, which is expected
for Ollama.

**Collector cannot authenticate to Scout.** All four `SCOUT_*` values must be set for the
OAuth extension in `otel-collector-config.yaml`. The collector log names the missing or
rejected credential.

## Adapting this to your own LangChain app

1. Copy `telemetry/setup.py` and adjust the resource attributes and OTLP endpoint.
2. Install `opentelemetry-instrumentation-genai-langchain` and call
   `LangChainInstrumentor().instrument()` after the tracer provider is set.
3. Copy `telemetry/genai_spans.py` for the attributes your traces need: conversation ID,
   data source, cost, scrubbing.
4. Name the agent with `create_agent(name=...)`, pass a conversation ID in the run's
   metadata, and keep content capture at `no_content` by default.
5. Add span assertions to your test suite using an in-memory exporter, so a refactor that
   drops an attribute fails CI.

## References

- [OTel GenAI semantic conventions](https://github.com/open-telemetry/semantic-conventions/tree/main/docs/gen-ai).
- [LangChain callbacks reference](https://reference.langchain.com/python/langchain-core/callbacks).
- [OpenTelemetry GenAI instrumentation for Python](https://github.com/open-telemetry/opentelemetry-python-genai).
- [Base14 Scout docs](https://docs.base14.io).
