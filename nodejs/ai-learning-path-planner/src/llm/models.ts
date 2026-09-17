import { createRequire } from "node:module";
import type { LanguageModel, ToolLoopAgentSettings } from "ai";
import { createOllama } from "ollama-ai-provider-v2";
import type { Config } from "../config.ts";

const require = createRequire(import.meta.url);

const HOSTED_PROVIDERS = new Set(["openai", "anthropic"]);

// @ai-sdk/openai and @ai-sdk/anthropic are not installed: no hosted provider is called here.
// These are the package and factory names guardHostedProvider stands in front of, resolved at
// runtime past the guard rather than at module load.
const HOSTED_PACKAGES: Record<"openai" | "anthropic", { packageName: string; factory: string }> = {
  openai: { packageName: "@ai-sdk/openai", factory: "openai" },
  anthropic: { packageName: "@ai-sdk/anthropic", factory: "anthropic" },
};

function guardHostedProvider(config: Config): void {
  if (HOSTED_PROVIDERS.has(config.llmProvider) && !config.allowHostedProvider) {
    throw new Error(
      `LLM_PROVIDER is '${config.llmProvider}', a hosted provider, but ALLOW_HOSTED_PROVIDER is not ` +
        "'true'. Set ALLOW_HOSTED_PROVIDER=true to let the service start a hosted provider.",
    );
  }
}

function modelIdFor(tier: "small" | "large", config: Config): string {
  return tier === "small" ? config.modelSmall : config.modelLarge;
}

// Builds a hosted model without a static import of the uninstalled provider package, so the
// module compiles with nothing hosted installed. Runs only past guardHostedProvider.
function buildHostedModel(provider: "openai" | "anthropic", modelId: string): LanguageModel {
  const { packageName, factory } = HOSTED_PACKAGES[provider];
  const providerModule = require(packageName) as Record<string, (modelId: string) => LanguageModel>;
  const createModel = providerModule[factory];
  if (createModel === undefined) {
    throw new Error(`${packageName} did not export a '${factory}' factory function.`);
  }
  return createModel(modelId);
}

export function selectModel(tier: "small" | "large", config: Config): LanguageModel {
  guardHostedProvider(config);

  const modelId = modelIdFor(tier, config);

  if (config.llmProvider === "ollama") {
    const ollama = createOllama({ baseURL: config.ollamaBaseUrl });
    return ollama(modelId);
  }

  return buildHostedModel(config.llmProvider, modelId);
}

// Ollama applies its default num_ctx of 4096 unless the request carries an options block, and
// a lead run overruns that partway through. Returned per config rather than baked into the
// model, because providerOptions is a per-call setting; absent on a hosted provider.
type AgentProviderOptions = ToolLoopAgentSettings["providerOptions"];

export function providerOptionsFor(config: Config): AgentProviderOptions {
  if (config.llmProvider !== "ollama") {
    return undefined;
  }
  return { ollama: { options: { num_ctx: config.ollamaNumCtx } } };
}
