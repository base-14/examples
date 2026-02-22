import { SpanStatusCode, trace } from "@opentelemetry/api";
import { Hono } from "hono";
import { findAnalysisByContract } from "../db/analyses.ts";
import { findClausesByContract } from "../db/clauses.ts";
import { findContractById, listContracts } from "../db/contracts.ts";
import { getPool } from "../db/pool.ts";
import { findRisksByContract } from "../db/risks.ts";
import { logger } from "../logger.ts";
import { analyzeContract } from "../pipeline/orchestrator.ts";

const tracer = trace.getTracer("ai-contract-analyzer");
export const contracts = new Hono();

// POST /api/contracts — upload + analyze
contracts.post("/contracts", async (c) => {
  const formData = await c.req.formData();
  const file = formData.get("file");

  if (!file || !(file instanceof File)) {
    return c.json({ error: "field 'file' is required (multipart/form-data)" }, 400);
  }

  const allowed = ["application/pdf", "text/plain"];
  if (!allowed.some((t) => file.type === t || file.type.startsWith(`${t};`))) {
    return c.json(
      { error: `unsupported file type '${file.type}', use application/pdf or text/plain` },
      415,
    );
  }

  const pool = getPool();

  return tracer.startActiveSpan("POST /api/contracts", async (span) => {
    span.setAttribute("document.filename", file.name);
    span.setAttribute("document.size_bytes", file.size);
    try {
      const result = await analyzeContract(file, pool);
      span.setAttribute("contract.id", result.ingest.contract_id);
      span.setAttribute("risk.overall", result.risks.overall_risk);
      span.end();
      return c.json(
        {
          contract_id: result.ingest.contract_id,
          filename: result.ingest.contract_id,
          overall_risk: result.risks.overall_risk,
          clauses_found: result.extraction.clauses.filter((cl) => cl.present).length,
          total_duration_ms: result.total_duration_ms,
          trace_id: result.trace_id,
        },
        201,
      );
    } catch (err) {
      logger.error("Contract analysis failed", {
        filename: file.name,
        error: (err as Error).message,
      });
      span.recordException(err as Error);
      span.setStatus({ code: SpanStatusCode.ERROR, message: (err as Error).message });
      span.end();
      const code = (err as { code?: string }).code;
      if (code === "PARSE_ERROR") return c.json({ error: (err as Error).message }, 422);
      if (code === "UNSUPPORTED_TYPE") return c.json({ error: (err as Error).message }, 415);
      return c.json({ error: "analysis failed" }, 500);
    }
  });
});

// GET /api/contracts — list all contracts
contracts.get("/contracts", async (c) => {
  const pool = getPool();
  const rows = await listContracts(pool);
  return c.json({ contracts: rows });
});

// GET /api/contracts/:id — full analysis result
contracts.get("/contracts/:id", async (c) => {
  const { id } = c.req.param();
  const pool = getPool();

  const contract = await findContractById(pool, id);
  if (!contract) return c.json({ error: "contract not found" }, 404);

  const [clauses, risks, analysis] = await Promise.all([
    findClausesByContract(pool, id),
    findRisksByContract(pool, id),
    findAnalysisByContract(pool, id),
  ]);

  return c.json({
    contract: {
      id: contract.id,
      filename: contract.filename,
      contract_type: contract.contract_type,
      status: contract.status,
      page_count: contract.page_count,
      total_characters: contract.total_characters,
      created_at: contract.created_at,
    },
    analysis,
    clauses: clauses.filter((cl) => cl.present),
    risks,
  });
});
