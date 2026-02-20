/**
 * Seed script — loads sample contracts from data/contracts/ and runs the
 * full analysis pipeline on each. Generated embeddings are persisted to the
 * database so semantic search works immediately after setup.
 *
 * Usage: bun run scripts/seed-data.ts
 */
import { readdirSync } from "fs";
import { join } from "path";
import pg from "pg";
import { config } from "../src/config.ts";
import { analyzeContract } from "../src/pipeline/orchestrator.ts";

const { Pool } = pg;

const CONTRACTS_DIR = join(import.meta.dir, "../data/contracts");

async function seed() {
  const pool = new Pool({ connectionString: config.databaseUrl });
  try {
    const files = readdirSync(CONTRACTS_DIR).filter(
      (f) => f.endsWith(".pdf") || f.endsWith(".txt")
    );

    if (files.length === 0) {
      console.log("No contracts found in data/contracts/. Add PDF or text files to seed.");
      return;
    }

    console.log(`Seeding ${files.length} contracts...`);

    for (const filename of files) {
      const filePath = join(CONTRACTS_DIR, filename);
      const fileData = Bun.file(filePath);
      const buffer = await fileData.arrayBuffer();
      const contentType = filename.endsWith(".pdf") ? "application/pdf" : "text/plain";
      const file = new File([buffer], filename, { type: contentType });

      console.log(`  Analyzing: ${filename}`);
      try {
        const result = await analyzeContract(file, pool);
        console.log(
          `    Done — ${result.extraction.clauses.filter((c) => c.present).length} clauses, risk: ${result.risks.overall_risk}`
        );
      } catch (err) {
        console.error(`    Failed: ${err instanceof Error ? err.message : err}`);
      }
    }

    console.log("Seed complete.");
  } finally {
    await pool.end();
  }
}

await seed();
