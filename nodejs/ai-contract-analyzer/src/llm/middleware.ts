/**
 * OTel GenAI Semantic Convention middleware for AI SDK v6.
 *
 * Wraps every LanguageModelV3 call with:
 * - A `gen_ai.chat {model}` span carrying all required semconv attributes
 * - `gen_ai.user.message` / `gen_ai.assistant.message` span events (truncated)
 * - Application-level retry (3 attempts, exponential backoff 1–10 s) on all errors
 * - Metrics: operation.duration, error.count, retry.count
 *
 * Usage (providers.ts):
 *   import { withSemconv } from "./llm/middleware.ts";
 *   const model = withSemconv(anthropic("claude-sonnet-4-6"), "anthropic", "api.anthropic.com");
 */
import type { LanguageModelV3, LanguageModelV3Middleware } from "@ai-sdk/provider";
import { metrics, SpanStatusCode, trace } from "@opentelemetry/api";
import { wrapLanguageModel } from "ai";

const tracer = trace.getTracer("ai-contract-analyzer");
const meter = metrics.getMeter("ai-contract-analyzer");

export const opDurationHistogram = meter.createHistogram("gen_ai.client.operation.duration", {
  description: "LLM operation duration",
  unit: "s",
});
export const errorCounter = meter.createCounter("gen_ai.client.error.count", {
  description: "LLM call error count",
  unit: "{error}",
});
export const retryCounter = meter.createCounter("gen_ai.client.retry.count", {
  description: "LLM call retry count",
  unit: "{retry}",
});
export const fallbackCounter = meter.createCounter("gen_ai.client.fallback.count", {
  description: "LLM provider fallback count",
  unit: "{fallback}",
});
export const tokenUsageHistogram = meter.createHistogram("gen_ai.client.token.usage", {
  description: "LLM token usage",
  unit: "{token}",
});
export const costCounter = meter.createCounter("gen_ai.client.cost", {
  description: "LLM cost in USD",
  unit: "usd",
});

// Semconv truncation limits (LLM Gateway Contract §events)
const TRUNCATE_PROMPT = 1_000;
const TRUNCATE_COMPLETION = 2_000;
const TRUNCATE_SYSTEM = 500;

// Retry config (LLM Gateway Contract §error_resilience)
const MAX_RETRIES = 2; // 3 total attempts
const MIN_BACKOFF_MS = 1_000;
const MAX_BACKOFF_MS = 10_000;

function truncate(s: string, max: number): string {
  return s.length > max ? `${s.slice(0, max)}…` : s;
}

function extractPromptText(
  prompt: LanguageModelV3["doGenerate"] extends (p: infer P) => unknown
    ? P extends { prompt: infer R }
      ? R
      : never
    : never,
): { system?: string; user: string } {
  let system: string | undefined;
  const userParts: string[] = [];
  for (const msg of prompt as Array<{ role: string; content: unknown }>) {
    if (msg.role === "system" && typeof msg.content === "string") {
      system = msg.content;
    } else if (msg.role === "user") {
      const parts = msg.content as Array<{ type: string; text?: string }>;
      if (Array.isArray(parts)) {
        for (const p of parts) {
          if (p.type === "text" && p.text) userParts.push(p.text);
        }
      }
    }
  }
  return { system, user: userParts.join("\n") };
}

async function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

