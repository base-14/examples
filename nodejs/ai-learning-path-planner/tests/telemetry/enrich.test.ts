import { OpenTelemetry } from "@ai-sdk/otel";
import type {
  LanguageModelV4GenerateResult,
  LanguageModelV4StreamResult,
  LanguageModelV4Usage,
} from "@ai-sdk/provider";
import { NodeSDK, metrics as sdkMetrics } from "@opentelemetry/sdk-node";
import {
  InMemorySpanExporter,
  type ReadableSpan,
  SimpleSpanProcessor,
} from "@opentelemetry/sdk-trace-base";
import { registerTelemetry } from "ai";
import { convertArrayToReadableStream, MockLanguageModelV4 } from "ai/test";
import { Hono } from "hono";
import { afterAll, beforeAll, beforeEach, describe, expect, it } from "vitest";
import { buildLeadAgent, runLeadPlan } from "../../src/agents/lead.ts";
import type { Config } from "../../src/config.ts";
import type { CorpusArtifact } from "../../src/corpus/index-build.ts";
import { CorpusStore } from "../../src/corpus/store.ts";
import { GAP_REASON_TAGS, SERVICE_GAP_REASONS } from "../../src/plans/schema.ts";
import { PlanStore } from "../../src/plans/store.ts";
import { plansRoutes } from "../../src/routes/plans.ts";
import {
  ATTR_AGENT_ROLE,
  ATTR_COST,
  ATTR_COST_SIMULATED,
  ATTR_PLAN_ID,
  ATTR_SUBTOPIC,
  ATTR_TOOL_CATALOGUE,
  enrichSpan,
  PlanCostSpanProcessor,
  takeRunCostUsd,
} from "../../src/telemetry/enrich.ts";
import { newRunCounters, recordPlan, toolDefinitionTokens } from "../../src/telemetry/metrics.ts";
import { type Finding, researchSubtopicTool } from "../../src/tools/research-subtopic.ts";

// PRICE_MODEL borrows a real hosted rate for the local token counts, which is how a run
// against Ollama gets a non-zero cost at all. No hosted provider is contacted anywhere in
// this file: every model is an in-memory stub.
const PRICE_MODEL = "gpt-5.6-luna";

function baseConfig(overrides: Partial<Config> = {}): Config {
  return {
    port: 3000,
    llmProvider: "ollama",
    ollamaBaseUrl: "http://host.docker.internal:11434/api",
    ollamaNumCtx: 32768,
    modelSmall: "gemma4:e2b",
    modelLarge: "qwen3.5:9B",
    priceModel: PRICE_MODEL,
    toolCatalogue: "deferred",
    maxSubtopics: 8,
    maxEscalations: 2,
    allowHostedProvider: false,
    captureMessageContent: false,
    ...overrides,
  };
}

const artifact: CorpusArtifact = {
  catalogue: [
    {
      path: "docs/guides/tracing.md",
      area: "docs",
      title: "Tracing basics",
      description: "Introduction to distributed tracing.",
      keywords: ["tracing"],
      headings: ["What is a trace"],
    },
  ],
  sections: [
    {
      path: "docs/guides/tracing.md",
      heading: "What is a trace",
      text: "A trace represents the end-to-end journey of a single request.",
    },
  ],
};

function store(): CorpusStore {
  return new CorpusStore(artifact);
}

function usage(input: number, output: number): LanguageModelV4Usage {
  return {
    inputTokens: { total: input, noCache: input, cacheRead: 0, cacheWrite: 0 },
    outputTokens: { total: output, text: output, reasoning: 0 },
  };
}

function stopWithObject(value: unknown): LanguageModelV4GenerateResult {
  return {
    content: [{ type: "text", text: JSON.stringify(value) }],
    finishReason: { unified: "stop", raw: "stop" },
    usage: usage(20, 20),
  };
}

function streamObject(value: unknown, input: number, output: number): LanguageModelV4StreamResult {
  return {
    stream: convertArrayToReadableStream([
      { type: "stream-start", warnings: [] },
      { type: "text-start", id: "1" },
      { type: "text-delta", id: "1", delta: JSON.stringify(value) },
      { type: "text-end", id: "1" },
      {
        type: "finish",
        finishReason: { unified: "stop", raw: "stop" },
        usage: usage(input, output),
      },
    ]),
  };
}

