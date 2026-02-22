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

  for (const r of risks) {
    const factors = Array.isArray(r.risk_factors) ? r.risk_factors : [String(r.risk_factors)];
    await pool.query(
      `INSERT INTO risks (contract_id, clause_type, risk_level, risk_factors, recommendation)
       VALUES ($1::uuid, $2, $3, $4::text[], $5)`,
      [contract_id, r.clause_type, r.risk_level, factors, r.recommendation ?? null],
    );
  }
}

export async function findRisksByContract(pool: Pool, contract_id: string): Promise<RiskRow[]> {
  const result = await pool.query<RiskRow>(
    "SELECT * FROM risks WHERE contract_id = $1 ORDER BY risk_level, clause_type",
    [contract_id],
  );
  return result.rows;
}
