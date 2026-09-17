import type { LanguageModelV4GenerateResult, LanguageModelV4Usage } from "@ai-sdk/provider";
import { MockLanguageModelV4 } from "ai/test";
import { describe, expect, it } from "vitest";
import { buildLeadAgent, runLeadPlan } from "../../src/agents/lead.ts";
import type { Config } from "../../src/config.ts";
import type { CorpusArtifact } from "../../src/corpus/index-build.ts";
import { CorpusStore } from "../../src/corpus/store.ts";
import { SERVICE_GAP_REASONS } from "../../src/plans/schema.ts";

function baseConfig(overrides: Partial<Config> = {}): Config {
  return {
    port: 3000,
    llmProvider: "ollama",
    ollamaBaseUrl: "http://host.docker.internal:11434/api",
    ollamaNumCtx: 32768,
    modelSmall: "gemma4:e2b",
    modelLarge: "qwen3.5:9B",
    priceModel: undefined,
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
    {
      path: "docs/guides/metrics.md",
      area: "docs",
      title: "Metrics basics",
      description: "Introduction to metrics.",
      keywords: ["metrics"],
      headings: ["Counters and gauges"],
    },
  ],
  sections: [
    {
      path: "docs/guides/tracing.md",
      heading: "What is a trace",
      text: "A trace represents the end-to-end journey of a single request.",
    },
    {
      path: "docs/guides/metrics.md",
      heading: "Counters and gauges",
      text: "A counter only goes up; a gauge can go up or down.",
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

function toolCallStep(
  toolName: string,
  input: unknown,
  callId: string,
): LanguageModelV4GenerateResult {
  return {
    content: [{ type: "tool-call", toolCallId: callId, toolName, input: JSON.stringify(input) }],
    finishReason: { unified: "tool-calls", raw: "tool_calls" },
    usage: usage(20, 5),
  };
}

// One structured call per researcher run, whatever the loop did before it, so this counts
// researchers rather than model calls. See agents/researcher.ts.
function researcherRuns(model: MockLanguageModelV4): number {
  return model.doGenerateCalls.filter((call) => call.responseFormat?.type === "json").length;
}

// A plan with a step in it. A plan with no steps in any week is a failed run now, not a
// planned one, so a fixture that stands for a successful plan has to carry one.
const PLANNED_PLAN = {
  topic: "tracing",
  weeks: [
    {
      subtopic: "tracing basics",
      steps: [
        {
          title: "Read the trace intro",
          path: "docs/guides/tracing.md",
          kind: "doc",
          why: "Establishes the vocabulary.",
        },
      ],
    },
  ],
  gaps: [],
};

// prepareStep requires a tool call while nothing has been researched and the SDK enforces
// that itself, so a lead model that answers in prose before researching anything fails the
// run rather than planning it. These fixtures research one subtopic first, the way a real
// run does, and the responses given here are what the loop and the shaping call get after
// that. The last one is repeated once the list runs out.
function leadModel(...after: LanguageModelV4GenerateResult[]): MockLanguageModelV4 {
  let callCount = 0;
  return new MockLanguageModelV4({
    doGenerate: async () => {
      callCount += 1;
      if (callCount === 1) {
        return toolCallStep("research_subtopic", { subtopic: "tracing basics" }, "call-1");
      }
      return after[Math.min(callCount - 2, after.length - 1)] as LanguageModelV4GenerateResult;
    },
  });
}

// The researcher the fixtures above fan out to. Its findings cite a path the test store
// really has, so the loop's research notes carry a citation the shaping call can use.
function researchedTracing(): MockLanguageModelV4 {
  return findingsModel([{ path: "docs/guides/tracing.md", note: "About tracing." }]);
}

function throwingModel(): MockLanguageModelV4 {
  return new MockLanguageModelV4({
    doGenerate: async () => {
      throw new Error("the model should not have been called");
    },
  });
}

function findingsModel(
  findings: { path: string; heading?: string; note: string }[],
): MockLanguageModelV4 {
  return new MockLanguageModelV4({
    doGenerate: stopWithObject({ subtopic: "x", findings }),
  });
}

describe("runLeadPlan: decline on empty coverage", () => {
  it("declines without ever calling the model when the topic has no coverage at all", async () => {
    const s = store();
    const lead = buildLeadAgent({ store: s, config: baseConfig(), model: throwingModel() });

    const outcome = await runLeadPlan(lead, { topic: "kubernetes" }, s);

    expect(outcome.status).toBe("declined");
    expect(outcome.plan.weeks).toEqual([]);
    expect(outcome.plan.gaps[0]?.term).toBe("kubernetes");
  });

  it("does not decline when the topic has at least a near miss", async () => {
    const s = store();
    const lead = buildLeadAgent({
      store: s,
      config: baseConfig(),
      model: leadModel(stopWithObject(PLANNED_PLAN)),
      researcherModels: { small: researchedTracing() },
    });

    const outcome = await runLeadPlan(lead, { topic: "tracing" }, s);

    expect(outcome.status).toBe("planned");
  });
});

describe("research_subtopic: fan-out stops at MAX_SUBTOPICS", () => {
  it("does not research a subtopic beyond the configured cap", async () => {
    const s = store();
    let callCount = 0;
    const leadModel = new MockLanguageModelV4({
      doGenerate: async () => {
        callCount += 1;
        if (callCount <= 3) {
          return toolCallStep(
            "research_subtopic",
            { subtopic: ["a", "b", "c"][callCount - 1] },
            `call-${callCount}`,
          );
        }
        return stopWithObject({ topic: "tracing", weeks: [], gaps: [] });
      },
    });
    const small = findingsModel([{ path: "docs/guides/tracing.md", note: "About tracing." }]);

    const lead = buildLeadAgent({
      store: s,
      config: baseConfig({ maxSubtopics: 2 }),
      model: leadModel,
      researcherModels: { small },
    });

    const result = await lead.loop.generate({ prompt: "Topic: tracing" });

    expect(researcherRuns(small)).toBe(2);
    const gaps = result.toolResults.map(
      (r) => (r.output as { gap?: { reason: string } }).gap?.reason,
    );
    expect(gaps.filter((reason) => reason?.includes("MAX_SUBTOPICS"))).toHaveLength(1);
  });
});

describe("research_subtopic: escalation stops at MAX_ESCALATIONS", () => {
  it("does not escalate a subtopic beyond the configured cap", async () => {
    const s = store();
    let callCount = 0;
    const leadModel = new MockLanguageModelV4({
      doGenerate: async () => {
        callCount += 1;
        if (callCount <= 3) {
          return toolCallStep(
            "research_subtopic",
            { subtopic: ["a", "b", "c"][callCount - 1] },
            `call-${callCount}`,
          );
        }
        return stopWithObject({ topic: "tracing", weeks: [], gaps: [] });
      },
    });
    const small = findingsModel([]);
    const large = findingsModel([]);

    const lead = buildLeadAgent({
      store: s,
      config: baseConfig({ maxSubtopics: 8, maxEscalations: 1 }),
      model: leadModel,
      researcherModels: { small, large },
    });

    const result = await lead.loop.generate({ prompt: "Topic: tracing" });

    expect(researcherRuns(small)).toBe(3);
    expect(researcherRuns(large)).toBe(1);

    const reasons = result.toolResults.map(
      (r) => (r.output as { gap?: { reason: string } }).gap?.reason,
    );
    expect(
      reasons.filter((reason) => reason?.includes("stayed low even after escalating")),
    ).toHaveLength(1);
    expect(
      reasons.filter((reason) => reason?.includes("MAX_ESCALATIONS was already reached")),
    ).toHaveLength(2);
  });
});

describe("runLeadPlan: invalid citation is dropped and recorded", () => {
  const planWithInvalidStep = {
    topic: "tracing",
    weeks: [
      {
        subtopic: "tracing basics",
        steps: [
          {
            title: "Read the trace intro",
            path: "docs/guides/tracing.md",
            kind: "doc",
            why: "Establishes the vocabulary.",
          },
          {
            title: "Read a bogus doc",
            path: "docs/guides/does-not-exist.md",
            kind: "doc",
            why: "Bad citation.",
          },
        ],
      },
    ],
    gaps: [],
  };

  it("keeps a step whose retry produced a valid citation", async () => {
    const s = store();
    const retryFixed = {
      ...planWithInvalidStep,
      weeks: [
        {
          subtopic: "tracing basics",
          steps: [
            planWithInvalidStep.weeks[0]?.steps[0],
            {
              title: "Read a bogus doc",
              path: "docs/guides/metrics.md",
              kind: "doc",
              why: "Corrected citation.",
            },
          ],
        },
      ],
    };
    // Three calls now, not two: the tool loop, the shaping call, and the shaping call
    // again for the retry. Only the shaping call is repeated.
    const model = leadModel(
      stopWithObject(planWithInvalidStep),
      stopWithObject(planWithInvalidStep),
      stopWithObject(retryFixed),
    );
    const lead = buildLeadAgent({
      store: s,
      config: baseConfig(),
      model,
      researcherModels: { small: researchedTracing() },
    });

    const outcome = await runLeadPlan(lead, { topic: "tracing" }, s);

    // Four calls: the research step, the loop's last step, the shaping call and the
    // shaping call again for the retry. Only the shaping call is repeated.
    expect(model.doGenerateCalls).toHaveLength(4);
    expect(outcome.plan.weeks[0]?.steps).toHaveLength(2);
    expect(outcome.plan.weeks[0]?.steps[1]?.path).toBe("docs/guides/metrics.md");
    expect(outcome.plan.gaps).toEqual([]);
  });

  it("drops a step whose retry is still invalid and records a gap", async () => {
    const s = store();
    const model = leadModel(stopWithObject(planWithInvalidStep));
    const lead = buildLeadAgent({
      store: s,
      config: baseConfig(),
      model,
      researcherModels: { small: researchedTracing() },
    });

    const outcome = await runLeadPlan(lead, { topic: "tracing" }, s);

    expect(model.doGenerateCalls).toHaveLength(4);
    expect(outcome.plan.weeks[0]?.steps).toHaveLength(1);
    expect(outcome.plan.weeks[0]?.steps[0]?.path).toBe("docs/guides/tracing.md");
    expect(outcome.plan.gaps).toHaveLength(1);
    expect(outcome.plan.gaps[0]?.reason).toContain("did not validate, even after one retry");
  });

  it("does not retry when every citation is already valid", async () => {
    const s = store();
    const validPlan = {
      topic: "tracing",
      weeks: [
        {
          subtopic: "tracing basics",
          steps: [
            {
              title: "Read the trace intro",
              path: "docs/guides/tracing.md",
              kind: "doc",
              why: "Establishes the vocabulary.",
            },
          ],
        },
      ],
      gaps: [],
    };
    const model = leadModel(stopWithObject(validPlan));
    const lead = buildLeadAgent({
      store: s,
      config: baseConfig(),
      model,
      researcherModels: { small: researchedTracing() },
    });

    const outcome = await runLeadPlan(lead, { topic: "tracing" }, s);

    // The research step, the loop's last step and the shaping call. No retry, since every
    // citation validated.
    expect(model.doGenerateCalls).toHaveLength(3);
    expect(outcome.status).toBe("planned");
    expect(outcome.plan).toEqual(validPlan);
  });
});

// The provider puts `format` on the wire for every step whose call options carry a json
// responseFormat, and `format` alongside tool definitions stops this model calling a tool at
// all. So the loop and the schema are two calls.
describe("the tool loop and the plan schema are separate model calls", () => {
  const validPlan = {
    topic: "tracing",
    weeks: [
      {
        subtopic: "tracing basics",
        steps: [
          {
            title: "Read the trace intro",
            path: "docs/guides/tracing.md",
            kind: "doc",
            why: "Establishes the vocabulary.",
          },
        ],
      },
    ],
    gaps: [],
  };

  it("sends no json response format on a model call that carries tool definitions", async () => {
    const s = store();
    const model = new MockLanguageModelV4({ doGenerate: stopWithObject(validPlan) });
    const lead = buildLeadAgent({ store: s, config: baseConfig(), model });

    await runLeadPlan(lead, { topic: "tracing" }, s);

    const withTools = model.doGenerateCalls.filter((call) => (call.tools ?? []).length > 0);
    expect(withTools.length).toBeGreaterThan(0);
    for (const call of withTools) {
      expect(call.responseFormat?.type).not.toBe("json");
    }
  });

  it("shapes the plan with a structured call that carries no tools", async () => {
    const s = store();
    const model = leadModel(stopWithObject(validPlan));
    const lead = buildLeadAgent({
      store: s,
      config: baseConfig(),
      model,
      researcherModels: { small: researchedTracing() },
    });

    const outcome = await runLeadPlan(lead, { topic: "tracing" }, s);

    const shaping = model.doGenerateCalls.filter((call) => call.responseFormat?.type === "json");
    expect(shaping).toHaveLength(1);
    expect(shaping[0]?.tools ?? []).toHaveLength(0);
    expect(outcome.plan).toEqual(validPlan);
  });

  it("puts the research the loop gathered in front of the shaping call", async () => {
    const s = store();
    let callCount = 0;
    const leadModel = new MockLanguageModelV4({
      doGenerate: async () => {
        callCount += 1;
        if (callCount === 1) {
          return toolCallStep("research_subtopic", { subtopic: "tracing basics" }, "call-1");
        }
        return stopWithObject(validPlan);
      },
    });
    const small = findingsModel([{ path: "docs/guides/tracing.md", note: "About tracing." }]);

    const lead = buildLeadAgent({
      store: s,
      config: baseConfig(),
      model: leadModel,
      researcherModels: { small },
    });

    await runLeadPlan(lead, { topic: "tracing" }, s);

    const shaping = leadModel.doGenerateCalls.filter(
      (call) => call.responseFormat?.type === "json",
    );
    expect(shaping).toHaveLength(1);
    const prompt = JSON.stringify(shaping[0]?.prompt);
    expect(prompt).toContain("docs/guides/tracing.md");

    // Only the findings, not the tool-call envelope: handed the envelope, the model cites the
    // toolCallId as if it were a corpus path.
    expect(prompt).not.toContain("call-1");
  });
});

// F1b. The provider sends no `options` block unless providerOptions.ollama.options is set,
// so Ollama applies its default num_ctx of 4096. Tool results from this corpus accumulate
// across sixteen steps and overrun that, which surfaces as done_reason "length" and an
// empty response.
describe("the Ollama context window", () => {
  it("sends num_ctx on every model call the lead makes", async () => {
    const s = store();
    const model = new MockLanguageModelV4({
      doGenerate: stopWithObject({ topic: "tracing", weeks: [], gaps: [] }),
    });
    const config = baseConfig();
    const lead = buildLeadAgent({ store: s, config, model });

    await runLeadPlan(lead, { topic: "tracing" }, s);

    expect(model.doGenerateCalls.length).toBeGreaterThan(0);
    for (const call of model.doGenerateCalls) {
      expect(call.providerOptions?.ollama).toEqual({ options: { num_ctx: config.ollamaNumCtx } });
    }
  });

  it("sends no ollama provider options when the provider is not ollama", async () => {
    const s = store();
    const model = new MockLanguageModelV4({
      doGenerate: stopWithObject({ topic: "tracing", weeks: [], gaps: [] }),
    });
    const lead = buildLeadAgent({
      store: s,
      config: baseConfig({ llmProvider: "anthropic", allowHostedProvider: true }),
      model,
    });

    await runLeadPlan(lead, { topic: "tracing" }, s);

    expect(model.doGenerateCalls.length).toBeGreaterThan(0);
    for (const call of model.doGenerateCalls) {
      expect(call.providerOptions?.ollama).toBeUndefined();
    }
  });
});

// With no response format on the loop, prose alone did not hold the lead to researching
// anything: it would call corpus_map, then check_coverage, then stop. prepareStep requires a
// tool call on the early steps instead, without naming the tool.
describe("the loop is held to calling a tool while nothing has been researched", () => {
  const validPlan = {
    topic: "tracing",
    weeks: [
      {
        subtopic: "tracing basics",
        steps: [
          {
            title: "Read the trace intro",
            path: "docs/guides/tracing.md",
            kind: "doc",
            why: "Establishes the vocabulary.",
          },
        ],
      },
    ],
    gaps: [],
  };

  it("requires a tool call on the first step of the loop", async () => {
    const s = store();
    const model = leadModel(stopWithObject(validPlan));
    const lead = buildLeadAgent({
      store: s,
      config: baseConfig(),
      model,
      researcherModels: { small: researchedTracing() },
    });

    await lead.loop.generate({ prompt: "Topic: tracing" });

    expect(model.doGenerateCalls[0]?.toolChoice).toEqual({ type: "required" });
  });

  it("names no tool, so the lead still chooses between surveying and researching", async () => {
    const s = store();
    const model = leadModel(stopWithObject(validPlan));
    const lead = buildLeadAgent({
      store: s,
      config: baseConfig(),
      model,
      researcherModels: { small: researchedTracing() },
    });

    await lead.loop.generate({ prompt: "Topic: tracing" });

    expect(model.doGenerateCalls[0]?.toolChoice).not.toHaveProperty("toolName");
    expect((model.doGenerateCalls[0]?.tools ?? []).map((tool) => tool.name)).toContain(
      "check_coverage",
    );
  });

  // toolChoice is the provider-agnostic half and the SDK enforces it, but Ollama accepts
  // tool_choice and ignores it, so the instruction override is what moves this model.
  it("tells the model in the step's instructions that it has researched nothing yet", async () => {
    const s = store();
    const model = leadModel(stopWithObject(validPlan));
    const lead = buildLeadAgent({
      store: s,
      config: baseConfig(),
      model,
      researcherModels: { small: researchedTracing() },
    });

    await lead.loop.generate({ prompt: "Topic: tracing" });

    const systemOf = (index: number) =>
      JSON.stringify(
        (model.doGenerateCalls[index]?.prompt ?? []).filter((part) => part.role === "system"),
      );

    expect(systemOf(0)).toContain("have not researched any subtopic yet");
    expect(systemOf(1)).not.toContain("have not researched any subtopic yet");
  });

  it("stops requiring a tool once a subtopic has been researched", async () => {
    const s = store();
    let callCount = 0;
    const leadModel = new MockLanguageModelV4({
      doGenerate: async () => {
        callCount += 1;
        if (callCount === 1) {
          return toolCallStep("research_subtopic", { subtopic: "tracing basics" }, "call-1");
        }
        return stopWithObject(validPlan);
      },
    });
    const small = findingsModel([{ path: "docs/guides/tracing.md", note: "About tracing." }]);

    const lead = buildLeadAgent({
      store: s,
      config: baseConfig(),
      model: leadModel,
      researcherModels: { small },
    });

    await lead.loop.generate({ prompt: "Topic: tracing" });

    expect(leadModel.doGenerateCalls).toHaveLength(2);
    expect(leadModel.doGenerateCalls[0]?.toolChoice).toEqual({ type: "required" });
    expect(leadModel.doGenerateCalls[1]?.toolChoice).not.toEqual({ type: "required" });
  });
});

// A run that researched nothing can still come back "planned", with empty steps and gap
// reasons the shaping call invented, and base14.plan.duration and base14.plan.cost then
// record it as a success. A plan with no steps in any week is not a plan.
describe("runLeadPlan: an empty plan is a failure, not a plan", () => {
  it("reports failed when no week has a single step", async () => {
    const s = store();
    const model = leadModel(
      stopWithObject({
        topic: "tracing",
        weeks: [
          { subtopic: "tracing basics", steps: [] },
          { subtopic: "spans", steps: [] },
        ],
        gaps: [{ term: "spans", reason: "The research findings for this subtopic are empty." }],
      }),
    );
    const lead = buildLeadAgent({
      store: s,
      config: baseConfig(),
      model,
      researcherModels: { small: researchedTracing() },
    });

    const outcome = await runLeadPlan(lead, { topic: "tracing" }, s);

    expect(outcome.status).toBe("failed");
    expect(outcome.plan.weeks).toHaveLength(2);
  });

  it("reports failed when every step was dropped for an invalid citation", async () => {
    const s = store();
    const onlyBadCitations = {
      topic: "tracing",
      weeks: [
        {
          subtopic: "tracing basics",
          steps: [
            {
              title: "Read a bogus doc",
              path: "docs/guides/does-not-exist.md",
              kind: "doc",
              why: "Bad citation.",
            },
          ],
        },
      ],
      gaps: [],
    };
    const model = leadModel(stopWithObject(onlyBadCitations));
    const lead = buildLeadAgent({
      store: s,
      config: baseConfig(),
      model,
      researcherModels: { small: researchedTracing() },
    });

    const outcome = await runLeadPlan(lead, { topic: "tracing" }, s);

    expect(outcome.status).toBe("failed");
    expect(outcome.plan.gaps).toHaveLength(1);
  });

  it("still reports planned when one week has a step", async () => {
    const s = store();
    const model = leadModel(
      stopWithObject({
        topic: "tracing",
        weeks: [
          { subtopic: "spans", steps: [] },
          {
            subtopic: "tracing basics",
            steps: [
              {
                title: "Read the trace intro",
                path: "docs/guides/tracing.md",
                kind: "doc",
                why: "Establishes the vocabulary.",
              },
            ],
          },
        ],
        gaps: [],
      }),
    );
    const lead = buildLeadAgent({
      store: s,
      config: baseConfig(),
      model,
      researcherModels: { small: researchedTracing() },
    });

    const outcome = await runLeadPlan(lead, { topic: "tracing" }, s);

    expect(outcome.status).toBe("planned");
  });

  it("does not accept a week with no subtopic", async () => {
    const s = store();
    const model = leadModel(
      stopWithObject({
        topic: "tracing",
        weeks: [
          {
            subtopic: "",
            steps: [
              {
                title: "Read the trace intro",
                path: "docs/guides/tracing.md",
                kind: "doc",
                why: "Establishes the vocabulary.",
              },
            ],
          },
        ],
        gaps: [],
      }),
    );
    const lead = buildLeadAgent({
      store: s,
      config: baseConfig(),
      model,
      researcherModels: { small: researchedTracing() },
    });

    await expect(runLeadPlan(lead, { topic: "tracing" }, s)).rejects.toThrow(
      /subtopic|weeks|validation|schema/i,
    );
  });
});

// Zero steps is not enough on its own. The lead can spend every nudged step on corpus_map and
// check_coverage, which violates nothing because it is calling tools, then answer in prose
// once the nudge is withdrawn; the shaping call writes steps citing real paths from that
// summary. So the outcome depends on what the loop did, not only on what the shaper wrote.
describe("runLeadPlan: a run that researched nothing is a failure", () => {
  const validPlan = {
    topic: "tracing",
    weeks: [
      {
        subtopic: "tracing basics",
        steps: [
          {
            title: "Read the trace intro",
            path: "docs/guides/tracing.md",
            kind: "doc",
            why: "Establishes the vocabulary.",
          },
        ],
      },
    ],
    gaps: [],
  };

  // Six tool calls, none of them research, then a written answer. Six is NUDGED_STEPS:
  // this is the longest a lead can legally survey before the requirement is withdrawn.
  function surveyOnlyModel(plan: unknown): MockLanguageModelV4 {
    let callCount = 0;
    return new MockLanguageModelV4({
      doGenerate: async () => {
        callCount += 1;
        if (callCount <= 6) {
          return toolCallStep("corpus_map", {}, `call-${callCount}`);
        }
        return stopWithObject(plan);
      },
    });
  }

  it("reports failed when the loop called tools but never researched a subtopic", async () => {
    const s = store();
    const lead = buildLeadAgent({
      store: s,
      config: baseConfig(),
      model: surveyOnlyModel(validPlan),
    });

    const outcome = await runLeadPlan(lead, { topic: "tracing" }, s);

    expect(outcome.status).toBe("failed");
  });

  it("records why it failed, so the metric does not read it as the model's own gap", async () => {
    const s = store();
    const lead = buildLeadAgent({
      store: s,
      config: baseConfig(),
      model: surveyOnlyModel(validPlan),
    });

    const outcome = await runLeadPlan(lead, { topic: "tracing" }, s);

    expect(outcome.plan.gaps.map((gap) => gap.reason)).toContain(SERVICE_GAP_REASONS.no_research);
  });

  // The reviewer's R2 shape: two subtopics researched, four weeks written, two of them
  // gap weeks with no steps. A plan, and it has to stay one.
  it("keeps a plan planned when two subtopics were researched and two weeks are gaps", async () => {
    const s = store();
    const fourWeeks = {
      topic: "tracing",
      weeks: [
        validPlan.weeks[0],
        {
          subtopic: "metrics basics",
          steps: [
            {
              title: "Read the metrics intro",
              path: "docs/guides/metrics.md",
              kind: "doc",
              why: "Counters and gauges.",
            },
          ],
        },
        { subtopic: "sampling", steps: [] },
        { subtopic: "exporters", steps: [] },
      ],
      gaps: [
        { term: "sampling", reason: "The corpus has nothing on sampling." },
        { term: "exporters", reason: "The corpus has nothing on exporters." },
      ],
    };
    let callCount = 0;
    const leadModelTwoSubtopics = new MockLanguageModelV4({
      doGenerate: async () => {
        callCount += 1;
        if (callCount <= 2) {
          return toolCallStep(
            "research_subtopic",
            { subtopic: ["tracing basics", "metrics basics"][callCount - 1] },
            `call-${callCount}`,
          );
        }
        return stopWithObject(fourWeeks);
      },
    });

    const lead = buildLeadAgent({
      store: s,
      config: baseConfig(),
      model: leadModelTwoSubtopics,
      researcherModels: { small: researchedTracing() },
    });

    const outcome = await runLeadPlan(lead, { topic: "tracing" }, s);

    expect(outcome.status).toBe("planned");
    expect(outcome.plan.weeks).toHaveLength(4);
    expect(outcome.plan.gaps).toHaveLength(2);
  });
});

// The tests above pin only that the window is not zero, so narrowing it to one step leaves the
// suite green while the lead is free to answer in prose from its second step on. These pin
// both edges: the sixth step is still required to call a tool, the seventh is not.
describe("the nudge window is six steps wide", () => {
  const validPlan = {
    topic: "tracing",
    weeks: [
      {
        subtopic: "tracing basics",
        steps: [
          {
            title: "Read the trace intro",
            path: "docs/guides/tracing.md",
            kind: "doc",
            why: "Establishes the vocabulary.",
          },
        ],
      },
    ],
    gaps: [],
  };

  // Calls corpus_map for the first `surveys` steps, none of them research, then answers in
  // prose. The step the prose lands on is the one the window is being tested at.
  function surveyThenAnswer(surveys: number): MockLanguageModelV4 {
    let callCount = 0;
    return new MockLanguageModelV4({
      doGenerate: async () => {
        callCount += 1;
        if (callCount <= surveys) {
          return toolCallStep("corpus_map", {}, `call-${callCount}`);
        }
        return stopWithObject(validPlan);
      },
    });
  }

  function leadWith(model: MockLanguageModelV4) {
    const s = store();
    return {
      s,
      lead: buildLeadAgent({ store: s, config: baseConfig(), model }),
    };
  }

  it("still requires a tool call on the sixth step", async () => {
    const { s, lead } = leadWith(surveyThenAnswer(5));

    await expect(lead.loop.generate({ prompt: "Topic: tracing" })).rejects.toThrow(
      /did not contain a tool call/,
    );
    expect((await runLeadPlan(lead, { topic: "tracing" }, s)).plan.gaps[0]?.reason).toBe(
      SERVICE_GAP_REASONS.no_tool_call,
    );
  });

  it("withdraws the requirement on the seventh step", async () => {
    const { lead } = leadWith(surveyThenAnswer(6));

    const result = await lead.loop.generate({ prompt: "Topic: tracing" });

    expect(result.steps).toHaveLength(7);
  });

  it("carries the nudge in the instructions on every step of the window", async () => {
    const model = surveyThenAnswer(6);
    const { lead } = leadWith(model);

    await lead.loop.generate({ prompt: "Topic: tracing" });

    const systemOf = (index: number) =>
      JSON.stringify(
        (model.doGenerateCalls[index]?.prompt ?? []).filter((part) => part.role === "system"),
      );

    for (const index of [0, 1, 2, 3, 4, 5]) {
      expect(systemOf(index)).toContain("have not researched any subtopic yet");
    }
    expect(systemOf(6)).not.toContain("have not researched any subtopic yet");
  });
});
