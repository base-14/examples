import { readFileSync } from "node:fs";
import { anthropic } from "@ai-sdk/anthropic";
import { google } from "@ai-sdk/google";
import { createOpenAI, openai } from "@ai-sdk/openai";
import {
  defaultEmbeddingSettingsMiddleware,
  type EmbeddingModel,
  type LanguageModel,
  wrapEmbeddingModel,
} from "ai";
import { config } from "./config.ts";

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

export function getCapableModel(): ModelDescriptor {
  if (config.llmProvider === "google") {
    const modelName = config.llmModelCapable ?? GOOGLE_CAPABLE_DEFAULT;
    return { modelId: modelName, model: google(modelName), ...modelPricing(modelName) };
  }

  if (config.llmProvider === "ollama") {
    const modelName = config.llmModelCapable ?? OLLAMA_CAPABLE_DEFAULT;
    const ollamaOpenAI = createOpenAI({ baseURL: `${config.ollamaBaseUrl}/v1`, apiKey: "ollama" });
    return {
      modelId: modelName,
      model: ollamaOpenAI(modelName),
      inputCostPerMToken: 0,
      outputCostPerMToken: 0,
    };
  }

  const modelName = config.llmModelCapable ?? ANTHROPIC_CAPABLE_DEFAULT;
  return { modelId: modelName, model: anthropic(modelName), ...modelPricing(modelName) };
}

export function getFastModel(): ModelDescriptor {
  if (config.llmProvider === "google") {
    const modelName = config.llmModelFast ?? GOOGLE_FAST_DEFAULT;
    return { modelId: modelName, model: google(modelName), ...modelPricing(modelName) };
  }

  if (config.llmProvider === "ollama") {
    const modelName = config.llmModelFast ?? OLLAMA_FAST_DEFAULT;
    const ollamaOpenAI = createOpenAI({ baseURL: `${config.ollamaBaseUrl}/v1`, apiKey: "ollama" });
    return {
      modelId: modelName,
      model: ollamaOpenAI(modelName),
      inputCostPerMToken: 0,
      outputCostPerMToken: 0,
    };
  }

  const modelName = config.llmModelFast ?? ANTHROPIC_FAST_DEFAULT;
  return { modelId: modelName, model: anthropic(modelName), ...modelPricing(modelName) };
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
