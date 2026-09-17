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

// _shared/pricing.json sits four levels up, at the examples repo root.
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

// Local models have no price row, so cost resolves three ways:
//
// 1. modelId names a row -- that row's real rate, simulated: false.
// 2. no row and PRICE_MODEL unset -- zero, simulated: true. A stand-in at zero, not a price.
// 3. no row and PRICE_MODEL names a row -- that row's rates over the local token counts,
//    simulated: true.
//
// PRICE_MODEL naming an id the table does not have is a misconfiguration, not an absent one,
// and throws rather than behaving like case 2.
function unknownPriceModelError(priceModel: string): Error {
  return new Error(
    `PRICE_MODEL is '${priceModel}', which is not a model in _shared/pricing.json. ` +
      "Set PRICE_MODEL to a model id listed there, or leave it unset to track cost as zero.",
  );
}

// costOf can throw from a span processor's onEnd, where the failure lands on the export path.
// src/telemetry.ts calls this at boot so it fails there instead.
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
