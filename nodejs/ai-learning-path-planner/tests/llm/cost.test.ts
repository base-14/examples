import type { LanguageModelUsage } from "ai";
import { describe, expect, it } from "vitest";
import type { Config } from "../../src/config.ts";
import { loadConfig } from "../../src/config.ts";
import { assertPriceModelIsKnown, costOf } from "../../src/llm/cost.ts";

function usage(overrides: Partial<LanguageModelUsage> = {}): LanguageModelUsage {
  return {
    inputTokens: 0,
    inputTokenDetails: { noCacheTokens: 0, cacheReadTokens: 0, cacheWriteTokens: 0 },
    outputTokens: 0,
    outputTokenDetails: { textTokens: 0, reasoningTokens: 0 },
    totalTokens: 0,
    ...overrides,
  };
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

describe("costOf", () => {
  it("computes real cost for a model that has its own price row, not simulated", () => {
    const config = baseConfig();
    const result = costOf(
      usage({ inputTokens: 1_000_000, outputTokens: 1_000_000 }),
      "gpt-4o",
      config,
    );

    // gpt-4o: input 2.5, output 10 per million tokens.
    expect(result.usd).toBeCloseTo(12.5, 10);
    expect(result.simulated).toBe(false);
  });

  it("marks simulated true when the price row is borrowed for a local model", () => {
    const config = baseConfig({ priceModel: "gpt-4o" });
    const result = costOf(
      usage({ inputTokens: 1_000_000, outputTokens: 1_000_000 }),
      "gemma4:e2b",
      config,
    );

    expect(result.usd).toBeCloseTo(12.5, 10);
    expect(result.simulated).toBe(true);
  });

  it("returns zero cost with simulated true and no throw when PRICE_MODEL is unset on a local model", () => {
    const config = baseConfig();
    const result = costOf(
      usage({ inputTokens: 1_000_000, outputTokens: 1_000_000 }),
      "gemma4:e2b",
      config,
    );

    expect(result.usd).toBe(0);
    expect(result.simulated).toBe(true);
  });

  it("applies the cached_input rate to cacheReadTokens when the price row carries one", () => {
    const config = baseConfig();
    // gpt-5.6-sol: input 5, output 30, cached_input 0.5 per million tokens.
    const result = costOf(
      usage({
        inputTokens: 1_000_000,
        inputTokenDetails: { noCacheTokens: 0, cacheReadTokens: 1_000_000, cacheWriteTokens: 0 },
        outputTokens: 0,
      }),
      "gpt-5.6-sol",
      config,
    );

    expect(result.usd).toBeCloseTo(0.5, 10);
    expect(result.simulated).toBe(false);
  });

  it("bills cached tokens at the plain input rate when the price row carries no cached tier", () => {
    const config = baseConfig();
    // gpt-5.5-pro: input 30, output 180, no cached_input row.
    const result = costOf(
      usage({
        inputTokens: 1_000_000,
        inputTokenDetails: { noCacheTokens: 0, cacheReadTokens: 1_000_000, cacheWriteTokens: 0 },
        outputTokens: 0,
      }),
      "gpt-5.5-pro",
      config,
    );

    // Every input token was a cache read, so the whole cost is the cached tokens
    // billed at the plain input rate. A fallback of zero would make this free.
    expect(result.usd).toBeCloseTo(30, 10);
    expect(result.simulated).toBe(false);
  });

  it("throws when PRICE_MODEL names a model id that is not in the pricing table", () => {
    const config = baseConfig({ priceModel: "not-a-real-model" });

    expect(() => costOf(usage(), "gemma4:e2b", config)).toThrow(/not-a-real-model/);
  });
});

// Over the configuration the repo ships rather than a literal: an empty PRICE_MODEL must not
// throw at boot, and must not leave every run reporting a cost of zero.
describe("the shipped configuration", () => {
  it("prices a local model's tokens above zero, and says the price is simulated", () => {
    const result = costOf(
      usage({ inputTokens: 100_000, outputTokens: 10_000 }),
      "qwen3.5:9B",
      loadConfig({}),
    );

    expect(result.usd).toBeGreaterThan(0);
    expect(result.simulated).toBe(true);
  });

  it("does not throw at boot on PRICE_MODEL=, the value compose.yaml ships", () => {
    expect(() => assertPriceModelIsKnown(loadConfig({ PRICE_MODEL: "" }))).not.toThrow();
  });

  it("names a price model that is a real row in _shared/pricing.json", () => {
    expect(() => assertPriceModelIsKnown(loadConfig({}))).not.toThrow();
  });
});
