import winston from 'winston';
import { trace, context as otelContext, type Span } from '@opentelemetry/api';
import { logs, SeverityNumber } from '@opentelemetry/api-logs';
import { config } from '../config.js';

const logLevel = process.env['LOG_LEVEL'] ?? 'info';

const otelLogger = logs.getLogger(config.otel.serviceName, config.app.version);

const baseLogger = winston.createLogger({
  level: logLevel,
  format: winston.format.combine(
    winston.format.timestamp(),
    winston.format.errors({ stack: true }),
    winston.format.json()
  ),
  defaultMeta: {
    service: config.otel.serviceName,
  },
  transports: [
    new winston.transports.Console({
      format: winston.format.combine(
        winston.format.colorize(),
        winston.format.printf((info) => {
          const { timestamp, level, message, component, trace_id, _span_id, ...meta } = info;
          const traceInfo =
            trace_id && typeof trace_id === 'string' ? `[trace_id=${trace_id.slice(0, 8)}]` : '';
          const componentInfo = component ? `[${component}]` : '';
          const filteredMeta = Object.keys(meta).filter(
            (k) => k !== 'service' && k !== 'trace_flags' && k !== 'span_id'
          );
          const metaStr = filteredMeta.length
            ? ` ${JSON.stringify(Object.fromEntries(filteredMeta.map((k) => [k, meta[k]])))}`
            : '';
          return `${timestamp} ${level} ${componentInfo}${traceInfo}: ${message}${metaStr}`;
        })
      ),
    }),
  ],
});

interface LogContext {
  component?: string;
  [key: string]: unknown;
}

function getTraceContext(): Record<string, string | number> {
  const span: Span | undefined = trace.getActiveSpan();
  if (span) {
    const spanContext = span.spanContext();
    return {
      trace_id: spanContext.traceId,
      span_id: spanContext.spanId,
      trace_flags: spanContext.traceFlags,
    };
  }
  return {};
}

function getSeverityNumber(level: string): SeverityNumber {
  switch (level) {
    case 'debug':
      return SeverityNumber.DEBUG;
    case 'info':
      return SeverityNumber.INFO;
    case 'warn':
      return SeverityNumber.WARN;
    case 'error':
      return SeverityNumber.ERROR;
    default:
      return SeverityNumber.INFO;
  }
}

export class Logger {
  private component: string;

  constructor(component: string) {
    this.component = component;
  }

  private log(level: string, message: string, context?: LogContext): void {
    const traceContext = getTraceContext();
    const logContext = {
      ...context,
      component: this.component,
      'deployment.environment': config.app.env,
    };

    baseLogger.log(level, message, { ...logContext, ...traceContext });

    otelLogger.emit({
      severityNumber: getSeverityNumber(level),
      severityText: level.toUpperCase(),
      body: message,
      attributes: logContext,
      context: otelContext.active(),
    });
  }

  debug(message: string, context?: LogContext): void {
    this.log('debug', message, context);
  }

  info(message: string, context?: LogContext): void {
    this.log('info', message, context);
  }

  warn(message: string, context?: LogContext): void {
    this.log('warn', message, context);
  }

  error(message: string, error?: Error, context?: LogContext): void {
    this.log('error', message, {
      ...context,
      error: error?.message,
      stack: error?.stack,
      error_name: error?.name,
    });
  }
}

export function getLogger(component: string): Logger {
  return new Logger(component);
}
