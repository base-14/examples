import { generateText, Output } from "ai";
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

const SYSTEM_PROMPT = `You are a legal document classifier. Choose the single document type that best matches the text.

nda: obligations to keep information confidential or not to disclose it.
employment: terms on which an employer hires an individual employee.
service_agreement: one party performs services or delivers work product for another in return for payment.
lease: the right to occupy or use property in return for rent.
partnership: two or more parties sharing ownership, profit or control of a joint venture.
unknown: the text is not a contract at all, for example an invoice, an article or a letter.

Always pick the closest of the five contract types, even when the document is unusual or covers
more than one subject. Use "unknown" only when the text is not a contract.

For complexity, go higher when in doubt.`;

export async function routeDocument(fullText: string): Promise<RouteResult> {
  // Only the first 3000 chars are needed to classify a document
  const preview = fullText.slice(0, 3000);

  const fastDescriptor = getFastModel();
  const { output, usage } = await generateText({
    model: fastDescriptor.model,
    output: Output.object({ schema: RouteSchema }),
    system: SYSTEM_PROMPT,
    prompt: preview,
  });

  const inputTokens = usage.inputTokens ?? 0;
  const outputTokens = usage.outputTokens ?? 0;
  const costUsd =
    (inputTokens * fastDescriptor.inputCostPerMToken +
      outputTokens * fastDescriptor.outputCostPerMToken) /
    1_000_000;

  return {
    ...output,
    input_tokens: inputTokens,
    cost_usd: costUsd,
  };
}
