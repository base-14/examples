# AI Data Analyst

NL-to-SQL pipeline that translates natural language questions into SQL queries against World Bank economic data, with full OpenTelemetry observability.

**Go 1.25 | Chi | Direct OpenAI API | Native OTel SDK | PostgreSQL**

## Architecture

```
Question → Parse → Generate SQL → Validate → Execute → Explain → Answer
              │         │              │          │          │
           No LLM    gpt-4.1       No LLM    PostgreSQL  gpt-4.1-mini
```

5-stage pipeline with manual OTel spans at every stage. Two LLM calls per question: SQL generation (capable model) and result explanation (fast model).

## Quick Start

```bash
# Copy and configure environment
cp .env.example .env
# Set OPENAI_API_KEY in .env

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
- `pipeline_stage parse` — entity extraction, question classification
- `gen_ai.chat {model}` — SQL generation with full GenAI semconv attributes
- `pipeline_stage validate` — SQL safety checks
- `pipeline_stage execute` — PostgreSQL query with row counts
- `data_analyst SELECT/SET/INSERT` — individual DB operation spans
- `gen_ai.chat {model}` — result explanation

GenAI metrics: token usage, operation duration, cost, retry count, fallback count, error count.
HTTP metrics: request duration, request/response body size.
Domain metrics: question duration, SQL validity, query rows, execution time, confidence.

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

| Provider | Models | Usage |
| --- | --- | --- |
| OpenAI | gpt-4.1 (capable), gpt-4.1-mini (fast) | Default primary |
| Google | gemini-2.0-flash | `LLM_PROVIDER=google` |
| Anthropic | claude-haiku-4-5-20251001 | Fallback |
| Ollama | Any local model | `LLM_PROVIDER=ollama` |

## Sample Questions

- Top 10 countries by GDP growth in 2023
- Compare life expectancy between Japan and Nigeria
- How has internet usage changed in China?
- What is the average unemployment rate in Europe?
- Which countries have the highest CO2 emissions per capita?