const PLAN = { topic: "tracing", weeks: [{ subtopic: "tracing", steps: [] }], gaps: [] };

const FINDINGS = {
  subtopic: "tracing",
  findings: [{ path: "docs/guides/tracing.md", note: "Explains what a trace is." }],
};

const spanExporter = new InMemorySpanExporter();
const metricExporter = new sdkMetrics.InMemoryMetricExporter(
  sdkMetrics.AggregationTemporality.CUMULATIVE,
);
const metricReader = new sdkMetrics.PeriodicExportingMetricReader({
  exporter: metricExporter,
  exportIntervalMillis: 3_600_000,
});

const spanProcessor = new SimpleSpanProcessor(spanExporter);

let sdk: NodeSDK;

beforeAll(() => {
  // The SDK is what installs the AsyncLocalStorage context manager, and without it
  // context does not cross an await, so every span would be its own root. Nothing leaves
  // the process: both exporters are in memory, and resource detection is off so that a
  // finished span is exportable as soon as it ends.
  sdk = new NodeSDK({
    spanProcessors: [new PlanCostSpanProcessor(baseConfig()), spanProcessor],
    metricReader,
    instrumentations: [],
    autoDetectResources: false,
  });
  sdk.start();
  registerTelemetry(new OpenTelemetry({ enrichSpan, usage: true }));
});

// SimpleSpanProcessor hands a finished span to the exporter in a promise, so a span that
// has ended is not necessarily a span the exporter has seen yet.
async function exportedSpans(): Promise<ReadableSpan[]> {
  await spanProcessor.forceFlush();
  return spanExporter.getFinishedSpans();
}

afterAll(async () => {
  await sdk.shutdown();
});

beforeEach(() => {
  spanExporter.reset();
});

async function spansWhere(predicate: (span: ReadableSpan) => boolean): Promise<ReadableSpan[]> {
  return (await exportedSpans()).filter(predicate);
}

function roleIs(role: string) {
  return (span: ReadableSpan) =>
    span.attributes[ATTR_AGENT_ROLE] === role &&
    span.attributes["gen_ai.operation.name"] === "invoke_agent";
}

function ancestorIds(span: ReadableSpan, all: ReadableSpan[]): string[] {
  const byId = new Map(all.map((s) => [s.spanContext().spanId, s]));
  const ids: string[] = [];
  let current: ReadableSpan | undefined = span;
  while (current?.parentSpanContext !== undefined) {
    const parentId = current.parentSpanContext.spanId;
    ids.push(parentId);
    current = byId.get(parentId);
  }
  return ids;
}

describe("enrichSpan", () => {
  it("maps the runtime context onto the four base14 span attributes", () => {
    const attributes = enrichSpan({
      spanType: "operation",
      operationId: "ai.generateText",
      callId: "call-1",
      runtimeContext: {
        planId: "plan-1",
        agentRole: "researcher",
        toolCatalogue: "full",
        subtopic: "sampling",
      },
    });

    expect(attributes).toEqual({
      [ATTR_PLAN_ID]: "plan-1",
      [ATTR_AGENT_ROLE]: "researcher",
      [ATTR_TOOL_CATALOGUE]: "full",
      [ATTR_SUBTOPIC]: "sampling",
    });
  });

  it("returns nothing when the agent was built without a run to attribute spans to", () => {
    expect(
      enrichSpan({
        spanType: "operation",
        operationId: "ai.generateText",
        callId: "call-1",
        runtimeContext: undefined,
      }),
    ).toBeUndefined();
  });
});

