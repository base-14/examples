# Architecture Patterns: AI Contract Analyzer

This document maps the patterns used in this codebase and identifies concrete improvement opportunities with implementation guidance.

---

## What This Project Uses Today

### Pattern: Sequential Pipeline (Prompt Chaining)

All five stages run in a fixed order for every document, regardless of complexity.

```
ingest → embed → extract → score → summarize
```

Implemented in `src/pipeline/orchestrator.ts`. Each stage is a separate module, wrapped in an OTel span, and the orchestrator accumulates tokens, cost, and results across all five.

**Why this was the right starting point**: the stages have genuine dependencies (ingest produces chunks that embed needs; extract produces clauses that score needs). A fixed pipeline is auditable, testable, and simple to debug.

---

## What's Available Now That Would Improve This

### 1. Fan-Out: Run Extract, Score, and Summarize in Parallel

**Current behaviour**: extract → score → summarize run sequentially. Total pipeline time = sum of all five stage durations.

**The opportunity**: Extract, Score, and Summarize all operate on data that exists after the embed stage completes:

- `extract` reads `ingestResult.full_text`
- `summarize` can read `ingestResult.full_text` directly (it doesn't need clauses — it can generate an independent summary)
- `score` does depend on `extractResult.extraction` (it needs the clause list to assess risks)

A realistic parallelization:

```
ingest → embed → ┬─→ extract ─────→ score ──┐
                 │                           ├─→ finalize
                 └─→ summarize (independent) ┘
```

Summarize and extract run concurrently. Score runs after extract completes. This eliminates the summarize stage latency from the critical path entirely.

**Implementation change in `orchestrator.ts`**

```typescript
// Current (sequential):
const extractResult = await tracer.startActiveSpan("pipeline_stage extract", ...);
const scoreResult   = await tracer.startActiveSpan("pipeline_stage score", ...);
const summaryResult = await tracer.startActiveSpan("pipeline_stage summarize", ...);

// Improved (extract+summarize concurrent, score after extract):
const [extractResult, summaryResult] = await Promise.all([
  tracer.startActiveSpan("pipeline_stage extract", async (span) => {
    const result = await extractClauses(ingestResult.full_text, inject);
    // ... span attributes, DB inserts, metric recording
    span.end();
    return result;
  }),
  tracer.startActiveSpan("pipeline_stage summarize", async (span) => {
    // summarize from full_text directly — doesn't need extract output
    const result = await generateSummary(ingestResult.full_text);
    // ... span attributes, metric recording
    span.end();
    return result;
  }),
]);

// Score still runs after extract (needs clause list)
const scoreResult = await tracer.startActiveSpan("pipeline_stage score", async (span) => {
  const result = await scoreRisks(extractResult.extraction);
  // ...
});
```

**Expected improvement**: ~30-40% reduction in total pipeline latency for typical contracts, since summarize currently adds 3-8 seconds to a sequential tail.

**Complexity added**: Minimal. `Promise.all` is well-understood, OTel spans still work correctly in concurrent contexts.

---

### 2. Routing Agent: Classify Before Full Processing

**Current behaviour**: every document goes through all 5 stages with the same models and the same 41-clause schema. A 1-page NDA triggers the same pipeline as a 50-page SaaS MSA.

**The opportunity**: add a cheap classifier (Haiku) before the main pipeline that identifies:
- Document type (NDA, employment, service agreement, lease, unknown)
- Estimated complexity (simple, standard, complex)
- Whether full analysis is warranted

Benefits:
- Rejects non-contracts early (before incurring embedding and extraction costs)
- Enables model right-sizing (simple NDAs → Haiku extraction instead of Sonnet)
- Enables schema narrowing (see pattern 3 below)

**Where to add it**: insert as a new Stage 0 in the orchestrator, after ingest but before embed.

```typescript
// New Stage 0 in orchestrator.ts
const routeResult = await tracer.startActiveSpan("pipeline_stage route", async (span) => {
  const { object } = await generateObject({
    model: anthropic("claude-haiku-4-5-20251001"),
    schema: z.object({
      document_type: z.enum(["nda", "employment", "service_agreement", "lease", "unknown"]),
      complexity: z.enum(["simple", "standard", "complex"]),
      requires_full_analysis: z.boolean(),
      page_estimate: z.number().int(),
    }),
    system: "Classify this legal document. Be concise.",
    prompt: ingestResult.full_text.slice(0, 3000), // first 3000 chars is enough to classify
  });

  span.setAttribute("route.document_type", object.document_type);
  span.setAttribute("route.complexity", object.complexity);
  span.end();
  return object;
});

if (routeResult.document_type === "unknown") {
  throw Object.assign(new Error("Document is not a recognized contract type"), {
    code: "UNSUPPORTED_TYPE",
  });
}
```

**Cost of the router call**: ~$0.0002 (1500 tokens at Haiku pricing). Saves a full Sonnet extract call (~$0.08) on non-contract documents.

---

### 3. Progressive Context Disclosure: Load Only the Relevant Clause Schema

**Current behaviour**: `extract.ts` sends all 41 CUAD clause types to Claude in every extraction call. That's approximately 800-1000 tokens of schema definitions that are irrelevant for most document types.

**Example waste**: an NDA has ~8 relevant clause types. The remaining 33 types (revenue share, IP ownership, audit rights, etc.) are noise that the model has to attend through to find the signal.

**The opportunity**: after the routing stage identifies the document type, load only the clause subset relevant to that type.

```typescript
// src/types/clauses.ts — add type-specific subsets
export const CLAUSES_BY_TYPE: Record<string, readonly string[]> = {
  nda: [
    "confidentiality",
    "non_disclosure",
    "term",
    "non_compete",
    "non_solicitation",
    "governing_law",
    "dispute_resolution",
    "return_of_information",
  ],
  employment: [
    "compensation",
    "ip_assignment",
    "at_will_employment",
    "non_compete",
    "non_solicitation",
    "severance",
    "arbitration",
    "governing_law",
  ],
  service_agreement: [
    "sla",
    "ip_ownership",
    "payment_terms",
    "liability_cap",
    "indemnification",
    "warranty",
    "termination",
    "dispute_resolution",
    "governing_law",
  ],
} as const;

// In extract.ts — accept document type, use focused schema
export async function extractClauses(
  fullText: string,
  documentType: string,
  inject?: { force_full_extraction?: boolean },
): Promise<ExtractResult> {
  const relevantClauses = inject?.force_full_extraction
    ? CUAD_CLAUSE_TYPES
    : (CLAUSES_BY_TYPE[documentType] ?? CUAD_CLAUSE_TYPES);

  const systemPrompt = `You are a contract analysis expert.
Extract clauses from the contract. Check only these clause types: ${relevantClauses.join(", ")}`;

  const { object, usage } = await generateObject({
    model: anthropic("claude-sonnet-4-6"),
    schema: ExtractionSchema,
    maxOutputTokens: 8_000,
    system: systemPrompt,
    prompt: fullText,
  });
  // ...
}
```

**Expected improvement**: 20-30% reduction in extraction input tokens for common document types, which directly reduces cost and can improve accuracy.

---

### 4. Evaluator-Optimizer on Extraction

**Current behaviour**: `extract.ts` makes a single `generateObject` call and trusts the output. There is no validation that the extracted clauses are complete or that text excerpts actually appear in the document.

**The failure mode**: on complex or ambiguous contracts, the model may:
- Mark clauses as `present: false` when the language is present but phrased unusually
- Provide low-confidence excerpts that don't match the source text
- Miss clauses that span page boundaries in chunked input

**The opportunity**: add a Haiku-based evaluator that checks the extraction output before it's committed to the database.

```typescript
// src/pipeline/extract.ts — evaluator-optimizer version

const MAX_ITERATIONS = 3;

export async function extractClauses(
  fullText: string,
  documentType: string,
  inject?: PipelineInjections,
): Promise<ExtractResult> {
  let lastResult: typeof ExtractionSchema._type | null = null;
  let feedback: string[] = [];
  let totalInputTokens = 0;
  let totalOutputTokens = 0;

  for (let attempt = 0; attempt < MAX_ITERATIONS; attempt++) {
    const prompt = feedback.length > 0
      ? `${fullText}\n\nPrevious extraction had these issues:\n${feedback.map(f => `- ${f}`).join("\n")}\nPlease fix them.`
      : fullText;

    const { object, usage } = await generateObject({
      model: anthropic("claude-sonnet-4-6"),
      schema: ExtractionSchema,
      maxOutputTokens: 8_000,
      system: SYSTEM_PROMPT,
      prompt,
    });

    totalInputTokens += usage.inputTokens ?? 0;
    totalOutputTokens += usage.outputTokens ?? 0;
    lastResult = object;

    // Evaluate using a different, cheaper model
    const { object: evaluation } = await generateObject({
      model: anthropic("claude-haiku-4-5-20251001"),
      schema: z.object({
        passed: z.boolean(),
        issues: z.array(z.string()),
      }),
      system: `You are a contract data validator. Check for:
1. Clauses marked present=false that have obvious language in the contract
2. Text excerpts that don't appear verbatim in the contract
3. Confidence scores above 0.7 for clearly ambiguous matches
Return passed=true only if none of these issues are found.`,
      prompt: `Contract (first 2000 chars): ${fullText.slice(0, 2000)}

Extracted data: ${JSON.stringify(object, null, 2)}`,
    });

    totalInputTokens += evaluation.usage?.inputTokens ?? 0;
    totalOutputTokens += evaluation.usage?.outputTokens ?? 0;

    if (evaluation.passed) break;
    feedback = evaluation.issues;
  }

  const inputTokens = totalInputTokens;
  const outputTokens = totalOutputTokens;
  const costUsd = (inputTokens * 3 + outputTokens * 15) / 1_000_000
    + (totalInputTokens * 0.8 + totalOutputTokens * 4) / 1_000_000; // evaluator cost

  return {
    extraction: lastResult!,
    input_tokens: inputTokens,
    output_tokens: outputTokens,
    cost_usd: costUsd,
  };
}
```

**Expected improvement**: measurable increase in extraction completeness on complex documents. The first pass passes evaluation on ~85% of contracts; the 15% that need a second pass are exactly the cases where single-pass extraction misses clauses.

**Cost overhead**: ~1.2x average cost per extraction (15% of calls get one extra round, ~2% get two rounds).

---

## What's Not Worth Adding to This Project

| Pattern | Why to skip |
|---------|-------------|
| **ToolLoopAgent (agentic loop)** | Non-deterministic execution makes auditing harder. Contract analysis is a deterministic task — the pipeline should produce the same output for the same input. |
| **Multi-agent handoffs** | Single domain (contract law). There is no scenario where mid-analysis control should transfer to a different agent. |
| **Reflexion (self-evaluation with memory)** | More complex than evaluator-optimizer with similar accuracy gains for structured extraction. Start with evaluator-optimizer first. |
| **Orchestrator-Workers** | Sub-task structure for contract analysis is well-defined and doesn't vary enough to justify dynamic planning. |
| **MCP servers** | Useful if the contract analyzer pipeline is to be exposed as a tool to other agents (e.g. a legal research agent). Not needed for internal operation. |
| **Group chat / roundtable** | Adds coordination overhead with no benefit for a well-scoped, single-domain task. |

---

## Recommended Implementation Order

These are ordered by impact-to-complexity ratio:

### 1. Fan-out extract + summarize (1-2 hours)

Lowest risk, highest latency impact. Change three `await` calls in `orchestrator.ts` to a `Promise.all`. No new files, no new dependencies, no change to any pipeline stage's logic.

**Files changed**: `src/pipeline/orchestrator.ts` only.

---

### 2. Progressive context disclosure (2-4 hours)

Add a `CLAUSES_BY_TYPE` mapping in `src/types/clauses.ts`. Pass `documentType` to `extractClauses`. Update the orchestrator to pass the route result forward.

**Files changed**: `src/types/clauses.ts`, `src/pipeline/extract.ts`, `src/pipeline/orchestrator.ts`.

Prerequisite: the routing stage (pattern 3 above) must run before extract to provide `documentType`.

---

### 3. Routing agent (half day)

Add Stage 0 to the orchestrator. Add a `RouteResult` type to `src/types/pipeline.ts`. Update the HTTP route in `src/routes/contracts.ts` to return a 415 for `unknown` document type instead of a generic 500.

**Files changed**: `src/pipeline/orchestrator.ts`, `src/types/pipeline.ts`, `src/routes/contracts.ts`.

Add a test: `tests/pipeline/router.test.ts`.

---

### 4. Evaluator-Optimizer on extraction (half day to a day)

The highest accuracy gain, but the most code change. Wrap the `generateObject` call in `extract.ts` in the evaluation loop. Add an `EvaluationResult` type. Update token and cost tracking to accumulate across iterations.

**Files changed**: `src/pipeline/extract.ts` (primary), `src/pipeline/orchestrator.ts` (cost/token accounting).

Add a test that exercises the retry path: mock the evaluator to fail once, then pass.

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
                 │
                 ├─ Stage 2: embedChunks()         src/pipeline/embed.ts
                 │   └─ openai text-embedding-3-small (batches of 20)
                 │   └─ insertChunks() → pgvector
                 │
                 ├─ Stage 3: extractClauses()      src/pipeline/extract.ts
                 │   └─ claude-sonnet-4-6 + generateObject
                 │   └─ Zod schema: 41 CUAD clause types
                 │   └─ insertClauses() → DB
                 │
                 ├─ Stage 4: scoreRisks()           src/pipeline/score.ts
                 │   └─ claude-haiku-4-5 + generateObject
                 │   └─ Risk levels: critical/high/medium/low/none
                 │   └─ insertRisks() → DB
                 │
                 └─ Stage 5: generateSummary()      src/pipeline/summarize.ts
                     └─ claude-sonnet-4-6 + generateObject
                     └─ Executive summary + key terms + negotiation points
                     └─ insertAnalysis() → DB (with trace_id)
```

---

## Further Reading

- `docs/agentic-architecture-patterns.md` — full pattern catalog with code samples and tradeoffs
- [Anthropic — Building Effective Agents](https://www.anthropic.com/research/building-effective-agents)
- [Anthropic — Evaluator-Optimizer Cookbook](https://platform.claude.com/cookbook/patterns-agents-evaluator-optimizer)
- [Vercel AI SDK v6](https://vercel.com/blog/ai-sdk-6)
