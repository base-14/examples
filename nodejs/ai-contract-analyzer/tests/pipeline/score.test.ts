import { describe, expect, it, vi } from "vitest";

vi.mock("ai", () => ({
  generateObject: vi.fn().mockResolvedValue({
    object: {
      clause_risks: [
        {
          clause_type: "liability_cap",
          risk_level: "high",
          risk_factors: ["cap is below industry standard"],
          recommendation: "Negotiate higher cap",
        },
      ],
      overall_risk: "high",
      missing_clauses: [
        {
          clause_type: "indemnification",
          importance: "required",
          explanation: "Standard for service agreements",
        },
      ],
    },
    usage: { inputTokens: 3000, outputTokens: 1500 },
  }),
}));

vi.mock("@ai-sdk/anthropic", () => ({
  anthropic: vi.fn().mockReturnValue("mock-model"),
}));

import { scoreRisks } from "../../src/pipeline/score.ts";

const mockExtraction = {
  clauses: [
    {
      clause_type: "liability_cap" as const,
      present: true,
      text_excerpt: "liability shall not exceed $10,000",
      page_number: 3,
      confidence: 0.9,
      notes: "",
    },
  ],
  parties: [{ name: "Acme", role: "party_a" as const }],
  effective_date: "2025-01-01",
  expiration_date: null,
  governing_law: "Delaware",
  contract_type: "service_agreement",
};

describe("scoreRisks", () => {
  it("returns overall risk and clause risks", async () => {
    const result = await scoreRisks(mockExtraction);

    expect(result.risks.overall_risk).toBe("high");
    expect(result.risks.clause_risks).toHaveLength(1);
    expect(result.risks.clause_risks[0]?.clause_type).toBe("liability_cap");
    expect(result.risks.missing_clauses[0]?.clause_type).toBe("indemnification");
  });

  it("calculates cost based on token usage", async () => {
    const result = await scoreRisks(mockExtraction);

    // Haiku pricing: $0.80/M input + $4/M output
    const expected = (3000 * 0.8 + 1500 * 4) / 1_000_000;
    expect(result.cost_usd).toBeCloseTo(expected, 6);
  });
});
