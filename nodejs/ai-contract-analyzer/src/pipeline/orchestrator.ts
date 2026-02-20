import { metrics, SpanStatusCode, trace } from "@opentelemetry/api";
import type { Pool } from "pg";
import { insertAnalysis } from "../db/analyses.ts";
import { insertChunks } from "../db/chunks.ts";
import { insertClauses } from "../db/clauses.ts";
import { createContract, updateContractStatus } from "../db/contracts.ts";
import { insertRisks } from "../db/risks.ts";
import type { AnalysisResult } from "../types/pipeline.ts";
import { embedChunks } from "./embed.ts";
import { extractClauses } from "./extract.ts";
import { ingestDocument } from "./ingest.ts";
import { scoreRisks } from "./score.ts";
import { generateSummary } from "./summarize.ts";

const tracer = trace.getTracer("ai-contract-analyzer");
const meter = metrics.getMeter("ai-contract-analyzer");

const analysisDuration = meter.createHistogram("contract.analysis.duration", {
  description: "Total contract analysis pipeline duration",
  unit: "s",
});
const clausesExtracted = meter.createHistogram("contract.clauses.extracted", {
  description: "Number of clauses extracted per contract",
  unit: "{clause}",
});
const riskScore = meter.createHistogram("contract.risk.score", {
  description: "Risk score distribution per contract",
  unit: "1",
});
const tokenUsage = meter.createHistogram("gen_ai.client.token.usage", {
  description: "LLM token usage per pipeline stage",
  unit: "{token}",
});
const aiCost = meter.createCounter("gen_ai.client.cost", {
  description: "LLM cost per pipeline stage",
  unit: "usd",
});
const embeddingDuration = meter.createHistogram("contract.embedding.duration", {
  description: "Time to generate embeddings for all chunks",
  unit: "s",
});

export interface PipelineInjections {
  force_full_extraction?: boolean;
  disable_chunking_fallback?: boolean;
  embedding_error?: "rate_limit" | "server_error";
}

const RISK_LEVEL_SCORE: Record<string, number> = {
  critical: 1.0,
  high: 0.75,
  medium: 0.5,
  low: 0.25,
  none: 0.0,
};

