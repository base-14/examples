# AI Data Analyst

> [Full Documentation](https://docs.base14.io/guides/ai-observability/llm-observability/)

NL-to-SQL pipeline that translates natural language questions into SQL queries against World Bank economic data, with full OpenTelemetry observability.

## How to instrument a Go chi service and its LLM calls with OpenTelemetry

1. Add `go.opentelemetry.io/otel`, `go.opentelemetry.io/otel/sdk`, `go.opentelemetry.io/otel/sdk/metric`,
   the OTLP HTTP trace and metric exporters, `go.opentelemetry.io/contrib/instrumentation/net/http/otelhttp`
   and `github.com/exaring/otelpgx` to `go.mod`.
2. Call `telemetry.Init` from `internal/telemetry/telemetry.go` at the start of `main`. It builds the
   tracer and meter providers, the OTLP exporters and the resource. Register
   `middleware.OTelHTTP`, `middleware.ErrorStatus` and `middleware.Recovery` on the chi router, and
   set `otelpgx.NewTracer()` on the pgx pool config in `internal/db/pool.go`. The LLM calls have no
   auto-instrumentation, so `internal/llm/client.go` opens the `chat {model}` CLIENT span itself.
3. Set `OTEL_SERVICE_NAME=ai-data-analyst`, `OTEL_EXPORTER_OTLP_ENDPOINT=http://otel-collector:4318`
   and `OTEL_SEMCONV_STABILITY_OPT_IN=gen_ai_latest_experimental` as in `compose.yaml`
   (`.env.example` uses `http://localhost:4318` for local runs).

This example adds `chat {model}` CLIENT spans with GenAI semantic convention attributes, token
usage, duration, cost, retry, fallback and error metrics from `internal/llm/client.go`, an
`output_guardrails` span that reports each SQL safety check as a `gen_ai.evaluation.result` event,
and a span per pipeline stage. Prompt and completion text is recorded on a
`gen_ai.client.inference.operation.details` event only when
`OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT=true`, PII-scrubbed and truncated. Run
`./scripts/verify-scout.sh` to check the collector received all of it.

## Requirements

* Go 1.26.
* Chi.
* Ollama, OpenAI, Gemini or Anthropic through their HTTP APIs.
* Native OTel SDK.
* PostgreSQL.
* A `--profile ollama` Compose service is also available; set `OLLAMA_BASE_URL=http://ollama:11434` to use it instead of a host install.

## Architecture

```text
Question → Parse → Generate SQL → Guardrails → Execute → Explain → Answer
              │         │              │           │          │
           No LLM    capable        No LLM    PostgreSQL     fast
                      model                                 model
```

Five pipeline stages with manual OTel spans at every stage. Two LLM calls per question: SQL
generation with the capable model and result explanation with the fast model.

## Quick Start

```bash
# Copy and configure environment
cp .env.example .env
# The defaults run against a local Ollama, so no API key is needed

# Start all services
docker compose up -d

# Run smoke tests
./scripts/test-api.sh

# Ask a question
curl -X POST http://localhost:8080/api/ask \
  -H "Content-Type: application/json" \
  -d '{"question":"Top 10 countries by GDP growth in 2023"}'
```

## API Endpoints

| Method | Path | Description |
| --- | --- | --- |
| `POST` | `/api/ask` | Ask a question in natural language |
| `GET` | `/api/health` | Health check |
| `GET` | `/api/schema` | Database schema description |
| `GET` | `/api/history` | Query history |
| `GET` | `/api/indicators` | Available indicators |

## Data

World Bank economic data: 217 countries, 20 indicators, years 2003-2023 (~74K data points).

Indicators include GDP growth, population, life expectancy, CO2 emissions, internet usage, unemployment, inflation, trade, and more.

## Observability

Every question produces a trace with:

* `pipeline_stage parse` for entity extraction and question classification.
* `chat {model}` for SQL generation, a CLIENT span with the GenAI semconv attributes.
* `output_guardrails` for the SQL safety checks, one `gen_ai.evaluation.result` event per check.
* `pipeline_stage execute` for the query stage, with the nested otelpgx spans carrying the database attributes.
* `data_analyst SELECT/SET/INSERT` for the individual database operations.
* `chat {model}` for the result explanation.

### Metrics

| Metric | Type | Description |
| --- | --- | --- |
| `gen_ai.client.token.usage` | Histogram | Tokens per call, split by `gen_ai.token.type`. |
| `gen_ai.client.operation.duration` | Histogram | LLM call duration, recorded on success and failure. |
| `base14.gen_ai.cost` | Counter | Cost in USD from `_shared/pricing.json`. |
| `base14.gen_ai.retry.count` | Counter | Retry attempts, excluding the initial attempt. |
| `base14.gen_ai.fallback.count` | Counter | Provider switches. |
| `base14.gen_ai.error.count` | Counter | Errors by provider and type. |
| `base14.nlsql.question.duration` | Histogram | Question-to-answer duration. |
| `base14.nlsql.sql.valid` | Counter | Guardrail outcomes. |
| `base14.nlsql.query.rows` | Histogram | Rows returned per query. |
| `base14.nlsql.query.execution_time` | Histogram | Query execution time in milliseconds. |
| `base14.nlsql.confidence` | Histogram | Model confidence in the generated SQL. |

HTTP metrics come from otelhttp: request duration and request and response body size.

### Events

One `gen_ai.client.inference.operation.details` event per LLM call carries the prompt and the
completion. It replaces the two per-message events the semconv removed, and it is emitted only when
`OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT=true`. Content is PII-scrubbed and truncated:
1000 characters for the input, 500 for the system instructions, 2000 for the output.

The `output_guardrails` span emits one `gen_ai.evaluation.result` event per SQL check, carrying
`gen_ai.evaluation.name`, `gen_ai.evaluation.score.value` and `gen_ai.evaluation.score.label`, plus
`gen_ai.evaluation.explanation` when the check fails.

### Error handling

A failed chat span records the exception, sets `error.type` and sets status ERROR. When the primary
provider fails after its retries, the calling span gets a `provider_fallback` event and
`gen_ai.fallback.triggered=true`, and keeps its own status. Panics are recorded on the active span by
`internal/middleware/errors.go`, and HTTP server spans are marked ERROR from status 400 up.

### Verify Telemetry

```bash
./scripts/verify-scout.sh
```

## Development

```bash
make check    # vet + fmt + test
make build    # compile binary
make test     # run tests
```

## LLM Providers

| Provider | `gen_ai.provider.name` | Usage |
| --- | --- | --- |
| Ollama | `ollama` | Default primary and fallback, `qwen3.5:9B` for both models. |
| OpenAI | `openai` | `LLM_PROVIDER=openai`, needs `OPENAI_API_KEY`. |
| Gemini | `gcp.gemini` | `LLM_PROVIDER=google`, needs `GOOGLE_API_KEY`. |
| Anthropic | `anthropic` | `LLM_PROVIDER=anthropic`, needs `ANTHROPIC_API_KEY`. |

`FALLBACK_PROVIDER` and `FALLBACK_MODEL` select the provider the client switches to when the primary
fails after its retries. The configuration key for Gemini is `google`; telemetry reports it as
`gcp.gemini`.

## Sample Questions

* Top 10 countries by GDP growth in 2023
* Compare life expectancy between Japan and Nigeria
* How has internet usage changed in China?
* What is the average unemployment rate in Europe?
* Which countries have the highest CO2 emissions per capita?
