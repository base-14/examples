import { vi } from 'vitest';

const createMockSpan = () => ({
  setAttributes: vi.fn().mockReturnThis(),
  setStatus: vi.fn().mockReturnThis(),
  addEvent: vi.fn().mockReturnThis(),
  recordException: vi.fn().mockReturnThis(),
  end: vi.fn(),
  spanContext: vi.fn(() => ({
    traceId: 'test-trace-id',
    spanId: 'test-span-id',
    traceFlags: 1,
  })),
});

vi.mock('@opentelemetry/api', () => ({
  trace: {
    getTracer: vi.fn(() => ({
      startSpan: vi.fn(createMockSpan),
    })),
    getActiveSpan: vi.fn(createMockSpan),
    setSpan: vi.fn((ctx, span) => ctx),
  },
  context: {
    active: vi.fn(() => ({})),
    with: vi.fn((ctx, fn) => fn()),
  },
  propagation: {
    inject: vi.fn(),
    extract: vi.fn(() => ({})),
  },
  SpanStatusCode: {
    OK: 0,
    ERROR: 2,
    UNSET: 1,
  },
  metrics: {
    getMeter: vi.fn(() => ({
      createCounter: vi.fn(() => ({ add: vi.fn() })),
      createHistogram: vi.fn(() => ({ record: vi.fn() })),
      createUpDownCounter: vi.fn(() => ({ add: vi.fn() })),
      createObservableGauge: vi.fn(() => ({ addCallback: vi.fn() })),
    })),
  },
}));

vi.mock('winston', () => {
  const mockLogger = {
    log: vi.fn(),
    info: vi.fn(),
    warn: vi.fn(),
    error: vi.fn(),
    debug: vi.fn(),
  };

  const winstonMock = {
    createLogger: vi.fn(() => mockLogger),
    format: {
      combine: vi.fn(),
      timestamp: vi.fn(),
      errors: vi.fn(() => ({})),
      json: vi.fn(),
      colorize: vi.fn(),
      printf: vi.fn(() => ({})),
    },
    transports: {
      Console: vi.fn(),
    },
  };

  return {
    default: winstonMock,
    ...winstonMock,
  };
});

vi.mock('@opentelemetry/api-logs', () => ({
  logs: {
    getLogger: vi.fn(() => ({
      emit: vi.fn(),
    })),
  },
  SeverityNumber: {
    TRACE: 1,
    DEBUG: 5,
    INFO: 9,
    WARN: 13,
    ERROR: 17,
    FATAL: 21,
  },
}));

vi.mock('isomorphic-dompurify', () => {
  const sanitize = vi.fn((input: string) => input);
  return {
    default: { sanitize },
    sanitize,
  };
});
