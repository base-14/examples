/**
 * The GenAI metric instruments shared by every instrumented model call.
 *
 * Names follow `_shared/llm-gateway-contract.yaml`: the two semconv metrics keep
 * their `gen_ai.` names, the four application metrics sit under `base14.`.
 */
import { metrics } from "@opentelemetry/api";

const meter = metrics.getMeter("ai-contract-analyzer");

export const tokenUsageHistogram = meter.createHistogram("gen_ai.client.token.usage", {
  description: "Tokens used per model call, split by type",
  unit: "{token}",
});

export const opDurationHistogram = meter.createHistogram("gen_ai.client.operation.duration", {
  description: "Wall-clock duration of a GenAI operation",
  unit: "s",
});

export const costCounter = meter.createCounter("base14.gen_ai.cost", {
  description: "Cumulative cost of GenAI operations in USD",
  unit: "usd",
});

export const retryCounter = meter.createCounter("base14.gen_ai.retry.count", {
  description: "Retry attempts, excluding the initial attempt",
  unit: "{retry}",
});

export const fallbackCounter = meter.createCounter("base14.gen_ai.fallback.count", {
  description: "Times the fallback provider was triggered",
  unit: "{fallback}",
});

export const errorCounter = meter.createCounter("base14.gen_ai.error.count", {
  description: "GenAI call errors by provider and type",
  unit: "{error}",
});
