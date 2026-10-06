# AI Content Quality Agent

A FastAPI service that reviews, improves and scores text with LlamaIndex, with Promptfoo
evals and OpenTelemetry export to [Base14 Scout](https://base14.io). The model calls are
traced by the official OpenTelemetry GenAI packages for the SDKs LlamaIndex calls.

**Stack**: Python 3.14 · FastAPI · LlamaIndex · Promptfoo · OpenTelemetry · Base14 Scout

The full guide is
[LlamaIndex OpenTelemetry Instrumentation](https://docs.base14.io/instrument/apps/auto-instrumentation/llamaindex/).

## How to instrument LlamaIndex with OpenTelemetry

1. The dependencies are pinned in `pyproject.toml`: the OpenTelemetry SDK and OTLP HTTP
   exporter, the FastAPI and logging instrumentations, and the GenAI instrumentations
   `opentelemetry-instrumentation-genai-openai`, `opentelemetry-instrumentation-genai-anthropic`
   and `opentelemetry-instrumentation-google-genai`. There is no official LlamaIndex package;
   LlamaIndex's integrations call these SDKs, and the SDK packages trace the calls.
2. `setup_telemetry(service_name=..., otlp_endpoint=...)` in `src/content_quality/telemetry.py`
   runs at import time in `src/content_quality/main.py`, before the app is created. It
   registers OTLP trace, metric and log exporters, the span processor and exporter from
   `src/content_quality/genai_spans.py`, `LoggingInstrumentor()`, and `instrument()` on
   `OpenAIInstrumentor`, `AnthropicInstrumentor` and `GoogleGenAiSdkInstrumentor`.
   `instrument_fastapi(app)` runs after the app is created and calls
   `FastAPIInstrumentor.instrument_app(app, excluded_urls="health", exclude_spans=["receive", "send"])`.
3. Ollama is reached through its OpenAI-compatible `/v1` endpoint with LlamaIndex's
   `OpenAILike`, so the OpenAI package traces it too.
4. `SERVICE_NAME=ai-content-quality`, `OTLP_ENDPOINT=http://otel-collector:4318`,
   `OTEL_SDK_DISABLED=false` and `OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT=no_content`
   are set in `compose.yaml` and `.env.example`. This example reads its own `SERVICE_NAME`
   and `OTLP_ENDPOINT` variables rather than the standard `OTEL_SERVICE_NAME` and
   `OTEL_EXPORTER_OTLP_ENDPOINT`.

The GenAI instrumentations create a span and the `gen_ai.client.token.usage` and
`gen_ai.client.operation.duration` metrics for every SDK call: `chat {model}` for the OpenAI
and Anthropic SDKs, Ollama included, and `generate_content {model}` for the Google Gen AI
SDK. This example adds:

- The endpoint, the content type and length, the provider and the cost on those spans, and
  PII scrubbing of their captured content, in `src/content_quality/genai_spans.py`.
- Cost, retry, fallback and error counters, in `src/content_quality/services/llm.py`.
- `gen_ai.evaluation.result` events and a score histogram, in
  `src/content_quality/services/analyzer.py`.
- HTTP request metrics, in `src/content_quality/middleware/metrics.py`, and OTLP logs
  correlated with traces.

## Prerequisites

- Python 3.14 and [uv](https://docs.astral.sh/uv/).
- Docker with Compose.
- [Ollama](https://ollama.com) on the host, with the model pulled, for the default provider:

  ```bash
  ollama pull qwen3.5:9B
  ```

  Or an API key for OpenAI, Anthropic or Google.
- Node.js with `npx`, for the Promptfoo evals, and an `OPENAI_API_KEY` to run them.
- `_shared/pricing.json` at the repository root, which ships with the repo; the app reads
  prices from it at startup.
- Base14 Scout credentials, to export to Scout: `SCOUT_CLIENT_ID`, `SCOUT_CLIENT_SECRET`,
  `SCOUT_TOKEN_URL` and `SCOUT_ENDPOINT` in `.env`. Without them the example still runs and
  prints telemetry to the collector log.

## Quick Start

### With Docker

```bash
cp .env.example .env
docker compose up -d --build

# Run API smoke tests
./scripts/test-api.sh

# Check the telemetry that reached the collector
./scripts/verify-scout.sh

# Tear down
docker compose down -v
```

This starts the app on port 8000 and the OpenTelemetry Collector. The collector is
configured with `memory_limiter`, `batch` processing, and `otlp_http` export to Base14 Scout
with OAuth2 authentication, retry, and gzip compression.

An `ollama` service is available under `docker compose --profile ollama up -d` for hosts
without a local Ollama install; when using it, set `OLLAMA_BASE_URL=http://ollama:11434` in
`.env` so the app reaches the container instead of the host.

### On the host

```bash
make dev
cp .env.example .env
docker compose up -d otel-collector
make run
```

`make run` points the app at the collector on `localhost:4318` and Ollama on
`localhost:11434`, and passes `--env-file .env` to uvicorn. The telemetry settings, such as
`OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT`, `OTEL_SDK_DISABLED` and
`SCOUT_ENVIRONMENT`, are read from the process environment, so they need `.env` exported
this way.

### Checks

```bash
make check   # lint, typecheck and unit tests
```

## API Endpoints

| Endpoint | Method | Description |
| --- | --- | --- |
| `/health` | GET | Liveness check |
| `/review` | POST | Review content for quality issues (hyperbole, bias, unsourced claims) |
| `/improve` | POST | Suggest specific text improvements with before/after |
| `/score` | POST | Score content 0-100 with clarity/accuracy/engagement/originality breakdown |

All analysis endpoints accept a JSON body with `content` (string, max 10,000 chars) and optional `content_type` (one of
`general`, `marketing`, `technical`, `blog`).

```bash
# Health check
curl http://localhost:8000/health

# Review content for quality issues
curl -X POST http://localhost:8000/review \
  -H "Content-Type: application/json" \
  -d '{"content": "This revolutionary product is the absolute best!", "content_type": "marketing"}'

# Get improvement suggestions
curl -X POST http://localhost:8000/improve \
  -H "Content-Type: application/json" \
  -d '{"content": "The thing is really good and stuff.", "content_type": "blog"}'

# Score content quality (0-100)
curl -X POST http://localhost:8000/score \
  -H "Content-Type: application/json" \
  -d '{"content": "Kubernetes orchestrates containerized workloads across clusters.", "content_type": "technical"}'
```

## Eval Pipeline

Prompts are evaluated offline with [Promptfoo](https://promptfoo.dev). The pipeline has 22
test cases across marketing, technical, and blog content, plus adversarial inputs (prompt
injection, whitespace, non-English, mixed HTML/markdown). Each prompt family has its own
config under `evals/`, so tests run only against the prompt they were written for:

| Config | Prompts | Test cases |
| --- | --- | --- |
| `evals/review.yaml` | `review_v1`, `review_v2` | 8 review + 4 adversarial |
| `evals/improve.yaml` | `improve_v1` | 5 |
| `evals/score.yaml` | `score_v1` | 5 |

Running the eval needs `OPENAI_API_KEY` in the environment. It calls `gpt-4o-mini` for the
prompts under test and for the `llm-rubric` grader. Multiple prompt versions, such as
`review_v1` and `review_v2`, run against the same test cases, and `make eval-view` shows
them side by side.

```bash
# Check the configs, prompt paths, datasets and assertion files without calling a model
make eval-validate

# Run all three configs (no cache, forces fresh LLM calls)
make eval

# View results in browser with side-by-side comparison
make eval-view
```

**CI**: The GitHub Actions workflow (`.github/workflows/eval.yml` at the repository root)
runs on pushes to `main` and on pull requests that touch the prompts, the evals, the
analyzer or the workflow, and can be started manually. It runs `promptfoo validate config`,
which needs no API key. The full `promptfoo eval` runs only when the `OPENAI_API_KEY`
repository secret is set, and fails if the pass rate across the three configs drops below
95%.

Prompt files live in `prompts/` as YAML with separate `system` and `user` templates. Test
datasets and custom assertion functions live in `evals/`.

## Observability

Each request produces one trace, from the HTTP span to the model call spans.

### Instrumentation Approach

LlamaIndex has no official OpenTelemetry package. Its OpenAI, OpenAI-compatible, Anthropic and
Google Gen AI integrations call those SDKs, and the OpenTelemetry GenAI instrumentations for the
SDKs record each call. `genai_spans.py` adds the endpoint, the content type and length, the
provider, the cost and scrubbing. LlamaIndex's own steps, such as query engines and workflows,
get no spans this way; this example calls the model directly for structured output and has
none.

### What's Instrumented

| Layer | Instrumentation | Type | What You Get |
| --- | --- | --- | --- |
| HTTP server | `FastAPIInstrumentor` | Auto | Request spans with method, path, status, duration (excludes `/health`, suppresses ASGI sub-spans) |
| HTTP server | `MetricsMiddleware` | Custom | `http.server.request.count`, `http.server.request.duration`, `http.server.active_requests` (excludes `/health`) |
| Logging | `LoggingInstrumentor` | Auto | Trace-correlated log records with `trace_id` and `span_id` |
| Model calls | GenAI SDK instrumentations | Auto | `chat {model}` or `generate_content {model}` CLIENT spans, `gen_ai.client.token.usage` and `gen_ai.client.operation.duration` |
| Call context | `LLMCallAttributesProcessor` | Custom | Endpoint, content type and length on model call spans, and `gen_ai.provider.name` from `LLM_PROVIDER` (so `ollama` rather than `openai` for Ollama) |
| Cost and scrubbing | `GenAISpanExporter` | Custom | `base14.gen_ai.cost_usd` on model call spans; emails, phone numbers, SSNs, card numbers and LinkedIn profile URLs scrubbed from captured span content |
| GenAI counters | Custom OTel counters | Custom | `base14.gen_ai.cost`, `base14.gen_ai.error.count`, `base14.gen_ai.retry.count`, `base14.gen_ai.fallback.count` |
| Evaluations | Custom OTel events + metrics | Custom | `gen_ai.evaluation.result` events, `base14.gen_ai.evaluation.score` histogram |

### Span Attributes

From the instrumentation, each model call span carries:

- `gen_ai.operation.name`, `gen_ai.provider.name`, `gen_ai.request.model`,
  `gen_ai.response.model` and `gen_ai.request.temperature`.
- `gen_ai.usage.input_tokens`, `gen_ai.usage.output_tokens`, `gen_ai.response.id` and
  `gen_ai.response.finish_reasons`.
- `server.address`, and `server.port` unless it is the default 443.

From this example:

- `base14.gen_ai.cost_usd`, `base14.content.type`, `base14.content.length` and
  `base14.endpoint`.

The OpenAI instrumentation names the provider `openai` for Ollama's endpoint; the span
processor corrects it on spans, and the `gen_ai.client.*` metric points keep `openai`.

### Token & Cost Tracking

The instrumentations record token counts on spans and in `gen_ai.client.token.usage`. Cost is
calculated from `_shared/pricing.json` at the repository root, keyed by model: the span
exporter sets `base14.gen_ai.cost_usd` on each model call span, and the client records the
`base14.gen_ai.cost` counter with the endpoint and content type. An unrecognized model, every
Ollama model included, costs `0.0`.

### Captured Content

`OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT` takes `no_content` (the default),
`span_only`, `event_only` or `span_and_event`. With `span_only`, the input messages, system
instructions and output messages are set on the model call span, and `GenAISpanExporter`
scrubs them before export. `event_only` and `span_and_event` send content as
`gen_ai.client.inference.operation.details` log records, which the exporter does not see and
does not scrub; use `span_only` when content may hold PII.

### Error Handling

Each SDK call is its own model call span; a failed one has error status, the recorded
exception and `error.type`. The Anthropic and OpenAI clients are built with `max_retries=0`,
so `LLMClient`'s tenacity retry is the only layer.

A failed call is handled in this order:

1. A response that fails schema validation is sent back with a correction, up to two times,
   and each correction is its own model call span.
2. Any failure, including a response that still fails validation after the corrections, is
   retried up to two more times with exponential backoff. `base14.gen_ai.retry.count`
   records each retry. One `generate_structured` call can therefore produce up to nine model
   call spans.
3. When the primary provider still fails, the client switches to the fallback provider and
   adds a `provider_fallback` event and `gen_ai.fallback.triggered=true` to the HTTP server
   span, which is not marked ERROR if the fallback succeeds. With the defaults,
   `FALLBACK_PROVIDER` equals `LLM_PROVIDER`, so no fallback is built and the error is
   returned.

`REQUEST_TIMEOUT` caps the whole chain; when it is reached the request returns 504.
Unhandled route errors are recorded on the active span by `unhandled_exception_handler` in
`src/content_quality/errors.py`, registered as a FastAPI exception handler in `main.py`.

## Configuration

Copy `.env.example` to `.env` and configure. The Default column shows the app's default.

| Variable | Default | Description |
| --- | --- | --- |
| `LLM_PROVIDER` | `ollama` | LLM provider (`ollama`, `openai`, `google`, `anthropic`) |
| `LLM_MODEL` | `qwen3.5:9B` | Model name for the selected provider |
| `LLM_TEMPERATURE` | `0.3` | LLM temperature |
| `FALLBACK_PROVIDER` | `ollama` | Provider used when `LLM_PROVIDER` fails after all retries; no fallback is built when it equals `LLM_PROVIDER` |
| `FALLBACK_MODEL` | `qwen3.5:9B` | Model name for the fallback provider |
| `OLLAMA_BASE_URL` | `http://localhost:11434` | Ollama server URL; Compose sets `http://host.docker.internal:11434` |
| `OLLAMA_REASONING` | `false` | Whether a thinking model such as `qwen3.5` reasons before answering; `false` sends `reasoning_effort=none` |
| `OLLAMA_CONTEXT_WINDOW` | `32768` | Context window LlamaIndex assumes for the model; the Ollama server's own setting (`OLLAMA_CONTEXT_LENGTH`) decides what it allocates |
| `OPENAI_API_KEY` | - | OpenAI API key (when provider is `openai`) |
| `GOOGLE_API_KEY` | - | Google API key (when provider is `google`) |
| `ANTHROPIC_API_KEY` | - | Anthropic API key (when provider is `anthropic`) |
| `SERVICE_NAME` | `ai-content-quality` | Becomes `service.name` |
| `OTLP_ENDPOINT` | `http://otel-collector:4318` | Collector endpoint; `make run` sets `http://localhost:4318` |
| `OTEL_SDK_DISABLED` | `false` | Disable telemetry (`true` to disable); read from the process environment |
| `OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT` | `no_content` | `no_content`, `span_only`, `event_only` or `span_and_event`; read from the process environment |
| `SCOUT_ENVIRONMENT` | `development` | Deployment environment tag; read from the process environment |
| `SCOUT_CLIENT_ID` / `SCOUT_CLIENT_SECRET` / `SCOUT_TOKEN_URL` / `SCOUT_ENDPOINT` | - | Base14 Scout OAuth credentials for the collector |
| `LLM_TIMEOUT` | `300.0` | Timeout in seconds for one model call; not applied to the Google client |
| `REQUEST_TIMEOUT` | `600.0` | Cap in seconds on a whole analysis request, retries and fallback included |
| `REVIEW_PROMPT_VERSION` | `v1` | Prompt version for `/review` |
| `IMPROVE_PROMPT_VERSION` | `v1` | Prompt version for `/improve` |
| `SCORE_PROMPT_VERSION` | `v1` | Prompt version for `/score` |
| `HOST` | `0.0.0.0` | Server bind address |
| `PORT` | `8000` | Server port |

## Project Structure

```text
ai-content-quality/
├── src/content_quality/
│   ├── main.py                  # FastAPI app, routes, lifespan
│   ├── config.py                # Settings from environment
│   ├── errors.py                # Unhandled exception handler
│   ├── genai_spans.py           # Context, provider, cost and scrubbing on model call spans
│   ├── pii.py                   # Scrubbing patterns for captured content
│   ├── pricing.py               # Prices from _shared/pricing.json
│   ├── telemetry.py             # OTel SDK setup (traces, metrics, logs, GenAI instrumentations)
│   ├── middleware/
│   │   └── metrics.py           # HTTP request metrics middleware
│   ├── models/
│   │   ├── requests.py          # ContentRequest with validation
│   │   └── responses.py         # Pydantic response models (ReviewResult, ImproveResult, ScoreResult)
│   └── services/
│       ├── analyzer.py          # ContentAnalyzer with eval event recording
│       ├── llm.py               # LlamaIndex models, structured output, retries, fallback, counters
│       └── prompts.py           # YAML prompt loader
├── prompts/                     # Versioned prompt templates (YAML)
│   ├── review_v1.yaml
│   ├── review_v2.yaml
│   ├── improve_v1.yaml
│   └── score_v1.yaml
├── evals/                       # Promptfoo eval pipeline
│   ├── review.yaml              # Eval config for the review prompts
│   ├── improve.yaml             # Eval config for the improve prompt
│   ├── score.yaml               # Eval config for the score prompt
│   ├── assertions/              # Custom JS assertion functions
│   └── datasets/                # Test cases and the shared case.js helper
├── tests/                       # Unit tests
│   ├── conftest.py
│   ├── test_analyzer.py
│   ├── test_api.py
│   ├── test_llm.py
│   ├── test_llm_vectors.py
│   ├── test_middleware.py
│   ├── test_models.py
│   ├── test_pii.py
│   ├── test_prompts.py
│   └── test_telemetry.py
├── scripts/
│   ├── test-api.sh              # API smoke test script
│   └── verify-scout.sh          # Telemetry verification script
├── .env.example
├── compose.yaml                 # Docker Compose (app + OTel Collector)
├── otel-collector-config.yaml   # Collector pipeline config
├── Dockerfile
├── Makefile
└── pyproject.toml
```
