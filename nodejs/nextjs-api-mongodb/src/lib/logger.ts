import pino from 'pino';
import { trace, context } from '@opentelemetry/api';

function getTraceContext(): Record<string, string> {
  const span = trace.getSpan(context.active());
  if (!span) {
    return {};
  }

  const spanContext = span.spanContext();
  return {
    traceId: spanContext.traceId,
    spanId: spanContext.spanId,
    traceFlags: spanContext.traceFlags.toString(),
  };
}

const baseLogger = pino({
  level: process.env.LOG_LEVEL || 'info',
  formatters: {
    level: (label) => ({ level: label }),
  },
  timestamp: pino.stdTimeFunctions.isoTime,
  base: {
    service: process.env.OTEL_SERVICE_NAME || 'nextjs-api-mongodb',
    env: process.env.NODE_ENV || 'development',
  },
});

function createLogMethod(level: 'info' | 'warn' | 'error' | 'debug') {
  return (message: string, data?: Record<string, unknown>) => {
    const traceContext = getTraceContext();
    baseLogger[level]({ ...traceContext, ...data }, message);
  };
}

export const logger = {
  info: createLogMethod('info'),
  warn: createLogMethod('warn'),
  error: createLogMethod('error'),
  debug: createLogMethod('debug'),

  child: (bindings: Record<string, unknown>) => {
    const childLogger = baseLogger.child(bindings);
    return {
      info: (message: string, data?: Record<string, unknown>) => {
        const traceContext = getTraceContext();
        childLogger.info({ ...traceContext, ...data }, message);
      },
      warn: (message: string, data?: Record<string, unknown>) => {
        const traceContext = getTraceContext();
        childLogger.warn({ ...traceContext, ...data }, message);
      },
      error: (message: string, data?: Record<string, unknown>) => {
        const traceContext = getTraceContext();
        childLogger.error({ ...traceContext, ...data }, message);
      },
      debug: (message: string, data?: Record<string, unknown>) => {
        const traceContext = getTraceContext();
        childLogger.debug({ ...traceContext, ...data }, message);
      },
    };
  },
};

export function logError(
  message: string,
  error: unknown,
  extra?: Record<string, unknown>
): void {
  const errorData: Record<string, unknown> = {
    ...extra,
  };

  if (error instanceof Error) {
    errorData.errorName = error.name;
    errorData.errorMessage = error.message;
    errorData.stack = error.stack;
  } else {
    errorData.error = String(error);
  }

  logger.error(message, errorData);
}
