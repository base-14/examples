interface Config {
  port: number;
  host: string;
  environment: string;
  logLevel: string;
  jwt: {
    secret: string;
    expiresIn: string;
  };
  db: {
    host: string;
    port: number;
    user: string;
    password: string;
    database: string;
    url: string;
  };
  redis: {
    url: string;
  };
}

function getEnvOrDefault(key: string, defaultValue: string): string {
  return process.env[key] || defaultValue;
}

function parseDbUrl(url: string): { host: string; port: number; user: string; password: string; database: string } {
  const parsed = new URL(url);
  return {
    host: parsed.hostname,
    port: parseInt(parsed.port || '5432', 10),
    user: parsed.username,
    password: parsed.password,
    database: parsed.pathname.slice(1),
  };
}

const databaseUrl = getEnvOrDefault('DATABASE_URL', 'postgresql://postgres:postgres@localhost:5432/fastify_app');
const dbParsed = parseDbUrl(databaseUrl);

export const config: Config = {
  port: parseInt(getEnvOrDefault('PORT', '3000'), 10),
  host: getEnvOrDefault('HOST', '0.0.0.0'),
  environment: getEnvOrDefault('NODE_ENV', 'development'),
  logLevel: getEnvOrDefault('LOG_LEVEL', 'info'),
  jwt: {
    secret: getEnvOrDefault('JWT_SECRET', 'dev-secret-key-change-in-production-must-be-32-chars'),
    expiresIn: getEnvOrDefault('JWT_EXPIRES_IN', '7d'),
  },
  db: {
    ...dbParsed,
    url: databaseUrl,
  },
  redis: {
    url: getEnvOrDefault('REDIS_URL', 'redis://localhost:6379'),
  },
};
