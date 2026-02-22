import { generateObject } from "ai";
import { z } from "zod";
import { getCapableModel } from "../providers.ts";
import type { ExtractionResult, RiskResult, SummaryResult } from "../types/pipeline.ts";

const SummarySchema = z.object({
  executive_summary: z.string().describe("2-3 paragraphs in plain language. No legal jargon."),
  key_terms: z.array(
    z.object({
      term: z.string().describe("e.g. Contract Duration, Payment Terms, Termination Notice"),
      value: z.string().describe("The actual value or clause text"),
    }),
  ),
  key_risks: z.array(
    z.object({
      risk: z.string(),
      severity: z.enum(["critical", "high", "medium", "low"]),
      recommendation: z.string(),
    }),
  ),
  negotiation_points: z
    .array(z.string())
    .describe("Specific items a party should push back on or negotiate"),
});

export interface SummarizeResult {
  summary: SummaryResult;
  input_tokens: number;
  output_tokens: number;
  cost_usd: number;
}

export async function generateSummary(
  extraction: ExtractionResult,
  risks: RiskResult,
): Promise<SummarizeResult> {
  const criticalAndHigh = risks.clause_risks
    .filter((r) => r.risk_level === "critical" || r.risk_level === "high")
    .map((r) => `${r.clause_type} (${r.risk_level}): ${r.risk_factors.join("; ")}`)
    .join("\n");

  const presentClauses = extraction.clauses
    .filter((c) => c.present)
    .map((c) => `${c.clause_type}: ${c.text_excerpt.slice(0, 150)}`)
    .join("\n");

  const prompt = `Contract type: ${extraction.contract_type}
Parties: ${extraction.parties.map((p) => `${p.name} (${p.role})`).join(", ")}
Effective date: ${extraction.effective_date ?? "not specified"}
Expiration: ${extraction.expiration_date ?? "not specified"}
Governing law: ${extraction.governing_law ?? "not specified"}
Overall risk: ${risks.overall_risk}

Present clauses (${extraction.clauses.filter((c) => c.present).length} of 41):
${presentClauses || "(none found)"}

High-severity risks:
${criticalAndHigh || "(none)"}

Missing required clauses:
${
  risks.missing_clauses
    .filter((m) => m.importance === "required")
    .map((m) => `${m.clause_type}: ${m.explanation}`)
    .join("\n") || "(none)"
}`;

  const capableDescriptor = getCapableModel();
  const { object, usage } = await generateObject({
    model: capableDescriptor.model,
    schema: SummarySchema,
    maxOutputTokens: 2_000,
    system: `You are a senior attorney writing a contract review memo for a business client.
Write in clear, plain English — no Latin phrases, no unnecessary jargon.
The executive summary should explain what this contract does, who it protects, and what the key concerns are.
Key terms should capture the most commercially significant provisions.
Negotiation points should be specific and actionable.`,
    prompt,
  });

  const inputTokens = usage.inputTokens ?? 0;
  const outputTokens = usage.outputTokens ?? 0;
  const costUsd =
    (inputTokens * capableDescriptor.inputCostPerMToken +
      outputTokens * capableDescriptor.outputCostPerMToken) /
    1_000_000;

  return {
    summary: object,
    input_tokens: inputTokens,
    output_tokens: outputTokens,
    cost_usd: costUsd,
  };
}
