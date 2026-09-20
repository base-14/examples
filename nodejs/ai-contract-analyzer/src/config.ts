import { flattenError, z } from "zod";

const ConfigSchema = z
  .object({
    port: z.coerce.number().default(3000),
    databaseUrl: z.string().min(1, "DATABASE_URL is required"),
    anthropicApiKey: z.string().optional(),
    openaiApiKey: z.string().optional(),
    otelServiceName: z.string().default("ai-contract-analyzer"),
    otelExporterEndpoint: z.string().default("http://localhost:4318"),
    // default("true") before transform so the transform always runs on a string
    otelEnabled: z
      .string()
      .default("true")
      .transform((v) => v === "true"),
    nodeEnv: z.enum(["development", "production", "test"]).default("development"),
    googleApiKey: z.string().optional(),
    llmProvider: z.enum(["anthropic", "google", "ollama"]).default("ollama"),
    embeddingProvider: z.enum(["openai", "ollama", "google"]).default("ollama"),
    ollamaBaseUrl: z.string().default("http://localhost:11434"),
    llmModelCapable: z.string().optional(),
    llmModelFast: z.string().optional(),
    llmProviderFallback: z.enum(["anthropic", "google", "ollama"]).optional(),
    llmModelFallback: z.string().optional(),
    embeddingModel: z.string().optional(),
  })
  .superRefine((data, ctx) => {
    if (data.llmProvider === "anthropic" && !data.anthropicApiKey) {
      ctx.addIssue({
        code: z.ZodIssueCode.custom,
        message: "ANTHROPIC_API_KEY is required when LLM_PROVIDER=anthropic",
        path: ["anthropicApiKey"],
      });
    }
    if (data.llmProvider === "google" && !data.googleApiKey) {
      ctx.addIssue({
        code: z.ZodIssueCode.custom,
        message: "GOOGLE_GENERATIVE_AI_API_KEY is required when LLM_PROVIDER=google",
        path: ["googleApiKey"],
      });
    }
    if (data.embeddingProvider === "openai" && !data.openaiApiKey) {
      ctx.addIssue({
        code: z.ZodIssueCode.custom,
        message: "OPENAI_API_KEY is required when EMBEDDING_PROVIDER=openai",
        path: ["openaiApiKey"],
      });
    }
    if (data.embeddingProvider === "google" && !data.googleApiKey) {
      ctx.addIssue({
        code: z.ZodIssueCode.custom,
        message: "GOOGLE_GENERATIVE_AI_API_KEY is required when EMBEDDING_PROVIDER=google",
        path: ["googleApiKey"],
      });
    }
  });

// compose forwards an unset optional variable as "" (`${VAR:-}`), which an enum
// rejects and a default does not replace. Treat blank as absent.
const env = (value: string | undefined): string | undefined => value || undefined;

const parsed = ConfigSchema.safeParse({
  port: env(Bun.env.PORT),
  databaseUrl: Bun.env.DATABASE_URL,
  anthropicApiKey: env(Bun.env.ANTHROPIC_API_KEY),
  openaiApiKey: env(Bun.env.OPENAI_API_KEY),
  googleApiKey: env(Bun.env.GOOGLE_GENERATIVE_AI_API_KEY),
  otelServiceName: env(Bun.env.OTEL_SERVICE_NAME),
  otelExporterEndpoint: env(Bun.env.OTEL_EXPORTER_OTLP_ENDPOINT),
  otelEnabled: env(Bun.env.OTEL_ENABLED),
  nodeEnv: env(Bun.env.NODE_ENV),
  llmProvider: env(Bun.env.LLM_PROVIDER),
  embeddingProvider: env(Bun.env.EMBEDDING_PROVIDER),
  ollamaBaseUrl: env(Bun.env.OLLAMA_BASE_URL),
  llmModelCapable: env(Bun.env.LLM_MODEL_CAPABLE),
  llmModelFast: env(Bun.env.LLM_MODEL_FAST),
  llmProviderFallback: env(Bun.env.FALLBACK_PROVIDER),
  llmModelFallback: env(Bun.env.FALLBACK_MODEL),
  embeddingModel: env(Bun.env.EMBEDDING_MODEL),
});

if (!parsed.success) {
  console.error("Configuration error:", flattenError(parsed.error).fieldErrors);
  throw new Error("Invalid configuration - check environment variables");
}

export const config = parsed.data;
