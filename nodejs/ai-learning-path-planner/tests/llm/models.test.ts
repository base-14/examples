import { describe, expect, it } from "vitest";
import type { Config } from "../../src/config.ts";
import { selectModel } from "../../src/llm/models.ts";

function selectedModelId(tier: "small" | "large", config: Config): string {
  const model = selectModel(tier, config) as { modelId: string };
  return model.modelId;
}

function selectedProvider(tier: "small" | "large", config: Config): string {
  const model = selectModel(tier, config) as { provider: string };
  return model.provider;
}

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

describe("selectModel", () => {
  it("throws when LLM_PROVIDER is openai and ALLOW_HOSTED_PROVIDER is unset", () => {
    const config = baseConfig({ llmProvider: "openai", allowHostedProvider: false });

    expect(() => selectModel("small", config)).toThrow(/ALLOW_HOSTED_PROVIDER/);
  });

  it("throws when LLM_PROVIDER is anthropic and ALLOW_HOSTED_PROVIDER is unset", () => {
    const config = baseConfig({ llmProvider: "anthropic", allowHostedProvider: false });

    expect(() => selectModel("large", config)).toThrow(/ALLOW_HOSTED_PROVIDER/);
  });

  it("returns an Ollama model for the small tier by default", () => {
    const config = baseConfig();

    expect(selectedModelId("small", config)).toBe("gemma4:e2b");
    expect(selectedProvider("small", config)).toContain("ollama");
  });

  it("returns an Ollama model for the large tier by default", () => {
    const config = baseConfig();

    expect(selectedModelId("large", config)).toBe("qwen3.5:9B");
    expect(selectedProvider("large", config)).toContain("ollama");
  });

  it("never gates the ollama provider on ALLOW_HOSTED_PROVIDER", () => {
    const config = baseConfig({ llmProvider: "ollama", allowHostedProvider: false });

    expect(() => selectModel("small", config)).not.toThrow();
  });
});
