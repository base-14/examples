# AI Contract Analyzer

AI-powered contract analysis pipeline demonstrating **multi-stage LLM observability** with OpenTelemetry GenAI semantic conventions and Base14 Scout.

**Stack**: Bun 1.2 · Hono 4 · Vercel AI SDK 6 · Anthropic / Google / Ollama · PostgreSQL 18 + pgvector · OpenTelemetry

---

## Why Multi-Stage Observability?

Single LLM call observability is solved. Multi-stage pipelines are not. When a contract analysis takes 25 seconds, you can't tell from a single span whether the bottleneck is extraction (the LLM), embedding (the model), or ingest (PDF parsing). When cost spikes, you don't know which stage caused it.

This project shows how to instrument a six-stage AI pipeline so every trace answers those questions:

```
analyze_contract                                      23.4s   $0.042
  pipeline_stage ingest       (pdf-parse + chunk)      0.8s
  pipeline_stage route        (classify doc type)      0.3s   $0.0001
  pipeline_stage embed ───┐   (embedding model)        1.4s   $0.0002
  pipeline_stage extract ─┘   (CUAD clause extract)   17.1s   $0.031
  pipeline_stage score        (risk per clause)        3.1s   $0.001
  pipeline_stage summarize    (plain-English summary)  1.7s   $0.008

  ✅ Bottleneck: extract (73% of time)
  ✅ Cost driver: extract (74% of cost)
  ✅ Embed + extract ran concurrently — saved ~1.4s
```

Every span carries `gen_ai.provider.name`, `gen_ai.request.model`, token counts, and cost. Swap to Google or Ollama with a single env var — the traces look identical.

---

## Pipeline

```
POST /api/contracts
    │
    ├─ ingest      Parse PDF or plain text, split into chunks
    ├─ route       Fast model classifies document type + complexity
    ├─ embed  ─┐   Embedding model indexes chunks for semantic search   (concurrent)
    ├─ extract ┘   Capable model extracts 41 CUAD clause types
    ├─ score       Capable model scores risk level per clause
    └─ summarize   Capable model writes plain-English summary for review
         │
         └─ PostgreSQL 18 + pgvector
              ├─ contracts, analyses
              ├─ clauses, risks
              └─ chunks  VECTOR(768), HNSW index
```

---

## Quick Start

### Prerequisites