describe("the run cost accumulator", () => {
  it("evicts the oldest run rather than growing without bound", () => {
    const processor = new PlanCostSpanProcessor(baseConfig());

    function endAgentSpan(planId: string): void {
      processor.onEnd({
        attributes: {
          "gen_ai.operation.name": "invoke_agent",
          "gen_ai.request.model": "gemma4:e2b",
          "gen_ai.usage.input_tokens": 100,
          "gen_ai.usage.output_tokens": 100,
          [ATTR_PLAN_ID]: planId,
        },
      } as unknown as ReadableSpan);
    }

    // One more run than the cap, so the first one has to have been evicted. Its spans are
    // still arriving 1024 runs later, which in a long-lived process is the shape of the
    // leak: nothing else ever deletes an entry that takeRunCostUsd has already taken.
    endAgentSpan("run-0");
    for (let i = 1; i <= 1024; i += 1) {
      endAgentSpan(`run-${i}`);
    }

    expect(takeRunCostUsd("run-0")).toBe(0);
    expect(takeRunCostUsd("run-1024")).toBeGreaterThan(0);

    for (let i = 1; i < 1024; i += 1) {
      takeRunCostUsd(`run-${i}`);
    }
  });

  it("keeps the whole cost of a slow run while faster ones churn past the cap", () => {
    const processor = new PlanCostSpanProcessor(baseConfig());

    function endAgentSpan(planId: string): void {
      processor.onEnd({
        attributes: {
          "gen_ai.operation.name": "invoke_agent",
          "gen_ai.request.model": "gemma4:e2b",
          "gen_ai.usage.input_tokens": 100,
          "gen_ai.usage.output_tokens": 100,
          [ATTR_PLAN_ID]: planId,
        },
      } as unknown as ReadableSpan);
    }

    endAgentSpan("cost-of-one-span");
    const oneSpan = takeRunCostUsd("cost-of-one-span");
    expect(oneSpan).toBeGreaterThan(0);

    // A run contributes one invoke_agent span per researcher across the twenty-odd seconds
    // it takes, so on a busy service far more than a cap's worth of shorter runs can finish
    // while one is still going. Evicting by insertion order drops that run's partial total
    // even though its spans are still arriving, and the spans that follow rebuild it from
    // zero: the run then reports a cost that looks plausible and is too low, which is worse
    // than a missing value because nothing announces it. Evicting by least-recently-updated
    // keeps a run alive for as long as it is still contributing.
    endAgentSpan("run-slow");
    for (let round = 0; round < 4; round += 1) {
      for (let i = 0; i < 320; i += 1) {
        endAgentSpan(`run-fast-${round}-${i}`);
      }
      endAgentSpan("run-slow");
    }

    expect(takeRunCostUsd("run-slow")).toBeCloseTo(oneSpan * 5, 10);

    for (let round = 0; round < 4; round += 1) {
      for (let i = 0; i < 320; i += 1) {
        takeRunCostUsd(`run-fast-${round}-${i}`);
      }
    }
  });
});

describe("subagent span parentage", () => {
  it("parents three concurrent researcher runs to the lead run", async () => {
    const s = store();

    let leadCalls = 0;
    const leadModel = new MockLanguageModelV4({
      doGenerate: async () => {
        leadCalls += 1;
        if (leadCalls === 1) {
          return {
            content: ["tracing", "sampling", "exporters"].map((subtopic, index) => ({
              type: "tool-call" as const,
              toolCallId: `call-${index}`,
              toolName: "research_subtopic",
              input: JSON.stringify({ subtopic }),
            })),
            finishReason: { unified: "tool-calls", raw: "tool_calls" },
            usage: usage(40, 10),
          };
        }
        return stopWithObject(PLAN);
      },
    });

    // The three researchers only get past this gate once all three have entered it. If
    // the fan-out ever became serial, the first would wait here forever and this test
    // would time out rather than quietly assert on three sequential spans.
    let entered = 0;
    let open = () => {};
    const allEntered = new Promise<void>((resolve) => {
      open = resolve;
    });
    const researcherModel = new MockLanguageModelV4({
      doGenerate: async () => {
        entered += 1;
        if (entered === 3) open();
        await allEntered;
        return stopWithObject(FINDINGS);
      },
    });

    const lead = buildLeadAgent({
      store: s,
      config: baseConfig(),
      model: leadModel,
      researcherModels: { small: researcherModel },
      run: { planId: "plan-parentage", counters: newRunCounters() },
    });

    await lead.loop.generate({ prompt: "Topic: tracing" });

    const all = await exportedSpans();
    const leadSpans = all.filter(roleIs("lead"));
    const researcherSpans = all.filter(roleIs("researcher"));

    expect(leadSpans).toHaveLength(1);
    // Six, not three: each researcher runs a tool loop and then a structured call to
    // report its findings (see agents/researcher.ts), and both carry the researcher role.
    // gen_ai.agent.name is the telemetry functionId, which is what separates the two.
    expect(researcherSpans).toHaveLength(6);
    const researchLoopSpans = researcherSpans.filter(
      (span) => span.attributes["gen_ai.agent.name"] === "researcher",
    );
    expect(researchLoopSpans).toHaveLength(3);

    const leadSpan = leadSpans[0] as ReadableSpan;
    const leadSpanId = leadSpan.spanContext().spanId;

    for (const researcherSpan of researcherSpans) {
      expect(researcherSpan.spanContext().traceId).toBe(leadSpan.spanContext().traceId);
      expect(ancestorIds(researcherSpan, all)).toContain(leadSpanId);
      expect(researcherSpan.attributes[ATTR_PLAN_ID]).toBe("plan-parentage");
    }

    expect(researchLoopSpans.map((span) => span.attributes[ATTR_SUBTOPIC]).sort()).toEqual([
      "exporters",
      "sampling",
      "tracing",
    ]);
  });
});

