# AI Contract Analyzer

A production-grade contract analysis pipeline built with **Bun + Hono + Vercel AI SDK + Anthropic Claude**, demonstrating how to build and observe a multi-stage AI document processing pipeline with [OpenTelemetry](https://opentelemetry.io/) and [Base14 Scout](https://base14.io).

---

## What It Does

Legal teams spend 2-4 hours per contract on initial review. This pipeline compresses that to ~20 seconds by:

1. **Ingesting** the document (PDF or plain text) and splitting it into semantic chunks
2. **Embedding** each chunk with OpenAI `text-embedding-3-small` for semantic search
3. **Extracting** all 41 [CUAD clause types](https://www.atticusprojectai.org/cuad) using Claude Sonnet with structured output
4. **Scoring** risk level per clause with Claude Haiku
5. **Summarizing** in plain English for attorney review with Claude Sonnet

Every stage emits structured OpenTelemetry spans. You get a single trace showing the full pipeline with token counts, latency, cost, and extraction confidence — all visible in Scout.

---

## Architecture

```
POST /api/contracts
    │
    ├─ pipeline_stage ingest      (pdf-parse, chunking)
    ├─ pipeline_stage embed       (OpenAI text-embedding-3-small)
    ├─ pipeline_stage extract     (claude-sonnet-4-6, generateObject + Zod)
    ├─ pipeline_stage score       (claude-haiku-4-5, generateObject + Zod)
    └─ pipeline_stage summarize   (claude-sonnet-4-6, generateObject + Zod)
         │
         └─ PostgreSQL 18 + pgvector
              ├─ contracts, analyses
              ├─ clauses, risks
              └─ chunks (VECTOR(1536), HNSW index)

OTel Collector → Base14 Scout
```

### Tech Stack

| Component | Choice |
|---|---|
| Runtime | Bun 1.2+ |
| HTTP | Hono 4.12 |
| AI Framework | Vercel AI SDK 6 |
| LLM | Anthropic Claude (Sonnet 4.6 + Haiku 4.5) |
| Embeddings | OpenAI text-embedding-3-small |
| Observability | OpenLLMetry (`@traceloop/node-server-sdk`) |
| Database | PostgreSQL 18 + pgvector |

---

## Quick Start

### 1. Prerequisites

- [Bun](https://bun.sh) 1.2+
- Docker + Docker Compose
- An Anthropic API key
- An OpenAI API key (for embeddings)
- A Base14 Scout account (for production traces; optional for local dev)

### 2. Configure

```bash
cp .env.example .env
# Edit .env — set ANTHROPIC_API_KEY and OPENAI_API_KEY at minimum
```

### 3. Start infrastructure

```bash
make docker-up
# Starts PostgreSQL 18 + pgvector and the OTel Collector
```

### 4. Install and run

```bash
make install
bun run dev
```

### 5. Analyze a contract

```bash
curl -X POST http://localhost:3000/api/contracts \
  -F "file=@data/contracts/sample-nda.txt;type=text/plain"
```

Response:
```json
{
  "contract_id": "abc-123",
  "overall_risk": "low",
  "clauses_found": 7,
  "total_duration_ms": 18400,
  "trace_id": "8a3b1d5e2f4c6d8e"
}
```

### 6. Seed sample contracts

```bash
make seed
# Loads all contracts from data/contracts/ through the full pipeline
```

---

## API Reference

| Method | Path | Description |
|---|---|---|
| `GET` | `/health` | Health check with DB connectivity |
| `POST` | `/api/contracts` | Upload + analyze a contract |
| `GET` | `/api/contracts` | List all analyzed contracts |
| `GET` | `/api/contracts/:id` | Full analysis result (clauses, risks, summary) |
| `POST` | `/api/contracts/:id/query` | Ask a question about a specific contract |
| `POST` | `/api/search` | Semantic search across all contracts |

### Upload a contract

```bash
curl -X POST http://localhost:3000/api/contracts \
  -F "file=@contract.pdf;type=application/pdf"
```

Accepts: `application/pdf`, `text/plain`

### Query a contract

```bash
curl -X POST http://localhost:3000/api/contracts/abc-123/query \
  -H "Content-Type: application/json" \
  -d '{"question": "What is the liability cap?"}'
```

### Semantic search

```bash
curl -X POST http://localhost:3000/api/search \
  -H "Content-Type: application/json" \
  -d '{"query": "indemnification obligations", "limit": 5}'
```

---

## Observability

### What You See in Scout

Every contract analysis produces a single trace with child spans:

```
analyze_contract                              ~20s
  pipeline_stage ingest                       0.8s
    document.page_count: 24
    document.chunks_created: 52
  pipeline_stage embed                        1.4s
    gen_ai.usage.input_tokens: 12000
    embedding.batch_count: 3
  pipeline_stage extract                     14.2s
    gen_ai.request.model: claude-sonnet-4-6
    gen_ai.usage.input_tokens: 25000
    extraction.clauses_found: 18
    extraction.confidence_avg: 0.84
  pipeline_stage score                        3.2s
    gen_ai.request.model: claude-haiku-4-5-20251001
    risk.overall: high
    risk.critical_count: 2
  pipeline_stage summarize                    2.4s
    gen_ai.request.model: claude-sonnet-4-6
    summary.word_count: 340
```

### OpenLLMetry Auto-Instrumentation

All Vercel AI SDK calls are automatically instrumented by `@traceloop/node-server-sdk`. No manual wiring needed — GenAI semantic convention spans with `gen_ai.*` attributes appear automatically on every LLM call.

### Metrics

| Metric | Type | Description |
|---|---|---|
| `contract.analysis.duration` | Histogram | End-to-end pipeline duration |
| `contract.clauses.extracted` | Histogram | Clauses found per contract |
| `contract.risk.score` | Histogram | Risk score distribution |
| `gen_ai.client.token.usage` | Histogram | Token usage per model per stage |
| `gen_ai.client.cost` | Counter | Cost per model per stage |
| `contract.search.similarity` | Histogram | Search result similarity scores |

---

## Failure Injection

The `scripts/inject-failures.ts` toolkit demonstrates 7 failure scenarios. Each produces a distinct trace pattern in Scout.

```bash
# Run a specific scenario
bun run scripts/inject-failures.ts hallucination
bun run scripts/inject-failures.ts token-overflow
bun run scripts/inject-failures.ts embedding-failure
bun run scripts/inject-failures.ts malformed-pdf
bun run scripts/inject-failures.ts encrypted-pdf
bun run scripts/inject-failures.ts batch-overload
bun run scripts/inject-failures.ts contradictory-clauses

# Run all scenarios
bun run scripts/inject-failures.ts
```

| Scenario | What happens | What Scout shows |
|---|---|---|
| `hallucination` | Minimal contract forces over-extraction | Low `extraction.confidence_avg`, clauses with no text excerpt |
| `token-overflow` | 675K+ char document exceeds 200K context | `document.total_characters` >> threshold, console warning |
| `embedding-failure` | Simulated 429 from OpenAI | Embed span `SpanStatus=ERROR`, `http_status=429` |
| `malformed-pdf` | Corrupted file upload | Ingest span `PARSE_ERROR`, pipeline aborts |
| `encrypted-pdf` | Password-protected PDF | Same `PARSE_ERROR` path as corrupted |
| `batch-overload` | All contracts uploaded concurrently | Cost counter spike, concurrent `analyze_contract` spans |
| `contradictory-clauses` | Contract has irrevocable + termination-for-convenience | Score stage flags contradiction |

---

## Development

```bash
make install        # Install dependencies
make dev            # Run with file watching
make check          # lint + typecheck + tests
make test           # Unit tests only
make test-api       # API smoke tests (server must be running)
make docker-up      # Start PostgreSQL + OTel Collector
make docker-down    # Stop and remove containers + volumes
```

### Running Tests

```bash
make test
# or
vitest run

# With coverage
vitest run --coverage
```

Tests are fully mocked — no database or API keys required.

---

## Cost Estimate

Per contract analysis (20-page document):

| Stage | Model | Typical Cost |
|---|---|---|
| Embed | text-embedding-3-small | ~$0.0002 |
| Extract | claude-sonnet-4-6 | ~$0.031 |
| Score | claude-haiku-4-5 | ~$0.001 |
| Summarize | claude-sonnet-4-6 | ~$0.008 |
| **Total** | | **~$0.040** |

At 50 contracts/day: ~$2/day, ~$60/month.

---

## References

- [Vercel AI SDK — Structured Output](https://sdk.vercel.ai/docs/ai-sdk-core/generating-structured-data)
- [OpenLLMetry Documentation](https://www.traceloop.com/docs/openllmetry/getting-started-ts)
- [Hono Documentation](https://hono.dev/)
- [pgvector for Node.js](https://github.com/pgvector/pgvector-node)
- [CUAD Dataset](https://www.atticusprojectai.org/cuad)
- [OpenTelemetry GenAI Semantic Conventions](https://opentelemetry.io/docs/specs/semconv/gen-ai/)
