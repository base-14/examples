/**
 * The pgvector lookup wrapped in a `retrieval {data_source}` CLIENT span.
 *
 * The embeddings span for the query text is a sibling, created before this call
 * by `embedValues`; both sit under the HTTP span of the route that ran them.
 */
import { SpanKind, SpanStatusCode, trace } from "@opentelemetry/api";
import type { Pool } from "pg";
import { type SearchResult, similaritySearch } from "../db/chunks.ts";

const tracer = trace.getTracer("ai-contract-analyzer");

const DATA_SOURCE_ID = "contract_chunks";

export async function retrieveChunks(
  pool: Pool,
  queryEmbedding: number[],
  limit: number,
  contractId?: string,
): Promise<SearchResult[]> {
  return tracer.startActiveSpan(
    `retrieval ${DATA_SOURCE_ID}`,
    {
      kind: SpanKind.CLIENT,
      attributes: {
        "gen_ai.operation.name": "retrieval",
        "gen_ai.data_source.id": DATA_SOURCE_ID,
        "gen_ai.request.top_k": limit,
      },
    },
    async (span) => {
      try {
        const results = await similaritySearch(pool, queryEmbedding, limit, contractId);
        const scores = results.map((r) => r.similarity);

        span.setAttribute("app.retrieval.chunk_count", results.length);
        if (scores.length > 0) {
          span.setAttribute("app.retrieval.score_min", Math.min(...scores));
          span.setAttribute("app.retrieval.score_max", Math.max(...scores));
        }

        span.end();
        return results;
      } catch (err) {
        span.recordException(err as Error);
        span.setAttribute("error.type", (err as Error)?.constructor?.name ?? "UnknownError");
        span.setStatus({ code: SpanStatusCode.ERROR, message: (err as Error).message });
        span.end();
        throw err;
      }
    },
  );
}
