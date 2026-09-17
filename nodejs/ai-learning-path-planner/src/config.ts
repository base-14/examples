import { z } from "zod";

// Keep the /api suffix. The provider appends `/chat` to this value, so a base URL without it
// posts to http://host:11434/chat, which Ollama 404s. The host form is the default, for
// `make start`; compose.yaml overrides it with host.docker.internal, which only resolves
// inside a container.
const DEFAULT_OLLAMA_BASE_URL = "http://localhost:11434/api";

// Ollama's own default of 4096 is overrun partway through a lead run, which comes back as
// done_reason "length" and fails with "No output generated". Nothing raises it unless
// providerOptions.ollama.options is set; see llm/models.ts. 16384 is the largest window that
// keeps qwen3.5:9B inside a 16 GB machine. Raise it on an overrun, at the cost of VRAM.
const DEFAULT_OLLAMA_NUM_CTX = 16384;

// A local model has no price row, so without this the shipped configuration reports a cost of
// zero on an example about cost. gpt-5-nano is the closest stand-in _shared/pricing.json has
// for a small local model. The rate is borrowed: every cost from it carries
// base14.gen_ai.cost.simulated=true. Ollama path only; a hosted provider prices its own rows.
const OLLAMA_SIMULATED_PRICE_MODEL = "gpt-5-nano";

// compose.yaml publishes 3000 and does not pass this through, so setting it moves a host run
// only.
const DEFAULT_PORT = 3000;

const ConfigSchema = z.object({
  port: z.coerce.number().int().positive().default(DEFAULT_PORT),
  llmProvider: z.enum(["ollama", "openai", "anthropic"]).default("ollama"),
  ollamaBaseUrl: z.string().default(DEFAULT_OLLAMA_BASE_URL),
  ollamaNumCtx: z.coerce.number().int().positive().default(DEFAULT_OLLAMA_NUM_CTX),
  modelSmall: z.string().default("gemma4:e2b"),
  modelLarge: z.string().default("qwen3.5:9B"),
  priceModel: z.string().optional(),
  toolCatalogue: z.enum(["deferred", "full"]).default("deferred"),
  maxSubtopics: z.coerce.number().int().positive().default(8),
  maxEscalations: z.coerce.number().int().nonnegative().default(2),
  allowHostedProvider: z
    .string()
    .optional()
    .transform((value) => value === "true"),
  captureMessageContent: z
    .string()
    .default("false")
    .transform((value) => value === "true"),
});

export type Config = z.infer<typeof ConfigSchema>;

// A present-but-empty environment variable is unset, not a value. Zod disagrees: .optional()
// reads "" as present, .default() fires only on undefined and .coerce.number() turns "" into 0.
// compose.yaml and .env.example both ship empty values, so this is applied to every variable.
function unset(value: string | undefined): string | undefined {
  return value === undefined || value.trim() === "" ? undefined : value;
}

export function loadConfig(env: NodeJS.ProcessEnv = process.env): Config {
  const config = ConfigSchema.parse({
    port: unset(env.PORT),
    llmProvider: unset(env.LLM_PROVIDER),
    ollamaBaseUrl: unset(env.OLLAMA_BASE_URL),
    ollamaNumCtx: unset(env.OLLAMA_NUM_CTX),
    modelSmall: unset(env.MODEL_SMALL),
    modelLarge: unset(env.MODEL_LARGE),
    priceModel: unset(env.PRICE_MODEL),
    toolCatalogue: unset(env.TOOL_CATALOGUE),
    maxSubtopics: unset(env.MAX_SUBTOPICS),
    maxEscalations: unset(env.MAX_ESCALATIONS),
    allowHostedProvider: unset(env.ALLOW_HOSTED_PROVIDER),
    captureMessageContent: unset(env.OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT),
  });

  if (config.llmProvider === "ollama" && config.priceModel === undefined) {
    return { ...config, priceModel: OLLAMA_SIMULATED_PRICE_MODEL };
  }

  return config;
}
