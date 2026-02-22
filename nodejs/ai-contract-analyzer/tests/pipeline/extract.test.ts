import { beforeEach, describe, expect, it, vi } from "vitest";

// vi.mock is hoisted — factory must not reference module-level variables
vi.mock("ai", () => ({ generateObject: vi.fn() }));
vi.mock("../../src/providers.ts", () => ({
  getCapableModel: vi.fn().mockReturnValue({
    model: "mock-capable-model",
    inputCostPerMToken: 3,
    outputCostPerMToken: 15,
  }),
  getFastModel: vi.fn().mockReturnValue({
    model: "mock-fast-model",
    inputCostPerMToken: 0.8,
    outputCostPerMToken: 4,
  }),
}));

import { generateObject } from "ai";
import { extractClauses } from "../../src/pipeline/extract.ts";

// Satisfies both ExtractionSchema and EvaluationSchema so the same object works for all calls
const EXTRACTION_OBJECT = {
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
  // EvaluationSchema fields — evaluator sees passed:true, so loop exits after first iteration
  passed: true,
  issues: [],
};

const mockResult = (object: unknown, inputTokens = 25000, outputTokens = 4000) =>
  ({ object, usage: { inputTokens, outputTokens } }) as unknown as Awaited<
    ReturnType<typeof generateObject>
  >;

describe("extractClauses", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    // Default: generator and evaluator both pass on first try
    vi.mocked(generateObject).mockResolvedValue(mockResult(EXTRACTION_OBJECT));
  });

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
    expect(result.eval_iterations).toBe(1);
  });

  it("calculates cost based on token usage for both generator and evaluator", async () => {
    const result = await extractClauses("contract text");

    // Generator: claude-sonnet-4-6 $3/M input + $15/M output
    // Evaluator: claude-haiku-4-5  $0.80/M input + $4/M output
    // Both calls return { inputTokens: 25000, outputTokens: 4000 }
    const generatorCost = (25000 * 3 + 4000 * 15) / 1_000_000;
    const evaluatorCost = (25000 * 0.8 + 4000 * 4) / 1_000_000;
    expect(result.cost_usd).toBeCloseTo(generatorCost + evaluatorCost, 6);
    expect(result.input_tokens).toBe(50000);
    expect(result.output_tokens).toBe(8000);
  });

  it("uses all 41 clause types in system prompt when force_full_extraction is set", async () => {
    await extractClauses("contract text", { force_full_extraction: true });

    // First call is the generator — check its system prompt
    const generatorCall = vi.mocked(generateObject).mock.calls[0]?.[0];
    expect((generatorCall as { system: string }).system).toContain("(41)");
  });

  it("narrows clause types based on document type", async () => {
    await extractClauses("contract text", undefined, "nda");

    const generatorCall = vi.mocked(generateObject).mock.calls[0]?.[0];
    const system = (generatorCall as { system: string }).system;
    expect(system).toContain("non_disclosure");
    expect(system).not.toContain("(41)");
  });

  it("retries extraction when evaluator fails and passes feedback to generator", async () => {
    vi.mocked(generateObject)
      .mockResolvedValueOnce(mockResult(EXTRACTION_OBJECT)) // generator attempt 1
      .mockResolvedValueOnce(
        mockResult(
          { passed: false, issues: ["non_disclosure clause present but text_excerpt is empty"] },
          300,
          25,
        ),
      ) // evaluator 1 — FAIL
      .mockResolvedValueOnce(mockResult(EXTRACTION_OBJECT, 25500, 4000)) // generator attempt 2
      .mockResolvedValueOnce(mockResult({ passed: true, issues: [] }, 300, 20)); // evaluator 2 — PASS

    const result = await extractClauses("contract text");

    // 4 total calls: generator, evaluator, generator, evaluator
    expect(vi.mocked(generateObject).mock.calls).toHaveLength(4);

    // Second generator prompt must contain feedback from the first failed evaluation
    const secondGeneratorPrompt = (
      vi.mocked(generateObject).mock.calls[2]?.[0] as { prompt: string }
    ).prompt;
    expect(secondGeneratorPrompt).toContain("Previous extraction had these issues");
    expect(secondGeneratorPrompt).toContain("non_disclosure clause present");

    expect(result.extraction.contract_type).toBe("nda");
    expect(result.eval_iterations).toBe(2);
  });
});
