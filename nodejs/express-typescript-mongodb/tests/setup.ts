import { beforeAll, afterAll, beforeEach, afterEach, vi } from 'vitest';
import { setupTestDatabase, teardownTestDatabase } from './helpers/db.helper';
import './helpers/mocks';

beforeAll(async () => {
  process.env.NODE_ENV = 'test';
  process.env.JWT_SECRET = 'test-secret-key-for-testing-only';
  process.env.MONGODB_URI = 'mongodb://localhost:27017/test-db';
  process.env.REDIS_URL = 'redis://localhost:6379';
  process.env.LOG_LEVEL = 'silent';
  process.env.OTEL_SDK_DISABLED = 'true';

  await setupTestDatabase();
});

afterAll(async () => {
  await teardownTestDatabase();
});

beforeEach(() => {
  vi.clearAllMocks();
  vi.resetModules();
});

afterEach(() => {
  vi.restoreAllMocks();
});

global.console = {
  ...console,
  log: vi.fn(),
  debug: vi.fn(),
  info: vi.fn(),
  warn: vi.fn(),
  error: vi.fn(),
};