- [Bun](https://bun.sh) 1.2+
- Docker + Docker Compose
- An API key for your chosen LLM provider (none needed for Ollama)

### Setup

```bash
cp .env.example .env
# Set LLM_PROVIDER and the matching API key (see Configuration below)

docker compose up -d postgres otel-collector
bun install
bun run db:migrate
bun run dev
```

### Analyze a contract

```bash
curl -X POST http://localhost:3000/api/contracts \
  -F "file=@data/contracts/sample-nda.txt;type=text/plain"
```

```json
{
  "contract_id": "abc-123",
  "overall_risk": "low",
  "clauses_found": 7,
  "total_duration_ms": 18400,
  "trace_id": "8a3b1d5e2f4c6d8e"
}
```

---

## API

| Method | Path | Description |
|---|---|---|
| `GET` | `/health` | Health check with DB connectivity |
| `POST` | `/api/contracts` | Upload and analyze a contract |
| `GET` | `/api/contracts` | List all analyzed contracts |
| `GET` | `/api/contracts/:id` | Full result — clauses, risks, summary |
| `POST` | `/api/contracts/:id/query` | Ask a question about a specific contract |
| `POST` | `/api/search` | Semantic search across all contracts |

```bash
# Ask a question about a contract
curl -X POST http://localhost:3000/api/contracts/abc-123/query \
  -H "Content-Type: application/json" \
  -d '{"question": "What is the liability cap?"}'

# Semantic search
curl -X POST http://localhost:3000/api/search \
  -H "Content-Type: application/json" \
  -d '{"query": "indemnification obligations", "limit": 5}'
```

---

## Observability

### Instrumentation Approach

GenAI telemetry is handled by a custom `LanguageModelV3Middleware` in `src/llm/middleware.ts`, not by the `@traceloop/node-server-sdk` auto-instrumentation. Auto-instrumentation wraps individual SDK calls but doesn't understand the pipeline — it can't attribute cost to a stage, correlate a retry to a specific span, or differentiate embedding tokens from extraction tokens.

The custom middleware wraps every `doGenerate` call at the model layer, so all routes — pipeline stages, `/query`, `/search` — are instrumented identically with no per-route wiring.

### What's Instrumented

| Layer | Instrumentation | Type | What You Get |
|---|---|---|---|
| HTTP server | Hono `requestMetrics` middleware | Custom | `http.server.request.duration`, `http.server.request.count` per method/path/status |
| HTTP server | `@opentelemetry/instrumentation-http` | Auto | Request spans with `http.method`, `http.route`, `http.status_code` |
| Database | `@opentelemetry/instrumentation-pg` | Auto | Query spans with SQL and duration |
| LLM calls | `LanguageModelV3Middleware` | Custom | `gen_ai.chat {model}` spans with GenAI semconv attributes, retry, cost |
| LLM metrics | `LanguageModelV3Middleware` | Custom | Token usage, cost, operation duration, retry count, fallback count, error count |
| Pipeline stages | `orchestrator.ts` | Custom | `pipeline_stage {name}` child spans with stage-specific attributes |
| Logs | `@opentelemetry/sdk-logs` | Custom | OTLP log export correlated with active trace via `trace_id` / `span_id` |

### Span Attributes

Each `gen_ai.chat {model}` span carries:

| Attribute | Example |
|---|---|
| `gen_ai.operation.name` | `chat` |
| `gen_ai.provider.name` | `anthropic` |
| `gen_ai.request.model` | `claude-sonnet-4-6` |
| `gen_ai.response.model` | `claude-sonnet-4-6` |
| `gen_ai.response.id` | `msg_abc123` |
| `gen_ai.response.finish_reasons` | `["end_turn"]` |
| `gen_ai.usage.input_tokens` | `25000` |
| `gen_ai.usage.output_tokens` | `820` |
| `gen_ai.usage.cost_usd` | `0.031` |
| `server.address` | `api.anthropic.com` |
| `error.type` | `Error` (on failure) |

Span events: `gen_ai.user.message` (prompt, truncated to 1000 chars; system prompt to 500) and `gen_ai.assistant.message` (completion, truncated to 2000).

### Metrics

| Metric | Type | Description |
|---|---|---|
| `gen_ai.client.operation.duration` | Histogram | LLM call duration per model |
| `gen_ai.client.token.usage` | Histogram | Tokens per call, split by `gen_ai.token.type` (`input` / `output`) |
| `gen_ai.client.cost` | Counter | Cost in USD per model |
| `gen_ai.client.retry.count` | Counter | Retry attempts per model |
| `gen_ai.client.fallback.count` | Counter | Fallback activations per primary provider |
| `gen_ai.client.error.count` | Counter | Failed calls per model and error type |
| `contract.analysis.duration` | Histogram | End-to-end pipeline duration |
| `contract.clauses.extracted` | Histogram | Clauses found per contract |
| `contract.risk.score` | Histogram | Risk score distribution |
| `contract.embedding.duration` | Histogram | Embedding generation duration |
| `http.server.request.duration` | Histogram | HTTP request duration per route |
| `http.server.request.count` | Counter | HTTP request count per route and status |

### Retry and Fallback

The middleware retries every error (not just network errors) with exponential backoff — 3 attempts, 1–10s. If a fallback provider is configured, it activates after all retries are exhausted and records `gen_ai.client.fallback.count`. Both the retry loop and fallback are covered by unit tests in `tests/llm/middleware.test.ts`.

---

## Configuration

```bash
cp .env.example .env
```

| Variable | Default | Description |
|---|---|---|
| `LLM_PROVIDER` | `anthropic` | LLM provider: `anthropic`, `google`, `ollama` |
| `LLM_MODEL_CAPABLE` | _(provider default)_ | Model for extract / score / summarize |
| `LLM_MODEL_FAST` | _(provider default)_ | Model for routing |
| `LLM_PROVIDER_FALLBACK` | — | Fallback provider if primary exhausts retries |
| `LLM_MODEL_FALLBACK` | — | Model to use on the fallback provider |
| `EMBEDDING_PROVIDER` | `openai` | Embedding provider: `openai`, `google`, `ollama` |
| `EMBEDDING_MODEL` | _(provider default)_ | Embedding model override |
| `ANTHROPIC_API_KEY` | — | Required when `LLM_PROVIDER=anthropic` |
| `GOOGLE_GENERATIVE_AI_API_KEY` | — | Required when `LLM_PROVIDER=google` or `EMBEDDING_PROVIDER=google` |
| `OPENAI_API_KEY` | — | Required when `EMBEDDING_PROVIDER=openai` |
| `OLLAMA_BASE_URL` | `http://localhost:11434` | Required when using Ollama |
| `DATABASE_URL` | `postgresql://...@localhost:5434/contract_analyzer` | PostgreSQL connection string |
| `OTEL_ENABLED` | `true` | Set to `false` to disable telemetry |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | `http://localhost:4318` | OTel Collector endpoint |
| `OTEL_SERVICE_NAME` | `ai-contract-analyzer` | Service name in traces |
| `SCOUT_CLIENT_ID` / `SCOUT_CLIENT_SECRET` | — | Base14 Scout OAuth credentials |

**Provider defaults:**

| Provider | Capable model | Fast model |
|---|---|---|
| Anthropic | `claude-sonnet-4-6` | `claude-haiku-4-5-20251001` |
| Google | `gemini-2.5-flash` | `gemini-2.0-flash` |
| Ollama | `llama3.1:8b` | `llama3.2` |

---

## Development

```bash
bun run dev          # Run with file watching
bun run check        # lint + typecheck + tests (42 tests, 11 files)
bun run test         # Unit tests only
bun run test:api     # API smoke tests (server must be running)
docker compose up -d # Start PostgreSQL + OTel Collector
docker compose down -v
```

Tests are fully mocked — no database or API keys required.

---

## Project Structure

```
src/
├── llm/
│   └── middleware.ts       # LanguageModelV3Middleware — spans, retry, metrics, fallback  ⭐
├── pipeline/
│   ├── orchestrator.ts     # Six-stage pipeline coordinator with trace per stage  ⭐
│   ├── ingest.ts           # PDF / plain-text parsing, chunking
│   ├── route.ts            # Document type classification
│   ├── embed.ts            # Embedding generation (batched)
│   ├── extract.ts          # CUAD clause extraction with structured output
│   ├── score.ts            # Risk scoring per clause
│   └── summarize.ts        # Plain-English summary
├── routes/
│   ├── contracts.ts        # POST /api/contracts, GET /api/contracts/:id
│   ├── query.ts            # POST /api/contracts/:id/query
│   ├── search.ts           # POST /api/search
│   └── health.ts           # GET /health
├── middleware/
│   └── metrics.ts          # HTTP request duration + count metrics
├── db/                     # pg query helpers (contracts, chunks, clauses, risks, analyses)
├── providers.ts            # Model construction — applies middleware, pricing, fallback  ⭐
├── config.ts               # Typed env var config
├── telemetry.ts            # OTel SDK setup (traces, metrics, logs)
└── logger.ts               # Structured JSON logger with trace correlation

tests/
├── llm/middleware.test.ts  # Retry, fallback, pass-through behavioral tests  ⭐
├── pipeline/               # Orchestrator, extract, score, summarize, ingest, router
└── routes/                 # contracts, search HTTP handler tests

⭐ = Key observability files
```

---

## Troubleshooting

### No traces in Scout

```bash
# Check collector is running and accepting data
docker compose ps
curl -s -o /dev/null -w "%{http_code}" http://localhost:4318/v1/traces  # expect 405

# Check zpages for pipeline debug
open http://localhost:55679/debug/tracez
```

Verify `OTEL_ENABLED` is not `false` and `SCOUT_CLIENT_ID` / `SCOUT_CLIENT_SECRET` are set.

### LLM calls failing

Check the API key for your active provider. The middleware retries 3 times with exponential backoff before throwing, so transient errors won't surface immediately. Set `LLM_PROVIDER_FALLBACK` to route to a secondary provider after retries are exhausted.

### Database connection issues

```bash
docker compose ps
docker compose logs postgres
docker compose exec postgres psql -U postgres -c "SELECT 1;"
```

The app connects to port `5434` by default (mapped from container port 5432 to avoid conflicts).

---

## References

- [OpenTelemetry GenAI Semantic Conventions](https://opentelemetry.io/docs/specs/semconv/gen-ai/)
- [Vercel AI SDK — Middleware](https://sdk.vercel.ai/docs/ai-sdk-core/middleware)
- [Vercel AI SDK — Structured Output](https://sdk.vercel.ai/docs/ai-sdk-core/generating-structured-data)
- [CUAD Dataset](https://www.atticusprojectai.org/cuad)
- [pgvector for Node.js](https://github.com/pgvector/pgvector-node)
- [Base14 Scout Documentation](https://docs.base14.io/)
