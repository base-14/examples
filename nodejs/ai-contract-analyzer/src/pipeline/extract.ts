import { generateObject } from "ai";
import { z } from "zod";
import { getCapableModel, getFastModel } from "../providers.ts";
import { CLAUSES_BY_TYPE, ClauseSchema, CUAD_CLAUSE_TYPES } from "../types/clauses.ts";
import type { ExtractionResult } from "../types/pipeline.ts";

const ExtractionSchema = z.object({
  clauses: z
    .array(ClauseSchema)
    .describe(
      "One entry per clause type listed. Set present=false for clauses not found in the contract.",
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

const EvaluationSchema = z.object({
  passed: z.boolean(),
  issues: z.array(z.string()).describe("Specific issues found, empty if passed"),
});

function buildSystemPrompt(clauseTypes: readonly string[]): string {
  return `You are a contract analysis expert with deep knowledge of commercial contracts.

Your task: extract all relevant clauses and metadata from the provided contract text.

For each clause type listed below, determine:
- present: true only if you can quote specific language from the contract
- text_excerpt: the exact quote (empty string if not present)
- page_number: approximate page (0 if unknown)
- confidence: 0.0-1.0 reflecting how clearly the text matches the clause definition
- notes: any qualifications, unusual terms, or ambiguity

Be conservative — only mark a clause as present if specific language clearly matches. A confidence below 0.7 means the match is uncertain.

Clause types to check (${clauseTypes.length}): ${clauseTypes.join(", ")}`;
}

export interface ExtractResult {
  extraction: ExtractionResult;
  input_tokens: number;
  output_tokens: number;
  cost_usd: number;
  eval_iterations: number;
}

const MAX_EVAL_ITERATIONS = 3;

export async function extractClauses(
  fullText: string,
  inject?: { force_full_extraction?: boolean },
  documentType?: string,
): Promise<ExtractResult> {
  const clauseTypes = inject?.force_full_extraction
    ? CUAD_CLAUSE_TYPES
    : (CLAUSES_BY_TYPE[documentType ?? ""] ?? CUAD_CLAUSE_TYPES);

  const systemPrompt = buildSystemPrompt(clauseTypes);
  // Contract preview used by the evaluator — first 2000 chars is enough to spot hallucinated excerpts
  const contractPreview = fullText.slice(0, 2000);

  let totalInputTokens = 0;
  let totalOutputTokens = 0;
  let totalCostUsd = 0;
  let lastExtraction: z.infer<typeof ExtractionSchema> | null = null;
  let feedback: string[] = [];
  let evalIterationsCompleted = 0;

  for (let iteration = 0; iteration < MAX_EVAL_ITERATIONS; iteration++) {
    evalIterationsCompleted = iteration + 1;
    // ── Generator ──────────────────────────────────────────────────────────
    const generatorPrompt =
      feedback.length > 0
        ? `${fullText}\n\nPrevious extraction had these issues — please fix them:\n${feedback.map((f) => `- ${f}`).join("\n")}`
        : fullText;

    const capableDescriptor = getCapableModel();
    const { object, usage: genUsage } = await generateObject({
      model: capableDescriptor.model,
      schema: ExtractionSchema,
      maxOutputTokens: 8_000,
      system: systemPrompt,
      prompt: generatorPrompt,
    });

    const genInput = genUsage.inputTokens ?? 0;
    const genOutput = genUsage.outputTokens ?? 0;
    totalInputTokens += genInput;
    totalOutputTokens += genOutput;
    totalCostUsd +=
      (genInput * capableDescriptor.inputCostPerMToken +
        genOutput * capableDescriptor.outputCostPerMToken) /
      1_000_000;
    lastExtraction = object;

    // ── Evaluator (different model — catches different failure modes) ───────
    const presentWithEmptyExcerpt = object.clauses
      .filter((c) => c.present && c.text_excerpt.trim() === "")
      .map((c) => c.clause_type);

    const highConfidenceAbsent = object.clauses
      .filter((c) => !c.present && c.confidence > 0.5)
      .map((c) => c.clause_type);

    const evalPrompt = `Contract excerpt (first 2000 chars):
${contractPreview}

Extracted data:
- contract_type: ${object.contract_type}
- parties: ${object.parties.map((p) => p.name).join(", ") || "(none)"}
- clauses marked present: ${object.clauses.filter((c) => c.present).length}
- clauses present but missing text_excerpt: ${presentWithEmptyExcerpt.join(", ") || "(none)"}
- clauses absent but confidence > 0.5: ${highConfidenceAbsent.join(", ") || "(none)"}

Check for:
1. Clauses marked present=true with an empty text_excerpt (excerpt is required when present)
2. Clauses marked present=false with confidence above 0.5 (suggests uncertain absence — should re-check)
3. contract_type missing or implausible
4. parties array empty when parties are visible in the excerpt`;

    const fastDescriptor = getFastModel();
    const { object: evaluation, usage: evalUsage } = await generateObject({
      model: fastDescriptor.model,
      schema: EvaluationSchema,
      system:
        "You are a contract data validator. Return passed=true only if none of the listed issues are present.",
      prompt: evalPrompt,
    });

    const evalInput = evalUsage.inputTokens ?? 0;
    const evalOutput = evalUsage.outputTokens ?? 0;
    totalInputTokens += evalInput;
    totalOutputTokens += evalOutput;
    totalCostUsd +=
      (evalInput * fastDescriptor.inputCostPerMToken +
        evalOutput * fastDescriptor.outputCostPerMToken) /
      1_000_000;

    if (evaluation.passed) break;
    feedback = evaluation.issues;
  }

  if (!lastExtraction) throw new Error("Extraction loop produced no result");
  return {
    extraction: lastExtraction,
    input_tokens: totalInputTokens,
    output_tokens: totalOutputTokens,
    cost_usd: totalCostUsd,
    eval_iterations: evalIterationsCompleted,
  };
}
