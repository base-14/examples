import type { Pool } from "pg";
import pgvector from "pgvector/pg";
import type { ChunkData } from "../types/pipeline.ts";

export interface ChunkRow {
  id: string;
  contract_id: string;
  chunk_index: number;
  text: string;
  page_start: number;
  page_end: number;
  character_count: number;
  created_at: Date;
}

export interface SearchResult {
  chunk_id: string;
  contract_id: string;
  text: string;
  similarity: number;
  page_start: number;
  page_end: number;
}

export function registerVectorTypes(pool: Pool): void {
  pool.on("connect", async (client) => {
    await pgvector.registerTypes(client);
  });
}

export async function insertChunks(
  pool: Pool,
  contract_id: string,
  chunks: ChunkData[],
  embeddings: number[][],
): Promise<void> {
  if (chunks.length === 0) return;

  const client = await pool.connect();
  try {
    await client.query("BEGIN");
    for (let i = 0; i < chunks.length; i++) {
      const chunk = chunks[i]!;
      await client.query(
        `INSERT INTO chunks (contract_id, chunk_index, text, page_start, page_end, character_count, embedding)
         VALUES ($1, $2, $3, $4, $5, $6, $7::vector)`,
        [
          contract_id,
          chunk.index,
          chunk.text,
          chunk.page_start,
          chunk.page_end,
          chunk.character_count,
          pgvector.toSql(embeddings[i]!),
        ],
      );
    }
    await client.query("COMMIT");
  } catch (err) {
    await client.query("ROLLBACK");
    throw err;
  } finally {
    client.release();
  }
}

export async function similaritySearch(
  pool: Pool,
  queryEmbedding: number[],
  limit = 5,
  contractId?: string,
): Promise<SearchResult[]> {
  const vectorStr = pgvector.toSql(queryEmbedding);

  if (contractId) {
    const result = await pool.query<SearchResult>(
      `SELECT
         id AS chunk_id,
         contract_id,
         text,
         1 - (embedding <=> $1::vector) AS similarity,
         page_start,
         page_end
       FROM chunks
       WHERE contract_id = $2
         AND embedding IS NOT NULL
       ORDER BY embedding <=> $1::vector
       LIMIT $3`,
      [vectorStr, contractId, limit],
    );
    return result.rows;
  }

  const result = await pool.query<SearchResult>(
    `SELECT
       id AS chunk_id,
       contract_id,
       text,
       1 - (embedding <=> $1::vector) AS similarity,
       page_start,
       page_end
     FROM chunks
     WHERE embedding IS NOT NULL
     ORDER BY embedding <=> $1::vector
     LIMIT $2`,
    [vectorStr, limit],
  );
  return result.rows;
}
