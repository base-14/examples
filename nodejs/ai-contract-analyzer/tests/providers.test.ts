import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";
import { MODEL_PRICING, modelPricing } from "../src/llm/pricing.ts";

describe("MODEL_PRICING", () => {
  it("is loaded from _shared/pricing.json, not an inline dict", () => {
    expect(MODEL_PRICING["gpt-4o"]).toBeDefined();
    expect(MODEL_PRICING["gpt-4o"]?.input).toBeCloseTo(2.5);
    expect(MODEL_PRICING["gpt-4o"]?.output).toBeCloseTo(10.0);
  });

  it("covers all models in _shared/pricing.json", () => {
    const sharedPath = new URL("../../../_shared/pricing.json", import.meta.url).pathname;
    const shared = JSON.parse(readFileSync(sharedPath, "utf-8")) as {
      models: Record<string, { input: number; output: number }>;
    };
    for (const modelId of Object.keys(shared.models)) {
      expect(MODEL_PRICING[modelId]).toBeDefined();
    }
  });
});

describe("modelPricing", () => {
  it("normalises a dated model id to its pricing.json key", () => {
    expect(modelPricing("claude-sonnet-4-20250514")).toEqual({
      inputCostPerMToken: 3,
      outputCostPerMToken: 15,
    });
  });

  it("prices an unknown model at zero", () => {
    expect(modelPricing("qwen3.5:9B")).toEqual({
      inputCostPerMToken: 0,
      outputCostPerMToken: 0,
    });
  });
});