describe("cost on the streaming path", () => {
  it("writes a non-zero cost onto the spans of a streamed run", async () => {
    const s = store();
    const leadModel = new MockLanguageModelV4({
      doStream: streamObject(PLAN, 120, 40),
    });

    const lead = buildLeadAgent({
      store: s,
      config: baseConfig(),
      model: leadModel,
      run: { planId: "plan-cost", counters: newRunCounters() },
    });

    const result = await lead.loop.stream({ prompt: "Topic: tracing" });
    await result.consumeStream();

    const costed = await spansWhere((span) => span.attributes[ATTR_COST] !== undefined);
    expect(costed.length).toBeGreaterThan(0);

    for (const span of costed) {
      expect(span.attributes[ATTR_COST]).toBeGreaterThan(0);
      expect(span.attributes[ATTR_COST_SIMULATED]).toBe(true);
    }

    expect((await spansWhere(roleIs("lead")))[0]?.attributes[ATTR_COST]).toBeGreaterThan(0);
    expect(takeRunCostUsd("plan-cost")).toBeGreaterThan(0);
  });

  it("leaves a span with no token counts alone", async () => {
    const s = store();
    const lead = buildLeadAgent({
      store: s,
      config: baseConfig(),
      model: new MockLanguageModelV4({ doStream: streamObject(PLAN, 120, 40) }),
      run: { planId: "plan-untouched", counters: newRunCounters() },
    });

    const result = await lead.loop.stream({ prompt: "Topic: tracing" });
    await result.consumeStream();

    const steps = await spansWhere(
      (span) => span.attributes["gen_ai.operation.name"] === "agent_step",
    );
    expect(steps.length).toBeGreaterThan(0);
    for (const step of steps) {
      expect(step.attributes[ATTR_COST]).toBeUndefined();
    }

    takeRunCostUsd("plan-untouched");
  });
});

interface MetricPoint {
  attributes: Record<string, unknown>;
  value: unknown;
}

interface HistogramPoint {
  count: number;
  sum: number;
  buckets: { boundaries: number[] };
}

// InMemoryMetricExporter appends a snapshot per flush and the reader is cumulative, so
// only the newest snapshot is the current state of every instrument.
async function exportedMetrics(): Promise<Map<string, MetricPoint[]>> {
  await metricReader.forceFlush();
  const snapshots = metricExporter.getMetrics();
  const latest = snapshots[snapshots.length - 1];
  const byName = new Map<string, MetricPoint[]>();
  for (const scope of latest?.scopeMetrics ?? []) {
    for (const metric of scope.metrics) {
      byName.set(metric.descriptor.name, metric.dataPoints as unknown as MetricPoint[]);
    }
  }
  return byName;
}

function pointsFor(exported: Map<string, MetricPoint[]>, name: string): MetricPoint[] {
  const points = exported.get(name);
  if (points === undefined) {
    throw new Error(`no points were exported for ${name}`);
  }
  return points;
}

function pointWith(
  exported: Map<string, MetricPoint[]>,
  name: string,
  attributes: Record<string, unknown>,
): MetricPoint {
  const match = pointsFor(exported, name).find((point) =>
    Object.entries(attributes).every(([key, value]) => point.attributes[key] === value),
  );
  if (match === undefined) {
    const seen = JSON.stringify(pointsFor(exported, name).map((point) => point.attributes));
    throw new Error(`${name} has no point tagged ${JSON.stringify(attributes)}. Seen: ${seen}`);
  }
  return match;
}

function histogram(point: MetricPoint): HistogramPoint {
  return point.value as HistogramPoint;
}

