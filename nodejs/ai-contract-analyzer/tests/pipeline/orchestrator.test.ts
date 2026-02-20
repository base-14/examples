import { describe, expect, it, vi } from "vitest";

// Mock all LLM-dependent pipeline stages before importing orchestrator
vi.mock("../../src/pipeline/route.ts", () => ({
  routeDocument: vi.fn().mockResolvedValue({
    document_type: "nda",
    complexity: "standard",
    requires_full_analysis: true,
    input_tokens: 500,
    cost_usd: 0.0004,
  }),
}));

vi.mock("../../src/pipeline/ingest.ts", () => ({
  ingestDocument: vi.fn().mockResolvedValue({
    contract_id: "test-id",
    filename: "test.txt",
    page_count: 5,
    total_characters: 5000,
    chunks: [{ index: 0, text: "Contract text", page_start: 1, page_end: 1, character_count: 13 }],
    full_text: "Contract text",
  }),
}));

vi.mock("../../src/pipeline/embed.ts", () => ({
  embedChunks: vi.fn().mockResolvedValue({
    embeddings: [[0.1, 0.2, 0.3]],
    total_tokens: 100,
    batch_count: 1,
  }),
}));

vi.mock("../../src/pipeline/extract.ts", () => ({
  extractClauses: vi.fn().mockResolvedValue({
    extraction: {
      clauses: [
        {
          clause_type: "non_disclosure",
          present: true,
          text_excerpt: "shall keep confidential",
          page_number: 1,
          confidence: 0.95,
          notes: "",
        },
      ],
      parties: [
        { name: "Acme Corp", role: "party_a" },
        { name: "Beta LLC", role: "party_b" },
      ],
      effective_date: "2025-01-01",
      expiration_date: null,
      governing_law: "Delaware",
      contract_type: "nda",
    },
    input_tokens: 5000,
    output_tokens: 800,
    cost_usd: 0.027,
  }),
}));

vi.mock("../../src/pipeline/score.ts", () => ({
  scoreRisks: vi.fn().mockResolvedValue({
    risks: {
      clause_risks: [
        {
          clause_type: "non_disclosure",
          risk_level: "low",
          risk_factors: ["standard NDA language"],
          recommendation: "No action required",
        },
      ],
      overall_risk: "low",
      missing_clauses: [],
    },
    input_tokens: 1000,
    output_tokens: 400,
    cost_usd: 0.002,
  }),
}));

vi.mock("../../src/pipeline/summarize.ts", () => ({
  generateSummary: vi.fn().mockResolvedValue({
    summary: {
      executive_summary: "Standard NDA between two parties.",
      key_terms: [{ term: "Governing Law", value: "Delaware" }],
      key_risks: [],
      negotiation_points: [],
    },
    input_tokens: 2000,
    output_tokens: 300,
    cost_usd: 0.01,
  }),
}));

vi.mock("../../src/db/contracts.ts", () => ({
  createContract: vi.fn().mockResolvedValue({ id: "test-contract-id" }),
  updateContractStatus: vi.fn().mockResolvedValue(undefined),
}));

vi.mock("../../src/db/chunks.ts", () => ({
  insertChunks: vi.fn().mockResolvedValue(undefined),
  registerVectorTypes: vi.fn(),
  similaritySearch: vi.fn().mockResolvedValue([]),
}));

vi.mock("../../src/db/clauses.ts", () => ({
  insertClauses: vi.fn().mockResolvedValue(undefined),
  findClausesByContract: vi.fn().mockResolvedValue([]),
}));

vi.mock("../../src/db/risks.ts", () => ({
  insertRisks: vi.fn().mockResolvedValue(undefined),
  findRisksByContract: vi.fn().mockResolvedValue([]),
}));

vi.mock("../../src/db/analyses.ts", () => ({
  insertAnalysis: vi.fn().mockResolvedValue({ id: "analysis-id" }),
  findAnalysisByContract: vi.fn().mockResolvedValue(null),
}));

import { analyzeContract } from "../../src/pipeline/orchestrator.ts";

const mockPool = {
  query: vi.fn().mockResolvedValue({ rows: [] }),
} as unknown as Parameters<typeof analyzeContract>[1];

describe("analyzeContract", () => {
  it("runs all 5 pipeline stages and returns a full result", async () => {
    const file = new File(["contract text"], "test.txt", { type: "text/plain" });
    const result = await analyzeContract(file, mockPool);

    expect(result.extraction.contract_type).toBe("nda");
    expect(result.risks.overall_risk).toBe("low");
    expect(result.summary.executive_summary).toContain("NDA");
    expect(result.total_tokens).toBeGreaterThan(0);
    expect(result.total_cost_usd).toBeGreaterThan(0);
    expect(result.total_duration_ms).toBeGreaterThanOrEqual(0);
  });

  it("marks contract as error and re-throws when a stage fails", async () => {
    const { extractClauses } = await import("../../src/pipeline/extract.ts");
    vi.mocked(extractClauses).mockRejectedValueOnce(new Error("LLM timeout"));

    const { updateContractStatus } = await import("../../src/db/contracts.ts");

    const file = new File(["contract text"], "test.txt", { type: "text/plain" });
    await expect(analyzeContract(file, mockPool)).rejects.toThrow("LLM timeout");

    expect(vi.mocked(updateContractStatus)).toHaveBeenCalledWith(
      mockPool,
      expect.any(String),
      "error",
    );
  });
});
