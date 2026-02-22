import { metrics, SpanStatusCode, trace } from "@opentelemetry/api";
import { embedMany } from "ai";
import { Hono } from "hono";
import { z } from "zod";
import { similaritySearch } from "../db/chunks.ts";
import { findContractById } from "../db/contracts.ts";
import { getPool } from "../db/pool.ts";
import { getEmbeddingModel } from "../providers.ts";

const tracer = trace.getTracer("ai-contract-analyzer");
const meter = metrics.getMeter("ai-contract-analyzer");
const searchSimilarity = meter.createHistogram("contract.search.similarity", {
  description: "Cosine similarity scores from semantic search",
  unit: "1",
});

const SearchBody = z.object({
  query: z.string().min(1).max(2000),
  limit: z.number().int().min(1).max(20).default(10),
  contract_id: z.string().uuid().optional(),
});

const search = new Hono();

// POST /api/search — semantic search across all contracts (or a specific one)
search.post("/search", async (c) => {
  const body = SearchBody.safeParse(await c.req.json());
  if (!body.success) {
    return c.json({ error: "query is required" }, 400);
  }

  const { query, limit, contract_id } = body.data;
  const pool = getPool();

  return tracer.startActiveSpan("POST /api/search", async (span) => {
    span.setAttribute("search.query_length", query.length);
    span.setAttribute("search.limit", limit);
    if (contract_id) span.setAttribute("search.contract_id", contract_id);

    try {
      const { embeddings } = await embedMany({
        model: getEmbeddingModel().model,
        values: [query],
      });
      const [queryEmbedding] = embeddings;
      if (!queryEmbedding) throw new Error("Embedding generation returned no results");

      const results = await similaritySearch(pool, queryEmbedding, limit, contract_id);

      span.setAttribute("search.results_count", results.length);

      // Record similarity distribution for observability
      for (const r of results) {
        searchSimilarity.record(r.similarity, {
          "search.type": contract_id ? "contract" : "corpus",
        });
      }

      // Enrich results with contract metadata
      const contractIds = [...new Set(results.map((r) => r.contract_id))];
      const contractMeta = await Promise.all(contractIds.map((cid) => findContractById(pool, cid)));
      const metaMap = Object.fromEntries(
        contractMeta
          .filter(Boolean)
          .map((c) => [c?.id, { filename: c?.filename, contract_type: c?.contract_type }]),
      );

      span.end();
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
      span.recordException(err as Error);
      span.setStatus({ code: SpanStatusCode.ERROR, message: (err as Error).message });
      span.end();
      return c.json({ error: "search failed" }, 500);
    }
  });
});

export { search };
