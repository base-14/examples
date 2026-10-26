/**
 * The GenAI metric instruments shared by every instrumented model call.
 *
 * Names follow `_shared/llm-gateway-contract.yaml`: the semconv metrics keep
 * their `gen_ai.` names, the four application metrics sit under `base14.`.
 * Inference calls record the token and inference duration histograms; non-inference
 * operations such as embeddings record `gen_ai.client.operation.duration`.
 */
import { metrics } from "@opentelemetry/api";

const meter = metrics.getMeter("ai-contract-analyzer");

const TOKEN_BUCKETS = [
  1, 4, 16, 64, 256, 1024, 4096, 16384, 65536, 262144, 1048576, 4194304, 16777216, 67108864,
];

const DURATION_BUCKETS = [
  0.01, 0.02, 0.04, 0.08, 0.16, 0.32, 0.64, 1.28, 2.56, 5.12, 10.24, 20.48, 40.96, 81.92,
];

export const inputTokensHistogram = meter.createHistogram(
  "gen_ai.client.inference.operation.input_tokens",
  {
    description: "Input tokens per inference call",
    unit: "{token}",
    advice: { explicitBucketBoundaries: TOKEN_BUCKETS },
  },
);

export const outputTokensHistogram = meter.createHistogram(
  "gen_ai.client.inference.operation.output_tokens",
  {
    description: "Output tokens per inference call",
    unit: "{token}",
    advice: { explicitBucketBoundaries: TOKEN_BUCKETS },
  },
);

export const inferenceDurationHistogram = meter.createHistogram(
  "gen_ai.client.inference.duration",
  {
    description: "Wall-clock duration of an inference call",
    unit: "s",
    advice: { explicitBucketBoundaries: DURATION_BUCKETS },
  },
);

export const opDurationHistogram = meter.createHistogram("gen_ai.client.operation.duration", {
  description: "Wall-clock duration of a non-inference GenAI operation",
  unit: "s",
  advice: { explicitBucketBoundaries: DURATION_BUCKETS },
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
