import { z } from 'zod';

const configSchema = z.object({
  app: z.object({
    port: z.coerce.number().default(3000),
    env: z.string().default('development'),
    version: z.string().default('1.0.0'),
  }),
  database: z.object({
    url: z.string().url().or(z.string().startsWith('postgresql://')),
  }),
  redis: z.object({
    url: z.string().default('redis://localhost:6379'),
  }),
  jwt: z.object({
    secret: z.string().min(1),
    expiresIn: z.string().default('7d'),
  }),
  cors: z.object({
    origin: z.string().default('*'),
  }),
  rateLimit: z.object({
    windowMs: z.coerce.number().default(900000),
    max: z.coerce.number().default(100),
  }),
  otel: z.object({
    serviceName: z.string().default('nestjs-postgres-app'),
    endpoint: z.string().default('http://localhost:4318'),
    resourceAttributes: z.string().optional(),
  }),
});

export type AppConfig = z.infer<typeof configSchema>;

export function loadConfiguration(): AppConfig {
  const config = {
    app: {
      port: process.env.APP_PORT,
      env: process.env.NODE_ENV,
      version: process.env.APP_VERSION,
    },
    database: {
      url: process.env.DATABASE_URL,
    },
    redis: {
      url: process.env.REDIS_URL,
    },
    jwt: {
      secret: process.env.JWT_SECRET,
      expiresIn: process.env.JWT_EXPIRES_IN,
    },
    cors: {
      origin: process.env.CORS_ORIGIN,
    },
    rateLimit: {
      windowMs: process.env.RATE_LIMIT_WINDOW_MS,
      max: process.env.RATE_LIMIT_MAX,
    },
    otel: {
      serviceName: process.env.OTEL_SERVICE_NAME,
      endpoint: process.env.OTEL_EXPORTER_OTLP_ENDPOINT,
      resourceAttributes: process.env.OTEL_RESOURCE_ATTRIBUTES,
    },
  };

  return configSchema.parse(config);
}

export default () => loadConfiguration();
