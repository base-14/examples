# Architecture Patterns: AI Contract Analyzer

This document maps the agentic patterns implemented in this codebase and the improvements that remain open.

---

## What This Project Uses Today

### Pipeline shape

```
ingest → route → ┬─→ embed ──────────────┐
                 │                       ├─→ score → summarize
                 └─→ extract ────────────┘
```

Implemented in `src/pipeline/orchestrator.ts`. Each stage is a separate module wrapped in an OTel span, and the orchestrator accumulates tokens, cost, and results across all of them.

Ingest creates the contract row and chunks the document. Route classifies it. Embed and extract then run concurrently under a single `Promise.all` — both read only `ingestResult.full_text`, so neither blocks the other. Score needs the clause list from extract, and summarize needs both the extraction and the risk scores, so those two stay sequential at the tail.

### Routing

`src/pipeline/route.ts` classifies the document with the fast model before the main pipeline runs. It returns `document_type`, `complexity`, and `requires_full_analysis` from the first 3000 characters.

An `unknown` document type throws with `code: "UNSUPPORTED_TYPE"`, which `src/routes/contracts.ts` maps to a 415 response. Non-contracts are rejected before any embedding or extraction cost is incurred.

### Progressive context disclosure

`src/types/clauses.ts` defines `CLAUSES_BY_TYPE`, mapping each document type to the clause subset relevant to it. `extractClauses()` receives `routeResult.document_type` and builds its system prompt from that subset instead of all 41 CUAD clause types.

Subsets exist for `nda`, `employment`, `service_agreement`, `lease`, and `partnership`. Any type without a subset — and any request carrying `force_full_extraction` — falls back to the full `CUAD_CLAUSE_TYPES` list.

### Evaluator-optimizer on extraction

`src/pipeline/extract.ts` runs a generator/evaluator loop up to `MAX_EVAL_ITERATIONS` (3). The capable model extracts; the fast model then checks the result for empty excerpts on clauses marked present, high-confidence absences, an implausible contract type, and an empty parties array.

When the evaluator fails the extraction, its `issues` are appended to the next generator prompt as feedback. Tokens and cost accumulate across every iteration, and the completed count is recorded on the span as `extraction.eval_iterations`.

### Model tiering

`src/providers.ts` exposes `getCapableModel()` and `getFastModel()`. Extraction and summarization use the capable model; routing and evaluation use the fast one. Both resolve against the configured provider — Anthropic, Google, or Ollama — so no stage hardcodes a model ID.

---

## What's Still Open

### Act on the complexity signal

**Current behaviour**: `routeDocument()` returns `complexity` and `requires_full_analysis`, and the orchestrator records both as span attributes. Neither value changes what runs. A document classified `simple` takes the same path as one classified `complex`.

**The opportunity**: use `complexity` to pick the extraction model, and `requires_full_analysis` to gate the extraction depth.

```typescript
// src/pipeline/extract.ts — accept the routing signal
export async function extractClauses(
  fullText: string,
  inject?: { force_full_extraction?: boolean },
  documentType?: string,
  complexity?: "simple" | "standard" | "complex",
): Promise<ExtractResult> {
  const descriptor = complexity === "simple" ? getFastModel() : getCapableModel();
  // ...
}
```

The routing data is already threaded to `extractClauses` for `document_type`, so this adds one more argument rather than new plumbing.

**Expected improvement**: on a corpus weighted toward short NDAs, extraction is the dominant cost line, and moving the simple cases to the fast model cuts it substantially. Measure the accuracy tradeoff on your own documents before enabling it — the evaluator loop will surface regressions as a rise in `extraction.eval_iterations`.

**Watch for**: a fast model that fails evaluation more often can cost more than the capable model it replaced, because each retry is a full extraction call.

---

## What's Not Worth Adding to This Project

| Pattern | Why to skip |
|---------|-------------|
| **ToolLoopAgent (agentic loop)** | Non-deterministic execution makes auditing harder. Contract analysis is a deterministic task — the pipeline should produce the same output for the same input. |
| **Multi-agent handoffs** | Single domain (contract law). There is no scenario where mid-analysis control should transfer to a different agent. |
| **Reflexion (self-evaluation with memory)** | More complex than the evaluator-optimizer loop already in `extract.ts`, for similar accuracy on structured extraction. |
| **Orchestrator-Workers** | Sub-task structure for contract analysis is well-defined and doesn't vary enough to justify dynamic planning. |
| **MCP servers** | Useful if the contract analyzer pipeline is to be exposed as a tool to other agents (e.g. a legal research agent). Not needed for internal operation. |
| **Group chat / roundtable** | Adds coordination overhead with no benefit for a well-scoped, single-domain task. |
| **Fan-out of summarize** | Summarize reads both the extraction and the risk scores, so it cannot move off the critical path without changing what the summary is based on. |

---

## Current Architecture Reference

```
POST /api/contracts (multipart/form-data)
  └─ src/routes/contracts.ts
       └─ analyzeContract(file, pool)
            └─ src/pipeline/orchestrator.ts
                 ├─ Stage 1: ingestDocument()     src/pipeline/ingest.ts
                 │   └─ PDF parse or UTF-8 decode
                 │   └─ Chunk into ~1000-char segments
                 │   └─ createContract() → DB, status "processing"
                 │
                 ├─ Stage 2: routeDocument()       src/pipeline/route.ts
                 │   └─ fast model, first 3000 chars
                 │   └─ document_type / complexity / requires_full_analysis
                 │   └─ "unknown" → UNSUPPORTED_TYPE → HTTP 415
                 │
                 ├─ Stages 3 & 4 run concurrently (Promise.all):
                 │
                 │   ├─ embedChunks()              src/pipeline/embed.ts
                 │   │   └─ configured embedding model (batches of 20)
                 │   │   └─ insertChunks() → pgvector
                 │   │
                 │   └─ extractClauses()           src/pipeline/extract.ts
                 │       └─ capable model, clause subset for document_type
                 │       └─ evaluator loop, fast model, max 3 iterations
                 │       └─ insertClauses() → DB
                 │
                 ├─ Stage 5: scoreRisks()          src/pipeline/score.ts
                 │   └─ fast model
                 │   └─ Risk levels: critical/high/medium/low/none
                 │   └─ insertRisks() → DB
                 │
                 └─ Stage 6: generateSummary()     src/pipeline/summarize.ts
                     └─ capable model, reads extraction + risks
                     └─ Executive summary + key terms + negotiation points
                     └─ insertAnalysis() → DB (with trace_id)
```

---

## Further Reading

- `docs/agentic-architecture-patterns.md` — full pattern catalog with code samples and tradeoffs
- [Anthropic — Building Effective Agents](https://www.anthropic.com/research/building-effective-agents)
- [Anthropic — Evaluator-Optimizer Cookbook](https://platform.claude.com/cookbook/patterns-agents-evaluator-optimizer)
- [Vercel AI SDK v6](https://vercel.com/blog/ai-sdk-6)
