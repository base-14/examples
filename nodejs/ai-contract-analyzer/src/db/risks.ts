import type { Pool } from "pg";
import type { ClauseRisk } from "../types/pipeline.ts";

export interface RiskRow {
  id: string;
  contract_id: string;
  clause_type: string;
  risk_level: string;
  risk_factors: string[];
  recommendation: string | null;
  created_at: Date;
}

export async function insertRisks(
  pool: Pool,
  contract_id: string,
  risks: ClauseRisk[],
): Promise<void> {
  if (risks.length === 0) return;

  const clauseTypes = risks.map((r) => r.clause_type);
  const riskLevels = risks.map((r) => r.risk_level);
  const riskFactors = risks.map((r) => r.risk_factors);
  const recommendations = risks.map((r) => r.recommendation ?? null);

  await pool.query(
    `INSERT INTO risks (contract_id, clause_type, risk_level, risk_factors, recommendation)
     SELECT $1::uuid, * FROM unnest(
       $2::text[],
       $3::text[],
       $4::text[][],
       $5::text[]
     ) AS t(clause_type, risk_level, risk_factors, recommendation)`,
    [contract_id, clauseTypes, riskLevels, riskFactors, recommendations],
  );
}

export async function findRisksByContract(pool: Pool, contract_id: string): Promise<RiskRow[]> {
  const result = await pool.query<RiskRow>(
    "SELECT * FROM risks WHERE contract_id = $1 ORDER BY risk_level, clause_type",
    [contract_id],
  );
  return result.rows;
}
