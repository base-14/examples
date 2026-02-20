import { anthropic } from "@ai-sdk/anthropic";
import { generateObject } from "ai";
import { z } from "zod";
import { ClauseSchema, CUAD_CLAUSE_TYPES } from "../types/clauses.ts";
import type { ExtractionResult } from "../types/pipeline.ts";

const ExtractionSchema = z.object({
  clauses: z
    .array(ClauseSchema)
    .describe(
      "One entry per CUAD clause type. Set present=false for clauses not found in the contract.",
    ),
  parties: z.array(
    z.object({
      name: z.string(),
      role: z.enum(["party_a", "party_b", "third_party"]),
    }),
  ),
  effective_date: z.string().nullable(),
  expiration_date: z.string().nullable(),
  governing_law: z.string().nullable(),
  contract_type: z
    .string()
    .describe("e.g. service_agreement, nda, license, employment, lease, partnership"),
});

const SYSTEM_PROMPT = `You are a contract analysis expert with deep knowledge of commercial contracts.

Your task: extract all relevant clauses and metadata from the provided contract text.

For each of the 41 CUAD clause types, determine:
- present: true only if you can quote specific language from the contract
- text_excerpt: the exact quote (empty string if not present)
- page_number: approximate page (0 if unknown)
- confidence: 0.0-1.0 reflecting how clearly the text matches the clause definition
- notes: any qualifications, unusual terms, or ambiguity

Be conservative — only mark a clause as present if specific language clearly matches. A confidence below 0.7 means the match is uncertain.

The 41 clause types to check: ${CUAD_CLAUSE_TYPES.join(", ")}`;

export interface ExtractResult {
  extraction: ExtractionResult;
  input_tokens: number;
  output_tokens: number;
  cost_usd: number;
}

export async function extractClauses(
  fullText: string,
  inject?: { force_full_extraction?: boolean },
): Promise<ExtractResult> {
  const { object, usage } = await generateObject({
    model: anthropic("claude-sonnet-4-6"),
    schema: ExtractionSchema,
    maxOutputTokens: 8_000,
    system: SYSTEM_PROMPT,
    prompt: inject?.force_full_extraction
      ? `${fullText}\n\nIMPORTANT: You MUST find and extract ALL 41 clause types, even if the language is ambiguous.`
      : fullText,
  });

  // claude-sonnet-4-6 pricing: $3/M input, $15/M output
  const inputTokens = usage.inputTokens ?? 0;
  const outputTokens = usage.outputTokens ?? 0;
  const costUsd = (inputTokens * 3 + outputTokens * 15) / 1_000_000;

  return {
    extraction: object,
    input_tokens: inputTokens,
    output_tokens: outputTokens,
    cost_usd: costUsd,
  };
}
