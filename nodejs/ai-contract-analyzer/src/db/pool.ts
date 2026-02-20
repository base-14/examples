import { Pool } from "pg";
import { config } from "../config.ts";
import { registerVectorTypes } from "./chunks.ts";

let pool: Pool | null = null;

export function getPool(): Pool {
  if (!pool) {
    pool = new Pool({ connectionString: config.databaseUrl });
    registerVectorTypes(pool);
  }
  return pool;
}

export async function closePool(): Promise<void> {
  if (pool) {
    await pool.end();
    pool = null;
  }
}
