# Agentic Architecture Patterns

A reference guide to the core patterns for building LLM-powered systems, with code samples, tradeoffs, and pointers to canonical sources. Current as of February 2026.

---

## The Foundational Principle

Anthropic's guidance (and every major platform's consensus): **start with the simplest shape that solves the problem**. Multi-agent complexity must be earned by demonstrable need — parallelism, specialization, security isolation, or context window limits. A sequential pipeline that works reliably beats a multi-agent graph that occasionally fails in unpredictable ways.

> "The best agent is the one that solves your problem with the fewest moving parts."
> — [Anthropic, Building Effective Agents](https://www.anthropic.com/research/building-effective-agents)

---

## Pattern 1: Prompt Chaining (Sequential Pipeline)

The default starting pattern. A task is decomposed into a fixed sequence of LLM calls where each call processes the output of the previous one.

**When to use**
- Stages have clear linear dependencies
- Progressive refinement is the goal (draft → review → finalize)
- Predictability and auditability matter more than latency

**When to avoid**
- Stages are independent of each other (use fan-out instead)
- The sequence varies based on input (use routing instead)

**Structure**

```
input → [stage 1] → [stage 2] → [stage 3] → output
```

**Code sample (Vercel AI SDK)**

```typescript
import { generateObject } from "ai";
import { anthropic } from "@ai-sdk/anthropic";

// Stage 1: Extract key facts
const { object: facts } = await generateObject({
  model: anthropic("claude-haiku-4-5-20251001"),
  schema: FactsSchema,
  prompt: rawDocument,
});

// Stage 2: Analyze extracted facts
const { object: analysis } = await generateObject({
  model: anthropic("claude-sonnet-4-6"),
  schema: AnalysisSchema,
  prompt: JSON.stringify(facts),
});

// Stage 3: Summarize analysis
const { text: summary } = await generateText({
  model: anthropic("claude-sonnet-4-6"),
  prompt: `Summarize this analysis: ${JSON.stringify(analysis)}`,
});
```

**Tradeoffs**

| Pro | Con |
|-----|-----|
| Predictable, auditable execution | Latency = sum of all stage durations |
| Easy to debug (one stage at a time) | Early-stage errors cascade |
| Simple to add observability spans | No adaptation based on input complexity |

**References**
- [Anthropic — Building Effective Agents](https://www.anthropic.com/research/building-effective-agents)
- [Azure Architecture — AI Agent Orchestration Patterns](https://learn.microsoft.com/en-us/azure/architecture/ai-ml/guide/ai-agent-design-patterns)

---

## Pattern 2: Routing Agent

A lightweight classifier runs first and dispatches the input to the appropriate handler. The router itself does no heavy reasoning — it only classifies.

**When to use**
- Input types vary significantly (document types, languages, query intents)
- Different inputs warrant different models or pipelines (cost optimization)
- You want to reject clearly invalid inputs before incurring LLM costs

**Structure**

```
input → [router/classifier] → dispatch:
                               ├→ handler A (e.g. NDA pipeline)
                               ├→ handler B (e.g. employment contract pipeline)
                               └→ reject (not a contract)
```

**Code sample**

```typescript
import { generateObject } from "ai";
import { anthropic } from "@ai-sdk/anthropic";
import { z } from "zod";

const RouteSchema = z.object({
  document_type: z.enum(["nda", "employment", "service_agreement", "lease", "unknown"]),
  complexity: z.enum(["simple", "standard", "complex"]),
  requires_full_analysis: z.boolean(),
});

async function routeDocument(text: string) {
  const { object } = await generateObject({
    model: anthropic("claude-haiku-4-5-20251001"), // cheap model for routing
    schema: RouteSchema,
    system: "Classify this legal document. Be concise.",
    prompt: text.slice(0, 2000), // only need the first ~2000 chars to classify
  });
  return object;
}

// Dispatch based on routing result
const route = await routeDocument(contractText);

if (route.document_type === "unknown") {
  throw Object.assign(new Error("Not a recognized contract type"), { code: "UNSUPPORTED_TYPE" });
}

const result = route.requires_full_analysis
  ? await fullAnalysisPipeline(contractText, route.document_type)
  : await quickSummaryPipeline(contractText);
```

**Tradeoffs**

| Pro | Con |
|-----|-----|
| Enables right-sizing model selection (cheap router → expensive specialist) | Adds one LLM call to every request |
| Eliminates wasted compute on irrelevant processing | Router misclassification causes hard-to-debug downstream failures |
| Enables early rejection before expensive steps | Classification errors compound — wrong route, wrong result |

**References**
- [Anthropic — Building Effective Agents (Routing section)](https://www.anthropic.com/research/building-effective-agents)
- [Stack AI — 2026 Guide to Agentic Workflow Architectures](https://www.stack-ai.com/blog/the-2026-guide-to-agentic-workflow-architectures)

---

## Pattern 3: Concurrent Fan-Out / Fan-In

An orchestrator dispatches the same input to multiple specialized agents simultaneously. Results are aggregated by a synthesizer.

**When to use**
- Multiple independent analyses of the same artifact are needed
- Stages do not depend on each other's output
- Latency is a constraint and the bottleneck is stage duration, not throughput

**Structure**

```
                    ┌→ [agent A: clause extraction] ──┐
input → [prepare] ──┼→ [agent B: risk scoring]    ────┼→ [synthesize] → output
                    └→ [agent C: plain summary]   ────┘
```

**Code sample (TypeScript with Promise.all)**

```typescript
const [extractResult, riskResult, summaryResult] = await Promise.all([
  extractClauses(fullText),
  scoreRisks(fullText),        // note: if score depends on extract output,
  generateSummary(fullText),   // only summarize can truly run in parallel
]);

const report = synthesize(extractResult, riskResult, summaryResult);
```

**Code sample (Vercel AI SDK with parallel agent calls)**

```typescript
import { generateObject } from "ai";

async function parallelAnalysis(document: string) {
  const [clauses, risks, summary] = await Promise.all([
    generateObject({ model, schema: ClauseSchema, prompt: document }),
    generateObject({ model, schema: RiskSchema, prompt: document }),
    generateObject({ model, schema: SummarySchema, prompt: document }),
  ]);

  return synthesize(clauses.object, risks.object, summary.object);
}
```

**Aggregation strategies**
- **Voting / majority rule**: for classification decisions (what is the overall risk level?)
- **Schema merge**: combine non-overlapping fields from each agent
- **LLM synthesis**: when results need narrative reconciliation

**Tradeoffs**

| Pro | Con |
|-----|-----|
| Latency = max(stage durations), not sum | All stages must finish before moving forward |
| Specialization: each agent has a focused prompt | Harder to share intermediate context between stages |
| Scales naturally with async execution | Synthesizer adds complexity; errors harder to attribute |

**References**
- [Azure Architecture — Scatter-Gather Pattern](https://learn.microsoft.com/en-us/azure/architecture/ai-ml/guide/ai-agent-design-patterns)
- [Google ADK — Multi-Agent Patterns](https://developers.googleblog.com/developers-guide-to-multi-agent-patterns-in-adk/)

---

## Pattern 4: Orchestrator-Workers

A central orchestrator LLM dynamically decomposes an incoming task into sub-tasks and delegates each to worker agents. Unlike a pipeline, the decomposition is decided at runtime.

**When to use**
- Sub-task structure cannot be predetermined (open-ended research, multi-document analysis)
- Tasks have variable scope (simple documents need 2 steps; complex ones need 8)
- Workers are specialized and reusable across different orchestrators

**Structure**

```
input → [orchestrator LLM] → plan:
                              task 1 → [worker A]
                              task 2 → [worker B]
                              task 3 → [worker A]  (reused)
                              ↓
                          [orchestrator synthesizes] → output
```

**Code sample (sub-agent as tool)**

```typescript
// Workers are exposed to the orchestrator as tools
const tools = {
  analyzeClause: tool({
    description: "Analyze a specific clause from the contract",
    parameters: z.object({ clause_text: z.string(), clause_type: z.string() }),
    execute: async ({ clause_text, clause_type }) =>
      analyzeClauseWorker(clause_text, clause_type),
  }),
  checkJurisdiction: tool({
    description: "Look up jurisdiction-specific requirements",
    parameters: z.object({ governing_law: z.string(), contract_type: z.string() }),
    execute: async ({ governing_law, contract_type }) =>
      jurisdictionWorker(governing_law, contract_type),
  }),
};

// Orchestrator calls workers as needed
const { text } = await generateText({
  model: anthropic("claude-sonnet-4-6"),
  tools,
  maxSteps: 10,
  system: "You are a contract analysis orchestrator. Use the available tools to analyze this contract fully.",
  prompt: contractText,
});
```

**Tradeoffs**

| Pro | Con |
|-----|-----|
| Adapts to input complexity — simple inputs skip unnecessary steps | Non-deterministic execution order — hard to test and audit |
| Workers are reusable across different task types | Orchestrator token cost is high (reasons about the full plan) |
| Handles tasks with unpredictable structure | Difficult to bound total LLM calls and cost |

**References**
- [Anthropic — Building Effective Agents (Orchestrator-Workers)](https://www.anthropic.com/research/building-effective-agents)
- [Vercel AI SDK — Building Agents](https://ai-sdk.dev/docs/agents/building-agents)

---

## Pattern 5: Evaluator-Optimizer (Generator-Critic Loop)

A generator produces output; an evaluator scores it against criteria. If the evaluation fails, feedback is passed back to the generator for a revised attempt. Repeats until pass or max iterations.

**When to use**
- Output quality can be objectively evaluated (schema validation, completeness checks)
- Iterative refinement demonstrably improves accuracy
- The cost of one extra LLM call is worth the accuracy gain

**Key design rules (from Anthropic's cookbook)**
- The generator maintains memory of all previous attempts and feedback
- Use a **different model** for evaluation than for generation — catches different failure modes
- Always define a max iteration cap (3-5 rounds) with a defined fallback
- Pass feedback as structured data, not free text

**Structure**

```
input → [generator] → output
           ↑               ↓
    [feedback]       [evaluator] → PASS → final output
                          ↓
                        FAIL (with specific reasons)
```

**Code sample**

```typescript
const MAX_ITERATIONS = 3;
let attempt = 0;
let result = null;
let feedback: string[] = [];

while (attempt < MAX_ITERATIONS) {
  const { object } = await generateObject({
    model: anthropic("claude-sonnet-4-6"),
    schema: ExtractionSchema,
    system: EXTRACTION_SYSTEM_PROMPT,
    prompt: feedback.length > 0
      ? `${contractText}\n\nPrevious attempt feedback:\n${feedback.join("\n")}\n\nPlease fix these issues.`
      : contractText,
  });

  // Evaluate using a different, cheaper model
  const { object: evaluation } = await generateObject({
    model: anthropic("claude-haiku-4-5-20251001"),
    schema: z.object({
      passed: z.boolean(),
      issues: z.array(z.string()),
    }),
    system: "You are a contract data validator. Check the extracted data for completeness and consistency.",
    prompt: `Contract: ${contractText.slice(0, 1000)}\n\nExtracted data: ${JSON.stringify(object)}`,
  });

  if (evaluation.passed) {
    result = object;
    break;
  }

  feedback = evaluation.issues;
  attempt++;
}

// Fallback: use last attempt even if not fully passing
if (!result) result = lastAttempt;
```

**Tradeoffs**

| Pro | Con |
|-----|-----|
| Significantly improves extraction accuracy on ambiguous documents | Adds 1-N extra LLM calls per request |
| Different models for generation vs. evaluation catches more errors | Requires a well-defined evaluation criterion |
| Self-correcting — handles edge cases the generator misses first pass | Cost must be bounded by iteration cap |

**References**
- [Anthropic — Evaluator-Optimizer Pattern (Cookbook)](https://platform.claude.com/cookbook/patterns-agents-evaluator-optimizer)
- [Azure Architecture — Maker-Checker Pattern](https://learn.microsoft.com/en-us/azure/architecture/ai-ml/guide/ai-agent-design-patterns)

---

## Pattern 6: ToolLoopAgent (Agentic Loop)

An agent is given a set of tools and a goal. It calls tools, receives results, and decides what to do next — repeating until the stop condition is met. The model drives the execution, not the application code.

**When to use**
- The right sequence of steps is unknown upfront and must be reasoned about
- Some steps are optional (the agent skips them if not needed)
- Tool calls need access to external systems, databases, or APIs

**Key primitives (Vercel AI SDK v6)**
- `stopWhen`: defines when the loop ends (`hasNoToolCalls()`, `hasToolCall("done")`, max steps)
- `prepareStep`: called before each step — allows modifying model or tools per step
- `needsApproval`: per-tool flag for human-in-the-loop on sensitive operations
- `Output.object()`: structured output alongside tool execution

**Code sample (Vercel AI SDK v6)**

```typescript
import { ToolLoopAgent, hasNoToolCalls, Output } from "ai";
import { anthropic } from "@ai-sdk/anthropic";

const agent = new ToolLoopAgent({
  model: anthropic("claude-sonnet-4-6"),
  instructions: `You are a contract analysis agent. Use the available tools to
    analyze the provided contract. Always extract clauses first, then score risks.
    Only generate a summary if the contract is longer than 5 pages.`,
  tools: {
    extractClauses: tool({ ... }),
    scoreRisks: tool({ ... }),
    generateSummary: tool({ ... }),
    searchPrecedents: tool({ ... }), // optional — agent calls this if relevant
  },
  stopWhen: hasNoToolCalls(),
  output: Output.object({ schema: AnalysisResultSchema }),
  onStepFinish: ({ stepType, toolCalls }) => {
    console.log(`Step: ${stepType}`, toolCalls);
  },
});

const result = await agent.run(contractText);
```

**Tradeoffs**

| Pro | Con |
|-----|-----|
| Adapts to input — skips unnecessary work | Non-deterministic execution, harder to test |
| Tool results feed back into reasoning loop | Runaway loops possible without `maxSteps` cap |
| Human approval gate per tool (`needsApproval`) | Debugging requires trace inspection, not log reading |
| Native structured output alongside tool calls | Higher token cost — model reasons at each step |

**References**
- [Vercel AI SDK v6 Release](https://vercel.com/blog/ai-sdk-6)
- [Vercel AI SDK — Loop Control](https://ai-sdk.dev/docs/agents/loop-control)
- [Vercel AI SDK — Building Agents](https://ai-sdk.dev/docs/agents/building-agents)

---

## Pattern 7: Progressive Context Disclosure

Context is loaded in levels, not all at once. Only context relevant to the current task state is in the active context window.

**Why this matters**

Context engineering is now a first-class discipline. Every token in the context window degrades attention quality for everything else. What you put in the context window is an architectural decision.

**Levels**

1. **Core metadata** — always present in system prompt (role, output format, hard constraints)
2. **Task-specific instructions** — loaded when task type is known (after routing)
3. **Dynamic resources** — retrieved as needed (RAG, tool results, previous conversation)

**Code sample**

```typescript
const BASE_SYSTEM = `You are a contract analysis expert. Output structured JSON.`;

// Loaded only after routing identifies document type
const SCHEMA_BY_TYPE: Record<string, string> = {
  nda: `NDA-specific clauses to check: confidentiality, term, non-compete, ...`,
  employment: `Employment clauses to check: compensation, IP assignment, at-will, ...`,
  service_agreement: `Service agreement clauses: SLA, IP ownership, payment terms, ...`,
};

async function extractWithContext(text: string, documentType: string) {
  const systemPrompt = [
    BASE_SYSTEM,
    SCHEMA_BY_TYPE[documentType], // only the relevant schema
  ].join("\n\n");

  return generateObject({
    model: anthropic("claude-sonnet-4-6"),
    schema: ExtractionSchema,
    system: systemPrompt,
    prompt: text,
  });
}
```

**Tradeoffs**

| Pro | Con |
|-----|-----|
| Higher extraction accuracy — less noise in context | Requires knowing the document type before loading context (needs routing) |
| Lower token cost — irrelevant schema tokens eliminated | Multi-step context assembly adds code complexity |
| Scales to large schema libraries without hitting context limits | Context version management becomes a concern over time |

**References**
- [Anthropic — Agent Skills Framework](https://medium.com/@AdithyaGiridharan/anthropic-just-released-a-32-page-playbook-for-building-claude-skills-heres-what-you-need-to-b86fe0b123ae)
- [Anthropic — Writing Tools for Agents](https://www.anthropic.com/engineering/writing-tools-for-agents)

---

## Pattern 8: RAG (Retrieval-Augmented Generation)

Retrieve semantically relevant content from a vector store, inject it into the prompt as context, then generate an answer grounded in the retrieved content.

**When to use**
- Questions reference content too large to fit in a single context window
- Answers must be grounded in specific source documents
- A knowledge base grows over time and must remain current

**Structure**

```
query → [embed query] → [vector similarity search] → [top-k chunks]
                                                           ↓
                                               [inject into prompt]
                                                           ↓
                                                 [generateText/Object] → answer
```

**Code sample (Vercel AI SDK + pgvector)**

```typescript
import { embedMany, generateText } from "ai";
import { openai } from "@ai-sdk/openai";
import { anthropic } from "@ai-sdk/anthropic";

async function queryContract(question: string, contractId: string, pool: Pool) {
  // 1. Embed the question
  const { embeddings } = await embedMany({
    model: openai.embedding("text-embedding-3-small"),
    values: [question],
  });

  // 2. Find semantically similar chunks in pgvector
  const chunks = await pool.query<{ text: string; page_start: number; similarity: number }>(
    `SELECT text, page_start, 1 - (embedding <=> $1::vector) AS similarity
     FROM contract_chunks
     WHERE contract_id = $2
     ORDER BY embedding <=> $1::vector
     LIMIT 5`,
    [`[${embeddings[0]!.join(",")}]`, contractId],
  );

  // 3. Build context from retrieved chunks
  const context = chunks.rows
    .map((r) => `[Page ${r.page_start}] ${r.text}`)
    .join("\n\n");

  // 4. Generate grounded answer
  const { text } = await generateText({
    model: anthropic("claude-sonnet-4-6"),
    system: `You are a contract analysis assistant. Answer questions using ONLY
      the provided contract excerpts. If the answer is not in the excerpts, say so.`,
    prompt: `Relevant contract sections:\n${context}\n\nQuestion: ${question}`,
  });

  return { answer: text, sources: chunks.rows };
}
```

**Tradeoffs**

| Pro | Con |
|-----|-----|
| Answers grounded in source content, not hallucinated | Retrieval quality determines answer quality |
| Scales to arbitrarily large document sets | Chunking strategy dramatically affects what gets retrieved |
| Source attribution is built in | Semantic similarity ≠ relevance for all question types |

**References**
- [pgvector — GitHub](https://github.com/pgvector/pgvector)
- [Vercel AI SDK — Retrieval-Augmented Generation](https://sdk.vercel.ai/docs/guides/rag-chatbot)

---

## Pattern 9: Structured Output vs. Tool Use

These are not competing approaches. They serve different purposes and are used together.

| Dimension | `generateObject` (Structured Output) | Tool Use (`generateText` with tools) |
|-----------|--------------------------------------|--------------------------------------|
| **Purpose** | Constrain response format to a Zod schema | Let the model invoke external systems |
| **Best for** | Final extraction, classification, structured reports | Fetching live data, taking side-effecting actions |
| **Schema adherence** | 100% guaranteed (native structured output) | Model must correctly infer tool name and parameters |
| **Context cost** | Full schema is in context at generation time | Tool descriptions are short; parameters generated after tool selection |
| **Iterability** | Single call produces final output | Multi-step: model selects tool, executes, feeds result back |

**Recommended hybrid**

```typescript
// Intermediate steps: use tool calls to fetch external data
const { text, toolResults } = await generateText({
  model: anthropic("claude-sonnet-4-6"),
  tools: {
    lookupPrecedent: tool({ ... }),   // fetches from case law DB
    checkJurisdiction: tool({ ... }), // fetches local regulations
  },
  prompt: `Analyze this clause: ${clauseText}`,
});

// Final step: use generateObject to enforce schema on the output
const { object: structuredResult } = await generateObject({
  model: anthropic("claude-sonnet-4-6"),
  schema: ClauseAnalysisSchema,
  prompt: `Based on this analysis, extract structured findings: ${text}`,
});
```

**References**
- [Anthropic — Writing Tools for Agents](https://www.anthropic.com/engineering/writing-tools-for-agents)
- [Agenta — Structured Outputs and Function Calling](https://agenta.ai/blog/the-guide-to-structured-outputs-and-function-calling-with-llms)

---

## Pattern 10: MCP (Model Context Protocol)

MCP standardizes how agents discover and invoke tools, replacing one-off function-calling wrappers. An MCP server exposes tools via a standard protocol; any MCP-compatible client can use them.

**Three MCP architecture patterns**

1. **Reusable Agent as MCP Server** — each MCP server is one packaged agent capability, reusable across multiple orchestrators
2. **Strict MCP Purity** — LLM runtime only on the client; MCP servers are stateless tool providers
3. **Hybrid** — server-side specialized processing + client-side orchestration

**What MCP adds (2025 spec)**
- Tool discovery at runtime, not hardcoded at build time
- Server-Sent Events for streaming long-running tool operations
- OAuth + PKCE authentication built into the protocol
- Context persistence across multi-step interactions

**When to use MCP**
- You want to expose an agent's capabilities to other agents or systems
- Tools are shared across multiple agents or applications
- Tool definitions need to evolve independently of the agent using them

**References**
- [MCP Specification 2025-11-25](https://modelcontextprotocol.io/specification/2025-11-25)
- [IBM — MCP Architecture Patterns for Multi-Agent AI Systems](https://developer.ibm.com/articles/mcp-architecture-patterns-ai-systems/)

---

## Quick Selection Guide

| Task shape | Pattern to use |
|------------|----------------|
| Fixed steps, linear dependencies | Prompt Chaining (Pipeline) |
| Variable document types / input classes | Routing Agent |
| Independent analyses of the same artifact | Fan-Out / Fan-In |
| Unknown sub-task structure at design time | Orchestrator-Workers |
| Accuracy matters, single-pass isn't enough | Evaluator-Optimizer |
| Agent decides which steps to take | ToolLoopAgent |
| Large schema library, context efficiency matters | Progressive Context Disclosure |
| Questions over large document corpus | RAG |
| Agent needs to call external APIs or take actions | Tool Use |
| Tools shared across multiple agents or systems | MCP |

---

## Further Reading

- [Anthropic — Building Effective Agents](https://www.anthropic.com/research/building-effective-agents)
- [Anthropic — Writing Tools for Agents](https://www.anthropic.com/engineering/writing-tools-for-agents)
- [Anthropic — Evaluator-Optimizer Cookbook](https://platform.claude.com/cookbook/patterns-agents-evaluator-optimizer)
- [Vercel AI SDK v6](https://vercel.com/blog/ai-sdk-6)
- [Vercel AI SDK — Building Agents](https://ai-sdk.dev/docs/agents/building-agents)
- [Azure — AI Agent Orchestration Patterns](https://learn.microsoft.com/en-us/azure/architecture/ai-ml/guide/ai-agent-design-patterns)
- [Google ADK — Multi-Agent Patterns](https://developers.googleblog.com/developers-guide-to-multi-agent-patterns-in-adk/)
- [IBM — MCP Architecture Patterns](https://developer.ibm.com/articles/mcp-architecture-patterns-ai-systems/)
- [Reflexion — Prompting Guide](https://www.promptingguide.ai/techniques/reflexion)
- [Stack AI — 2026 Agentic Workflow Architectures](https://www.stack-ai.com/blog/the-2026-guide-to-agentic-workflow-architectures)
