import { z } from "zod";

// ollama-ai-provider-v2 builds every request URL as `${baseURL}${path}`, where path is
// already `/chat` or `/show`, and its own default base URL is http://127.0.0.1:11434/api.
// A base URL without the /api suffix therefore resolves to http://host:11434/chat, which
// Ollama answers 404 to on every call.
//
// The host part cannot be one value for both ways of running this. Ollama runs on the
// host, not in Compose: a container reaches it at host.docker.internal, which does not
// resolve on the host itself, and localhost inside a container is the container. This
// default is the host form, for `make start`; compose.yaml overrides it with the container
// form. Both then work with no .env at all, and tests/packaging.test.ts pins both halves.
const DEFAULT_OLLAMA_BASE_URL = "http://localhost:11434/api";

// Ollama's own default num_ctx is 4096. A lead run accumulates sixteen steps of tool
// results from this corpus and overruns that partway through, which Ollama reports as
// done_reason "length" with no content, and the run fails with "No output generated".
// The provider sends no options block at all unless providerOptions.ollama.options is
// set, so nothing raises it without this. See llm/models.ts.
//
// 16384 rather than more, because it is the largest window that keeps qwen3.5:9B inside a
// 16 GB machine: 5.91 GB of VRAM at this setting against 6.47 GB at 32768. Raise it on a
// measured overrun, which is Ollama answering done_reason "length"; lower it if the VRAM
// budget changes. tests/config.test.ts asserts that floor and nothing else.
//
// For scale, not as a rule: across 601 model calls in 26 plan runs the largest single
// prompt was 10984 tokens and the 95th percentile was 3716. That peak is a sample, so it
// only ever grows, and pinning a ratio to it would mean the next person to measure finds
// the rule already broken - which is exactly what happened to the ratio that used to be
// here.
const DEFAULT_OLLAMA_NUM_CTX = 16384;

// A local model has no price row of its own, so without this every run of the shipped
// configuration reports a cost of zero - on an example whose subject is cost per
// completed task under fan-out. gpt-5-nano is the cheapest current-generation small
// model in _shared/pricing.json, which makes it the closest stand-in the table has for a
// small local model. The rate is borrowed, not real: every cost computed from it carries
// base14.gen_ai.cost.simulated=true (see llm/cost.ts). Only applied on the Ollama path;
// a hosted provider prices its own models from their own rows.
const OLLAMA_SIMULATED_PRICE_MODEL = "gpt-5-nano";

// The port the HTTP server binds. Routed through loadConfig like every other setting
// rather than left a literal in index.ts: a reader with anything else already on 3000 has
// no way to move it without editing source, and a host run then dies with EADDRINUSE.
// compose.yaml publishes 3000 and does not pass this through, so setting it in .env moves
// a host run only.
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

// An environment variable that is present and empty is an unset variable, not a value.
// Zod disagrees: .optional() reads "" as present, .default() only fires on undefined and
// .coerce.number() turns "" into 0. compose.yaml and .env.example both ship PRICE_MODEL=
// empty, which reached assertPriceModelIsKnown as the empty string and threw at boot on
// exactly the configuration the repo ships. Applied to every variable rather than to that
// one, since the same shape produces a different wrong answer for each kind of field.
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
