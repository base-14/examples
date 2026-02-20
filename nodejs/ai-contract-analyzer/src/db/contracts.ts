import type { Pool } from "pg";
import type { ContractRow, ContractStatus, ContractSummary } from "../types/contracts.ts";

export async function createContract(
  pool: Pool,
  data: {
    filename: string;
    content_type: string;
    full_text: string;
    page_count: number;
    total_characters: number;
  },
): Promise<ContractRow> {
  const result = await pool.query<ContractRow>(
    `INSERT INTO contracts (filename, content_type, full_text, page_count, total_characters)
     VALUES ($1, $2, $3, $4, $5)
     RETURNING *`,
    [data.filename, data.content_type, data.full_text, data.page_count, data.total_characters],
  );
  const inserted = result.rows[0];
  if (!inserted) throw new Error("INSERT into contracts returned no rows");
  return inserted;
}

export async function findContractById(pool: Pool, id: string): Promise<ContractRow | null> {
  const result = await pool.query<ContractRow>("SELECT * FROM contracts WHERE id = $1", [id]);
  return result.rows[0] ?? null;
}

export async function listContracts(pool: Pool): Promise<ContractSummary[]> {
  const result = await pool.query<ContractSummary>(
    `SELECT id, filename, contract_type, status, created_at
     FROM contracts
     ORDER BY created_at DESC`,
  );
  return result.rows;
}

export async function updateContractStatus(
  pool: Pool,
  id: string,
  status: ContractStatus,
  contract_type?: string,
): Promise<void> {
  if (contract_type) {
    await pool.query("UPDATE contracts SET status = $1, contract_type = $2 WHERE id = $3", [
      status,
      contract_type,
      id,
    ]);
  } else {
    await pool.query("UPDATE contracts SET status = $1 WHERE id = $2", [status, id]);
  }
}
