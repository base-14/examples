import type { Pool } from "pg";
import type { AnalysisRow } from "../types/contracts.ts";
import type { AnalysisResult } from "../types/pipeline.ts";

export async function insertAnalysis(
  pool: Pool,
  contract_id: string,
  result: AnalysisResult,
  traceId?: string,
): Promise<AnalysisRow> {
  const row = await pool.query<AnalysisRow>(
    `INSERT INTO analyses (
       contract_id, overall_risk, executive_summary, key_terms, key_risks,
       negotiation_points, missing_clauses, parties, effective_date, expiration_date,
       governing_law, total_duration_ms, total_tokens, total_cost_usd, trace_id
     ) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15)
     RETURNING *`,
    [
      contract_id,
      result.risks.overall_risk,
      result.summary.executive_summary,
      JSON.stringify(result.summary.key_terms),
      JSON.stringify(result.summary.key_risks),
      result.summary.negotiation_points,
      JSON.stringify(result.risks.missing_clauses),
      JSON.stringify(result.extraction.parties),
      result.extraction.effective_date,
      result.extraction.expiration_date,
      result.extraction.governing_law,
      result.total_duration_ms,
      result.total_tokens,
      result.total_cost_usd,
      traceId ?? null,
    ],
  );
  const inserted = row.rows[0];
  if (!inserted) throw new Error("INSERT into analyses returned no rows");
  return inserted;
}

export async function findAnalysisByContract(
  pool: Pool,
  contract_id: string,
): Promise<AnalysisRow | null> {
  const result = await pool.query<AnalysisRow>(
    "SELECT * FROM analyses WHERE contract_id = $1 ORDER BY created_at DESC LIMIT 1",
    [contract_id],
  );
  return result.rows[0] ?? null;
}
