# AI Contract Analyzer

> [Full Documentation](https://docs.base14.io/guides/ai-observability/llm-observability/)

AI-powered contract analysis pipeline demonstrating **multi-stage LLM observability** with OpenTelemetry GenAI semantic conventions and Base14 Scout.

**Stack**: Bun 1.3 · Hono 4 · Vercel AI SDK 6 · Ollama / Anthropic / Google · PostgreSQL 18 + pgvector · OpenTelemetry

## How to instrument Vercel AI SDK with OpenTelemetry

1. Install `ai` and a provider package (`@ai-sdk/openai` also serves Ollama through its
   OpenAI-compatible API, plus `@ai-sdk/anthropic` and `@ai-sdk/google`), plus
   `@opentelemetry/sdk-node`, `@opentelemetry/api`, `@opentelemetry/instrumentation-pg`,
   `@opentelemetry/sdk-metrics`, `@opentelemetry/sdk-logs`,
   `@opentelemetry/exporter-trace-otlp-http`, `@opentelemetry/exporter-metrics-otlp-http` and
   `@opentelemetry/exporter-logs-otlp-http`.
2. Preload `src/telemetry.ts` with `bun run --preload ./src/telemetry.ts src/index.ts`; it starts
   a `NodeSDK` with OTLP trace and metric exporters and `PgInstrumentation`. Wrap each model with
   `withSemconv()` from `src/llm/middleware.ts`, which uses the AI SDK `wrapLanguageModel()` to open
   a `chat {model}` CLIENT span around every call.
3. Set `OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4318`, `OTEL_SERVICE_NAME=ai-contract-analyzer`,
   `OTEL_ENABLED=true` and `OTEL_SEMCONV_STABILITY_OPT_IN=gen_ai_latest_experimental` in `.env`.

This example adds GenAI semantic convention span attributes and events, the `gen_ai.client.*` and
`base14.gen_ai.*` metrics for token usage, cost, duration, retries and fallbacks, a span per
pipeline stage, and provider fallback. The full guide is
[Vercel AI SDK OpenTelemetry Instrumentation](https://docs.base14.io/instrument/apps/auto-instrumentation/vercel-ai-sdk/).

---

## Why Multi-Stage Observability?

A single LLM call is easy to trace. A multi-stage pipeline needs a span per stage. When a contract
analysis takes 25 seconds, one span cannot show whether the bottleneck is extraction (the LLM),
embedding (the model), or ingest (PDF parsing). When cost spikes, one span cannot show which stage
caused it.

This project shows how to instrument a six-stage AI pipeline so every trace answers those questions:

```text
analyze_contract                                      23.4s   $0.042
  pipeline_stage ingest       (pdf-parse + chunk)      0.8s
  pipeline_stage route        (classify doc type)      0.3s   $0.0001
  pipeline_stage embed ───┐   (embedding model)        1.4s   $0.0002
  pipeline_stage extract ─┘   (CUAD clause extract)   17.1s   $0.031
  pipeline_stage score        (risk per clause)        3.1s   $0.001
  pipeline_stage summarize    (plain-English summary)  1.7s   $0.008

  ✅ Bottleneck: extract (73% of time)
  ✅ Cost driver: extract (74% of cost)
  ✅ Embed + extract ran concurrently - saved ~1.4s
```

Every chat span carries `gen_ai.provider.name`, `gen_ai.request.model`, token counts and cost. Swap
to Anthropic or Google with a single env var and the traces look the same.

---

## Pipeline

```text
POST /api/contracts
    │
    ├─ ingest      Parse PDF or plain text, split into chunks
    ├─ route       Fast model classifies document type + complexity
    ├─ embed  ─┐   Embedding model indexes chunks for semantic search   (concurrent)
    ├─ extract ┘   Capable model extracts the CUAD clauses for that document type
    ├─ score       Fast model scores risk level per clause
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

- [Bun](https://bun.sh) 1.3+.
- Docker + Docker Compose.
- [Ollama](https://ollama.ai) with `qwen3.5:9B` and `embeddinggemma` pulled and a context of at
  least 32768 tokens, or an API key for Anthropic or Google.

Ollama serves a 4096-token context by default. The extract and score stages send a prompt, a JSON
schema and expect a JSON answer that together run past it, and the answer comes back cut off, so
raise the context to 32768 before the first run.

The context is read by the Ollama daemon at startup, not by this app, so how you set it depends on
how the daemon is started. Prefixing `ollama serve` with the variable only works when you start the
daemon yourself in that shell; it does nothing if something else already holds port 11434.

- Homebrew service: `launchctl setenv OLLAMA_CONTEXT_LENGTH 32768`, then
  `brew services restart ollama`.
- macOS Ollama app: `launchctl setenv OLLAMA_CONTEXT_LENGTH 32768`, then quit and reopen the app.
- Daemon you start yourself: stop it, then run `OLLAMA_CONTEXT_LENGTH=32768 ollama serve`.
- Linux with systemd: add a drop-in with
  `Environment="OLLAMA_CONTEXT_LENGTH=32768"`, then `systemctl daemon-reload` and
  `systemctl restart ollama`.

Check it with `ollama ps`, which prints a CONTEXT column for each loaded model. The column reflects
how the model was loaded, so it updates after the next request rather than the moment you restart.

Expect the sample NDA to take between ten and twenty-five minutes on `qwen3.5:9B` on a laptop,
most of it in the extract stage, which generates a few thousand tokens of JSON at a few tokens per
second. Requests to Ollama run with Bun's 300 second fetch timeout turned off for that reason. The
scripts under `scripts/` allow up to thirty minutes for that upload. A hosted provider finishes the
same contract in under a minute.

### Setup

The defaults run against a local Ollama and need no API key.

```bash
cp .env.example .env

docker compose up -d postgres otel-collector
bun install
bun run db:migrate
bun run dev
```

To run Ollama in Compose instead of on the host:

```bash
docker compose --profile ollama up -d
docker compose exec ollama ollama pull qwen3.5:9B
docker compose exec ollama ollama pull embeddinggemma
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
| `GET` | `/api/contracts/:id` | Full result - clauses, risks, summary |
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

GenAI telemetry comes from a `LanguageModelV3Middleware` in `src/llm/middleware.ts`. It wraps every
`doGenerate` call at the model layer, so all routes - pipeline stages, `/query`, `/search` - are
instrumented the same way with no per-route wiring.

The middleware sits at the model layer rather than the SDK layer because the pipeline's questions
are about stages: which stage drove the cost, which retry belongs to which span, how embedding
tokens differ from extraction tokens.

### What's Instrumented

| Layer | Instrumentation | Type | What You Get |
|---|---|---|---|
| HTTP server | Hono `httpTracing` middleware | Custom | SERVER spans named `{METHOD} {route}`, ERROR status on 400 and above |
| HTTP server | Hono `requestMetrics` middleware | Custom | `http.server.request.duration`, `http.server.request.count` per method, path and status |
| Database | `@opentelemetry/instrumentation-pg` | Auto | Query spans with SQL and duration |
| LLM calls | `LanguageModelV3Middleware` | Custom | `chat {model}` CLIENT spans with GenAI semconv attributes, retry and cost |
| Embeddings | `src/llm/embeddings.ts` | Custom | `embeddings {model}` CLIENT spans with token usage and cost |
| Retrieval | `src/llm/retrieval.ts` | Custom | `retrieval contract_chunks` CLIENT spans around the pgvector lookup |
| LLM metrics | `src/llm/instruments.ts` | Custom | Token usage, cost, operation duration, retry count, fallback count, error count |
| Pipeline stages | `orchestrator.ts` | Custom | `pipeline_stage {name}` child spans with stage-specific attributes |
| Logs | `@opentelemetry/sdk-logs` | Custom | OTLP log export correlated with the active trace via `trace_id` and `span_id` |

Bun serves the app through `Bun.serve`, which `@opentelemetry/instrumentation-http` does not patch,
so the HTTP server span is opened by Hono middleware instead of by auto-instrumentation.

### Span Attributes

Each `chat {model}` span carries:

| Attribute | Example |
|---|---|
| `gen_ai.operation.name` | `chat` |
| `gen_ai.provider.name` | `ollama`, `anthropic`, `gcp.gemini` |
| `gen_ai.request.model` | `qwen3.5:9B` |
| `gen_ai.request.temperature` | `0.2` |
| `gen_ai.request.max_tokens` | `1000` |
| `gen_ai.response.model` | `qwen3.5:9B` |
| `gen_ai.response.id` | `msg_abc123` |
| `gen_ai.response.finish_reasons` | `["end_turn"]` |
| `gen_ai.usage.input_tokens` | `25000` |
| `gen_ai.usage.output_tokens` | `820` |
| `base14.gen_ai.cost_usd` | `0.031` |
| `server.address` | `localhost` |
| `server.port` | `11434` |
| `error.type` | `Error` (on failure) |

The config key `google` selects Gemini; the emitted `gen_ai.provider.name` for it is `gcp.gemini`.

Token counts sit on the `chat {model}` span only. Pipeline stage spans carry stage rollups under
`base14.gen_ai.usage.input_tokens` and `base14.gen_ai.usage.output_tokens`.

One span event per call, `gen_ai.client.inference.operation.details`, carries
`gen_ai.input.messages` (1000 chars), `gen_ai.output.messages` (2000) and
`gen_ai.system_instructions` (500, omitted when empty). It is emitted only when
`OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT=true`, and the content is PII-scrubbed by
`src/llm/scrub.ts` first. The default is off.

### Metrics

| Metric | Type | Description |
|---|---|---|
| `gen_ai.client.operation.duration` | Histogram | Call duration per operation, provider and model, with `error.type` on failure |
| `gen_ai.client.token.usage` | Histogram | Tokens per call, split by `gen_ai.token.type` (`input` / `output`) |
| `base14.gen_ai.cost` | Counter | Cost in USD per model |
| `base14.gen_ai.retry.count` | Counter | Retry attempts, excluding the initial attempt |
| `base14.gen_ai.fallback.count` | Counter | Fallback activations per primary provider |
| `base14.gen_ai.error.count` | Counter | Failed calls per provider and error type |
| `base14.contract.analysis.duration` | Histogram | End-to-end pipeline duration |
| `base14.contract.clauses.extracted` | Histogram | Clauses found per contract |
| `base14.contract.risk.score` | Histogram | Risk score distribution |
| `base14.contract.embedding.duration` | Histogram | Embedding generation duration |
| `http.server.request.duration` | Histogram | HTTP request duration per route |
| `http.server.request.count` | Counter | HTTP request count per route and status |

### Retry and Fallback

The middleware retries every error, not just network errors, with exponential backoff: 3 attempts,
1 s to 10 s. Each retry increments `base14.gen_ai.retry.count` and adds a `base14.gen_ai.retry`
event to the chat span.

When `FALLBACK_PROVIDER` is set, the fallback provider is called after the retries are
exhausted. The switch adds a `provider_fallback` event and `gen_ai.fallback.triggered=true` to the
calling span and increments `base14.gen_ai.fallback.count`. The calling span is not marked ERROR,
because the operation still succeeded.

`tests/llm/middleware.test.ts` covers the retry loop, the content-capture gate and the pricing
fallback. `tests/llm/vectors.test.ts` drives the three shared vectors in `_shared/test-vectors`
through the same wrappers and asserts what reaches the in-memory span and metric exporters.

---

## Configuration

```bash
cp .env.example .env
```

| Variable | Default | Description |
|---|---|---|
| `LLM_PROVIDER` | `ollama` | LLM provider: `ollama`, `anthropic`, `google` |
| `LLM_MODEL_CAPABLE` | _(provider default)_ | Model for extract / score / summarize |
| `LLM_MODEL_FAST` | _(provider default)_ | Model for routing |
| `FALLBACK_PROVIDER` | - | Fallback provider if primary exhausts retries |
| `FALLBACK_MODEL` | - | Model to use on the fallback provider |
| `EMBEDDING_PROVIDER` | `ollama` | Embedding provider: `ollama`, `openai`, `google` |
| `EMBEDDING_MODEL` | _(provider default)_ | Embedding model override |
| `ANTHROPIC_API_KEY` | - | Required when `LLM_PROVIDER=anthropic` |
| `GOOGLE_GENERATIVE_AI_API_KEY` | - | Required when `LLM_PROVIDER=google` or `EMBEDDING_PROVIDER=google` |
| `OPENAI_API_KEY` | - | Required when `EMBEDDING_PROVIDER=openai` |
| `OLLAMA_BASE_URL` | `http://host.docker.internal:11434` | Required when using Ollama; use `http://localhost:11434` when running the app directly on the host |
| `DATABASE_URL` | `postgresql://...@localhost:5434/contract_analyzer` | PostgreSQL connection string |
| `OTEL_ENABLED` | `true` | Set to `false` to disable telemetry |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | `http://localhost:4318` | OTel Collector endpoint |
| `OTEL_SERVICE_NAME` | `ai-contract-analyzer` | Service name in traces |
| `OTEL_SEMCONV_STABILITY_OPT_IN` | `gen_ai_latest_experimental` | Keeps SDKs on the current GenAI attribute names |
| `OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT` | `false` | Set to `true` to record scrubbed prompts and completions |
| `SCOUT_CLIENT_ID` / `SCOUT_CLIENT_SECRET` | - | Base14 Scout OAuth credentials |

**Provider defaults:**

| Provider | Capable model | Fast model | Embedding model |
|---|---|---|---|
| Ollama | `qwen3.5:9B` | `qwen3.5:9B` | `embeddinggemma` |
| Anthropic | `claude-sonnet-4-6` | `claude-haiku-4-5-20251001` | - |
| Google | `gemini-2.5-flash` | `gemini-2.5-flash-lite` | `gemini-embedding-001` |
| OpenAI | - | - | `text-embedding-3-small` |

Prices come from `_shared/pricing.json` at the repo root. A model the file does not list costs
`0.0`, which is what the local Ollama models do.

---

## Development

```bash
make dev             # Run with file watching
make check           # lint, typecheck, build and tests
make test            # Unit tests only
make test-api        # API smoke tests (server must be running)
make verify          # Telemetry verification against the collector debug output
docker compose up -d # Start the app, PostgreSQL and the OTel Collector
docker compose down
```

The tests need no database and no API keys. They mock the provider SDKs and assert against
in-memory OTel exporters.

---

## Project Structure

```text
src/
├── llm/
│   ├── middleware.ts       # LanguageModelV3Middleware - chat spans, retry, metrics, fallback  ⭐
│   ├── embeddings.ts       # embeddings {model} spans
│   ├── retrieval.ts        # retrieval {data_source} spans over pgvector
│   ├── instruments.ts      # The six GenAI metric instruments
│   ├── pricing.ts          # _shared/pricing.json lookup and model id normalization
│   └── scrub.ts            # PII scrubbing for captured content
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
│   ├── tracing.ts          # HTTP SERVER spans, ERROR on status 400 and above
│   └── metrics.ts          # HTTP request duration and count metrics
├── db/                     # pg query helpers (contracts, chunks, clauses, risks, analyses)
├── providers.ts            # Model construction - applies middleware, pricing, fallback  ⭐
├── config.ts               # Typed env var config
├── telemetry.ts            # OTel SDK setup (traces, metrics, logs)
└── logger.ts               # Structured JSON logger with trace correlation

tests/
├── telemetry.ts            # In-memory span and metric exporters for the tests
├── llm/middleware.test.ts  # Retry, fallback, content capture, pricing  ⭐
├── llm/vectors.test.ts     # The three _shared/test-vectors cases  ⭐
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

### Upload returns 500 and the log says "No object generated"

The model returned something the schema could not parse. With Ollama this is almost always the
context window: check `ollama ps` and raise it to 32768 if the CONTEXT column shows 4096, following
[Prerequisites](#prerequisites) for the way your daemon is started. The trace names the
stage, because a stage that throws still ends its span with an error status.

Two settings already guard against the other causes. Requests to Ollama carry
`reasoning: { effort: "none" }` on the responses route the AI SDK uses, because a thinking model
otherwise returns its reasoning on a separate channel and leaves the message content empty; the
chat completions spelling `reasoning_effort` is ignored there and the model thinks until the
request times out. The extract and score schemas are narrowed to the
clause types the document type actually uses, rather than all 42 CUAD types.

### Upload returns 415 "Document is not a recognized contract type"

The route stage asks the fast model to classify the document and the pipeline stops when it answers
`unknown`. Small local models often do, because the classifier prompt tells them to prefer `unknown`
when unsure. The telemetry is still complete for the stages that ran: the `pipeline_stage route`
span carries `base14.route.document_type=unknown`, and the HTTP span carries `error.type=415`. Use a larger
local model or a hosted provider to get the full six-stage trace.

### LLM calls failing

With the default `LLM_PROVIDER=ollama`, check that Ollama is running and that `qwen3.5:9B` and
`embeddinggemma` are pulled. For a hosted provider, check its API key. The middleware retries 3
times with exponential backoff before throwing, so transient errors do not surface immediately.
Set `FALLBACK_PROVIDER` to route to a secondary provider after the retries are exhausted.

### Database connection issues

```bash
docker compose ps
docker compose logs postgres
docker compose exec postgres psql -U postgres -c "SELECT 1;"
```

The app connects to port `5434` by default (mapped from container port 5432 to avoid conflicts).

---

## References

- [OpenTelemetry GenAI Semantic Conventions](https://opentelemetry.io/docs/specs/semconv/gen-ai/).
- [Vercel AI SDK - Middleware](https://sdk.vercel.ai/docs/ai-sdk-core/middleware).
- [Vercel AI SDK - Structured Output](https://sdk.vercel.ai/docs/ai-sdk-core/generating-structured-data).
- [CUAD Dataset](https://www.atticusprojectai.org/cuad).
- [pgvector for Node.js](https://github.com/pgvector/pgvector-node).
- [Base14 Scout Documentation](https://docs.base14.io/).
