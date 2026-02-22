import { describe, expect, it, vi } from "vitest";

vi.mock("../../src/db/pool.ts", () => ({
  getPool: vi.fn().mockReturnValue({}),
}));

vi.mock("ai", () => ({
  embedMany: vi.fn().mockResolvedValue({
    embeddings: [[0.1, 0.2, 0.3]],
    usage: { tokens: 10 },
  }),
}));

vi.mock("../../src/providers.ts", () => ({
  getEmbeddingModel: vi.fn().mockReturnValue({
    model: "mock-embedding-model",
    dimensions: 768,
    costPerMToken: 0.02,
  }),
}));

vi.mock("../../src/db/chunks.ts", () => ({
  similaritySearch: vi.fn().mockResolvedValue([
    {
      contract_id: "abc-123",
      text: "shall keep confidential all proprietary information",
      page_start: 2,
      similarity: 0.87,
    },
  ]),
  registerVectorTypes: vi.fn(),
}));

vi.mock("../../src/db/contracts.ts", () => ({
  findContractById: vi.fn().mockResolvedValue({
    id: "abc-123",
    filename: "sample-nda.txt",
    contract_type: "nda",
  }),
}));

import { Hono } from "hono";
import { search } from "../../src/routes/search.ts";

const app = new Hono();
app.route("/api", search);

const VALID_CONTRACT_UUID = "aaaaaaaa-aaaa-4aaa-aaaa-aaaaaaaaaaaa";

describe("POST /api/search", () => {
  it("returns search results for a valid query", async () => {
    const res = await app.request("/api/search", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ query: "confidentiality obligations", limit: 5 }),
    });

    expect(res.status).toBe(200);
    const body = (await res.json()) as { results: Array<{ similarity: number; filename: string }> };
    expect(body.results).toHaveLength(1);
    expect(body.results[0]?.similarity).toBeGreaterThan(0);
    expect(body.results[0]?.filename).toBe("sample-nda.txt");
  });

  it("returns 400 when query is missing", async () => {
    const res = await app.request("/api/search", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ limit: 5 }),
    });

    expect(res.status).toBe(400);
  });

  it("filters by contract_id when provided", async () => {
    const { similaritySearch } = await import("../../src/db/chunks.ts");

    await app.request("/api/search", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ query: "liability", contract_id: VALID_CONTRACT_UUID }),
    });

    expect(vi.mocked(similaritySearch)).toHaveBeenCalledWith(
      expect.anything(),
      expect.any(Array),
      expect.any(Number),
      VALID_CONTRACT_UUID,
    );
  });
});
