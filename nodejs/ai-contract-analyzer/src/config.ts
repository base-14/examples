import { flattenError, z } from "zod";

const ConfigSchema = z.object({
  port: z.coerce.number().default(3000),
  databaseUrl: z.string().min(1, "DATABASE_URL is required"),
  anthropicApiKey: z.string().min(1, "ANTHROPIC_API_KEY is required"),
  openaiApiKey: z.string().min(1, "OPENAI_API_KEY is required"),
  otelServiceName: z.string().default("ai-contract-analyzer"),
  otelExporterEndpoint: z.string().default("http://localhost:4318"),
  // default("true") before transform so the transform always runs on a string
  otelEnabled: z
    .string()
    .default("true")
    .transform((v) => v === "true"),
  nodeEnv: z.enum(["development", "production", "test"]).default("development"),
});

const parsed = ConfigSchema.safeParse({
  port: Bun.env.PORT,
  databaseUrl: Bun.env.DATABASE_URL,
  anthropicApiKey: Bun.env.ANTHROPIC_API_KEY,
  openaiApiKey: Bun.env.OPENAI_API_KEY,
  otelServiceName: Bun.env.OTEL_SERVICE_NAME,
  otelExporterEndpoint: Bun.env.OTEL_EXPORTER_OTLP_ENDPOINT,
  otelEnabled: Bun.env.OTEL_ENABLED,
  nodeEnv: Bun.env.NODE_ENV,
});

if (!parsed.success) {
  console.error("Configuration error:", flattenError(parsed.error).fieldErrors);
  throw new Error("Invalid configuration — check environment variables");
}

export const config = parsed.data;
