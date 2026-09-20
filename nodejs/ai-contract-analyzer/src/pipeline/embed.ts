import { embedValues } from "../llm/embeddings.ts";
import type { ChunkData } from "../types/pipeline.ts";

const BATCH_SIZE = 20;

export interface EmbedResult {
  embeddings: number[][];
  total_tokens: number;
  total_cost_usd: number;
  batch_count: number;
}

export async function embedChunks(
  chunks: ChunkData[],
  inject?: { embedding_error?: "rate_limit" | "server_error" },
): Promise<EmbedResult> {
  if (inject?.embedding_error) {
    const status = inject.embedding_error === "rate_limit" ? 429 : 500;
    throw Object.assign(new Error(`Embedding API failure (injected): HTTP ${status}`), {
      code: "EMBEDDING_FAILURE",
      http_status: status,
    });
  }

  const texts = chunks.map((c) => c.text);
  const allEmbeddings: number[][] = [];
  let totalTokens = 0;
  let totalCost = 0;

  for (let i = 0; i < texts.length; i += BATCH_SIZE) {
    const outcome = await embedValues(texts.slice(i, i + BATCH_SIZE));
    allEmbeddings.push(...outcome.embeddings);
    totalTokens += outcome.tokens;
    totalCost += outcome.costUsd;
  }

  return {
    embeddings: allEmbeddings,
    total_tokens: totalTokens,
    total_cost_usd: totalCost,
    batch_count: Math.ceil(texts.length / BATCH_SIZE),
  };
}
