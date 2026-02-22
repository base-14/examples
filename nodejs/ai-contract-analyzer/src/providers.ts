import { readFileSync } from "node:fs";
import { anthropic } from "@ai-sdk/anthropic";
import { google } from "@ai-sdk/google";
import { createOpenAI, openai } from "@ai-sdk/openai";
import type { LanguageModelV3 } from "@ai-sdk/provider";
import {
  defaultEmbeddingSettingsMiddleware,
  type EmbeddingModel,
  type LanguageModel,
  wrapEmbeddingModel,
} from "ai";
import { config } from "./config.ts";
import { withFallback, withSemconv } from "./llm/middleware.ts";

export interface ModelDescriptor {
  modelId: string;
  model: LanguageModel;
  inputCostPerMToken: number;
  outputCostPerMToken: number;
}

export interface EmbeddingDescriptor {
  modelId: string;
  model: EmbeddingModel;
  dimensions: number;
  costPerMToken: number;
}

const ANTHROPIC_CAPABLE_DEFAULT = "claude-sonnet-4-6";
const ANTHROPIC_FAST_DEFAULT = "claude-haiku-4-5-20251001";
const GOOGLE_CAPABLE_DEFAULT = "gemini-2.5-flash";
const GOOGLE_FAST_DEFAULT = "gemini-2.0-flash";
const OLLAMA_CAPABLE_DEFAULT = "llama3.1:8b";
const OLLAMA_FAST_DEFAULT = "llama3.2";
const OPENAI_EMBED_DEFAULT = "text-embedding-3-small";
const OLLAMA_EMBED_DEFAULT = "nomic-embed-text";
const GOOGLE_EMBED_DEFAULT = "gemini-embedding-001";
const EMBEDDING_DIMENSIONS = 768;

// Provider → OTel semconv name + server address (LLM Gateway Contract §providers)
const PROVIDER_META: Record<string, { semconvName: string; serverAddress: string }> = {
  anthropic: { semconvName: "anthropic", serverAddress: "api.anthropic.com" },
  google: { semconvName: "google", serverAddress: "generativelanguage.googleapis.com" },
  openai: { semconvName: "openai", serverAddress: "api.openai.com" },
  ollama: { semconvName: "ollama", serverAddress: "localhost" },
};

// Pricing per million tokens (USD) — loaded from _shared/pricing.json
// Single source of truth shared across all AI examples in this repo.
let _pricingFile: { models: Record<string, { provider: string; input: number; output: number }> };
try {
  _pricingFile = JSON.parse(
    readFileSync(new URL("../../../_shared/pricing.json", import.meta.url).pathname, "utf-8"),
  );
} catch (err) {
  throw new Error(
    `Failed to load _shared/pricing.json — ensure the repo root includes _shared/. Cause: ${(err as Error).message}`,
  );
}

export const MODEL_PRICING: Record<string, { input: number; output: number }> = Object.fromEntries(
  Object.entries(_pricingFile.models).map(([id, m]) => [id, { input: m.input, output: m.output }]),
);

// Conservative fallback for unknown/custom models
const DEFAULT_PRICING = { input: 3.0, output: 15.0 };

function modelPricing(modelId: string): {
  inputCostPerMToken: number;
  outputCostPerMToken: number;
} {
  const p = MODEL_PRICING[modelId] ?? DEFAULT_PRICING;
  return { inputCostPerMToken: p.input, outputCostPerMToken: p.output };
}

/** Build a raw (unwrapped) language model for the given provider + modelId. */
function buildRawModel(
  provider: "anthropic" | "google" | "ollama",
  modelId: string,
): LanguageModelV3 {
  if (provider === "google") return google(modelId) as unknown as LanguageModelV3;

  if (provider === "ollama") {
    const ollamaOpenAI = createOpenAI({ baseURL: `${config.ollamaBaseUrl}/v1`, apiKey: "ollama" });
    return ollamaOpenAI(modelId) as unknown as LanguageModelV3;
  }

  return anthropic(modelId) as unknown as LanguageModelV3;
}

/** Wrap a raw model with the GenAI semconv middleware for its provider. */
function wrapWithSemconv(
  raw: LanguageModelV3,
  provider: "anthropic" | "google" | "ollama",
  modelId: string,
): LanguageModelV3 {
  const meta = PROVIDER_META[provider] ?? { semconvName: provider, serverAddress: "localhost" };
  return withSemconv(raw, meta.semconvName, meta.serverAddress, modelPricing(modelId));
}

