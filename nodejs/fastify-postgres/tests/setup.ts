import { vi } from 'vitest';

vi.mock('@opentelemetry/api', () => ({
  trace: {
    getTracer: () => ({
      startActiveSpan: (_name: string, fn: (span: unknown) => unknown) => {
        const mockSpan = {
          setAttribute: vi.fn(),
          setStatus: vi.fn(),
          recordException: vi.fn(),
          addEvent: vi.fn(),
          end: vi.fn(),
        };
        return fn(mockSpan);
      },
    }),
    getActiveSpan: () => null,
  },
  SpanStatusCode: {
    OK: 0,
    ERROR: 1,
  },
  context: {
    active: () => ({}),
  },
  propagation: {
    inject: vi.fn(),
    extract: vi.fn(),
  },
}));

vi.mock('../src/db/index.js', () => ({
  db: {
    select: vi.fn(),
    insert: vi.fn(),
    update: vi.fn(),
    delete: vi.fn(),
    transaction: vi.fn(),
  },
  checkDatabaseHealth: vi.fn().mockResolvedValue(true),
  closeDatabase: vi.fn().mockResolvedValue(undefined),
}));

vi.mock('../src/jobs/queue.js', () => ({
  notificationQueue: {
    add: vi.fn().mockResolvedValue({ id: 'mock-job-id' }),
    getJobCounts: vi.fn().mockResolvedValue({ waiting: 0, active: 0 }),
  },
  closeQueues: vi.fn().mockResolvedValue(undefined),
}));
