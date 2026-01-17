import { z } from 'zod';

const isBuildTime = process.env.NEXT_PHASE === 'phase-production-build';

const configSchema = z.object({
  nodeEnv: z.enum(['development', 'production', 'test']).default('development'),
  port: z.coerce.number().default(3000),
  mongodbUri: isBuildTime
    ? z.string().default('mongodb://localhost:27017/build-placeholder')
    : z.string().min(1, 'MongoDB URI is required'),
  jwtSecret: isBuildTime
    ? z.string().default('build-placeholder-secret-key-32-chars!')
    : z.string().min(32, 'JWT secret must be at least 32 characters for security'),
  jwtExpiresIn: z.string().default('7d'),
  redisHost: z.string().default('localhost'),
  redisPort: z.coerce.number().default(6379),
  otelEndpoint: z.string().url().default('http://localhost:4318'),
  otelServiceName: z.string().default('nextjs-api-mongodb'),
  scoutEndpoint: z.string().url().optional(),
  scoutClientId: z.string().optional(),
  scoutClientSecret: z.string().optional(),
  scoutTokenUrl: z.string().url().optional(),
  scoutEnvironment: z.string().default('development'),
});

function loadConfig() {
  const result = configSchema.safeParse({
    nodeEnv: process.env.NODE_ENV,
    port: process.env.PORT,
    mongodbUri: process.env.MONGODB_URI,
    jwtSecret: process.env.JWT_SECRET,
    jwtExpiresIn: process.env.JWT_EXPIRES_IN,
    redisHost: process.env.REDIS_HOST,
    redisPort: process.env.REDIS_PORT,
    otelEndpoint: process.env.OTEL_EXPORTER_OTLP_ENDPOINT,
    otelServiceName: process.env.OTEL_SERVICE_NAME,
    scoutEndpoint: process.env.SCOUT_ENDPOINT,
    scoutClientId: process.env.SCOUT_CLIENT_ID,
    scoutClientSecret: process.env.SCOUT_CLIENT_SECRET,
    scoutTokenUrl: process.env.SCOUT_TOKEN_URL,
    scoutEnvironment: process.env.SCOUT_ENVIRONMENT,
  });

  if (!result.success) {
    // Zod 4: use error.issues not error.errors
    const errors = result.error.issues.map(
      (issue) => `${issue.path.join('.')}: ${issue.message}`
    );
    console.error('Configuration validation failed:', errors);
    throw new Error(`Configuration validation failed: ${errors.join(', ')}`);
  }

  return result.data;
}

export const config = loadConfig();

export type Config = z.infer<typeof configSchema>;