/**
 * Build a ModelDescriptor for the given provider + modelId.
 * Applies the GenAI semconv middleware automatically.
 * If LLM_PROVIDER_FALLBACK is configured, wraps with fallback on top.
 */
function buildDescriptor(
  provider: "anthropic" | "google" | "ollama",
  modelId: string,
): ModelDescriptor {
  const rawPrimary = buildRawModel(provider, modelId);
  let wrappedModel: LanguageModelV3 = wrapWithSemconv(rawPrimary, provider, modelId);

  // Optional fallback provider (LLM Gateway Contract §error_resilience.fallback)
  if (config.llmProviderFallback && config.llmProviderFallback !== provider) {
    const fallbackProvider = config.llmProviderFallback;
    const fallbackModelId = config.llmModelFallback ?? modelId;
    const rawFallback = buildRawModel(fallbackProvider, fallbackModelId);
    const wrappedFallback = wrapWithSemconv(rawFallback, fallbackProvider, fallbackModelId);
    wrappedModel = withFallback(
      wrappedModel,
      PROVIDER_META[provider]?.semconvName ?? provider,
      wrappedFallback,
    );
  }

  return {
    modelId,
    model: wrappedModel as unknown as LanguageModel,
    ...modelPricing(modelId),
  };
}

export function getCapableModel(): ModelDescriptor {
  if (config.llmProvider === "google") {
    return buildDescriptor("google", config.llmModelCapable ?? GOOGLE_CAPABLE_DEFAULT);
  }
  if (config.llmProvider === "ollama") {
    const d = buildDescriptor("ollama", config.llmModelCapable ?? OLLAMA_CAPABLE_DEFAULT);
    return { ...d, inputCostPerMToken: 0, outputCostPerMToken: 0 };
  }
  return buildDescriptor("anthropic", config.llmModelCapable ?? ANTHROPIC_CAPABLE_DEFAULT);
}

export function getFastModel(): ModelDescriptor {
  if (config.llmProvider === "google") {
    return buildDescriptor("google", config.llmModelFast ?? GOOGLE_FAST_DEFAULT);
  }
  if (config.llmProvider === "ollama") {
    const d = buildDescriptor("ollama", config.llmModelFast ?? OLLAMA_FAST_DEFAULT);
    return { ...d, inputCostPerMToken: 0, outputCostPerMToken: 0 };
  }
  return buildDescriptor("anthropic", config.llmModelFast ?? ANTHROPIC_FAST_DEFAULT);
}

export function getEmbeddingModel(): EmbeddingDescriptor {
  if (config.embeddingProvider === "google") {
    const modelName = config.embeddingModel ?? GOOGLE_EMBED_DEFAULT;
    return {
      modelId: modelName,
      // providerOptions.google.outputDimensionality reduces gemini-embedding-001 (3072-dim)
      // to 768 to match the pgvector column dimension.
      model: wrapEmbeddingModel({
        model: google.textEmbeddingModel(modelName),
        middleware: defaultEmbeddingSettingsMiddleware({
          settings: {
            providerOptions: { google: { outputDimensionality: EMBEDDING_DIMENSIONS } },
          },
        }),
      }),
      dimensions: EMBEDDING_DIMENSIONS,
      costPerMToken: 0.025,
    };
  }

  if (config.embeddingProvider === "ollama") {
    const modelName = config.embeddingModel ?? OLLAMA_EMBED_DEFAULT;
    // Use Ollama's OpenAI-compatible /v1 endpoint — ollama-ai-provider only
    // implements the v1 embedding spec which ai@6 no longer accepts.
    const ollamaOpenAI = createOpenAI({
      baseURL: `${config.ollamaBaseUrl}/v1`,
      apiKey: "ollama",
    });
    return {
      modelId: modelName,
      model: ollamaOpenAI.embedding(modelName),
      dimensions: EMBEDDING_DIMENSIONS,
      costPerMToken: 0,
    };
  }

  const modelName = config.embeddingModel ?? OPENAI_EMBED_DEFAULT;
  return {
    modelId: modelName,
    model: wrapEmbeddingModel({
      model: openai.embedding(modelName),
      middleware: defaultEmbeddingSettingsMiddleware({
        settings: {
          providerOptions: { openai: { dimensions: EMBEDDING_DIMENSIONS } },
        },
      }),
    }),
    dimensions: EMBEDDING_DIMENSIONS,
    costPerMToken: 0.02,
  };
}
