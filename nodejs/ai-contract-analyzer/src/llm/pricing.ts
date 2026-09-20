/**
 * Model prices, loaded once from `_shared/pricing.json` at the repo root.
 *
 * The file is the single source of truth shared by every AI example. A model it
 * does not list costs zero, which is not an error.
 */
import { readFileSync } from "node:fs";
import type { ModelPricing } from "./provider-target.ts";

interface PricingFile {
  models: Record<string, { provider: string; input: number; output: number }>;
}

let pricingFile: PricingFile;
try {
  pricingFile = JSON.parse(
    readFileSync(new URL("../../../../_shared/pricing.json", import.meta.url).pathname, "utf-8"),
  );
} catch (err) {
  throw new Error(
    `Failed to load _shared/pricing.json, ensure the repo root includes _shared/. Cause: ${(err as Error).message}`,
  );
}

export const MODEL_PRICING: Record<string, { input: number; output: number }> = Object.fromEntries(
  Object.entries(pricingFile.models).map(([id, m]) => [id, { input: m.input, output: m.output }]),
);

const UNKNOWN_MODEL_PRICING = { input: 0, output: 0 };

const MODEL_DATE_SUFFIX = /-\d{8}$/;
const MODEL_MINOR_VERSION = /^(claude-(?:sonnet|opus|haiku))-(\d+)-(\d+)$/;

// Providers return dated IDs (claude-sonnet-4-5-20250929) and dash-minor forms
// (claude-opus-4-6); pricing.json keys are dot-form (claude-opus-4.6).
function normalizeModelId(modelId: string): string {
  return modelId.replace(MODEL_DATE_SUFFIX, "").replace(MODEL_MINOR_VERSION, "$1-$2.$3");
}

export function modelPricing(modelId: string): ModelPricing {
  const price =
    MODEL_PRICING[modelId] ?? MODEL_PRICING[normalizeModelId(modelId)] ?? UNKNOWN_MODEL_PRICING;
  return { inputCostPerMToken: price.input, outputCostPerMToken: price.output };
}
