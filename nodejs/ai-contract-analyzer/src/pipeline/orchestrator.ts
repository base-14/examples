import { metrics, SpanStatusCode, trace } from "@opentelemetry/api";
import type { Pool } from "pg";
import { config } from "../config.ts";
import { insertAnalysis } from "../db/analyses.ts";
import { insertChunks } from "../db/chunks.ts";
import { insertClauses } from "../db/clauses.ts";
import { createContract, updateContractStatus } from "../db/contracts.ts";
import { insertRisks } from "../db/risks.ts";
import { costCounter, tokenUsageHistogram } from "../llm/middleware.ts";
import { logger } from "../logger.ts";
import { getEmbeddingModel } from "../providers.ts";
import type { AnalysisResult } from "../types/pipeline.ts";
import { embedChunks } from "./embed.ts";
import { extractClauses } from "./extract.ts";
import { ingestDocument } from "./ingest.ts";
import { routeDocument } from "./route.ts";
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

    logger.info("Contract analysis started", { filename: file.name, size_bytes: file.size });

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

      // contractId is set inside the ingest callback — extract to a const so TypeScript knows it's string
      if (!contractId) throw new Error("Contract ID not set after ingest stage");
      const id = contractId;

      // ── Stage 0: Route ────────────────────────────────────────────────────
      const routeResult = await tracer.startActiveSpan("pipeline_stage route", async (span) => {
        span.setAttribute("pipeline.stage", "route");

        const result = await routeDocument(ingestResult.full_text);

        span.setAttribute("route.document_type", result.document_type);
        span.setAttribute("route.complexity", result.complexity);
        span.setAttribute("route.requires_full_analysis", result.requires_full_analysis);
        span.setAttribute("gen_ai.usage.input_tokens", result.input_tokens);
        span.end();

        if (result.document_type === "unknown") {
          throw Object.assign(new Error("Document is not a recognized contract type"), {
            code: "UNSUPPORTED_TYPE",
          });
        }

        totalTokens += result.input_tokens;
        totalCost += result.cost_usd;
        return result;
      });

      // ── Stages 2 & 3: Embed + Extract (concurrent — both need only ingest output) ──
      const [, extractResult] = await Promise.all([
        tracer.startActiveSpan("pipeline_stage embed", async (span) => {
          span.setAttribute("pipeline.stage", "embed");

          const embedStart = Date.now();
          const embedResult = await embedChunks(ingestResult.chunks, inject);
          const embedDurationS = (Date.now() - embedStart) / 1000;
          await insertChunks(pool, id, ingestResult.chunks, embedResult.embeddings);

          const embeddingDescriptor = getEmbeddingModel();
          const embedModelId = embeddingDescriptor.modelId;
          const embedCostUsd =
            (embedResult.total_tokens * embeddingDescriptor.costPerMToken) / 1_000_000;

          span.setAttribute("embedding.chunk_count", ingestResult.chunks.length);
          span.setAttribute("embedding.dimensions", embeddingDescriptor.dimensions);
          span.setAttribute("embedding.batch_count", embedResult.batch_count);
          span.setAttribute("gen_ai.usage.input_tokens", embedResult.total_tokens);

          // Embedding token usage — gen_ai.operation.name + provider required by contract
          const embedProviderName = config.embeddingProvider;
          tokenUsageHistogram.record(embedResult.total_tokens, {
            "gen_ai.operation.name": "embeddings",
            "gen_ai.provider.name": embedProviderName,
            "gen_ai.request.model": embedModelId,
            "gen_ai.token.type": "input",
          });
          embeddingDuration.record(embedDurationS, {
            "embedding.model": embedModelId,
          });
          costCounter.add(embedCostUsd, {
            "gen_ai.operation.name": "embeddings",
            "gen_ai.provider.name": embedProviderName,
            "gen_ai.request.model": embedModelId,
          });
          totalTokens += embedResult.total_tokens;
          totalCost += embedCostUsd;

          span.end();
        }),

        tracer.startActiveSpan("pipeline_stage extract", async (span) => {
          span.setAttribute("pipeline.stage", "extract");

          const result = await extractClauses(
            ingestResult.full_text,
            inject,
            routeResult.document_type,
          );
          await insertClauses(pool, id, result.extraction.clauses);

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
          span.setAttribute("extraction.eval_iterations", result.eval_iterations);
          span.setAttribute("gen_ai.usage.input_tokens", result.input_tokens);
          span.setAttribute("gen_ai.usage.output_tokens", result.output_tokens);

          clausesExtracted.record(presentClauses.length, {
            contract_type: result.extraction.contract_type,
          });
          totalTokens += result.input_tokens + result.output_tokens;
          totalCost += result.cost_usd;

          await updateContractStatus(pool, id, "processing", result.extraction.contract_type);
          span.end();
          return result;
        }),
      ]);

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
        await insertRisks(pool, id, result.risks.clause_risks);

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
      await insertAnalysis(pool, id, analysisResult, traceId);
      await updateContractStatus(pool, id, "complete");

      rootSpan.setAttribute("pipeline.total_stages", 6);
      rootSpan.setAttribute("route.document_type", routeResult.document_type);
      rootSpan.setAttribute("route.complexity", routeResult.complexity);
      rootSpan.setAttribute("pipeline.status", "complete");
      rootSpan.setAttribute("pipeline.total_tokens", totalTokens);
      rootSpan.setAttribute("pipeline.total_cost_usd", Math.round(totalCost * 10_000) / 10_000);
      rootSpan.setAttribute("pipeline.duration_ms", totalDurationMs);

      analysisDuration.record(totalDurationMs / 1000, {
        "document.type": file.type,
        "risk.overall": scoreResult.risks.overall_risk,
      });

      logger.info("Contract analysis complete", {
        filename: file.name,
        duration_ms: totalDurationMs,
        total_tokens: totalTokens,
        overall_risk: scoreResult.risks.overall_risk,
      });
      rootSpan.end();
      return { ...analysisResult, trace_id: traceId };
    } catch (err) {
      if (contractId) {
        await updateContractStatus(pool, contractId, "error").catch(() => {});
      }
      logger.error("Contract analysis failed", {
        filename: file.name,
        error: (err as Error).message,
      });
      rootSpan.recordException(err as Error);
      rootSpan.setStatus({ code: SpanStatusCode.ERROR, message: (err as Error).message });
      rootSpan.end();
      throw err;
    }
  });
}