// The processor reads token counts and a model id off a finished span and prices them.
// tests/llm/cost.test.ts covers costOf's arithmetic, but nothing joined the two halves:
// zeroing the cache-read attribute read, or dropping the response-model preference, left
// the whole suite green while every cached hosted call was overpriced and every run was
// priced against the model that was asked rather than the one that answered. Both rows
// below come from _shared/pricing.json and are far enough apart to tell which was used.
describe("PlanCostSpanProcessor: which numbers it prices", () => {
  // input 2, output 12, cached_input 0.2 per million.
  const ANSWERING_MODEL = "gpt-5.6-terra";

  async function runOne(model: MockLanguageModelV4): Promise<void> {
    const lead = buildLeadAgent({
      store: store(),
      config: baseConfig(),
      model,
      run: { planId: "plan-pricing", counters: newRunCounters() },
    });
    // The shaping call rather than the loop: it makes exactly one model call, with no
    // tool requirement in front of it, so the span under test is the only one there is.
    await lead.shaper.generate({ prompt: "Write the plan." });
    takeRunCostUsd("plan-pricing");
  }

  function answeringWith(
    modelId: string,
    tokens: { input: number; output: number; cacheRead: number },
  ): MockLanguageModelV4 {
    return new MockLanguageModelV4({
      modelId: "mock-model-id",
      doGenerate: async () => ({
        content: [{ type: "text", text: JSON.stringify(PLAN) }],
        finishReason: { unified: "stop", raw: "stop" },
        usage: {
          inputTokens: {
            total: tokens.input,
            noCache: tokens.input - tokens.cacheRead,
            cacheRead: tokens.cacheRead,
            cacheWrite: 0,
          },
          outputTokens: { total: tokens.output, text: tokens.output, reasoning: 0 },
        },
        response: { modelId },
      }),
    });
  }

  it("prices the cached part of the input at the cached rate", async () => {
    await runOne(answeringWith(ANSWERING_MODEL, { input: 100, output: 10, cacheRead: 40 }));

    const chat = (
      await spansWhere((span) => span.attributes["gen_ai.operation.name"] === "chat")
    )[0];
    expect(chat?.attributes["gen_ai.usage.cache_read.input_tokens"]).toBe(40);
    // 60 uncached at 2, 40 cached at 0.2, 10 output at 12, per million. Reading the
    // cache-read count as zero prices all 100 at 2 and gives 0.00032 instead.
    expect(chat?.attributes[ATTR_COST]).toBeCloseTo(0.000248, 9);
  });

  it("prices against the model that answered, not the model that was asked", async () => {
    await runOne(answeringWith(ANSWERING_MODEL, { input: 100, output: 10, cacheRead: 0 }));

    const chat = (
      await spansWhere((span) => span.attributes["gen_ai.operation.name"] === "chat")
    )[0];
    expect(chat?.attributes["gen_ai.request.model"]).toBe("mock-model-id");
    expect(chat?.attributes["gen_ai.response.model"]).toBe(ANSWERING_MODEL);
    // The answering model has a price row of its own, so this is a real rate rather than
    // a borrowed one. Falling back to the request model finds no row, borrows PRICE_MODEL
    // and reports 0.000032 as simulated.
    expect(chat?.attributes[ATTR_COST_SIMULATED]).toBe(false);
    expect(chat?.attributes[ATTR_COST]).toBeCloseTo(0.00032, 9);
  });

  it("falls back to the requested model when nothing answered with one", async () => {
    const model = new MockLanguageModelV4({
      modelId: ANSWERING_MODEL,
      doGenerate: async () => ({
        content: [{ type: "text", text: JSON.stringify(PLAN) }],
        finishReason: { unified: "stop", raw: "stop" },
        usage: usage(100, 10),
      }),
    });
    await runOne(model);

    const agent = (await spansWhere(roleIs("lead")))[0];
    expect(agent?.attributes["gen_ai.request.model"]).toBe(ANSWERING_MODEL);
    expect(agent?.attributes[ATTR_COST]).toBeCloseTo(0.00032, 9);
  });
});

