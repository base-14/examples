import { generateObject } from "ai";
import { z } from "zod";
import { getFastModel } from "../providers.ts";
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

  const fastDescriptor = getFastModel();
  const { object, usage } = await generateObject({
    model: fastDescriptor.model,
    schema: RouteSchema,
    system: `You are a legal document classifier. Identify the document type, complexity, and whether it requires full analysis.
Be conservative: if in doubt about document type, use "unknown". If in doubt about complexity, go higher.`,
    prompt: preview,
    experimental_telemetry: { isEnabled: true, functionId: "pipeline.route" },
  });

  const inputTokens = usage.inputTokens ?? 0;
  const outputTokens = usage.outputTokens ?? 0;
  const costUsd =
    (inputTokens * fastDescriptor.inputCostPerMToken +
      outputTokens * fastDescriptor.outputCostPerMToken) /
    1_000_000;

  return {
    ...object,
    input_tokens: inputTokens,
    cost_usd: costUsd,
  };
}
