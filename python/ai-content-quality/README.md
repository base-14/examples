# AI Content Quality Agent

AI-powered content quality analysis with eval-driven development and unified observability via Base14 Scout.

**Stack**: Python 3.14 · FastAPI · LlamaIndex · Promptfoo · OpenTelemetry · Base14 Scout

## Why Eval-Driven

AI applications suffer from "prompt roulette" — teams iterate on prompts by gut feel, ship without quality gates, and have no visibility into LLM behavior in production. This project demonstrates an eval-driven workflow: systematic prompt evaluation with Promptfoo before deploy, CI quality gates blocking regressions, and full production observability through OpenTelemetry with traces spanning HTTP through LLM calls.

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

Prompts are evaluated offline using [Promptfoo](https://promptfoo.dev) before they reach production. The pipeline includes 22 test cases across marketing, technical, and blog content, plus adversarial inputs (prompt injection, whitespace, non-English, mixed HTML/markdown).

```bash
# Run full eval suite (no cache, forces fresh LLM calls)
make eval

# View results in browser with side-by-side comparison
make eval-view
```

**CI gate**: The GitHub Actions workflow (`.github/workflows/eval.yml`) runs `promptfoo eval --no-cache` on every PR and blocks merge if the pass rate drops below 95%. Concurrency controls prevent parallel PRs from racing on the LLM API.

**Side-by-side comparison**: Multiple prompt versions (e.g., `review_v1` vs `review_v2`) run against the same test cases, letting you compare output quality before switching production prompts.

Prompt files live in `prompts/` as YAML with separate `system` and `user` templates. Test datasets and custom assertion functions live in `evals/`.

## Observability

Every request produces a unified trace spanning HTTP and LLM calls — all visible in Base14 Scout.

### Instrumentation Approach

GenAI telemetry (spans, metrics, events) is handled by **custom instrumentation** in `llm.py` following [OTel GenAI semantic conventions](https://opentelemetry.io/docs/specs/semconv/gen-ai/). We intentionally do NOT use OpenInference/LlamaIndex auto-instrumentation to avoid non-standard attributes (`llm.*`, `input.*`, `output.*`) that pollute telemetry with framework-specific data outside the OTel GenAI semconv.

### What's Instrumented

| Layer | Instrumentation | Type | What You Get |
|-------|----------------|------|-------------|
| HTTP server | `FastAPIInstrumentor` | Auto | Request spans with method, path, status, duration (excludes `/health`, suppresses ASGI sub-spans) |
| HTTP server | `MetricsMiddleware` | Custom | `http.server.request.count`, `http.server.request.duration`, `http.server.active_requests` (excludes `/health`) |
| Logging | `LoggingInstrumentor` | Auto | Trace-correlated log records with `trace_id` and `span_id` |
| GenAI spans | Custom OTel spans | Custom | `chat {model}` spans with OTel GenAI semconv attributes |
| GenAI metrics | Custom OTel meters | Custom | `gen_ai.client.token.usage`, `gen_ai.client.cost`, `gen_ai.client.operation.duration` |
| GenAI errors | Custom OTel counters | Custom | `gen_ai.client.error.count`, `gen_ai.client.retry.count` |
| Evaluations | Custom OTel events + metrics | Custom | `gen_ai.evaluation.result` events, `gen_ai.evaluation.score` histogram |
| PII scrubbing | Custom event processing | Custom | Emails, phone numbers, SSNs scrubbed from span events before export |

### Span Attributes (OTel GenAI Semconv)

Each `chat {model}` span carries these attributes:

| Attribute | Source | Example |
|-----------|--------|---------|
| `gen_ai.operation.name` | Custom | `chat` |
| `gen_ai.request.model` | Custom | `claude-3-5-haiku-20241022` |
| `gen_ai.response.model` | Custom | `claude-3-5-haiku-20241022` |
| `gen_ai.provider.name` | Custom | `anthropic` |
| `gen_ai.request.temperature` | Custom | `0.3` |
| `gen_ai.output.type` | Custom | `json` |
| `gen_ai.usage.input_tokens` | Custom | `923` |
| `gen_ai.usage.output_tokens` | Custom | `150` |
| `gen_ai.usage.cost_usd` | Custom | `0.001666` |
| `gen_ai.response.id` | Custom | `msg_abc123` |
| `gen_ai.response.finish_reasons` | Custom | `["end_turn"]` |
| `server.address` | Custom | `api.anthropic.com` |
| `server.port` | Custom | `443` |
| `content.type` | Custom | `marketing` |
| `content.length` | Custom | `42` |
| `endpoint` | Custom | `/review` |

### Token & Cost Tracking

Token usage and cost are extracted from each LLM response across all supported providers:

| Provider | Token Source | Pricing |
|----------|-------------|---------|
| OpenAI | `additional_kwargs["prompt_tokens"]` / `["completion_tokens"]` | Per-model lookup table |
| Google Gemini | `additional_kwargs["prompt_tokens"]` / `["completion_tokens"]` | Per-model lookup table |
| Anthropic | `raw["usage"]["input_tokens"]` / `["output_tokens"]` | Per-model lookup table |

Cost is calculated using a built-in pricing table (`PRICING` in `llm.py`) and recorded as both a span attribute (`gen_ai.usage.cost_usd`) and a counter metric (`gen_ai.client.cost`).

## Configuration

Copy `.env.example` to `.env` and configure:

| Variable | Default | Description |
|----------|---------|-------------|
| `LLM_PROVIDER` | `openai` | LLM provider (`openai`, `google`, `anthropic`) |
| `LLM_MODEL` | `gpt-4.1-nano` | Model name for the selected provider |
| `LLM_TEMPERATURE` | `0.3` | LLM temperature |
| `OPENAI_API_KEY` | — | OpenAI API key (when provider is `openai`) |
| `GOOGLE_API_KEY` | — | Google API key (when provider is `google`) |
| `ANTHROPIC_API_KEY` | — | Anthropic API key (when provider is `anthropic`) |
| `OTEL_SDK_DISABLED` | `false` | Disable telemetry (`true` to disable) |
| `OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT` | `false` | Capture prompt/completion content on span events |
| `SCOUT_ENVIRONMENT` | `development` | Deployment environment tag |
| `SCOUT_CLIENT_ID` | — | Base14 Scout OAuth client ID |
| `SCOUT_CLIENT_SECRET` | — | Base14 Scout OAuth client secret |
| `REQUEST_TIMEOUT` | `60.0` | Request timeout (seconds) for LLM analysis endpoints |
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

The OTel Collector (`otel-collector-config.yaml`) is configured with `memory_limiter`, `batch` processing, and `otlp_http` export to Base14 Scout with OAuth2 authentication, retry, and gzip compression.

## Dashboards

Three Base14 Scout dashboards provide production visibility:

### Content Quality Dashboard

Tracks content analysis quality and evaluation scores.

| Panel | Metric / Query | Description |
|-------|---------------|-------------|
| Avg Quality Score | `avg(gen_ai.evaluation.score)` | 24h average with day-over-day comparison |
| Score Distribution | `histogram(gen_ai.evaluation.score)` | Bucketed distribution (90-100, 80-89, etc.) |
| Quality Over Time | `gen_ai.evaluation.score` time series | Weekly trend with pass threshold line at 60 |
| Issues by Type | `count by content_issue.type` | Breakdown: hyperbole, unsourced, unclear, bias, grammar |
| Quality by Content Type | `avg(gen_ai.evaluation.score) by content.type` | Comparison across technical, blog, marketing |

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
| Total Cost (24h) | `sum(gen_ai.client.cost)` | Daily total with day-over-day delta |
| Cost per Request | `avg(gen_ai.client.cost)` | Average cost per LLM call |
| Token Usage Over Time | `gen_ai.client.token.usage` time series | Input vs output token trend |
| Cost by Endpoint | `sum(gen_ai.client.cost) by endpoint` | Breakdown: `/review`, `/improve`, `/score` |
| Input vs Output Tokens | `sum(gen_ai.client.token.usage) by gen_ai.token.type` | Ratio of input to output tokens |

## Alerts

Recommended alert rules for production monitoring:

| Alert | Condition | Severity | Action |
|-------|-----------|----------|--------|
| Quality Drop | `avg(gen_ai.evaluation.score) < 70` | Warning | Review prompts, run eval suite |
| Eval Pass Rate Drop | CI pass rate < 90% | Critical | Block deploy, investigate failures |
| High Latency | `p95(gen_ai.client.operation.duration) > 5s` | Warning | Check provider status, consider model |
| Cost Spike | `rate(gen_ai.client.cost) > 2x baseline` | Warning | Review request volume, model selection |
| High Daily Cost | `sum(gen_ai.client.cost) > $10` | Warning | Review usage patterns |
| Error Rate | `sum(gen_ai.client.error.count) / total > 5%` | Critical | Check logs, investigate trace |
| Retry Storm | `rate(gen_ai.client.retry.count) > 10/min` | Warning | Possible upstream degradation |
| Token Anomaly | `tokens > 3x baseline` | Warning | Possible prompt injection |

## Project Structure

```
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
├── compose.yml                  # Docker Compose (app + OTel Collector)
├── otel-collector-config.yaml   # Collector pipeline config
├── Dockerfile
├── Makefile
└── pyproject.toml
```
