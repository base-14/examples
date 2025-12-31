import pino, { type LoggerOptions } from 'pino';
import { trace } from '@opentelemetry/api';

function getTraceContext() {
  const span = trace.getActiveSpan();
  if (!span) return {};

  const spanContext = span.spanContext();
  if (!spanContext.traceId) return {};

  return {
    traceId: spanContext.traceId,
    spanId: spanContext.spanId,
  };
}

const loggerOptions: LoggerOptions = {
  level: process.env.LOG_LEVEL || 'info',
  mixin() {
    return getTraceContext();
  },
};

if (process.env.NODE_ENV === 'development') {
  loggerOptions.transport = { target: 'pino-pretty', options: { colorize: true } };
}

export const logger = pino(loggerOptions);

export function createChildLogger(bindings: Record<string, unknown>) {
  return logger.child(bindings);
}
