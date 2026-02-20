import { readFileSync } from "fs";
import { join } from "path";
import pg from "pg";
import { config } from "../src/config.ts";

const { Pool } = pg;

async function migrate() {
  const pool = new Pool({ connectionString: config.databaseUrl });
  try {
    const schema = readFileSync(join(import.meta.dir, "../db/schema.sql"), "utf-8");
    await pool.query(schema);
    console.log("Migration complete");
  } finally {
    await pool.end();
  }
}

await migrate();
