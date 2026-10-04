import type {
  LanguageModelV4CallOptions,
  LanguageModelV4GenerateResult,
  LanguageModelV4StreamPart,
  LanguageModelV4Usage,
} from "@ai-sdk/provider";
import { convertArrayToReadableStream, MockLanguageModelV4 } from "ai/test";
import { describe, expect, it } from "vitest";
import { LEAD_NUDGE, runLeadPlan } from "../../src/agents/lead.ts";
import { buildMastraLeadAgent } from "../../src/agents/mastra.ts";
import type { Config } from "../../src/config.ts";
import type { CorpusArtifact } from "../../src/corpus/index-build.ts";
import { CorpusStore } from "../../src/corpus/store.ts";
import { SERVICE_GAP_REASONS } from "../../src/plans/schema.ts";
import { PlanStore } from "../../src/plans/store.ts";
import { plansRoutes } from "../../src/routes/plans.ts";

function baseConfig(overrides: Partial<Config> = {}): Config {
  return {
    port: 3000,
    llmProvider: "ollama",
    plannerFramework: "mastra",
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
  ],
  sections: [
    {
      path: "docs/guides/tracing.md",
      heading: "What is a trace",
      text: "A trace represents the end-to-end journey of a single request.",
    },
  ],
};

function usage(input: number, output: number): LanguageModelV4Usage {
  return {
    inputTokens: { total: input, noCache: input, cacheRead: 0, cacheWrite: 0 },
    outputTokens: { total: output, text: output, reasoning: 0 },
  };
}

function stopWithText(text: string): LanguageModelV4GenerateResult {
  return {
    content: [{ type: "text", text }],
    finishReason: { unified: "stop", raw: "stop" },
    usage: usage(20, 20),
  };
}

function toolCallStep(toolName: string, input: unknown): LanguageModelV4GenerateResult {
  return {
    content: [
      { type: "tool-call", toolCallId: `call-${toolName}`, toolName, input: JSON.stringify(input) },
    ],
    finishReason: { unified: "tool-calls", raw: "tool_calls" },
    usage: usage(20, 5),
  };
}

function streamPartsOf(result: LanguageModelV4GenerateResult): LanguageModelV4StreamPart[] {
  const parts: LanguageModelV4StreamPart[] = [{ type: "stream-start", warnings: [] }];
  for (const content of result.content) {
    if (content.type === "text") {
      parts.push(
        { type: "text-start", id: "text" },
        { type: "text-delta", id: "text", delta: content.text },
        { type: "text-end", id: "text" },
      );
    } else if (content.type === "tool-call") {
      parts.push(content);
    }
  }
  parts.push({ type: "finish", finishReason: result.finishReason, usage: result.usage });
  return parts;
}

// Mastra may call a model through doGenerate or doStream, so the script answers both and
// records every call's options in order. The last response repeats once the list runs out.
function scriptedModel(...responses: LanguageModelV4GenerateResult[]) {
  const calls: LanguageModelV4CallOptions[] = [];
  const next = (options: LanguageModelV4CallOptions): LanguageModelV4GenerateResult => {
    calls.push(options);
    return responses[
      Math.min(calls.length - 1, responses.length - 1)
    ] as LanguageModelV4GenerateResult;
  };
  const model = new MockLanguageModelV4({
    doGenerate: async (options) => next(options),
    doStream: async (options) => ({
      stream: convertArrayToReadableStream(streamPartsOf(next(options))),
    }),
  });
  return { model, calls };
}

