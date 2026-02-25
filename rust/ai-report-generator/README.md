# AI Report Generator

Economic report generation pipeline that retrieves FRED indicator data from PostgreSQL, analyzes trends and correlations via LLM, generates structured narrative reports, and formats the final output -- with full OpenTelemetry observability.

**Rust 1.92 | Axum | async-openai | tracing + OTel SDK | PostgreSQL**

## Architecture

```
Request → Retrieve → Analyze → Generate → Format → Report
             │           │          │          │
          PostgreSQL  gpt-4.1-mini gpt-4.1   No LLM
```

4-stage pipeline with manual OTel spans at every stage. Two LLM calls per report: trend analysis (fast model) and narrative generation (capable model).

## Quick Start

```bash
# Copy and configure environment
cp .env.example .env
# Set OPENAI_API_KEY in .env (or configure another provider)

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

Indicators: unemployment rate (UNRATE), CPI (CPIAUCSL), federal funds rate (FEDFUNDS), housing starts (HOUST), industrial production (INDPRO), GDP, retail sales (RSAFS), 10-year treasury (GS10), nonfarm payrolls (PAYEMS), personal savings rate (PSAVERT).

## Observability

Every report generation produces a trace with:
- `pipeline_stage retrieve` -- PostgreSQL queries for indicator data
- `pipeline_stage analyze` -- trend and correlation analysis via LLM
- `gen_ai.chat {model}` -- LLM calls with full GenAI semconv attributes
- `pipeline_stage generate` -- narrative report generation via LLM
- `pipeline_stage format` -- final report assembly

GenAI metrics: token usage, operation duration, cost, retry count, fallback count, error count.
HTTP metrics: request count, request duration.
Domain metrics: pipeline duration, data points processed.

### Verify Telemetry

```bash
./scripts/verify-scout.sh
```

## Development

```bash
make check    # clippy + fmt + test
make build    # compile binary
make test     # run tests
make run      # run locally (needs DATABASE_URL)
```

## LLM Providers

| Provider | Models | Usage |
| --- | --- | --- |
| OpenAI | gpt-4.1 (capable), gpt-4.1-mini (fast) | Default primary |
| Google | gemini-2.0-flash | `LLM_PROVIDER=google` |
| Anthropic | claude-haiku-4-5-20251001 | Default fallback (auto model switch via `FALLBACK_MODEL`); `LLM_PROVIDER=anthropic` for primary |
| Ollama | Any local model | `LLM_PROVIDER=ollama` |

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
