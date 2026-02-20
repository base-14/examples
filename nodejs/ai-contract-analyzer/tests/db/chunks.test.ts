import { beforeEach, describe, expect, it, vi } from "vitest";

// Mock pgvector before importing chunks module
vi.mock("pgvector/pg", () => ({
  default: {
    toSql: (arr: number[]) => `[${arr.join(",")}]`,
    registerTypes: vi.fn(),
  },
}));

const mockQuery = vi.fn();
const mockRelease = vi.fn();
const mockClient = {
  query: mockQuery,
  release: mockRelease,
};
const mockPool = {
  connect: vi.fn().mockResolvedValue(mockClient),
  query: mockQuery,
  on: vi.fn(),
};

import { insertChunks, similaritySearch } from "../../src/db/chunks.ts";
import type { ChunkData } from "../../src/types/pipeline.ts";

const chunks: ChunkData[] = [
  { index: 0, text: "First chunk", page_start: 1, page_end: 1, character_count: 11 },
  { index: 1, text: "Second chunk", page_start: 1, page_end: 2, character_count: 12 },
];

const embeddings = [
  [0.1, 0.2, 0.3],
  [0.4, 0.5, 0.6],
];

describe("insertChunks", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockQuery.mockResolvedValue({ rows: [] });
  });

  it("wraps inserts in a transaction", async () => {
    await insertChunks(mockPool as never, "contract-1", chunks, embeddings);

    const calls = mockQuery.mock.calls.map((c) => c[0] as string);
    expect(calls).toContain("BEGIN");
    expect(calls).toContain("COMMIT");
  });

  it("inserts one row per chunk", async () => {
    await insertChunks(mockPool as never, "contract-1", chunks, embeddings);

    const insertCalls = mockQuery.mock.calls.filter(
      (c) => typeof c[0] === "string" && (c[0] as string).includes("INSERT INTO chunks"),
    );
    expect(insertCalls).toHaveLength(chunks.length);
  });

  it("rolls back on error", async () => {
    mockQuery
      .mockResolvedValueOnce(undefined) // BEGIN
      .mockRejectedValueOnce(new Error("db error")); // first INSERT

    await expect(insertChunks(mockPool as never, "contract-1", chunks, embeddings)).rejects.toThrow(
      "db error",
    );

    const calls = mockQuery.mock.calls.map((c) => c[0] as string);
    expect(calls).toContain("ROLLBACK");
    expect(calls).not.toContain("COMMIT");
  });

  it("is a no-op for empty chunk array", async () => {
    await insertChunks(mockPool as never, "contract-1", [], []);
    expect(mockQuery).not.toHaveBeenCalled();
  });
});

describe("similaritySearch", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockQuery.mockResolvedValue({ rows: [] });
  });

  it("queries with contract_id filter when provided", async () => {
    await similaritySearch(mockPool as never, [0.1, 0.2], 5, "contract-abc");

    const call = mockQuery.mock.calls[0];
    expect(call?.[0]).toContain("WHERE contract_id = $2");
  });

  it("queries across all contracts when contract_id is omitted", async () => {
    await similaritySearch(mockPool as never, [0.1, 0.2], 5);

    const call = mockQuery.mock.calls[0];
    expect(call?.[0]).not.toContain("contract_id = $2");
  });
});