const PLAN = {
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

const FINDINGS = {
  subtopic: "tracing basics",
  findings: [
    { path: "docs/guides/tracing.md", heading: "What is a trace", note: "Defines a trace." },
  ],
};

function leadScript() {
  return scriptedModel(
    toolCallStep("research_subtopic", { subtopic: "tracing basics" }),
    stopWithText("tracing basics: docs/guides/tracing.md"),
    stopWithText(JSON.stringify(PLAN)),
  );
}

function researcherScript() {
  return scriptedModel(
    toolCallStep("fetch_section", { path: "docs/guides/tracing.md", heading: "What is a trace" }),
    stopWithText("docs/guides/tracing.md, What is a trace: defines a trace."),
    stopWithText(JSON.stringify(FINDINGS)),
  );
}

function systemText(options: LanguageModelV4CallOptions): string {
  return options.prompt
    .filter((message) => message.role === "system")
    .map((message) => (typeof message.content === "string" ? message.content : ""))
    .join("\n");
}

function promptText(options: LanguageModelV4CallOptions): string {
  return JSON.stringify(options.prompt);
}

async function runPlan(config: Config = baseConfig()) {
  const store = new CorpusStore(artifact);
  const lead = leadScript();
  const researcher = researcherScript();
  const agent = buildMastraLeadAgent({
    store,
    config,
    model: lead.model,
    researcherModels: { small: researcher.model, large: researcher.model },
  });
  const outcome = await runLeadPlan(agent, { topic: "tracing" }, store);
  return { outcome, lead, researcher };
}

describe("the Mastra lead plans through the same runner", () => {
  it("returns a planned outcome whose step cites what the researcher read", async () => {
    const { outcome } = await runPlan();

    expect(outcome.status).toBe("planned");
    expect(outcome.plan.weeks[0]?.steps[0]?.path).toBe("docs/guides/tracing.md");
    expect(outcome.plan.gaps).toEqual([]);
  });

  it("puts the researcher's findings in front of the plan shaping call", async () => {
    const { lead } = await runPlan();

    const shaping = lead.calls.at(-1) as LanguageModelV4CallOptions;
    expect(promptText(shaping)).toContain("Defines a trace.");
  });

  it("puts the documents the researcher opened in front of its findings call", async () => {
    const { researcher } = await runPlan();

    const findings = researcher.calls.at(-1) as LanguageModelV4CallOptions;
    expect(promptText(findings)).toContain("docs/guides/tracing.md");
    expect(promptText(findings)).toContain("What is a trace");
  });
});

describe("the Mastra tool loop and the structured call are separate model calls", () => {
  it("sends tools and no json response format on the loop, and the reverse on the shaping call", async () => {
    const { lead } = await runPlan();

    const loopCall = lead.calls[0] as LanguageModelV4CallOptions;
    const shaping = lead.calls.at(-1) as LanguageModelV4CallOptions;

    expect(loopCall.tools?.length).toBeGreaterThan(0);
    expect(loopCall.responseFormat?.type).not.toBe("json");
    expect(shaping.responseFormat?.type).toBe("json");
    expect(shaping.tools ?? []).toEqual([]);
  });

  it("gives the lead only its own four tools under the deferred catalogue", async () => {
    const { lead } = await runPlan();

    const names = (lead.calls[0]?.tools ?? []).map((tool) => tool.name).sort();
    expect(names).toEqual(["check_coverage", "corpus_map", "get_related", "research_subtopic"]);
  });
});

describe("the Ollama context window under Mastra", () => {
  it("sends num_ctx on every model call the lead and the researcher make", async () => {
    const { lead, researcher } = await runPlan(baseConfig({ ollamaNumCtx: 12345 }));

    for (const call of [...lead.calls, ...researcher.calls]) {
      expect(call.providerOptions?.ollama).toEqual({ options: { num_ctx: 12345 } });
    }
  });
});

describe("the Mastra lead is nudged while nothing has been researched", () => {
  it("requires a tool call and says so on the first step, and stops once it has researched", async () => {
    const { lead } = await runPlan();

    const first = lead.calls[0] as LanguageModelV4CallOptions;
    const afterResearch = lead.calls[1] as LanguageModelV4CallOptions;

    expect(first.toolChoice).toEqual({ type: "required" });
    expect(systemText(first)).toContain(LEAD_NUDGE);
    expect(afterResearch.toolChoice).not.toEqual({ type: "required" });
    expect(systemText(afterResearch)).not.toContain(LEAD_NUDGE);
  });
});

describe("the Mastra researcher under the full catalogue", () => {
  it("carries all nine tool definitions, as the tool definition metric counts them", async () => {
    const { researcher } = await runPlan(baseConfig({ toolCatalogue: "full" }));

    const names = (researcher.calls[0]?.tools ?? []).map((tool) => tool.name);
    expect(names).toHaveLength(9);
    expect(names).toContain("research_subtopic");
  });

  it("carries only its own five under the deferred catalogue", async () => {
    const { researcher } = await runPlan();

    const names = (researcher.calls[0]?.tools ?? []).map((tool) => tool.name).sort();
    expect(names).toEqual([
      "fetch_example_file",
      "fetch_section",
      "list_examples",
      "outline",
      "search_docs",
    ]);
  });
});

describe("a Mastra lead that answers in prose while required to call a tool", () => {
  it("fails the run with the no_tool_call gap and makes no shaping call", async () => {
    const store = new CorpusStore(artifact);
    const lead = scriptedModel(stopWithText("Tracing is about following a request."));
    const agent = buildMastraLeadAgent({ store, config: baseConfig(), model: lead.model });

    const outcome = await runLeadPlan(agent, { topic: "tracing" }, store);

    expect(outcome.status).toBe("failed");
    expect(outcome.plan.gaps).toEqual([
      { term: "tracing", reason: SERVICE_GAP_REASONS.no_tool_call },
    ]);
    expect(lead.calls).toHaveLength(1);
  });
});

describe("POST /plans with PLANNER_FRAMEWORK=mastra", () => {
  it("runs the plan on the Mastra agents and ends planned", async () => {
    const lead = leadScript();
    const researcher = researcherScript();
    const app = plansRoutes({
      store: new CorpusStore(artifact),
      config: baseConfig(),
      plans: new PlanStore(),
      model: lead.model,
      researcherModels: { small: researcher.model, large: researcher.model },
    });

    const response = await app.request("/plans", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ topic: "tracing" }),
    });
    const lines = (await response.text())
      .trim()
      .split("\n")
      .map((line) => JSON.parse(line) as { event: string; status?: string });

    expect(response.status).toBe(200);
    expect(lines.at(-1)).toMatchObject({ event: "plan", status: "planned" });
    expect(lead.calls.length).toBeGreaterThan(0);
  });
});
