import { describe, expect, it, vi } from "vitest";

vi.mock("ai", () => ({
  generateObject: vi.fn().mockResolvedValue({
    object: {
      executive_summary:
        "This is a standard NDA between two parties protecting proprietary information.",
      key_terms: [
        { term: "Governing Law", value: "Delaware" },
        { term: "Effective Date", value: "2025-01-01" },
      ],
      key_risks: [
        {
          risk: "No liability cap present",
          severity: "high",
          recommendation: "Negotiate a mutual liability cap",
        },
      ],
      negotiation_points: ["Add liability cap", "Clarify definition of confidential information"],
    },
    usage: { inputTokens: 6000, outputTokens: 1200 },
  }),
}));

vi.mock("../../src/providers.ts", () => ({
  getCapableModel: vi.fn().mockReturnValue({
    model: "mock-capable-model",
    inputCostPerMToken: 3,
    outputCostPerMToken: 15,
  }),
}));

import { generateSummary } from "../../src/pipeline/summarize.ts";

const mockExtraction = {
  clauses: [
    {
      clause_type: "non_disclosure" as const,
      present: true,
      text_excerpt: "shall keep confidential",
      page_number: 1,
      confidence: 0.95,
      notes: "",
    },
  ],
  parties: [{ name: "Acme Corp", role: "party_a" as const }],
  effective_date: "2025-01-01",
  expiration_date: null,
  governing_law: "Delaware",
  contract_type: "nda",
};

const mockRisks = {
  clause_risks: [
    {
      clause_type: "non_disclosure" as const,
      risk_level: "low" as const,
      risk_factors: ["standard NDA language"],
      recommendation: "No action required",
    },
  ],
  overall_risk: "high" as const,
  missing_clauses: [
    {
      clause_type: "liability_cap" as const,
      importance: "required" as const,
      explanation: "No liability protection present",
    },
  ],
};

describe("generateSummary", () => {
  it("returns structured summary with all required fields", async () => {
    const result = await generateSummary(mockExtraction, mockRisks);

    expect(result.summary.executive_summary).toContain("NDA");
    expect(result.summary.key_terms).toHaveLength(2);
    expect(result.summary.key_risks).toHaveLength(1);
    expect(result.summary.negotiation_points).toHaveLength(2);
  });

  it("calculates cost based on token usage", async () => {
    const result = await generateSummary(mockExtraction, mockRisks);

    // claude-sonnet-4-6 pricing: $3/M input + $15/M output
    const expected = (6000 * 3 + 1200 * 15) / 1_000_000;
    expect(result.cost_usd).toBeCloseTo(expected, 6);
    expect(result.input_tokens).toBe(6000);
    expect(result.output_tokens).toBe(1200);
  });
});
