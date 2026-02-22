import { embedMany } from "ai";
import { getEmbeddingModel } from "../providers.ts";
import type { ChunkData } from "../types/pipeline.ts";

const BATCH_SIZE = 20;

export interface EmbedResult {
  embeddings: number[][];
  total_tokens: number;
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

  const embeddingDescriptor = getEmbeddingModel();
  for (let i = 0; i < texts.length; i += BATCH_SIZE) {
    const batch = texts.slice(i, i + BATCH_SIZE);
    const { embeddings, usage } = await embedMany({
      model: embeddingDescriptor.model,
      values: batch,
    });
    allEmbeddings.push(...embeddings);
    totalTokens += usage.tokens;
  }

  return {
    embeddings: allEmbeddings,
    total_tokens: totalTokens,
    batch_count: Math.ceil(texts.length / BATCH_SIZE),
  };
}
