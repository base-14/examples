import { describe, expect, it, vi } from "vitest";

vi.mock("../../src/providers.ts", () => ({
  getFastModel: vi.fn().mockReturnValue({
    model: "mock-fast-model",
    inputCostPerMToken: 0.8,
    outputCostPerMToken: 4,
  }),
}));

vi.mock("ai", () => ({
  Output: { object: (opts: unknown) => opts },
  generateText: vi.fn().mockResolvedValue({
    output: {
      document_type: "nda",
      complexity: "standard",
      requires_full_analysis: true,
    },
    usage: { inputTokens: 500, outputTokens: 30 },
  }),
}));

import { routeDocument } from "../../src/pipeline/route.ts";

describe("routeDocument", () => {
  it("returns route result with document_type, complexity, and cost", async () => {
    const result = await routeDocument("This Non-Disclosure Agreement is entered into...");

    expect(result.document_type).toBe("nda");
    expect(result.complexity).toBe("standard");
    expect(result.requires_full_analysis).toBe(true);
    expect(result.input_tokens).toBe(500);
    expect(result.cost_usd).toBeGreaterThan(0);
  });

  it("only passes the first 3000 chars to the model", async () => {
    const { generateText } = await import("ai");
    const longText = "x".repeat(10_000);

    await routeDocument(longText);

    const call = vi.mocked(generateText).mock.calls.at(-1)?.[0] as { prompt: string };
    expect(call.prompt.length).toBe(3000);
  });

  it("uses fast model for cost efficiency", async () => {
    const { getFastModel } = await import("../../src/providers.ts");

    await routeDocument("contract text");

    expect(vi.mocked(getFastModel)).toHaveBeenCalled();
  });
});
