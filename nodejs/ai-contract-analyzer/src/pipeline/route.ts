import { anthropic } from "@ai-sdk/anthropic";
import { generateObject } from "ai";
import { z } from "zod";
import type { RouteResult } from "../types/pipeline.ts";

const RouteSchema = z.object({
  document_type: z
    .enum(["nda", "employment", "service_agreement", "lease", "partnership", "unknown"])
    .describe("The primary type of this legal document"),
  complexity: z
    .enum(["simple", "standard", "complex"])
    .describe(
      "simple: <5 pages, few clauses; standard: 5-20 pages; complex: >20 pages or highly negotiated",
    ),
  requires_full_analysis: z
    .boolean()
    .describe("false only for trivially simple, single-purpose documents with no unusual terms"),
});

export async function routeDocument(fullText: string): Promise<RouteResult> {
  // Only the first 3000 chars are needed to classify a document
  const preview = fullText.slice(0, 3000);

  const { object, usage } = await generateObject({
    model: anthropic("claude-haiku-4-5-20251001"),
    schema: RouteSchema,
    system: `You are a legal document classifier. Identify the document type, complexity, and whether it requires full analysis.
Be conservative: if in doubt about document type, use "unknown". If in doubt about complexity, go higher.`,
    prompt: preview,
  });

  // claude-haiku-4-5 pricing: $0.80/M input, $4/M output (output is tiny for classification)
  const inputTokens = usage.inputTokens ?? 0;
  const outputTokens = usage.outputTokens ?? 0;
  const costUsd = (inputTokens * 0.8 + outputTokens * 4) / 1_000_000;

  return {
    ...object,
    input_tokens: inputTokens,
    cost_usd: costUsd,
  };
}
