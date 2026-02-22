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
    llmProvider: z.enum(["anthropic", "google", "ollama"]).default("anthropic"),
    embeddingProvider: z.enum(["openai", "ollama", "google"]).default("openai"),
    ollamaBaseUrl: z.string().default("http://localhost:11434"),
    llmModelCapable: z.string().optional(),
    llmModelFast: z.string().optional(),
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

const parsed = ConfigSchema.safeParse({
  port: Bun.env.PORT,
  databaseUrl: Bun.env.DATABASE_URL,
  anthropicApiKey: Bun.env.ANTHROPIC_API_KEY,
  openaiApiKey: Bun.env.OPENAI_API_KEY,
  googleApiKey: Bun.env.GOOGLE_GENERATIVE_AI_API_KEY,
  otelServiceName: Bun.env.OTEL_SERVICE_NAME,
  otelExporterEndpoint: Bun.env.OTEL_EXPORTER_OTLP_ENDPOINT,
  otelEnabled: Bun.env.OTEL_ENABLED,
  nodeEnv: Bun.env.NODE_ENV,
  llmProvider: Bun.env.LLM_PROVIDER,
  embeddingProvider: Bun.env.EMBEDDING_PROVIDER,
  ollamaBaseUrl: Bun.env.OLLAMA_BASE_URL,
  llmModelCapable: Bun.env.LLM_MODEL_CAPABLE,
  llmModelFast: Bun.env.LLM_MODEL_FAST,
  embeddingModel: Bun.env.EMBEDDING_MODEL,
});

if (!parsed.success) {
  console.error("Configuration error:", flattenError(parsed.error).fieldErrors);
  throw new Error("Invalid configuration — check environment variables");
}

export const config = parsed.data;
