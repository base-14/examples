import type { Pool } from "pg";
import type { Clause } from "../types/clauses.ts";

export interface ClauseRow {
  id: string;
  contract_id: string;
  clause_type: string;
  present: boolean;
  text_excerpt: string | null;
  page_number: number | null;
  confidence: string;
  notes: string | null;
  created_at: Date;
}

export async function insertClauses(
  pool: Pool,
  contract_id: string,
  clauses: Clause[],
): Promise<void> {
  if (clauses.length === 0) return;

  // Unnest-based batch insert — single round-trip for all clauses
  const clauseTypes = clauses.map((c) => c.clause_type);
  const presents = clauses.map((c) => c.present);
  const excerpts = clauses.map((c) => c.text_excerpt ?? null);
  const pageNumbers = clauses.map((c) => c.page_number ?? null);
  const confidences = clauses.map((c) => c.confidence);
  const notes = clauses.map((c) => c.notes ?? null);

  await pool.query(
    `INSERT INTO clauses (contract_id, clause_type, present, text_excerpt, page_number, confidence, notes)
     SELECT $1::uuid, * FROM unnest(
       $2::text[],
       $3::boolean[],
       $4::text[],
       $5::int[],
       $6::numeric[],
       $7::text[]
     ) AS t(clause_type, present, text_excerpt, page_number, confidence, notes)`,
    [contract_id, clauseTypes, presents, excerpts, pageNumbers, confidences, notes],
  );
}

export async function findClausesByContract(pool: Pool, contract_id: string): Promise<ClauseRow[]> {
  const result = await pool.query<ClauseRow>(
    "SELECT * FROM clauses WHERE contract_id = $1 ORDER BY clause_type",
    [contract_id],
  );
  return result.rows;
}