describe("recordPlan", () => {
  it("records a declined run on all six instruments, with a fan-out of zero", async () => {
    recordPlan({
      status: "declined",
      durationSeconds: 0.01,
      costUsd: 0,
      counters: newRunCounters(),
      gaps: [{ term: "kubernetes", reason: SERVICE_GAP_REASONS.topic_out_of_range }],
      catalogue: "deferred",
      toolDefinitionTokens: { lead: 290, researcher: 361 },
    });

    const exported = await exportedMetrics();

    expect([...exported.keys()].sort()).toEqual([
      "base14.gen_ai.tool_definition.tokens",
      "base14.plan.cost",
      "base14.plan.duration",
      "base14.plan.escalation.count",
      "base14.plan.fanout",
      "base14.plan.gap.count",
    ]);

    const cost = pointsFor(exported, "base14.plan.cost")[0] as MetricPoint;
    expect(cost.attributes).toEqual({
      catalogue: "deferred",
      fanout_bucket: "0",
      outcome: "declined",
    });
    expect(histogram(cost)).toMatchObject({ count: 1, sum: 0 });
    // Not the SDK defaults, which start [0, 5, 10, ...] and put every plan this service
    // produces in one bucket. A measured plan costs 0.00034 USD.
    expect(histogram(cost).buckets.boundaries).toEqual([
      0.0001, 0.0003, 0.001, 0.003, 0.01, 0.03, 0.1, 0.3, 1,
    ]);

    const fanout = pointsFor(exported, "base14.plan.fanout")[0] as MetricPoint;
    expect(fanout.attributes).toEqual({ outcome: "declined" });
    expect(histogram(fanout)).toMatchObject({ count: 1, sum: 0 });
    expect(histogram(fanout).buckets.boundaries).toEqual([0, 1, 2, 3, 4, 5, 6, 8]);

    const duration = pointsFor(exported, "base14.plan.duration")[0] as MetricPoint;
    expect(duration.attributes).toEqual({ outcome: "declined" });
    expect(histogram(duration)).toMatchObject({ count: 1, sum: 0.01 });
    // A measured plan takes 72 to 153 seconds and a decline about 0.02, so the two are
    // never in the same bucket. See tests/telemetry/metrics.test.ts.
    expect(histogram(duration).buckets.boundaries).toEqual([
      0.1, 1, 10, 30, 60, 90, 120, 150, 180, 240, 300,
    ]);

    const gap = pointsFor(exported, "base14.plan.gap.count")[0] as MetricPoint;
    expect(gap.attributes).toEqual({ reason: "topic_out_of_range" });
    expect(gap.value).toBe(1);

    const escalation = pointsFor(exported, "base14.plan.escalation.count")[0] as MetricPoint;
    expect(escalation.attributes).toEqual({ trigger: "low_confidence" });
    expect(escalation.value).toBe(0);

    const tokens = pointsFor(exported, "base14.gen_ai.tool_definition.tokens");
    expect(tokens.map((point) => point.attributes)).toEqual([
      { role: "lead", catalogue: "deferred" },
      { role: "researcher", catalogue: "deferred" },
    ]);
    expect(tokens.map((point) => histogram(point).sum)).toEqual([290, 361]);
  });

  // These are the numbers Task 10's README quotes, at four characters per token, and they
  // exclude the $schema URL that z.toJSONSchema emits and no provider ever receives.
  // Changing a tool description changes them, and that is the point of asserting them.
  it("estimates the tool definition size without the $schema URL", () => {
    const agent = buildLeadAgent({
      store: store(),
      config: baseConfig(),
      model: new MockLanguageModelV4({ doGenerate: stopWithObject(PLAN) }),
    });

    expect(toolDefinitionTokens(agent.tools, "lead", baseConfig())).toBe(290);
    expect(toolDefinitionTokens(agent.tools, "researcher", baseConfig())).toBe(361);
    expect(toolDefinitionTokens(agent.tools, "lead", baseConfig({ toolCatalogue: "full" }))).toBe(
      650,
    );
  });

  it("records a run that failed mid-stream, tagged failed, with the fan-out it reached", async () => {
    const s = store();
    const app = new Hono();
    app.route(
      "/",
      plansRoutes({
        store: s,
        config: baseConfig(),
        plans: new PlanStore(),
        model: new MockLanguageModelV4({
          doGenerate: async () => {
            throw new Error("ollama unreachable");
          },
        }),
      }),
    );

    const response = await app.request("/plans", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ topic: "tracing" }),
    });
    const lines = (await response.text())
      .trim()
      .split("\n")
      .map((line) => JSON.parse(line));

    expect(lines[1]).toMatchObject({ event: "error", id: lines[0].id });

    const exported = await exportedMetrics();

    const fanout = pointWith(exported, "base14.plan.fanout", { outcome: "failed" });
    expect(histogram(fanout)).toMatchObject({ count: 1, sum: 0 });

    const duration = pointWith(exported, "base14.plan.duration", { outcome: "failed" });
    expect(histogram(duration).count).toBe(1);
  });
});

