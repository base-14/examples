import { generateObject } from "ai";
import { z } from "zod";
import { getFastModel } from "../providers.ts";
import { CUAD_CLAUSE_TYPES } from "../types/clauses.ts";
import type { ExtractionResult, RiskResult } from "../types/pipeline.ts";

const RiskLevelEnum = z.enum(["critical", "high", "medium", "low", "none"]);

const RiskSchema = z.object({
  clause_risks: z.array(
    z.object({
      clause_type: z.enum(CUAD_CLAUSE_TYPES),
      risk_level: RiskLevelEnum,
      risk_factors: z.preprocess(
        (v) =>
          typeof v === "string"
            ? v
                .split(",")
                .map((s) => s.trim())
                .filter(Boolean)
            : v,
        z.array(z.string()),
      ),
      recommendation: z.string(),
    }),
  ),
  overall_risk: z.enum(["critical", "high", "medium", "low"]),
  missing_clauses: z.array(
    z.object({
      clause_type: z.enum(CUAD_CLAUSE_TYPES),
      importance: z.enum(["required", "recommended", "optional"]),
      explanation: z.string(),
    }),
  ),
});

export interface ScoreResult {
  risks: RiskResult;
  input_tokens: number;
  output_tokens: number;
  cost_usd: number;
}

export async function scoreRisks(extraction: ExtractionResult): Promise<ScoreResult> {
  const presentClauses = extraction.clauses
    .filter((c) => c.present)
    .map((c) => `${c.clause_type}: "${c.text_excerpt.slice(0, 200)}"`)
    .join("\n");

  const missingClauses = extraction.clauses
    .filter((c) => !c.present)
    .map((c) => c.clause_type)
    .join(", ");

  const prompt = `Contract type: ${extraction.contract_type}
Parties: ${extraction.parties.map((p) => `${p.name} (${p.role})`).join(", ")}
Governing law: ${extraction.governing_law ?? "not specified"}

Present clauses:
${presentClauses || "(none found)"}

Missing clause types: ${missingClauses || "(none missing)"}

Assess the risk level for each present clause and identify which missing clauses are concerning.`;

  const fastDescriptor = getFastModel();
  const { object, usage } = await generateObject({
    model: fastDescriptor.model,
    schema: RiskSchema,
    maxOutputTokens: 3_000,
    experimental_telemetry: { isEnabled: true, functionId: "pipeline.score" },
    system: `You are a contract risk analyst. For each present clause, assess:
- risk_level: critical (immediate action), high (significant concern), medium (review), low (acceptable), none (standard)
- risk_factors: specific reasons the clause poses risk
- recommendation: concrete action for the reviewing attorney

For missing clauses, note which are required by standard practice, recommended, or optional for this contract type.

Set overall_risk to the highest risk level found across all clauses.`,
    prompt,
  });

  const inputTokens = usage.inputTokens ?? 0;
  const outputTokens = usage.outputTokens ?? 0;
  const costUsd =
    (inputTokens * fastDescriptor.inputCostPerMToken +
      outputTokens * fastDescriptor.outputCostPerMToken) /
    1_000_000;

  return {
    risks: object,
    input_tokens: inputTokens,
    output_tokens: outputTokens,
    cost_usd: costUsd,
  };
}
