# AI Report Generator

> [Full Documentation](https://docs.base14.io/guides/ai-observability/rust-llm-observability/)

Economic report generation pipeline that retrieves FRED indicator data from PostgreSQL, analyzes
trends and correlations through an LLM, generates a structured narrative report and formats the
final output, with OpenTelemetry instrumentation throughout.

Stack: Rust 1.98, Axum, async-openai, tracing with the OpenTelemetry SDK, PostgreSQL.

## How to instrument async-openai LLM calls in Rust with OpenTelemetry

1. Add `async-openai`, `opentelemetry`, `opentelemetry_sdk` (features `rt-tokio`, `logs`,
   `metrics`), `opentelemetry-otlp` (features `grpc-tonic`, `trace`, `logs`, `metrics`),
   `opentelemetry-appender-tracing`, `tracing`, `tracing-subscriber` and `tracing-opentelemetry`
   to `Cargo.toml`.
2. Call `init_telemetry(&config)` from `src/telemetry/init.rs` at the start of `main()`. It builds
   OTLP tracer, meter and logger providers and installs `OpenTelemetryLayer` and
   `OpenTelemetryTracingBridge` on the `tracing_subscriber` registry. `LlmClient` in
   `src/llm/client.rs` opens a CLIENT span named `chat {model}` around each chat completion and
   records the response model, token counts and cost on it.
3. Set `OTEL_SERVICE_NAME=ai-report-generator`,
   `OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4317` and
   `OTEL_SEMCONV_STABILITY_OPT_IN=gen_ai_latest_experimental` in `.env`.

This example adds GenAI semantic convention span attributes, the
`gen_ai.client.inference.operation.details` event, token, duration and cost metrics, a span per
pipeline stage, and retry with provider fallback. The full guide is
[Rust LLM Observability with OpenTelemetry](https://docs.base14.io/guides/ai-observability/rust-llm-observability/).

## Architecture

```text
Request → Retrieve → Analyze → Generate → Format → Report
             │           │          │          │
          PostgreSQL  fast model  capable    No LLM
                                   model
```

Four-stage pipeline with manual OTel spans at every stage. Two LLM calls per report: trend analysis
(fast model) and narrative generation (capable model).

## Quick Start

```bash
# Copy and configure environment
cp .env.example .env
# The defaults use the host's Ollama through http://host.docker.internal:11434 with qwen3.5:9B.
# For a hosted provider, set LLM_PROVIDER and that provider's API key in .env.

# Start all services
docker compose up -d

# Run smoke tests
./scripts/test-api.sh

# Generate a report
curl -X POST http://localhost:8080/api/reports \
  -H "Content-Type: application/json" \
  -d '{"indicators":["GDP","UNRATE","CPIAUCSL"],"start_date":"2020-01-01","end_date":"2023-12-31"}'
```

## API Endpoints

| Method | Path | Description |
| --- | --- | --- |
| `POST` | `/api/reports` | Generate a new economic report |
| `GET` | `/api/reports` | List generated reports |
| `GET` | `/api/reports/{id}` | Get a specific report by ID |
| `GET` | `/api/indicators` | Available economic indicators |
| `GET` | `/api/health` | Health check |

## Data

FRED economic indicators: 10 series, monthly observations from 2003-2023 (~2,700 data points).

Indicators: unemployment rate (UNRATE), CPI (CPIAUCSL), federal funds rate (FEDFUNDS), housing
starts (HOUST), industrial production (INDPRO), GDP, retail sales (RSAFS), 10-year treasury (GS10),
nonfarm payrolls (PAYEMS), personal savings rate (PSAVERT).

## Observability

Every report generation produces a trace with:

- `pipeline_stage retrieve` - PostgreSQL queries for indicator data.
- `pipeline_stage analyze` - trend and correlation analysis through an LLM.
- `chat {model}` - CLIENT spans for LLM calls with GenAI semconv attributes.
- `pipeline_stage generate` - narrative report generation through an LLM.
- `pipeline_stage format` - final report assembly.

| Metric | Type | What it records |
| --- | --- | --- |
| `gen_ai.client.token.usage` | histogram | Input and output tokens, split by `gen_ai.token.type`. |
| `gen_ai.client.operation.duration` | histogram | Wall-clock seconds per LLM call, on success and failure. |
| `base14.gen_ai.cost` | counter | Cost in USD from `_shared/pricing.json`. Models missing from the file cost 0. |
| `base14.gen_ai.retry.count` | counter | Retry attempts, excluding the initial attempt. |
| `base14.gen_ai.fallback.count` | counter | Switches to the fallback provider. |
| `base14.gen_ai.error.count` | counter | LLM calls that failed after their retries. |
| `base14.http.requests.total` | counter | HTTP requests, split by `http.response.status_code`. |
| `base14.http.request.duration` | histogram | HTTP request duration in milliseconds. |
| `base14.report.generation.duration` | histogram | Wall-clock seconds per report. |
| `base14.report.data_points` | histogram | Indicator observations read per report. |
| `base14.report.sections` | histogram | Sections in the generated report. |

The two HTTP metrics also carry `base14.http.status_class` (`2xx`, `4xx`, `5xx`).

Prompts and completions are not recorded by default. Set
`OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT=true` to add the
`gen_ai.client.inference.operation.details` event to each chat span. Its content is scrubbed of
emails, phone numbers and card-like numbers, and truncated to 1000 characters for the prompt, 500
for the system instructions and 2000 for the completion.

### Verify Telemetry

```bash
./scripts/verify-scout.sh
```

## Development

```bash
make check    # check + clippy + test
make build    # compile binary
make test     # run tests
make run      # run locally (needs DATABASE_URL)
```

## LLM Providers

| Config key | `gen_ai.provider.name` | Models | Usage |
| --- | --- | --- | --- |
| `ollama` | `ollama` | Any local model, qwen3.5:9B by default | Default primary and fallback. |
| `openai` | `openai` | gpt-4.1 (capable), gpt-4.1-mini (fast) | `LLM_PROVIDER=openai` with `OPENAI_API_KEY`. |
| `google` | `gcp.gemini` | gemini-2.5-flash-lite | `LLM_PROVIDER=google` with `GOOGLE_API_KEY`. |
| `anthropic` | `anthropic` | claude-haiku-4.5 | `LLM_PROVIDER=anthropic` with `ANTHROPIC_API_KEY`. |

`FALLBACK_PROVIDER` and `FALLBACK_MODEL` select the provider the client switches to when the
primary fails after three attempts. Ollama reads its host and port from `OLLAMA_BASE_URL`; the
compose file also ships an `ollama` service under the `ollama` profile for hosts without a local
install. When you start that profile with `docker compose --profile ollama up -d`, set
`OLLAMA_BASE_URL=http://ollama:11434` so the app reaches the container instead of the host.

## Sample Reports

```bash
# US monetary policy analysis
curl -X POST http://localhost:8080/api/reports \
  -H "Content-Type: application/json" \
  -d '{"indicators":["FEDFUNDS","CPIAUCSL","UNRATE"],"start_date":"2020-01-01","end_date":"2023-12-31"}'

# Housing market overview
curl -X POST http://localhost:8080/api/reports \
  -H "Content-Type: application/json" \
  -d '{"indicators":["HOUST","GS10","GDP"],"start_date":"2015-01-01","end_date":"2023-12-31"}'

# Full economic snapshot
curl -X POST http://localhost:8080/api/reports \
  -H "Content-Type: application/json" \
  -d '{"indicators":["GDP","UNRATE","CPIAUCSL","FEDFUNDS","INDPRO","RSAFS","PAYEMS","PSAVERT","HOUST","GS10"],"start_date":"2003-01-01","end_date":"2023-12-31"}'
```
