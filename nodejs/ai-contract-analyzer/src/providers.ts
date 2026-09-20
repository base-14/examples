import { anthropic } from "@ai-sdk/anthropic";
import { createGoogleGenerativeAI, google } from "@ai-sdk/google";
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
import { modelPricing } from "./llm/pricing.ts";
import type { ModelPricing, ProviderTarget } from "./llm/provider-target.ts";
import { thinkingOff } from "./llm/thinking-off.ts";

export interface ModelDescriptor extends ModelPricing {
  modelId: string;
  model: LanguageModel;
}

export interface EmbeddingDescriptor {
  modelId: string;
  model: EmbeddingModel;
  dimensions: number;
  costPerMToken: number;
  target: ProviderTarget;
}

type LlmProvider = "anthropic" | "google" | "ollama";
type EmbeddingProvider = "openai" | "google" | "ollama";

const ANTHROPIC_CAPABLE_DEFAULT = "claude-sonnet-4-6";
const ANTHROPIC_FAST_DEFAULT = "claude-haiku-4-5-20251001";
const GOOGLE_CAPABLE_DEFAULT = "gemini-2.5-flash";
const GOOGLE_FAST_DEFAULT = "gemini-2.5-flash-lite";
const OLLAMA_CAPABLE_DEFAULT = "qwen3.5:9B";
const OLLAMA_FAST_DEFAULT = "qwen3.5:9B";
const OPENAI_EMBED_DEFAULT = "text-embedding-3-small";
const OLLAMA_EMBED_DEFAULT = "embeddinggemma";
const GOOGLE_EMBED_DEFAULT = "gemini-embedding-001";
const EMBEDDING_DIMENSIONS = 768;

function ollamaTarget(): ProviderTarget {
  return {
    semconvName: "ollama",
    serverAddress: new URL(config.ollamaBaseUrl).hostname,
    serverPort: 11434,
  };
}

/**
 * Provider config key to telemetry target (LLM Gateway Contract §providers).
 * The key `google` selects Gemini; its `gen_ai.provider.name` is `gcp.gemini`.
 */
function providerTarget(provider: LlmProvider | EmbeddingProvider): ProviderTarget {
  switch (provider) {
    case "anthropic":
      return {
        semconvName: "anthropic",
        serverAddress: "api.anthropic.com",
        serverPort: 443,
      };
    case "google":
      return {
        semconvName: "gcp.gemini",
        serverAddress: "generativelanguage.googleapis.com",
        serverPort: 443,
      };
    case "openai":
      return { semconvName: "openai", serverAddress: "api.openai.com", serverPort: 443 };
    case "ollama":
      return ollamaTarget();
  }
}

const googleV1 = createGoogleGenerativeAI({
  baseURL: "https://generativelanguage.googleapis.com/v1",
});

// Ollama speaks the OpenAI wire protocol at /v1, which is what ai@6 accepts.
function ollamaClient() {
  return createOpenAI({
    baseURL: `${config.ollamaBaseUrl}/v1`,
    apiKey: "ollama",
    fetch: thinkingOff as typeof fetch,
  });
}

/** Build a raw (unwrapped) language model for the given provider + modelId. */
function buildRawModel(provider: LlmProvider, modelId: string): LanguageModelV3 {
  if (provider === "google") return google(modelId) as unknown as LanguageModelV3;
  if (provider === "ollama") return ollamaClient()(modelId) as unknown as LanguageModelV3;
  return anthropic(modelId) as unknown as LanguageModelV3;
}

/**
 * Build a ModelDescriptor for the given provider + modelId, wrapped in the
 * GenAI semconv middleware and, when FALLBACK_PROVIDER is set, in fallback.
 */
function buildDescriptor(provider: LlmProvider, modelId: string): ModelDescriptor {
  const target = providerTarget(provider);
  const pricing = modelPricing(modelId);
  let model = withSemconv(buildRawModel(provider, modelId), target, pricing);

  if (config.llmProviderFallback && config.llmProviderFallback !== provider) {
    const fallbackProvider = config.llmProviderFallback;
    const fallbackModelId = config.llmModelFallback ?? modelId;
    const fallbackTarget = providerTarget(fallbackProvider);
    const fallback = withSemconv(
      buildRawModel(fallbackProvider, fallbackModelId),
      fallbackTarget,
      modelPricing(fallbackModelId),
    );
    model = withFallback(model, target, fallback, fallbackTarget);
  }

  return { modelId, model: model as unknown as LanguageModel, ...pricing };
}

export function getCapableModel(): ModelDescriptor {
  if (config.llmProvider === "google") {
    return buildDescriptor("google", config.llmModelCapable ?? GOOGLE_CAPABLE_DEFAULT);
  }
  if (config.llmProvider === "ollama") {
    return buildDescriptor("ollama", config.llmModelCapable ?? OLLAMA_CAPABLE_DEFAULT);
  }
  return buildDescriptor("anthropic", config.llmModelCapable ?? ANTHROPIC_CAPABLE_DEFAULT);
}

export function getFastModel(): ModelDescriptor {
  if (config.llmProvider === "google") {
    return buildDescriptor("google", config.llmModelFast ?? GOOGLE_FAST_DEFAULT);
  }
  if (config.llmProvider === "ollama") {
    return buildDescriptor("ollama", config.llmModelFast ?? OLLAMA_FAST_DEFAULT);
  }
  return buildDescriptor("anthropic", config.llmModelFast ?? ANTHROPIC_FAST_DEFAULT);
}

export function getEmbeddingModel(): EmbeddingDescriptor {
  if (config.embeddingProvider === "google") {
    const modelId = config.embeddingModel ?? GOOGLE_EMBED_DEFAULT;
    return {
      modelId,
      // providerOptions.google.outputDimensionality reduces gemini-embedding-001 (3072-dim)
      // to 768 to match the pgvector column dimension.
      model: wrapEmbeddingModel({
        model: googleV1.textEmbeddingModel(modelId),
        middleware: defaultEmbeddingSettingsMiddleware({
          settings: {
            providerOptions: { google: { outputDimensionality: EMBEDDING_DIMENSIONS } },
          },
        }),
      }),
      dimensions: EMBEDDING_DIMENSIONS,
      costPerMToken: modelPricing(modelId).inputCostPerMToken,
      target: providerTarget("google"),
    };
  }

  if (config.embeddingProvider === "ollama") {
    const modelId = config.embeddingModel ?? OLLAMA_EMBED_DEFAULT;
    return {
      modelId,
      model: ollamaClient().embedding(modelId),
      dimensions: EMBEDDING_DIMENSIONS,
      costPerMToken: modelPricing(modelId).inputCostPerMToken,
      target: providerTarget("ollama"),
    };
  }

  const modelId = config.embeddingModel ?? OPENAI_EMBED_DEFAULT;
  return {
    modelId,
    model: wrapEmbeddingModel({
      model: openai.embedding(modelId),
      middleware: defaultEmbeddingSettingsMiddleware({
        settings: {
          providerOptions: { openai: { dimensions: EMBEDDING_DIMENSIONS } },
        },
      }),
    }),
    dimensions: EMBEDDING_DIMENSIONS,
    costPerMToken: modelPricing(modelId).inputCostPerMToken,
    target: providerTarget("openai"),
  };
}
