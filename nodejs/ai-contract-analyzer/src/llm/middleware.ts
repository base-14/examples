/**
 * OTel GenAI semantic convention middleware for AI SDK v6.
 *
 * `withSemconv` wraps a LanguageModelV3 so every call runs inside a CLIENT span
 * named `chat {model}`, retries all errors three times with exponential backoff,
 * and records the token, duration, cost, retry and error instruments.
 *
 * `withFallback` wraps a wrapped model with a second provider. A switch is
 * recorded as a `provider_fallback` event on the calling span, which stays OK.
 *
 * Usage (providers.ts):
 *   const model = withSemconv(anthropic("claude-sonnet-4-6"), target, pricing);
 */
import type { LanguageModelV3, LanguageModelV3Middleware } from "@ai-sdk/provider";
import { type Span, SpanKind, SpanStatusCode, trace } from "@opentelemetry/api";
import { wrapLanguageModel } from "ai";
import {
  costCounter,
  errorCounter,
  fallbackCounter,
  opDurationHistogram,
  retryCounter,
  tokenUsageHistogram,
} from "./instruments.ts";
import type { ModelPricing, ProviderTarget } from "./provider-target.ts";
import { scrubPii } from "./scrub.ts";

const tracer = trace.getTracer("ai-contract-analyzer");

// Content capture limits (LLM Gateway Contract §content_capture.truncation)
const TRUNCATE_PROMPT = 1_000;
const TRUNCATE_COMPLETION = 2_000;
const TRUNCATE_SYSTEM = 500;

// Retry config (LLM Gateway Contract §error_resilience)
const MAX_RETRIES = 2; // 3 total attempts
const MIN_BACKOFF_MS = 1_000;
const MAX_BACKOFF_MS = 10_000;

type GeneratePrompt = Parameters<LanguageModelV3["doGenerate"]>[0]["prompt"];

function contentCaptureEnabled(): boolean {
  return process.env.OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT === "true";
}

function scrubAndTruncate(text: string, max: number): string {
  return scrubPii(text).slice(0, max);
}

function errorType(err: unknown): string {
  return (err as Error)?.constructor?.name ?? "UnknownError";
}

function extractPromptText(prompt: GeneratePrompt): { system: string; user: string } {
  let system = "";
  const userParts: string[] = [];
  for (const msg of prompt) {
    if (msg.role === "system") {
      system = msg.content;
    } else if (msg.role === "user") {
      for (const part of msg.content) {
        if (part.type === "text") userParts.push(part.text);
      }
    }
  }
  return { system, user: userParts.join("\n") };
}

/**
 * The single content event per call, replacing the removed per-message events.
 * Emitted only when content capture is switched on.
 */
function emitInferenceEvent(
  span: Span,
  prompt: { system: string; user: string },
  completion: string | undefined,
): void {
  if (!contentCaptureEnabled()) return;

  const attributes: Record<string, string> = {
    "gen_ai.input.messages": scrubAndTruncate(prompt.user, TRUNCATE_PROMPT),
  };
  const systemInstructions = scrubAndTruncate(prompt.system, TRUNCATE_SYSTEM);
  if (systemInstructions) attributes["gen_ai.system_instructions"] = systemInstructions;
  if (completion !== undefined) {
    attributes["gen_ai.output.messages"] = scrubAndTruncate(completion, TRUNCATE_COMPLETION);
  }

  span.addEvent("gen_ai.client.inference.operation.details", attributes);
}

async function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

