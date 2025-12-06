import { z } from 'zod';

const configSchema = z.object({
  app: z.object({
    port: z.number().int().min(1).max(65535),
    env: z.enum(['development', 'production', 'test']),
    version: z.string(),
  }),
  jwt: z.object({
    secret: z.string().min(32, 'JWT_SECRET should be at least 32 characters for security'),
    expiresIn: z.string(),
  }),
  mongodb: z.object({
    uri: z.string()
      .refine(
        (val) => val.startsWith('mongodb://') || val.startsWith('mongodb+srv://'),
        'MONGODB_URI must start with mongodb:// or mongodb+srv://'
      ),
  }),
  redis: z.object({
    url: z.string()
      .refine(
        (val) => val.startsWith('redis://') || val.startsWith('rediss://'),
        'REDIS_URL must start with redis:// or rediss://'
      ),
  }),
  otel: z.object({
    serviceName: z.string().min(1),
    endpoint: z.string()
      .refine(
        (val) => val.startsWith('http://') || val.startsWith('https://'),
        'OTEL_EXPORTER_OTLP_ENDPOINT must start with http:// or https://'
      ),
  }),
  cors: z.object({
    origin: z.string(),
  }),
  rateLimit: z.object({
    windowMs: z.number().int().positive(),
    max: z.number().int().positive(),
  }),
  pagination: z.object({
    defaultLimit: z.number().int().positive(),
    maxLimit: z.number().int().positive(),
  }),
  auth: z.object({
    bcryptRounds: z.number().int().min(10).max(15),
    minPasswordLength: z.number().int().min(8),
  }),
}).refine(
  (data) => {
    if (data.app.env === 'production') {
      return data.jwt.secret !== 'your-secret-key-change-in-production';
    }
    return true;
  },
  {
    message: 'JWT_SECRET must be changed from default value in production',
    path: ['jwt', 'secret'],
  }
);

const rawConfig = {
  app: {
    port: parseInt(process.env['APP_PORT'] ?? '3000', 10),
    env: process.env['NODE_ENV'] ?? 'development',
    version: process.env['APP_VERSION'] ?? '1.0.0',
  },
  jwt: {
    secret: process.env['JWT_SECRET'] ?? 'your-secret-key-change-in-production',
    expiresIn: process.env['JWT_EXPIRES_IN'] ?? '7d',
  },
  mongodb: {
    uri: process.env['MONGODB_URI'] ?? 'mongodb://mongo:27017/express-app',
  },
  redis: {
    url: process.env['REDIS_URL'] ?? 'redis://localhost:6379',
  },
  otel: {
    serviceName: process.env['OTEL_SERVICE_NAME'] ?? 'express-mongodb-app',
    endpoint: process.env['OTEL_EXPORTER_OTLP_ENDPOINT'] ?? 'http://otel-collector:4318',
  },
  cors: {
    origin: process.env['CORS_ORIGIN'] ?? '*',
  },
  rateLimit: {
    windowMs: parseInt(process.env['RATE_LIMIT_WINDOW_MS'] ?? '900000', 10),
    max: parseInt(process.env['RATE_LIMIT_MAX'] ?? '100', 10),
  },
  pagination: {
    defaultLimit: 10,
    maxLimit: 100,
  },
  auth: {
    bcryptRounds: 10,
    minPasswordLength: 8,
  },
};

const parseResult = configSchema.safeParse(rawConfig);

if (!parseResult.success) {
  console.error('❌ Configuration validation failed:');
  parseResult.error.issues.forEach((issue) => {
    console.error(`  - ${issue.path.join('.')}: ${issue.message}`);
  });
  process.exit(1);
}

export const config = parseResult.data;

// Production-specific warnings (non-fatal)
if (config.app.env === 'production') {
  if (config.cors.origin === '*') {
    console.warn('⚠️  Warning: CORS origin is set to "*" in production - this is a security risk');
  }
}

export type Config = z.infer<typeof configSchema>;
