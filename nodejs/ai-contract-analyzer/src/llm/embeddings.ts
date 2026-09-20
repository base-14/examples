/**
 * Embedding calls wrapped in an `embeddings {model}` CLIENT span.
 *
 * Every embedding in the app goes through here: the pipeline's embed stage,
 * the semantic search route and the per-contract query route.
 */
import { SpanKind, SpanStatusCode, trace } from "@opentelemetry/api";
import { embedMany } from "ai";
import { getEmbeddingModel } from "../providers.ts";
import {
  costCounter,
  errorCounter,
  opDurationHistogram,
  tokenUsageHistogram,
} from "./instruments.ts";

const tracer = trace.getTracer("ai-contract-analyzer");

export interface EmbedOutcome {
  embeddings: number[][];
  tokens: number;
  costUsd: number;
}

export async function embedValues(values: string[]): Promise<EmbedOutcome> {
  const descriptor = getEmbeddingModel();
  const metricAttrs = {
    "gen_ai.operation.name": "embeddings",
    "gen_ai.provider.name": descriptor.target.semconvName,
    "gen_ai.request.model": descriptor.modelId,
  };

  return tracer.startActiveSpan(
    `embeddings ${descriptor.modelId}`,
    {
      kind: SpanKind.CLIENT,
      attributes: {
        ...metricAttrs,
        "server.address": descriptor.target.serverAddress,
        "server.port": descriptor.target.serverPort,
        "gen_ai.embeddings.dimension.count": descriptor.dimensions,
      },
    },
    async (span) => {
      const startMs = Date.now();
      try {
        const { embeddings, usage } = await embedMany({
          model: descriptor.model,
          values,
        });
        const costUsd = (usage.tokens * descriptor.costPerMToken) / 1_000_000;

        span.setAttribute("gen_ai.usage.input_tokens", usage.tokens);
        span.setAttribute("base14.gen_ai.cost_usd", costUsd);

        tokenUsageHistogram.record(usage.tokens, { ...metricAttrs, "gen_ai.token.type": "input" });
        costCounter.add(costUsd, metricAttrs);
        opDurationHistogram.record((Date.now() - startMs) / 1000, metricAttrs);

        span.end();
        return { embeddings, tokens: usage.tokens, costUsd };
      } catch (err) {
        const type = (err as Error)?.constructor?.name ?? "UnknownError";

        span.recordException(err as Error);
        span.setAttribute("error.type", type);
        span.setStatus({ code: SpanStatusCode.ERROR, message: (err as Error).message });

        errorCounter.add(1, {
          "gen_ai.provider.name": descriptor.target.semconvName,
          "gen_ai.request.model": descriptor.modelId,
          "error.type": type,
        });
        opDurationHistogram.record((Date.now() - startMs) / 1000, {
          ...metricAttrs,
          "error.type": type,
        });

        span.end();
        throw err;
      }
    },
  );
}
