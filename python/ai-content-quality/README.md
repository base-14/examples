# AI Content Quality Agent

> [Full Documentation](https://docs.base14.io/guides/ai-observability/llm-observability/)

AI-powered content quality analysis with eval-driven development and unified observability via Base14 Scout.

**Stack**: Python 3.14 · FastAPI · LlamaIndex · Promptfoo · OpenTelemetry · Base14 Scout

## How to instrument LlamaIndex with OpenTelemetry

1. Install `opentelemetry-api`, `opentelemetry-sdk`, `opentelemetry-exporter-otlp-proto-http`,
   `opentelemetry-instrumentation-fastapi` and `opentelemetry-instrumentation-logging` from
   `pyproject.toml`. No LlamaIndex-specific instrumentation package is used.
2. Call `setup_telemetry(service_name=..., otlp_endpoint=...)` from
   `src/content_quality/telemetry.py` at import time in `src/content_quality/main.py`, before the app is created.
   It registers OTLP trace, metric and log exporters and `LoggingInstrumentor()`. After
   creating the app, call `instrument_fastapi(app)`, which runs
   `FastAPIInstrumentor.instrument_app(app, excluded_urls="health", exclude_spans=["receive", "send"])`.
   LlamaIndex LLM calls are wrapped by hand in `src/content_quality/services/llm.py` with
   `tracer.start_as_current_span(f"chat {model_name}", kind=SpanKind.CLIENT)`.
3. Set `SERVICE_NAME=ai-content-quality` and `OTLP_ENDPOINT=http://otel-collector:4318` as in
   `compose.yaml` and `.env.example` (use `http://localhost:4318` when running the app on the host), plus
   `OTEL_SDK_DISABLED=false`, `OTEL_SEMCONV_STABILITY_OPT_IN=gen_ai_latest_experimental` and
   `OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT=false`.
   This example reads its own `SERVICE_NAME` and `OTLP_ENDPOINT` variables rather than the
   standard `OTEL_SERVICE_NAME` and `OTEL_EXPORTER_OTLP_ENDPOINT`.

This example adds GenAI semantic convention spans and metrics (`gen_ai.client.token.usage`,
`gen_ai.client.operation.duration`, `base14.gen_ai.cost`, retry and fallback counters), a single
`gen_ai.client.inference.operation.details` event per call in place of the removed per-message
events, custom HTTP request metrics from `src/content_quality/middleware/metrics.py`, PII
scrubbing of captured prompt and completion content, and OTLP logs correlated with traces. The
full guide is
[LlamaIndex OpenTelemetry Instrumentation](https://docs.base14.io/instrument/apps/auto-instrumentation/llamaindex/).

## Eval-driven workflow

Prompts are evaluated with Promptfoo before deploy, CI fails on a drop in the eval scores, and
production requests are traced through OpenTelemetry from the HTTP request down to each LLM call.

## Quick Start

```bash
# Install dependencies
make dev

# Run locally
make run

# Run checks (lint + typecheck + tests)
make check
```

## API Endpoints

| Endpoint | Method | Description |
|-----------|--------|-------------|
| `/health` | GET | Health check with component status |
| `/review` | POST | Review content for quality issues (hyperbole, bias, unsourced claims) |
| `/improve` | POST | Suggest specific text improvements with before/after |
| `/score` | POST | Score content 0-100 with clarity/accuracy/engagement/originality breakdown |

All analysis endpoints accept a JSON body with `content` (string, max 10,000 chars) and optional `content_type` (one of `general`, `marketing`, `technical`, `blog`).

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

Prompts are evaluated offline using [Promptfoo](https://promptfoo.dev) before they reach production.
The pipeline includes 22 test cases across marketing, technical, and blog content, plus adversarial
inputs (prompt injection, whitespace, non-English, mixed HTML/markdown).

```bash
# Run full eval suite (no cache, forces fresh LLM calls)
make eval

# View results in browser with side-by-side comparison
make eval-view
```

**CI gate**: The GitHub Actions workflow (`.github/workflows/eval.yml`) runs `promptfoo eval
--no-cache` on every PR and blocks merge if the pass rate drops below 95%. Concurrency controls
prevent parallel PRs from racing on the LLM API.

**Side-by-side comparison**: Multiple prompt versions (e.g., `review_v1` vs `review_v2`) run
against the same test cases, letting you compare output quality before switching production
prompts.

Prompt files live in `prompts/` as YAML with separate `system` and `user` templates. Test datasets and custom assertion functions live in `evals/`.

## Observability

Every request produces a unified trace spanning HTTP and LLM calls - all visible in Base14 Scout.

### Instrumentation Approach

GenAI telemetry (spans, metrics, events) is handled by **custom instrumentation** in `llm.py`
following [OTel GenAI semantic conventions](https://opentelemetry.io/docs/specs/semconv/gen-ai/).
LlamaIndex has no OTel GenAI instrumentation that emits the current semconv names, so this
example instruments the LLM calls by hand.

### What's Instrumented

| Layer | Instrumentation | Type | What You Get |
|-------|----------------|------|-------------|
| HTTP server | `FastAPIInstrumentor` | Auto | Request spans with method, path, status, duration (excludes `/health`, suppresses ASGI sub-spans) |
| HTTP server | `MetricsMiddleware` | Custom | `http.server.request.count`, `http.server.request.duration`, `http.server.active_requests` (excludes `/health`) |
| Logging | `LoggingInstrumentor` | Auto | Trace-correlated log records with `trace_id` and `span_id` |
| GenAI spans | Custom OTel spans | Custom | `chat {model}` CLIENT spans with OTel GenAI semconv attributes |
| GenAI inference event | Custom OTel span event | Custom | `gen_ai.client.inference.operation.details` (only when content capture is enabled) |
| GenAI metrics | Custom OTel meters | Custom | `gen_ai.client.token.usage`, `base14.gen_ai.cost`, `gen_ai.client.operation.duration` |
| GenAI errors | Custom OTel counters | Custom | `base14.gen_ai.error.count`, `base14.gen_ai.retry.count`, `base14.gen_ai.fallback.count` |
| Evaluations | Custom OTel events + metrics | Custom | `gen_ai.evaluation.result` events, `base14.gen_ai.evaluation.score` histogram |
| PII scrubbing | Custom event processing | Custom | Emails, phone numbers, SSNs scrubbed from span events before export |

### Span Attributes (OTel GenAI Semconv)

Each `chat {model}` span carries these attributes:

| Attribute | Source | Example |
|-----------|--------|---------|
| `gen_ai.operation.name` | Custom | `chat` |
| `gen_ai.request.model` | Custom | `claude-haiku-4.5` |
| `gen_ai.response.model` | Custom | `claude-haiku-4.5` |
| `gen_ai.provider.name` | Custom | `anthropic` |
| `gen_ai.request.temperature` | Custom | `0.3` |
| `gen_ai.output.type` | Custom | `json` |
| `gen_ai.usage.input_tokens` | Custom | `923` |
| `gen_ai.usage.output_tokens` | Custom | `150` |
| `base14.gen_ai.cost_usd` | Custom | `0.001666` |
| `gen_ai.response.id` | Custom | `msg_abc123` |
| `gen_ai.response.finish_reasons` | Custom | `["end_turn"]` |
| `server.address` | Custom | `api.anthropic.com` |
| `server.port` | Custom | `443` |
| `base14.content.type` | Custom | `marketing` |
| `base14.content.length` | Custom | `42` |
| `base14.endpoint` | Custom | `/review` |

### Token & Cost Tracking

Token usage and cost are extracted from each LLM response across all supported providers:

| Provider | Token Source | Pricing |
|----------|-------------|---------|
| OpenAI | `additional_kwargs["prompt_tokens"]` / `["completion_tokens"]` | `_shared/pricing.json` |
| Google Gemini | `additional_kwargs["prompt_tokens"]` / `["completion_tokens"]` | `_shared/pricing.json` |
| Anthropic | `raw["usage"]["input_tokens"]` / `["output_tokens"]` | `_shared/pricing.json` |

Only the token count a provider actually returns is recorded; a call that returns just one of
input or output tokens still records that one and its cost, instead of skipping both.

Cost is calculated from the shared pricing table at `_shared/pricing.json`, keyed by model, and
recorded as both a span attribute (`base14.gen_ai.cost_usd`) and a counter metric
(`base14.gen_ai.cost`). An unrecognized model costs `0.0` rather than failing the call.

### Error Handling

A failed chat span records the exception, sets `error.type`, and sets status ERROR. Each network
error is retried up to two more times with exponential backoff, and `base14.gen_ai.retry.count` records
each retry beyond the initial attempt. When the primary provider still fails after its retries,
the calling span gets a `provider_fallback` event and `gen_ai.fallback.triggered=true`, and is
not marked ERROR if the fallback succeeds. `REQUEST_TIMEOUT` caps the whole chain; with the
defaults a call that times out at `LLM_TIMEOUT` gets one retry before the request returns 504.
Unhandled route errors are recorded on the active span by `unhandled_exception_handler` in
`src/content_quality/errors.py`, registered as a FastAPI exception handler in `main.py`.

## Configuration

Copy `.env.example` to `.env` and configure:

| Variable | Default | Description |
|----------|---------|-------------|
| `LLM_PROVIDER` | `ollama` | LLM provider (`ollama`, `openai`, `google`, `anthropic`) |
| `LLM_MODEL` | `qwen3.5:9B` | Model name for the selected provider |
| `LLM_TEMPERATURE` | `0.3` | LLM temperature |
| `FALLBACK_PROVIDER` | `ollama` | Provider used when `LLM_PROVIDER` fails after all retries |
| `FALLBACK_MODEL` | `qwen3.5:9B` | Model name for the fallback provider |
| `OLLAMA_BASE_URL` | `http://host.docker.internal:11434` | Ollama server URL as compose sets it; the code default is `http://localhost:11434` for running the app directly on the host |
| `OLLAMA_REASONING` | `false` | Whether Ollama lets a thinking model such as `qwen3.5` reason before answering; leave off, or each review generates over a thousand tokens |
| `OLLAMA_CONTEXT_WINDOW` | `32768` | Context window requested per Ollama call; without it LlamaIndex requests the model's full trained length (262144 for `qwen3.5:9B`), which makes each call several times slower |
| `OPENAI_API_KEY` | - | OpenAI API key (when provider is `openai`) |
| `GOOGLE_API_KEY` | - | Google API key (when provider is `google`) |
| `ANTHROPIC_API_KEY` | - | Anthropic API key (when provider is `anthropic`) |
| `OTEL_SDK_DISABLED` | `false` | Disable telemetry (`true` to disable) |
| `OTEL_SEMCONV_STABILITY_OPT_IN` | `gen_ai_latest_experimental` | Emit the latest GenAI attribute names rather than the deprecated ones |
| `OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT` | `false` | Capture prompt/completion content on span events |
| `SCOUT_ENVIRONMENT` | `development` | Deployment environment tag |
| `SCOUT_CLIENT_ID` | - | Base14 Scout OAuth client ID |
| `SCOUT_CLIENT_SECRET` | - | Base14 Scout OAuth client secret |
| `LLM_TIMEOUT` | `300.0` | Timeout (seconds) for one model call; a local 9B model at about 5 tokens per second needs 5 to 30 s per call with thinking off, and minutes with it on |
| `REQUEST_TIMEOUT` | `600.0` | Cap (seconds) on a whole LLM analysis request, retries and fallback included; a chain of slow calls ends with a 504 when it is reached, so it does not wait for every retry of a call that takes the full `LLM_TIMEOUT` |
| `REVIEW_PROMPT_VERSION` | `v1` | Prompt version for `/review` |
| `IMPROVE_PROMPT_VERSION` | `v1` | Prompt version for `/improve` |
| `SCORE_PROMPT_VERSION` | `v1` | Prompt version for `/score` |
| `HOST` | `0.0.0.0` | Server bind address |
| `PORT` | `8000` | Server port |

## Docker

```bash
cp .env.example .env
# Edit .env with your API keys and LLM provider

# Start full stack (app + OTel Collector)
docker compose up -d

# Run API smoke tests
./scripts/test-api.sh

# Verify telemetry pipeline
./scripts/verify-scout.sh

# Tear down
docker compose down -v
```

The OTel Collector (`otel-collector-config.yaml`) is configured with `memory_limiter`, `batch`
processing, and `otlp_http` export to Base14 Scout with OAuth2 authentication, retry, and gzip
compression.

An `ollama` service is available under `docker compose --profile ollama up -d` for hosts without
a local Ollama install; when using it, set `OLLAMA_BASE_URL=http://ollama:11434` so the app reaches
the container instead of the host.

## Dashboards

Three Base14 Scout dashboards provide production visibility:

### Content Quality Dashboard

Tracks content analysis quality and evaluation scores.

| Panel | Metric / Query | Description |
|-------|---------------|-------------|
| Avg Quality Score | `avg(base14.gen_ai.evaluation.score)` | 24h average with day-over-day comparison |
| Score Distribution | `histogram(base14.gen_ai.evaluation.score)` | Bucketed distribution (90-100, 80-89, etc.) |
| Quality Over Time | `base14.gen_ai.evaluation.score` time series | Weekly trend with pass threshold line at 60 |
| Issues by Type | `count by content_issue.type` | Breakdown: hyperbole, unsourced, unclear, bias, grammar |
| Quality by Content Type | `avg(base14.gen_ai.evaluation.score) by base14.content.type` | Comparison across technical, blog, marketing |

### Eval Pass Rate Dashboard

Tracks Promptfoo eval results and prompt version performance.

| Panel | Metric / Query | Description |
|-------|---------------|-------------|
| Current Pass Rate | CI eval pass/total ratio | Current rate with delta vs last run |
| CI Gate Threshold | Static: `95.0%` | Visual threshold indicator |
| Pass Rate by Prompt Version | Pass rate per `prompt.version` | Side-by-side: `review_v1` vs `review_v2`, `improve_v1`, `score_v1` |
| Failed Assertions | Failed test case + assertion detail | Table of test case, assertion type, expected vs actual |

### Cost & Token Dashboard

Tracks LLM costs and token usage.

| Panel | Metric / Query | Description |
|-------|---------------|-------------|
| Total Cost (24h) | `sum(base14.gen_ai.cost)` | Daily total with day-over-day delta |
| Cost per Request | `avg(base14.gen_ai.cost)` | Average cost per LLM call |
| Token Usage Over Time | `gen_ai.client.token.usage` time series | Input vs output token trend |
| Cost by Endpoint | `sum(base14.gen_ai.cost) by base14.endpoint` | Breakdown: `/review`, `/improve`, `/score` |
| Input vs Output Tokens | `sum(gen_ai.client.token.usage) by gen_ai.token.type` | Ratio of input to output tokens |

## Alerts

Recommended alert rules for production monitoring:

| Alert | Condition | Severity | Action |
|-------|-----------|----------|--------|
| Quality Drop | `avg(base14.gen_ai.evaluation.score) < 70` | Warning | Review prompts, run eval suite |
| Eval Pass Rate Drop | CI pass rate < 90% | Critical | Block deploy, investigate failures |
| High Latency | `p95(gen_ai.client.operation.duration) > 5s` | Warning | Check provider status, consider model |
| Cost Spike | `rate(base14.gen_ai.cost) > 2x baseline` | Warning | Review request volume, model selection |
| High Daily Cost | `sum(base14.gen_ai.cost) > $10` | Warning | Review usage patterns |
| Error Rate | `sum(base14.gen_ai.error.count) / total > 5%` | Critical | Check logs, investigate trace |
| Retry Storm | `rate(base14.gen_ai.retry.count) > 10/min` | Warning | Possible upstream degradation |
| Token Anomaly | `tokens > 3x baseline` | Warning | Possible prompt injection |

## Project Structure

```text
ai-content-quality/
├── src/content_quality/
│   ├── main.py                  # FastAPI app, routes, lifespan
│   ├── config.py                # Settings from environment
│   ├── pii.py                   # PII scrubbing for span events
│   ├── telemetry.py             # OTel SDK setup (traces, metrics, logs)
│   ├── middleware/
│   │   └── metrics.py           # HTTP request metrics middleware
│   ├── models/
│   │   ├── requests.py          # ContentRequest with validation
│   │   └── responses.py         # Pydantic response models (ReviewResult, ImproveResult, ScoreResult)
│   └── services/
│       ├── analyzer.py          # ContentAnalyzer with eval event recording
│       ├── llm.py               # LLM call with OTel GenAI semconv, retry, cost tracking, PII scrubbing
│       └── prompts.py           # YAML prompt loader
├── prompts/                     # Versioned prompt templates (YAML)
│   ├── review_v1.yaml
│   ├── review_v2.yaml
│   ├── improve_v1.yaml
│   └── score_v1.yaml
├── evals/                       # Promptfoo eval pipeline
│   ├── assertions/              # Custom JS assertion functions
│   │   ├── review.js
│   │   ├── improve.js
│   │   └── score.js
│   └── datasets/                # Test case data
│       ├── review_cases.json
│       ├── improve_cases.json
│       └── score_cases.json
├── tests/                       # Unit tests (137 tests)
│   ├── conftest.py
│   ├── test_analyzer.py
│   ├── test_api.py
│   ├── test_llm.py
│   ├── test_middleware.py
│   ├── test_models.py
│   ├── test_pii.py
│   ├── test_prompts.py
│   └── test_telemetry.py
├── scripts/
│   ├── test-api.sh              # API smoke test script
│   └── verify-scout.sh          # Telemetry verification script
├── promptfooconfig.yaml         # Eval pipeline configuration
├── compose.yaml                  # Docker Compose (app + OTel Collector)
├── otel-collector-config.yaml   # Collector pipeline config
├── Dockerfile
├── Makefile
└── pyproject.toml
```
