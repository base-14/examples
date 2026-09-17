import type { LanguageModelV4GenerateResult, LanguageModelV4Usage } from "@ai-sdk/provider";
import { MockLanguageModelV4 } from "ai/test";
import { describe, expect, it } from "vitest";
import { buildResearcherAgent } from "../../src/agents/researcher.ts";
import type { Config } from "../../src/config.ts";
import type { CorpusArtifact } from "../../src/corpus/index-build.ts";
import { CorpusStore } from "../../src/corpus/store.ts";
import { ALL_TOOL_NAMES, RESEARCHER_TOOL_NAMES } from "../../src/tools/catalogue.ts";

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

function storeWithTracing(): CorpusStore {
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
  return new CorpusStore(artifact);
}

describe("buildResearcherAgent", () => {
  it("always builds all nine tool definitions, regardless of TOOL_CATALOGUE", () => {
    const build = (toolCatalogue: "deferred" | "full") =>
      buildResearcherAgent({
        store: {} as never,
        config: baseConfig({ toolCatalogue }),
        subtopic: "tracing",
        tier: "small",
        model: new MockLanguageModelV4({
          doGenerate: stopWithObject({ subtopic: "x", findings: [] }),
        }),
      });

    expect(Object.keys(build("deferred").tools).sort()).toEqual([...ALL_TOOL_NAMES].sort());
    expect(Object.keys(build("full").tools).sort()).toEqual([...ALL_TOOL_NAMES].sort());
  });

  it("sends only the five researcher tool definitions to the model in deferred mode", async () => {
    const model = new MockLanguageModelV4({
      doGenerate: stopWithObject({ subtopic: "x", findings: [] }),
    });
    const agent = buildResearcherAgent({
      store: {} as never,
      config: baseConfig({ toolCatalogue: "deferred" }),
      subtopic: "tracing",
      tier: "small",
      model,
    });

    await agent.generate({ prompt: "Subtopic: tracing" });

    const sentNames = (model.doGenerateCalls[0]?.tools ?? []).map((t) => t.name).sort();
    expect(sentNames).toEqual([...RESEARCHER_TOOL_NAMES].sort());
  });

  it("sends all nine tool definitions to the model when TOOL_CATALOGUE is full", async () => {
    const model = new MockLanguageModelV4({
      doGenerate: stopWithObject({ subtopic: "x", findings: [] }),
    });
    const agent = buildResearcherAgent({
      store: {} as never,
      config: baseConfig({ toolCatalogue: "full" }),
      subtopic: "tracing",
      tier: "small",
      model,
    });

    await agent.generate({ prompt: "Subtopic: tracing" });

    const sentNames = (model.doGenerateCalls[0]?.tools ?? []).map((t) => t.name).sort();
    expect(sentNames).toEqual([...ALL_TOOL_NAMES].sort());
  });

  it("returns the model's structured findings through result.output", async () => {
    const fixed = {
      subtopic: "tracing",
      findings: [
        { path: "docs/guides/tracing.md", heading: "What is a trace", note: "Defines a trace." },
      ],
    };
    const model = new MockLanguageModelV4({ doGenerate: stopWithObject(fixed) });
    const agent = buildResearcherAgent({
      store: {} as never,
      config: baseConfig(),
      subtopic: "tracing",
      tier: "small",
      model,
    });

    const result = await agent.generate({ prompt: "Subtopic: tracing" });

    expect(result.output).toEqual(fixed);
  });

  it("selects a model through selectModel when no model override is given", () => {
    const config = baseConfig({ llmProvider: "anthropic", allowHostedProvider: false });

    expect(() =>
      buildResearcherAgent({
        store: {} as never,
        config,
        subtopic: "tracing",
        tier: "small",
      }),
    ).toThrow(/ALLOW_HOSTED_PROVIDER/);
  });
});

// The same split, on the other half of the fan-out: a researcher runs Output.object over a
// tool loop too, so the same `format` grammar would sit in front of its five corpus tools and
// it would report findings having read nothing.
describe("the researcher's tool loop and its findings schema are separate model calls", () => {
  const findings = {
    subtopic: "tracing",
    findings: [{ path: "docs/guides/tracing.md", note: "Defines a trace." }],
  };

  it("sends no json response format on a model call that carries tool definitions", async () => {
    const model = new MockLanguageModelV4({ doGenerate: stopWithObject(findings) });
    const agent = buildResearcherAgent({
      store: {} as never,
      config: baseConfig(),
      subtopic: "tracing",
      tier: "small",
      model,
    });

    await agent.generate({ prompt: "Subtopic: tracing" });

    const withTools = model.doGenerateCalls.filter((call) => (call.tools ?? []).length > 0);
    expect(withTools.length).toBeGreaterThan(0);
    for (const call of withTools) {
      expect(call.responseFormat?.type).not.toBe("json");
    }
  });

  it("reports the findings from a structured call that carries no tools", async () => {
    const model = new MockLanguageModelV4({ doGenerate: stopWithObject(findings) });
    const agent = buildResearcherAgent({
      store: {} as never,
      config: baseConfig(),
      subtopic: "tracing",
      tier: "small",
      model,
    });

    const result = await agent.generate({ prompt: "Subtopic: tracing" });

    const shaping = model.doGenerateCalls.filter((call) => call.responseFormat?.type === "json");
    expect(shaping).toHaveLength(1);
    expect(shaping[0]?.tools ?? []).toHaveLength(0);
    expect(result.output).toEqual(findings);
  });

  // The loop's prose does not reliably name the paths it read, so a shaping call given only
  // that prose invents citations, every finding fails validateCitation, and the subtopic
  // escalates and comes back as a gap.
  it("names the documents the loop opened in the shaping call", async () => {
    let calls = 0;
    const model = new MockLanguageModelV4({
      doGenerate: async () => {
        calls += 1;
        if (calls === 1) {
          return {
            content: [
              {
                type: "tool-call" as const,
                toolCallId: "call-1",
                toolName: "fetch_section",
                input: JSON.stringify({
                  path: "docs/guides/tracing.md",
                  heading: "What is a trace",
                }),
              },
            ],
            finishReason: { unified: "tool-calls" as const, raw: "tool_calls" },
            usage: usage(20, 5),
          };
        }
        return stopWithObject(findings);
      },
    });
    const agent = buildResearcherAgent({
      store: storeWithTracing(),
      config: baseConfig(),
      subtopic: "tracing",
      tier: "small",
      model,
    });

    await agent.generate({ prompt: "Subtopic: tracing" });

    const shaping = model.doGenerateCalls.filter((call) => call.responseFormat?.type === "json");
    expect(shaping).toHaveLength(1);
    const prompt = JSON.stringify(shaping[0]?.prompt);
    expect(prompt).toContain("docs/guides/tracing.md");
    expect(prompt).toContain("What is a trace");
    expect(prompt).not.toContain("call-1");
  });

  it("sends num_ctx on every model call it makes", async () => {
    const model = new MockLanguageModelV4({ doGenerate: stopWithObject(findings) });
    const config = baseConfig();
    const agent = buildResearcherAgent({
      store: {} as never,
      config,
      subtopic: "tracing",
      tier: "small",
      model,
    });

    await agent.generate({ prompt: "Subtopic: tracing" });

    expect(model.doGenerateCalls.length).toBeGreaterThan(0);
    for (const call of model.doGenerateCalls) {
      expect(call.providerOptions?.ollama).toEqual({ options: { num_ctx: config.ollamaNumCtx } });
    }
  });
});
