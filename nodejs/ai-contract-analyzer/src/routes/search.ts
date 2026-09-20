import { metrics, SpanStatusCode, trace } from "@opentelemetry/api";
import { Hono } from "hono";
import { z } from "zod";
import { findContractById } from "../db/contracts.ts";
import { getPool } from "../db/pool.ts";
import { embedValues } from "../llm/embeddings.ts";
import { retrieveChunks } from "../llm/retrieval.ts";

const meter = metrics.getMeter("ai-contract-analyzer");
const searchSimilarity = meter.createHistogram("base14.contract.search.similarity", {
  description: "Cosine similarity scores from semantic search",
  unit: "1",
});

const SearchBody = z.object({
  query: z.string().min(1).max(2000),
  limit: z.number().int().min(1).max(20).default(10),
  contract_id: z.string().uuid().optional(),
});

const search = new Hono();

// POST /api/search - semantic search across all contracts (or a specific one)
search.post("/search", async (c) => {
  const body = SearchBody.safeParse(await c.req.json());
  if (!body.success) {
    return c.json({ error: "query is required" }, 400);
  }

  const { query, limit, contract_id } = body.data;
  const pool = getPool();
  const span = trace.getActiveSpan();

  span?.setAttribute("base14.search.query_length", query.length);
  span?.setAttribute("base14.search.limit", limit);
  if (contract_id) span?.setAttribute("base14.search.contract_id", contract_id);

  try {
    const { embeddings } = await embedValues([query]);
    const [queryEmbedding] = embeddings;
    if (!queryEmbedding) throw new Error("Embedding generation returned no results");

    const results = await retrieveChunks(pool, queryEmbedding, limit, contract_id);

    span?.setAttribute("base14.search.results_count", results.length);

    for (const r of results) {
      searchSimilarity.record(r.similarity, {
        "base14.search.type": contract_id ? "contract" : "corpus",
      });
    }

    const contractIds = [...new Set(results.map((r) => r.contract_id))];
    const contractMeta = await Promise.all(contractIds.map((cid) => findContractById(pool, cid)));
    const metaMap = Object.fromEntries(
      contractMeta
        .filter(Boolean)
        .map((ct) => [ct?.id, { filename: ct?.filename, contract_type: ct?.contract_type }]),
    );

    return c.json({
      results: results.map((r) => ({
        contract_id: r.contract_id,
        filename: metaMap[r.contract_id]?.filename,
        contract_type: metaMap[r.contract_id]?.contract_type,
        text: r.text,
        similarity: Math.round(r.similarity * 1000) / 1000,
        page_start: r.page_start,
      })),
    });
  } catch (err) {
    span?.recordException(err as Error);
    span?.setAttribute("error.type", (err as Error)?.constructor?.name ?? "UnknownError");
    span?.setStatus({ code: SpanStatusCode.ERROR, message: (err as Error).message });
    return c.json({ error: "search failed" }, 500);
  }
});

export { search };