// Ordered after the recordPlan tests above on purpose: the metric reader is cumulative
// across this file, and those assert an exact count on points these two also write to.
// The reason tag on base14.plan.gap.count is produced by matching the gap text the service
// writes. That text and the match used to live in two files, so renaming the sentence in
// agents/lead.ts left every test green while the metric silently retagged itself
// model_reported. These two drive the real lead paths and read the tag back off the
// exported point, so the coupling is asserted rather than assumed.
describe("recordPlan: the reasons the service writes are tagged, not read as the model's", () => {
  function recordFrom(gaps: { term: string; reason: string }[]): void {
    recordPlan({
      status: "failed",
      durationSeconds: 1,
      costUsd: 0,
      counters: newRunCounters(),
      gaps,
      catalogue: "deferred",
      toolDefinitionTokens: { lead: 290, researcher: 361 },
    });
  }

  it("tags the gap a run that never called a tool produces", async () => {
    const s = store();
    const lead = buildLeadAgent({
      store: s,
      config: baseConfig(),
      model: new MockLanguageModelV4({
        doGenerate: stopWithObject({ topic: "tracing", weeks: [], gaps: [] }),
      }),
    });

    const outcome = await runLeadPlan(lead, { topic: "tracing" }, s);
    expect(outcome.status).toBe("failed");
    recordFrom(outcome.plan.gaps);

    const gap = pointWith(await exportedMetrics(), "base14.plan.gap.count", {
      reason: "no_tool_call",
    });
    expect(gap.value).toBeGreaterThanOrEqual(1);
  });

  it("tags the gap a run that called tools but researched nothing produces", async () => {
    const s = store();
    let callCount = 0;
    const lead = buildLeadAgent({
      store: s,
      config: baseConfig(),
      model: new MockLanguageModelV4({
        doGenerate: async () => {
          callCount += 1;
          if (callCount <= 6) {
            return {
              content: [
                {
                  type: "tool-call" as const,
                  toolCallId: `call-${callCount}`,
                  toolName: "corpus_map",
                  input: "{}",
                },
              ],
              finishReason: { unified: "tool-calls" as const, raw: "tool_calls" },
              usage: usage(20, 5),
            };
          }
          return stopWithObject({ topic: "tracing", weeks: [], gaps: [] });
        },
      }),
    });

    const outcome = await runLeadPlan(lead, { topic: "tracing" }, s);
    expect(outcome.status).toBe("failed");
    recordFrom(outcome.plan.gaps);

    const gap = pointWith(await exportedMetrics(), "base14.plan.gap.count", {
      reason: "no_research",
    });
    expect(gap.value).toBeGreaterThanOrEqual(1);
  });

  // Drives the real research_subtopic tool, so the reason each of these asserts is the
  // sentence the tool writes rather than a copy of it held in this file.
  async function gapFromTool(
    findings: { small: Finding[]; large: Finding[] },
    overrides: Partial<Config>,
  ): Promise<string | undefined> {
    const tool = researchSubtopicTool({
      store: store(),
      config: baseConfig(overrides),
      buildResearcher: ({ tier }) => ({
        generate: async () => ({
          output: { findings: tier === "small" ? findings.small : findings.large },
        }),
      }),
    });
    const execute = tool.execute;
    if (execute === undefined) throw new Error("research_subtopic has no execute");
    const result = (await execute(
      { subtopic: "tracing" },
      { toolCallId: "call-1", messages: [] },
    )) as { gap?: { term: string; reason: string } };
    return result.gap?.reason;
  }

  const INVENTED = { path: "docs/guides/does-not-exist.md", note: "Made up." };
  const CITED = { path: "docs/guides/tracing.md", note: "Real path." };

  it("tags the gap a declined topic produces", async () => {
    const s = store();
    const lead = buildLeadAgent({
      store: s,
      config: baseConfig(),
      model: new MockLanguageModelV4({
        doGenerate: async () => {
          throw new Error("the model should not have been called");
        },
      }),
    });

    const outcome = await runLeadPlan(lead, { topic: "kubernetes" }, s);
    expect(outcome.status).toBe("declined");
    recordFrom(outcome.plan.gaps);

    const gap = pointWith(await exportedMetrics(), "base14.plan.gap.count", {
      reason: "topic_out_of_range",
    });
    expect(gap.value).toBeGreaterThanOrEqual(1);
  });

  it("tags the gap a subtopic past MAX_SUBTOPICS produces", async () => {
    const reason = await gapFromTool({ small: [CITED], large: [] }, { maxSubtopics: 0 });
    expect(reason).toBeDefined();
    recordFrom([{ term: "tracing", reason: reason as string }]);

    const gap = pointWith(await exportedMetrics(), "base14.plan.gap.count", {
      reason: "max_subtopics",
    });
    expect(gap.value).toBeGreaterThanOrEqual(1);
  });

  it("tags the gap an escalation past MAX_ESCALATIONS produces", async () => {
    const reason = await gapFromTool({ small: [INVENTED], large: [] }, { maxEscalations: 0 });
    expect(reason).toBeDefined();
    recordFrom([{ term: "tracing", reason: reason as string }]);

    const gap = pointWith(await exportedMetrics(), "base14.plan.gap.count", {
      reason: "max_escalations",
    });
    expect(gap.value).toBeGreaterThanOrEqual(1);
  });

  it("tags the gap a subtopic that stayed low after escalating produces", async () => {
    const reason = await gapFromTool({ small: [INVENTED], large: [INVENTED] }, {});
    expect(reason).toBeDefined();
    recordFrom([{ term: "tracing", reason: reason as string }]);

    const gap = pointWith(await exportedMetrics(), "base14.plan.gap.count", {
      reason: "low_confidence",
    });
    expect(gap.value).toBeGreaterThanOrEqual(1);
  });

  it("tags the gap a citation that never validated produces", async () => {
    const s = store();
    const planWithBadStep = {
      topic: "tracing",
      weeks: [
        {
          subtopic: "tracing",
          steps: [
            {
              title: "Read a doc that is not there",
              path: "docs/guides/does-not-exist.md",
              kind: "doc",
              why: "Invented.",
            },
          ],
        },
      ],
      gaps: [],
    };
    let callCount = 0;
    const lead = buildLeadAgent({
      store: s,
      config: baseConfig(),
      model: new MockLanguageModelV4({
        doGenerate: async () => {
          callCount += 1;
          if (callCount === 1) {
            return {
              content: [
                {
                  type: "tool-call" as const,
                  toolCallId: "call-1",
                  toolName: "research_subtopic",
                  input: JSON.stringify({ subtopic: "tracing" }),
                },
              ],
              finishReason: { unified: "tool-calls" as const, raw: "tool_calls" },
              usage: usage(20, 5),
            };
          }
          return stopWithObject(planWithBadStep);
        },
      }),
      researcherModels: {
        small: new MockLanguageModelV4({ doGenerate: stopWithObject(FINDINGS) }),
      },
    });

    const outcome = await runLeadPlan(lead, { topic: "tracing" }, s);
    recordFrom(outcome.plan.gaps);

    const gap = pointWith(await exportedMetrics(), "base14.plan.gap.count", {
      reason: "citation_invalid",
    });
    expect(gap.value).toBeGreaterThanOrEqual(1);
  });

  it("tags the service's own outage reason rather than reading it as the model's", async () => {
    recordFrom([{ term: "tracing", reason: SERVICE_GAP_REASONS.service_error }]);

    const gap = pointWith(await exportedMetrics(), "base14.plan.gap.count", {
      reason: "service_error",
    });
    expect(gap.value).toBeGreaterThanOrEqual(1);
  });

  it("tags a gap the lead model wrote itself as model_reported", async () => {
    recordFrom([{ term: "tracing", reason: "I could not find much about this, sorry." }]);

    const gap = pointWith(await exportedMetrics(), "base14.plan.gap.count", {
      reason: "model_reported",
    });
    expect(gap.value).toBeGreaterThanOrEqual(1);
  });

  // The completeness check. Every tag gapReason can return is driven by one of the tests
  // above, so a tag that stops being reachable, or a new one that nothing exercises,
  // fails here rather than going unnoticed.
  it("has recorded a point for every tag base14.plan.gap.count can carry", async () => {
    const recorded = new Set(
      pointsFor(await exportedMetrics(), "base14.plan.gap.count").map(
        (point) => point.attributes.reason,
      ),
    );

    expect([...GAP_REASON_TAGS].sort()).toEqual([...recorded].sort());
  });
});