export async function analyzeContract(
  file: File,
  pool: Pool,
  inject?: PipelineInjections,
): Promise<AnalysisResult> {
  const startMs = Date.now();

  return tracer.startActiveSpan("analyze_contract", async (rootSpan) => {
    rootSpan.setAttribute("document.filename", file.name);
    rootSpan.setAttribute("document.size_bytes", file.size);
    rootSpan.setAttribute("document.content_type", file.type);

    let contractId: string | undefined;
    let totalTokens = 0;
    let totalCost = 0;

    try {
      // ── Stage 1: Ingest ───────────────────────────────────────────────────
      const ingestResult = await tracer.startActiveSpan("pipeline_stage ingest", async (span) => {
        span.setAttribute("pipeline.stage", "ingest");
        span.setAttribute("document.filename", file.name);

        // Create DB record first so we have an ID for all subsequent inserts
        const contract = await createContract(pool, {
          filename: file.name,
          content_type: file.type || "text/plain",
          full_text: "",
          page_count: 0,
          total_characters: 0,
        });
        contractId = contract.id;
        await updateContractStatus(pool, contractId, "processing");

        const result = await ingestDocument(file, contractId, inject);

        // Back-fill full_text and page stats now that we have them
        await pool.query(
          "UPDATE contracts SET full_text=$1, page_count=$2, total_characters=$3 WHERE id=$4",
          [result.full_text, result.page_count, result.total_characters, contractId],
        );

        span.setAttribute("document.page_count", result.page_count);
        span.setAttribute("document.total_characters", result.total_characters);
        span.setAttribute("document.chunks_created", result.chunks.length);
        span.setAttribute(
          "document.parse_method",
          file.type === "application/pdf" ? "pdf-parse" : "utf-8",
        );
        span.end();
        return result;
      });

      // ── Stage 2: Embed ────────────────────────────────────────────────────
      await tracer.startActiveSpan("pipeline_stage embed", async (span) => {
        span.setAttribute("pipeline.stage", "embed");

        const embedStart = Date.now();
        const embedResult = await embedChunks(ingestResult.chunks, inject);
        const embedDurationS = (Date.now() - embedStart) / 1000;
        await insertChunks(pool, contractId!, ingestResult.chunks, embedResult.embeddings);

        span.setAttribute("embedding.chunk_count", ingestResult.chunks.length);
        span.setAttribute("embedding.dimensions", 1536);
        span.setAttribute("embedding.batch_count", embedResult.batch_count);
        span.setAttribute("gen_ai.usage.input_tokens", embedResult.total_tokens);

        tokenUsage.record(embedResult.total_tokens, {
          "gen_ai.token.type": "input",
          "gen_ai.request.model": "text-embedding-3-small",
          "pipeline.stage": "embed",
        });
        embeddingDuration.record(embedDurationS, {
          "embedding.model": "text-embedding-3-small",
        });
        totalTokens += embedResult.total_tokens;

        span.end();
      });

      // ── Stage 3: Extract ──────────────────────────────────────────────────
      const extractResult = await tracer.startActiveSpan("pipeline_stage extract", async (span) => {
        span.setAttribute("pipeline.stage", "extract");

        const result = await extractClauses(ingestResult.full_text, inject);
        await insertClauses(pool, contractId!, result.extraction.clauses);

        const presentClauses = result.extraction.clauses.filter((c) => c.present);
        const avgConfidence =
          presentClauses.length > 0
            ? presentClauses.reduce((s, c) => s + c.confidence, 0) / presentClauses.length
            : 0;

        span.setAttribute("extraction.clauses_found", presentClauses.length);
        span.setAttribute(
          "extraction.clause_types",
          presentClauses.map((c) => c.clause_type).join(","),
        );
        span.setAttribute("extraction.confidence_avg", Math.round(avgConfidence * 100) / 100);
        span.setAttribute("extraction.parties_count", result.extraction.parties.length);
        span.setAttribute("extraction.contract_type", result.extraction.contract_type);
        span.setAttribute("gen_ai.usage.input_tokens", result.input_tokens);
        span.setAttribute("gen_ai.usage.output_tokens", result.output_tokens);

        clausesExtracted.record(presentClauses.length, {
          contract_type: result.extraction.contract_type,
        });
        tokenUsage.record(result.input_tokens, {
          "gen_ai.token.type": "input",
          "gen_ai.request.model": "claude-sonnet-4-6",
          "pipeline.stage": "extract",
        });
        tokenUsage.record(result.output_tokens, {
          "gen_ai.token.type": "output",
          "gen_ai.request.model": "claude-sonnet-4-6",
          "pipeline.stage": "extract",
        });
        aiCost.add(result.cost_usd, {
          "gen_ai.request.model": "claude-sonnet-4-6",
          "pipeline.stage": "extract",
        });
        totalTokens += result.input_tokens + result.output_tokens;
        totalCost += result.cost_usd;

        await updateContractStatus(
          pool,
          contractId!,
          "processing",
          result.extraction.contract_type,
        );
        span.end();
        return result;
      });

      // ── Stage 4: Score ────────────────────────────────────────────────────
      const scoreResult = await tracer.startActiveSpan("pipeline_stage score", async (span) => {
        span.setAttribute("pipeline.stage", "score");

        // Cross-stage validation: flag if extract found no liability protection
        const hasLiabilityCap = extractResult.extraction.clauses.some(
          (c) =>
            c.present &&
            (c.clause_type === "liability_cap" || c.clause_type === "cap_on_liability"),
        );
        span.setAttribute("validation.has_liability_cap", hasLiabilityCap);

        const result = await scoreRisks(extractResult.extraction);
        await insertRisks(pool, contractId!, result.risks.clause_risks);

        const criticalCount = result.risks.clause_risks.filter(
          (r) => r.risk_level === "critical",
        ).length;
        const highCount = result.risks.clause_risks.filter((r) => r.risk_level === "high").length;

        span.setAttribute("risk.overall", result.risks.overall_risk);
        span.setAttribute("risk.critical_count", criticalCount);
        span.setAttribute("risk.high_count", highCount);
        span.setAttribute(
          "risk.missing_required",
          result.risks.missing_clauses.filter((m) => m.importance === "required").length,
        );
        span.setAttribute("gen_ai.usage.input_tokens", result.input_tokens);
        span.setAttribute("gen_ai.usage.output_tokens", result.output_tokens);

        riskScore.record(RISK_LEVEL_SCORE[result.risks.overall_risk] ?? 0, {
          contract_type: extractResult.extraction.contract_type,
          "risk.overall": result.risks.overall_risk,
        });
        tokenUsage.record(result.input_tokens + result.output_tokens, {
          "gen_ai.request.model": "claude-haiku-4-5-20251001",
          "pipeline.stage": "score",
        });
        aiCost.add(result.cost_usd, {
          "gen_ai.request.model": "claude-haiku-4-5-20251001",
          "pipeline.stage": "score",
        });
        totalTokens += result.input_tokens + result.output_tokens;
        totalCost += result.cost_usd;

        span.end();
        return result;
      });

      // ── Stage 5: Summarize ────────────────────────────────────────────────
      const summaryResult = await tracer.startActiveSpan(
        "pipeline_stage summarize",
        async (span) => {
          span.setAttribute("pipeline.stage", "summarize");

          const result = await generateSummary(extractResult.extraction, scoreResult.risks);
          const wordCount = result.summary.executive_summary.split(/\s+/).length;

          span.setAttribute("summary.word_count", wordCount);
          span.setAttribute("summary.key_risks_count", result.summary.key_risks.length);
          span.setAttribute(
            "summary.negotiation_points_count",
            result.summary.negotiation_points.length,
          );
          span.setAttribute("gen_ai.usage.input_tokens", result.input_tokens);
          span.setAttribute("gen_ai.usage.output_tokens", result.output_tokens);

          tokenUsage.record(result.input_tokens + result.output_tokens, {
            "gen_ai.request.model": "claude-sonnet-4-6",
            "pipeline.stage": "summarize",
          });
          aiCost.add(result.cost_usd, {
            "gen_ai.request.model": "claude-sonnet-4-6",
            "pipeline.stage": "summarize",
          });
          totalTokens += result.input_tokens + result.output_tokens;
          totalCost += result.cost_usd;

          span.end();
          return result;
        },
      );

      // ── Finalize ──────────────────────────────────────────────────────────
      const totalDurationMs = Date.now() - startMs;

      const analysisResult: AnalysisResult = {
        ingest: ingestResult,
        extraction: extractResult.extraction,
        risks: scoreResult.risks,
        summary: summaryResult.summary,
        total_duration_ms: totalDurationMs,
        total_tokens: totalTokens,
        total_cost_usd: totalCost,
      };

      const traceId = rootSpan.spanContext().traceId;
      await insertAnalysis(pool, contractId!, analysisResult, traceId);
      await updateContractStatus(pool, contractId!, "complete");

      rootSpan.setAttribute("pipeline.total_stages", 5);
      rootSpan.setAttribute("pipeline.status", "complete");
      rootSpan.setAttribute("pipeline.total_tokens", totalTokens);
      rootSpan.setAttribute("pipeline.total_cost_usd", Math.round(totalCost * 10_000) / 10_000);
      rootSpan.setAttribute("pipeline.duration_ms", totalDurationMs);

      analysisDuration.record(totalDurationMs / 1000, {
        "document.type": file.type,
        "risk.overall": scoreResult.risks.overall_risk,
      });

      rootSpan.end();
      return { ...analysisResult, trace_id: traceId };
    } catch (err) {
      if (contractId) {
        await updateContractStatus(pool, contractId, "error").catch(() => {});
      }
      rootSpan.recordException(err as Error);
      rootSpan.setStatus({ code: SpanStatusCode.ERROR, message: (err as Error).message });
      rootSpan.end();
      throw err;
    }
  });
}
