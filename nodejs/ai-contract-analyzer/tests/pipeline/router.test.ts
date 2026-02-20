import { describe, expect, it, vi } from "vitest";

vi.mock("@ai-sdk/anthropic", () => ({
  anthropic: vi.fn().mockReturnValue("mock-haiku-model"),
}));

vi.mock("ai", () => ({
  generateObject: vi.fn().mockResolvedValue({
    object: {
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
    const { generateObject } = await import("ai");
    const longText = "x".repeat(10_000);

    await routeDocument(longText);

    const call = vi.mocked(generateObject).mock.calls.at(-1)?.[0] as { prompt: string };
    expect(call.prompt.length).toBe(3000);
  });

  it("uses haiku model for cost efficiency", async () => {
    const { anthropic } = await import("@ai-sdk/anthropic");

    await routeDocument("contract text");

    expect(vi.mocked(anthropic)).toHaveBeenCalledWith("claude-haiku-4-5-20251001");
  });
});
