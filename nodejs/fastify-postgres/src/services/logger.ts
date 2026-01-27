import pino, { Logger, LoggerOptions } from 'pino';
import { trace } from '@opentelemetry/api';
import { logs as otelLogs, SeverityNumber } from '@opentelemetry/api-logs';

const isDevelopment = process.env.NODE_ENV === 'development';
const logLevel = process.env.LOG_LEVEL || 'info';

const severityMap: Record<string, SeverityNumber> = {
  trace: SeverityNumber.TRACE,
  debug: SeverityNumber.DEBUG,
  info: SeverityNumber.INFO,
  warn: SeverityNumber.WARN,
  error: SeverityNumber.ERROR,
  fatal: SeverityNumber.FATAL,
};

function emitToOTel(level: string, msg: string, obj: Record<string, unknown>) {
  const logger = otelLogs.getLogger('pino-otel-bridge');
  const span = trace.getActiveSpan();
  const spanContext = span?.spanContext();

  logger.emit({
    severityNumber: severityMap[level] || SeverityNumber.INFO,
    severityText: level.toUpperCase(),
    body: msg,
    attributes: {
      ...obj,
      ...(spanContext && {
        'trace.id': spanContext.traceId,
        'span.id': spanContext.spanId,
      }),
    },
  });
}

function createLoggerOptions(name: string): LoggerOptions {
  return {
    level: logLevel,
    name,
    formatters: {
      log(object: Record<string, unknown>) {
        const span = trace.getActiveSpan();
        if (span) {
          const { traceId, spanId } = span.spanContext();
          return { ...object, traceId, spanId };
        }
        return object;
      },
    },
    hooks: {
      logMethod(inputArgs, method, level) {
        const levelLabel = pino.levels.labels[level] || 'info';
        const [objOrMsg, ...rest] = inputArgs;

        let msg = '';
        let obj: Record<string, unknown> = {};

        if (typeof objOrMsg === 'string') {
          msg = objOrMsg;
        } else if (typeof objOrMsg === 'object' && objOrMsg !== null) {
          obj = objOrMsg as Record<string, unknown>;
          msg = rest[0] as string || '';
        }

        if (levelLabel === 'warn' || levelLabel === 'error' || levelLabel === 'fatal') {
          emitToOTel(levelLabel, msg, obj);
        }

        method.apply(this, inputArgs);
      },
    },
    transport: isDevelopment ? { target: 'pino-pretty' } : undefined,
  };
}

export function createLogger(name: string): Logger {
  return pino(createLoggerOptions(name));
}

export const logger = createLogger('fastify-postgres');

export function createFastifyLoggerConfig(): LoggerOptions {
  return createLoggerOptions('fastify');
}