export function createSemconvMiddleware(
  providerName: string,
  serverAddress: string,
  pricing?: { inputCostPerMToken: number; outputCostPerMToken: number },
): LanguageModelV3Middleware {
  return {
    specificationVersion: "v3",
    async wrapGenerate({ doGenerate, params, model }) {
      const modelId = model.modelId;
      const spanName = `gen_ai.chat ${modelId}`;

      const { system, user } = extractPromptText(
        params.prompt as Parameters<typeof extractPromptText>[0],
      );

      return tracer.startActiveSpan(spanName, async (span) => {
        // Required semconv attributes
        span.setAttribute("gen_ai.operation.name", "chat");
        span.setAttribute("gen_ai.provider.name", providerName);
        span.setAttribute("gen_ai.request.model", modelId);
        span.setAttribute("server.address", serverAddress);

        // Recommended attributes
        if (params.maxOutputTokens !== undefined)
          span.setAttribute("gen_ai.request.max_tokens", params.maxOutputTokens);
        if (params.temperature !== undefined)
          span.setAttribute("gen_ai.request.temperature", params.temperature);

        // gen_ai.user.message event (truncated)
        span.addEvent("gen_ai.user.message", {
          "gen_ai.prompt": truncate(user, TRUNCATE_PROMPT),
          ...(system ? { "gen_ai.system_instructions": truncate(system, TRUNCATE_SYSTEM) } : {}),
        });

        const startMs = Date.now();
        let lastError: Error | undefined;

        for (let attempt = 0; attempt <= MAX_RETRIES; attempt++) {
          try {
            const result = await doGenerate();
            const durationS = (Date.now() - startMs) / 1000;

            const inputTokens = result.usage.inputTokens.total ?? 0;
            const outputTokens = result.usage.outputTokens.total ?? 0;

            // Response attributes
            if (result.response?.modelId)
              span.setAttribute("gen_ai.response.model", result.response.modelId);
            if (result.response?.id) span.setAttribute("gen_ai.response.id", result.response.id);
            if (result.finishReason)
              span.setAttribute("gen_ai.response.finish_reasons", [result.finishReason.unified]);
            span.setAttribute("gen_ai.usage.input_tokens", inputTokens);
            span.setAttribute("gen_ai.usage.output_tokens", outputTokens);

            // gen_ai.assistant.message event (truncated text content)
            const completionText = result.content
              .filter((c): c is { type: "text"; text: string } => c.type === "text")
              .map((c) => c.text)
              .join("");
            span.addEvent("gen_ai.assistant.message", {
              "gen_ai.completion": truncate(completionText, TRUNCATE_COMPLETION),
            });

            // gen_ai.client.token.usage — required attrs per LLM Gateway Contract
            const metricAttrs = {
              "gen_ai.operation.name": "chat",
              "gen_ai.provider.name": providerName,
              "gen_ai.request.model": modelId,
            };
            tokenUsageHistogram.record(inputTokens, {
              ...metricAttrs,
              "gen_ai.token.type": "input",
            });
            tokenUsageHistogram.record(outputTokens, {
              ...metricAttrs,
              "gen_ai.token.type": "output",
            });

            // gen_ai.client.cost + span attribute when pricing is available
            if (pricing) {
              const costUsd =
                (inputTokens * pricing.inputCostPerMToken +
                  outputTokens * pricing.outputCostPerMToken) /
                1_000_000;
              span.setAttribute("gen_ai.usage.cost_usd", costUsd);
              costCounter.add(costUsd, metricAttrs);
            }

            opDurationHistogram.record(durationS, {
              "gen_ai.request.model": modelId,
              "gen_ai.provider.name": providerName,
            });

            span.end();
            return result;
          } catch (err) {
            lastError = err as Error;

            if (attempt < MAX_RETRIES) {
              retryCounter.add(1, {
                "gen_ai.request.model": modelId,
                "gen_ai.provider.name": providerName,
              });
              const backoffMs = Math.min(MIN_BACKOFF_MS * 2 ** attempt, MAX_BACKOFF_MS);
              span.addEvent("gen_ai.retry", {
                attempt: attempt + 1,
                backoff_ms: backoffMs,
                error: (err as Error).message,
              });
              await sleep(backoffMs);
            }
          }
        }

        // All retries exhausted
        const durationS = (Date.now() - startMs) / 1000;
        const errorType = lastError?.constructor?.name ?? "UnknownError";

        span.recordException(lastError as Error);
        span.setAttribute("error.type", errorType);
        span.setStatus({ code: SpanStatusCode.ERROR, message: lastError?.message });

        errorCounter.add(1, {
          "gen_ai.request.model": modelId,
          "gen_ai.provider.name": providerName,
          "error.type": errorType,
        });
        opDurationHistogram.record(durationS, {
          "gen_ai.request.model": modelId,
          "gen_ai.provider.name": providerName,
        });

        span.end();
        throw lastError;
      });
    },
  };
}

/**
 * Wraps a model with:
 * 1. GenAI semconv spans + retry (via createSemconvMiddleware)
 * 2. Fallback to a secondary model if all retries fail
 */
export function withFallback(
  primary: LanguageModelV3,
  primaryProviderName: string,
  fallback: LanguageModelV3,
): LanguageModelV3 {
  const fallbackMiddleware: LanguageModelV3Middleware = {
    specificationVersion: "v3",
    async wrapGenerate({ doGenerate, params, model }) {
      try {
        return await doGenerate();
      } catch (_err) {
        fallbackCounter.add(1, {
          "gen_ai.request.model": model.modelId,
          "gen_ai.provider.name": primaryProviderName,
        });
        // Call fallback model directly (it has its own semconv wrapper)
        return await fallback.doGenerate(params);
      }
    },
  };

  return wrapLanguageModel({ model: primary, middleware: fallbackMiddleware });
}

/** Convenience: wrap a raw model with semconv middleware. */
export function withSemconv(
  model: LanguageModelV3,
  providerName: string,
  serverAddress: string,
  pricing?: { inputCostPerMToken: number; outputCostPerMToken: number },
): LanguageModelV3 {
  return wrapLanguageModel({
    model,
    middleware: createSemconvMiddleware(providerName, serverAddress, pricing),
  });
}
