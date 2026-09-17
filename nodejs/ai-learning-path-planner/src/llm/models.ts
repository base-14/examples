import { createRequire } from "node:module";
import type { LanguageModel, ToolLoopAgentSettings } from "ai";
import { createOllama } from "ollama-ai-provider-v2";
import type { Config } from "../config.ts";

const require = createRequire(import.meta.url);

const HOSTED_PROVIDERS = new Set(["openai", "anthropic"]);

// @ai-sdk/openai and @ai-sdk/anthropic are not installed in this example on purpose: no
// hosted provider is ever called on this branch. These are the packages and the exported
// factory function names that guardHostedProvider stands in front of. If ALLOW_HOSTED_PROVIDER
// is ever set true and a hosted client is actually built, buildHostedModel below is where that
// happens, by name that is only resolved at runtime past the guard, never at module load time.
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

// Builds a hosted-provider model without a static import of the (uninstalled) provider
// package, so the module still compiles and runs when nothing hosted is ever used. This
// only runs once guardHostedProvider has let a hosted provider through, which on this
// branch never happens outside a deliberately configured, non-default run.
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

// Ollama applies its own default num_ctx of 4096 unless the request carries an options
// block, and ollama-ai-provider-v2 only sends one when providerOptions.ollama.options is
// set. A lead run accumulates sixteen steps of tool results from this corpus and overruns
// 4096 partway through, which comes back as done_reason "length" with no content.
//
// Returned per config rather than baked into the model, because providerOptions is a
// per-call setting: every agent passes this straight through to its ToolLoopAgent. The
// ollama key is absent on a hosted provider, which would ignore it anyway but would also
// carry a setting that means nothing on that path.
type AgentProviderOptions = ToolLoopAgentSettings["providerOptions"];

export function providerOptionsFor(config: Config): AgentProviderOptions {
  if (config.llmProvider !== "ollama") {
    return undefined;
  }
  return { ollama: { options: { num_ctx: config.ollamaNumCtx } } };
}