export function createSemconvMiddleware(
  target: ProviderTarget,
  pricing?: ModelPricing,
): LanguageModelV3Middleware {
  return {
    specificationVersion: "v3",
    async wrapGenerate({ doGenerate, params, model }) {
      const modelId = model.modelId;
      const prompt = extractPromptText(params.prompt);

      // Sampling-relevant attributes are set at span creation.
      const metricAttrs = {
        "gen_ai.operation.name": "chat",
        "gen_ai.provider.name": target.semconvName,
        "gen_ai.request.model": modelId,
      };
      const spanAttrs: Record<string, string | number> = {
        ...metricAttrs,
        "server.address": target.serverAddress,
        "server.port": target.serverPort,
      };
      if (params.maxOutputTokens !== undefined)
        spanAttrs["gen_ai.request.max_tokens"] = params.maxOutputTokens;
      if (params.temperature !== undefined)
        spanAttrs["gen_ai.request.temperature"] = params.temperature;

      return tracer.startActiveSpan(
        `chat ${modelId}`,
        { kind: SpanKind.CLIENT, attributes: spanAttrs },
        async (span) => {
          const startMs = Date.now();
          let lastError: Error | undefined;

          for (let attempt = 0; attempt <= MAX_RETRIES; attempt++) {
            try {
              const result = await doGenerate();

              const inputTokens = result.usage.inputTokens.total ?? 0;
              const outputTokens = result.usage.outputTokens.total ?? 0;

              if (result.response?.modelId)
                span.setAttribute("gen_ai.response.model", result.response.modelId);
              if (result.response?.id) span.setAttribute("gen_ai.response.id", result.response.id);
              if (result.finishReason)
                span.setAttribute("gen_ai.response.finish_reasons", [result.finishReason.unified]);
              span.setAttribute("gen_ai.usage.input_tokens", inputTokens);
              span.setAttribute("gen_ai.usage.output_tokens", outputTokens);

              tokenUsageHistogram.record(inputTokens, {
                ...metricAttrs,
                "gen_ai.token.type": "input",
              });
              tokenUsageHistogram.record(outputTokens, {
                ...metricAttrs,
                "gen_ai.token.type": "output",
              });

              const costUsd = pricing
                ? (inputTokens * pricing.inputCostPerMToken +
                    outputTokens * pricing.outputCostPerMToken) /
                  1_000_000
                : 0;
              span.setAttribute("base14.gen_ai.cost_usd", costUsd);
              costCounter.add(costUsd, metricAttrs);

              opDurationHistogram.record((Date.now() - startMs) / 1000, metricAttrs);

              const completionText = result.content
                .filter((c): c is { type: "text"; text: string } => c.type === "text")
                .map((c) => c.text)
                .join("");
              emitInferenceEvent(span, prompt, completionText);

              span.end();
              return result;
            } catch (err) {
              lastError = err as Error;

              if (attempt < MAX_RETRIES) {
                const backoffMs = Math.min(MIN_BACKOFF_MS * 2 ** attempt, MAX_BACKOFF_MS);
                retryCounter.add(1, {
                  "gen_ai.provider.name": target.semconvName,
                  "gen_ai.request.model": modelId,
                  "error.type": errorType(err),
                  "base14.retry.attempt": attempt + 1,
                });
                span.addEvent("base14.gen_ai.retry", {
                  "base14.retry.attempt": attempt + 1,
                  "base14.retry.backoff_ms": backoffMs,
                  "error.type": errorType(err),
                });
                await sleep(backoffMs);
              }
            }
          }

          const failure = lastError as Error;
          const type = errorType(failure);

          span.recordException(failure);
          span.setAttribute("error.type", type);
          span.setStatus({ code: SpanStatusCode.ERROR, message: failure.message });

          errorCounter.add(1, {
            "gen_ai.provider.name": target.semconvName,
            "gen_ai.request.model": modelId,
            "error.type": type,
          });
          opDurationHistogram.record((Date.now() - startMs) / 1000, {
            ...metricAttrs,
            "error.type": type,
          });

          emitInferenceEvent(span, prompt, undefined);

          span.end();
          throw failure;
        },
      );
    },
  };
}

/** Wrap a raw model with the GenAI semconv span, retry and metrics. */
export function withSemconv(
  model: LanguageModelV3,
  target: ProviderTarget,
  pricing?: ModelPricing,
): LanguageModelV3 {
  return wrapLanguageModel({ model, middleware: createSemconvMiddleware(target, pricing) });
}

/**
 * Switch to a second provider when the primary has exhausted its retries.
 *
 * The switch is non-fatal: the calling span records the exception and a
 * `provider_fallback` event, and keeps its OK status if the fallback succeeds.
 */
export function withFallback(
  primary: LanguageModelV3,
  primaryTarget: ProviderTarget,
  fallback: LanguageModelV3,
  fallbackTarget: ProviderTarget,
): LanguageModelV3 {
  const fallbackMiddleware: LanguageModelV3Middleware = {
    specificationVersion: "v3",
    async wrapGenerate({ doGenerate, params }) {
      try {
        return await doGenerate();
      } catch (err) {
        const attrs = {
          "gen_ai.provider.name": primaryTarget.semconvName,
          "base14.gen_ai.fallback.provider": fallbackTarget.semconvName,
          "error.type": errorType(err),
        };

        const span = trace.getActiveSpan();
        if (span) {
          span.recordException(err as Error);
          span.addEvent("provider_fallback", attrs);
          span.setAttribute("gen_ai.fallback.triggered", true);
        }
        fallbackCounter.add(1, attrs);

        return await fallback.doGenerate(params);
      }
    },
  };

  return wrapLanguageModel({ model: primary, middleware: fallbackMiddleware });
}
