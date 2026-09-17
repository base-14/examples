import { readFileSync } from "node:fs";
import type { LanguageModelUsage } from "ai";
import type { Config } from "../config.ts";

interface PriceRow {
  provider: string;
  input: number;
  output: number;
  cached_input?: number;
}

interface PricingFile {
  version: string;
  note: string;
  models: Record<string, PriceRow>;
}

// _shared/pricing.json sits at the examples repo root, four levels up from this package:
// src/llm/cost.ts -> src -> ai-learning-path-planner -> nodejs -> repo root. Follows the
// same relative-path load and failure style as nodejs/ai-contract-analyzer's providers.ts.
function loadPricing(): PricingFile {
  try {
    const raw = readFileSync(new URL("../../../../_shared/pricing.json", import.meta.url), "utf8");
    return JSON.parse(raw) as PricingFile;
  } catch (err) {
    throw new Error(
      `Failed to load _shared/pricing.json -- ensure the repo root includes _shared/. Cause: ${(err as Error).message}`,
    );
  }
}

const pricing = loadPricing();

function computeUsd(usage: LanguageModelUsage, price: PriceRow): number {
  const inputTokens = usage.inputTokens ?? 0;
  const outputTokens = usage.outputTokens ?? 0;
  const cacheReadTokens = usage.inputTokenDetails.cacheReadTokens ?? 0;
  const billableInputTokens = Math.max(inputTokens - cacheReadTokens, 0);
  const cachedInputRate = price.cached_input ?? price.input;

  const usd =
    (billableInputTokens * price.input +
      cacheReadTokens * cachedInputRate +
      outputTokens * price.output) /
    1_000_000;

  return usd;
}

// Local models (the default on this branch) have no price row of their own in
// _shared/pricing.json. costOf resolves cost in three steps:
//
// 1. modelId names a real row (a hosted model, or a local id someone added with
//    input/output 0 per the pricing file's ollama_note) -- that row's real rate applies,
//    simulated: false.
// 2. modelId has no row and PRICE_MODEL is unset -- an unconfigured run stays usable:
//    zero cost, simulated: true, no throw. The figure is not a real per-model price, it
//    is a stand-in, so it carries the same simulated flag as case 3, just at zero.
// 3. modelId has no row and PRICE_MODEL names a row -- that row's rates are applied to
//    the local token counts as a stand-in, simulated: true.
//
// PRICE_MODEL naming an id that is not in the table at all is a misconfiguration, not an
// absent configuration, and is handled separately below: it throws rather than silently
// behaving like case 2.
function unknownPriceModelError(priceModel: string): Error {
  return new Error(
    `PRICE_MODEL is '${priceModel}', which is not a model in _shared/pricing.json. ` +
      "Set PRICE_MODEL to a model id listed there, or leave it unset to track cost as zero.",
  );
}

// costOf's throw is reachable on every call, including calls made from a span
// processor's onEnd, where a throw lands on the SDK's export path rather than on the
// request that caused it. src/telemetry.ts calls this at boot so the misconfiguration
// fails there instead.
export function assertPriceModelIsKnown(config: Config): void {
  if (config.priceModel === undefined) {
    return;
  }
  if (pricing.models[config.priceModel] === undefined) {
    throw unknownPriceModelError(config.priceModel);
  }
}

export function costOf(
  usage: LanguageModelUsage,
  modelId: string,
  config: Config,
): { usd: number; simulated: boolean } {
  const ownRow = pricing.models[modelId];
  if (ownRow !== undefined) {
    return { usd: computeUsd(usage, ownRow), simulated: false };
  }

  if (config.priceModel === undefined) {
    return { usd: 0, simulated: true };
  }

  const borrowedRow = pricing.models[config.priceModel];
  if (borrowedRow === undefined) {
    throw unknownPriceModelError(config.priceModel);
  }

  return { usd: computeUsd(usage, borrowedRow), simulated: true };
}
