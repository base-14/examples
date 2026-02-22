import { readFileSync } from "node:fs";
import { describe, expect, it, vi } from "vitest";

// Mock config to avoid Bun.env dependency — providers.ts imports config at module level
vi.mock("../src/config.ts", () => ({
  config: {
    llmProvider: "anthropic",
    embeddingProvider: "openai",
    ollamaBaseUrl: "http://localhost:11434",
    llmModelCapable: undefined,
    llmModelFast: undefined,
    embeddingModel: undefined,
  },
}));

// Also mock the AI SDK providers to avoid network/key requirements
vi.mock("@ai-sdk/anthropic", () => ({ anthropic: vi.fn(() => ({})) }));
vi.mock("@ai-sdk/google", () => ({ google: vi.fn(() => ({})) }));
vi.mock("@ai-sdk/openai", () => ({
  openai: { embedding: vi.fn(() => ({})) },
  createOpenAI: vi.fn(() => ({ embedding: vi.fn(() => ({})) })),
}));
vi.mock("ollama-ai-provider", () => ({ createOllama: vi.fn(() => () => ({})) }));
vi.mock("ai", () => ({
  wrapEmbeddingModel: vi.fn((x) => x.model),
  defaultEmbeddingSettingsMiddleware: vi.fn(() => ({})),
}));

import { MODEL_PRICING } from "../src/providers.ts";

describe("MODEL_PRICING", () => {
  it("is loaded from _shared/pricing.json, not an inline dict", () => {
    expect(MODEL_PRICING["gpt-4o"]).toBeDefined();
    expect(MODEL_PRICING["gpt-4o"].input).toBeCloseTo(2.5);
    expect(MODEL_PRICING["gpt-4o"].output).toBeCloseTo(10.0);
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
