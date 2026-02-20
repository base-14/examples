import { describe, expect, it, vi } from "vitest";

vi.mock("ai", () => ({
  generateObject: vi.fn().mockResolvedValue({
    object: {
      clauses: [
        {
          clause_type: "non_disclosure",
          present: true,
          text_excerpt: "shall keep confidential all proprietary information",
          page_number: 2,
          confidence: 0.95,
          notes: "",
        },
        {
          clause_type: "governing_law",
          present: true,
          text_excerpt: "governed by the laws of the State of Delaware",
          page_number: 8,
          confidence: 0.99,
          notes: "",
        },
        {
          clause_type: "liability_cap",
          present: false,
          text_excerpt: "",
          page_number: 0,
          confidence: 0,
          notes: "",
        },
      ],
      parties: [
        { name: "Acme Corp", role: "party_a" },
        { name: "Beta LLC", role: "party_b" },
      ],
      effective_date: "2025-01-01",
      expiration_date: "2026-01-01",
      governing_law: "Delaware",
      contract_type: "nda",
    },
    usage: { inputTokens: 25000, outputTokens: 4000 },
  }),
}));

vi.mock("@ai-sdk/anthropic", () => ({
  anthropic: vi.fn().mockReturnValue("mock-model"),
}));

import { extractClauses } from "../../src/pipeline/extract.ts";

describe("extractClauses", () => {
  it("returns extraction result with clauses and metadata", async () => {
    const result = await extractClauses("This is a sample contract text.");

    expect(result.extraction.contract_type).toBe("nda");
    expect(result.extraction.parties).toHaveLength(2);
    expect(result.extraction.governing_law).toBe("Delaware");
    expect(result.extraction.clauses.find((c) => c.clause_type === "non_disclosure")?.present).toBe(
      true,
    );
    expect(result.extraction.clauses.find((c) => c.clause_type === "liability_cap")?.present).toBe(
      false,
    );
  });

  it("calculates cost based on token usage", async () => {
    const result = await extractClauses("contract text");

    // claude-sonnet-4-6 pricing: $3/M input + $15/M output
    const expected = (25000 * 3 + 4000 * 15) / 1_000_000;
    expect(result.cost_usd).toBeCloseTo(expected, 6);
    expect(result.input_tokens).toBe(25000);
    expect(result.output_tokens).toBe(4000);
  });

  it("passes force_full_extraction inject flag to prompt", async () => {
    const { generateObject } = await import("ai");
    await extractClauses("contract text", { force_full_extraction: true });

    const call = vi.mocked(generateObject).mock.calls.at(-1)?.[0];
    expect((call as { prompt: string }).prompt).toContain("IMPORTANT: You MUST find");
  });
});
