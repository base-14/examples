import { describe, expect, it, vi } from "vitest";

vi.mock("ai", () => ({
  embedMany: vi.fn().mockResolvedValue({
    embeddings: [[0.1, 0.2, 0.3]],
    usage: { tokens: 10 },
  }),
}));

vi.mock("../../src/providers.ts", () => ({
  getEmbeddingModel: vi.fn().mockReturnValue({
    modelId: "mock-embedding-model",
    model: "mock-embedding-model",
    dimensions: 768,
    costPerMToken: 0.02,
    target: { semconvName: "openai", serverAddress: "api.openai.com", serverPort: 443 },
  }),
}));

import { embedMany } from "ai";
import { embedValues } from "../../src/llm/embeddings.ts";
import { findSpan, histogramBoundaries, metricCount } from "../telemetry.ts";

const ATTRS = {
  "gen_ai.operation.name": "embeddings",
  "gen_ai.provider.name": "openai",
  "gen_ai.request.model": "mock-embedding-model",
};

describe("embedValues", () => {
  it("records operation duration and keeps token counts on the span only", async () => {
    await embedValues(["hello"]);

    expect(
      findSpan("embeddings mock-embedding-model").attributes["gen_ai.usage.input_tokens"],
    ).toBe(10);
    expect(await metricCount("gen_ai.client.operation.duration", ATTRS)).toBe(1);
    expect(await metricCount("gen_ai.client.inference.duration", {})).toBe(0);
    expect(await metricCount("gen_ai.client.inference.operation.input_tokens", {})).toBe(0);
    expect(await metricCount("gen_ai.client.token.usage", {})).toBe(0);
    expect(await histogramBoundaries("gen_ai.client.operation.duration")).toEqual([
      0.01, 0.02, 0.04, 0.08, 0.16, 0.32, 0.64, 1.28, 2.56, 5.12, 10.24, 20.48, 40.96, 81.92,
    ]);
  });

  it("records the failed operation duration with error.type", async () => {
    vi.mocked(embedMany).mockRejectedValueOnce(new TypeError("boom"));

    await expect(embedValues(["hello"])).rejects.toThrow("boom");

    expect(
      await metricCount("gen_ai.client.operation.duration", {
        ...ATTRS,
        "error.type": "TypeError",
      }),
    ).toBe(1);
  });
});
