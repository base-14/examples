import { SpanStatusCode, trace } from "@opentelemetry/api";
import { generateText } from "ai";
import { Hono } from "hono";
import { z } from "zod";
import { findClausesByContract } from "../db/clauses.ts";
import { findContractById } from "../db/contracts.ts";
import { getPool } from "../db/pool.ts";
import { embedValues } from "../llm/embeddings.ts";
import { retrieveChunks } from "../llm/retrieval.ts";
import { getCapableModel } from "../providers.ts";

const query = new Hono();

const QueryBody = z.object({
  question: z.string().min(1).max(1000),
});

const RETRIEVAL_TOP_K = 5;

// POST /api/contracts/:id/query - ask a question about a specific contract
query.post("/contracts/:id/query", async (c) => {
  const { id } = c.req.param();
  const pool = getPool();

  const contract = await findContractById(pool, id);
  if (!contract) return c.json({ error: "contract not found" }, 404);
  if (contract.status !== "complete") {
    return c.json(
      { error: `contract analysis is '${contract.status}', not ready for queries` },
      409,
    );
  }

  const body = QueryBody.safeParse(await c.req.json());
  if (!body.success) {
    return c.json({ error: "question is required" }, 400);
  }

  const { question } = body.data;
  const span = trace.getActiveSpan();

  span?.setAttribute("base14.contract.id", id);
  span?.setAttribute("base14.query.length", question.length);

  try {
    const { embeddings } = await embedValues([question]);
    const [queryEmbedding] = embeddings;
    if (!queryEmbedding) throw new Error("Embedding generation returned no results");

    const relevantChunks = await retrieveChunks(pool, queryEmbedding, RETRIEVAL_TOP_K, id);

    span?.setAttribute("base14.query.chunks_retrieved", relevantChunks.length);

    const clauseContext = (await findClausesByContract(pool, id))
      .filter((cl) => cl.present)
      .map((cl) => `[${cl.clause_type}] ${cl.text_excerpt}`)
      .join("\n");

    const chunkContext = relevantChunks
      .map((ch) => `[page ${ch.page_start}] ${ch.text}`)
      .join("\n\n");

    const { text, usage } = await generateText({
      model: getCapableModel().model,
      maxOutputTokens: 1_000,
      system: `You are a contract analysis assistant. Answer questions about the following contract strictly based on the provided text. If the answer cannot be found in the contract, say so clearly.

Contract: ${contract.filename}
Contract type: ${contract.contract_type ?? "unknown"}

Extracted clauses:
${clauseContext || "(none)"}`,
      prompt: `Relevant contract sections:
${chunkContext || "(none found)"}

Question: ${question}`,
    });

    span?.setAttribute("base14.gen_ai.usage.input_tokens", usage.inputTokens ?? 0);
    span?.setAttribute("base14.gen_ai.usage.output_tokens", usage.outputTokens ?? 0);

    return c.json({
      answer: text,
      sources: relevantChunks.map((ch) => ({
        page_start: ch.page_start,
        similarity: ch.similarity,
      })),
    });
  } catch (err) {
    span?.recordException(err as Error);
    span?.setAttribute("error.type", (err as Error)?.constructor?.name ?? "UnknownError");
    span?.setStatus({ code: SpanStatusCode.ERROR, message: (err as Error).message });
    return c.json({ error: "query failed" }, 500);
  }
});

export { query };
