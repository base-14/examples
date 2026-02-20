import { describe, expect, it, vi } from "vitest";

vi.mock("../../src/pipeline/orchestrator.ts", () => ({
  analyzeContract: vi.fn().mockResolvedValue({
    ingest: { contract_id: "abc-123", filename: "test.txt" },
    extraction: { clauses: [], parties: [], contract_type: "nda" },
    risks: { overall_risk: "low", clause_risks: [], missing_clauses: [] },
    summary: {
      executive_summary: "A simple NDA.",
      key_terms: [],
      key_risks: [],
      negotiation_points: [],
    },
    total_duration_ms: 5000,
    total_tokens: 8000,
    total_cost_usd: 0.03,
    trace_id: "trace-xyz",
  }),
}));

vi.mock("../../src/db/pool.ts", () => ({
  getPool: vi.fn().mockReturnValue({}),
}));

vi.mock("../../src/db/contracts.ts", () => ({
  findContractById: vi.fn().mockResolvedValue({
    id: "abc-123",
    filename: "test.txt",
    contract_type: "nda",
    status: "complete",
    page_count: 5,
    total_characters: 5000,
    created_at: new Date("2025-01-01"),
  }),
  listContracts: vi.fn().mockResolvedValue([]),
}));

vi.mock("../../src/db/clauses.ts", () => ({
  findClausesByContract: vi.fn().mockResolvedValue([]),
}));

vi.mock("../../src/db/risks.ts", () => ({
  findRisksByContract: vi.fn().mockResolvedValue([]),
}));

vi.mock("../../src/db/analyses.ts", () => ({
  findAnalysisByContract: vi.fn().mockResolvedValue(null),
}));

// Import AFTER mocks are set up
const { contracts } = await import("../../src/routes/contracts.ts");

describe("POST /api/contracts", () => {
  it("returns 400 when no file is provided", async () => {
    const form = new FormData();
    const req = new Request("http://localhost/contracts", {
      method: "POST",
      body: form,
    });
    const res = await contracts.fetch(req);
    expect(res.status).toBe(400);
    const body = (await res.json()) as { error: string };
    expect(body.error).toContain("file");
  });

  it("returns 201 with contract_id on successful upload", async () => {
    const form = new FormData();
    form.append("file", new File(["contract content"], "test.txt", { type: "text/plain" }));
    const req = new Request("http://localhost/contracts", {
      method: "POST",
      body: form,
    });
    const res = await contracts.fetch(req);
    expect(res.status).toBe(201);
    const body = (await res.json()) as { contract_id: string; overall_risk: string };
    expect(body.contract_id).toBe("abc-123");
    expect(body.overall_risk).toBe("low");
  });

  it("returns 415 for unsupported file types", async () => {
    const form = new FormData();
    form.append("file", new File(["data"], "data.csv", { type: "text/csv" }));
    const req = new Request("http://localhost/contracts", {
      method: "POST",
      body: form,
    });
    const res = await contracts.fetch(req);
    expect(res.status).toBe(415);
  });
});

describe("GET /api/contracts", () => {
  it("returns an array of contracts", async () => {
    const req = new Request("http://localhost/contracts");
    const res = await contracts.fetch(req);
    expect(res.status).toBe(200);
    const body = (await res.json()) as { contracts: unknown[] };
    expect(Array.isArray(body.contracts)).toBe(true);
  });
});

describe("GET /api/contracts/:id", () => {
  it("returns contract with analysis when found", async () => {
    const req = new Request("http://localhost/contracts/abc-123");
    const res = await contracts.fetch(req);
    expect(res.status).toBe(200);
    const body = (await res.json()) as { contract: { id: string } };
    expect(body.contract.id).toBe("abc-123");
  });

  it("returns 404 when contract does not exist", async () => {
    const { findContractById } = await import("../../src/db/contracts.ts");
    vi.mocked(findContractById).mockResolvedValueOnce(null);

    const req = new Request("http://localhost/contracts/not-found");
    const res = await contracts.fetch(req);
    expect(res.status).toBe(404);
  });
});
