import { describe, expect, it } from "vitest";
import type { Config } from "../../src/config.ts";
import { ALL_TOOL_NAMES, activeToolsFor } from "../../src/tools/catalogue.ts";

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

describe("activeToolsFor", () => {
  it("gives the lead its four tools in deferred mode", () => {
    const config = baseConfig({ toolCatalogue: "deferred" });

    expect(activeToolsFor("lead", config).sort()).toEqual(
      ["corpus_map", "check_coverage", "get_related", "research_subtopic"].sort(),
    );
  });

  it("gives the researcher its five tools in deferred mode", () => {
    const config = baseConfig({ toolCatalogue: "deferred" });

    expect(activeToolsFor("researcher", config).sort()).toEqual(
      ["search_docs", "outline", "fetch_section", "list_examples", "fetch_example_file"].sort(),
    );
  });

  // The lever this example measures: deferred has to send each role strictly fewer tool
  // definitions than full, or there is no difference to measure. The exact counts are
  // pinned above; this pins the relationship between the two modes.
  it("sends each role fewer tools in deferred mode than in full", () => {
    const deferred = baseConfig({ toolCatalogue: "deferred" });
    const full = baseConfig({ toolCatalogue: "full" });

    expect(activeToolsFor("lead", deferred).length).toBeLessThan(
      activeToolsFor("lead", full).length,
    );
    expect(activeToolsFor("researcher", deferred).length).toBeLessThan(
      activeToolsFor("researcher", full).length,
    );
  });

  it("gives the lead all nine tools when TOOL_CATALOGUE is full", () => {
    const config = baseConfig({ toolCatalogue: "full" });

    expect(activeToolsFor("lead", config).sort()).toEqual([...ALL_TOOL_NAMES].sort());
    expect(activeToolsFor("lead", config)).toHaveLength(9);
  });

  it("gives the researcher all nine tools when TOOL_CATALOGUE is full", () => {
    const config = baseConfig({ toolCatalogue: "full" });

    expect(activeToolsFor("researcher", config).sort()).toEqual([...ALL_TOOL_NAMES].sort());
    expect(activeToolsFor("researcher", config)).toHaveLength(9);
  });

  it("has nine distinct names in the catalogue with no overlap between roles", () => {
    expect(ALL_TOOL_NAMES).toHaveLength(9);
    expect(new Set(ALL_TOOL_NAMES).size).toBe(9);
  });
});
