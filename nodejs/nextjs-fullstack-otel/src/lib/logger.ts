import { logs, SeverityNumber } from '@opentelemetry/api-logs';

const logger = logs.getLogger('sample-nextjs-app');

export function logInfo(message: string, attributes?: Record<string, string | number | boolean>) {
  logger.emit({
    severityNumber: SeverityNumber.INFO,
    severityText: 'INFO',
    body: message,
    attributes,
  });
}

export function logError(message: string, attributes?: Record<string, string | number | boolean>) {
  logger.emit({
    severityNumber: SeverityNumber.ERROR,
    severityText: 'ERROR',
    body: message,
    attributes,
  });
}

export function logWarn(message: string, attributes?: Record<string, string | number | boolean>) {
  logger.emit({
    severityNumber: SeverityNumber.WARN,
    severityText: 'WARN',
    body: message,
    attributes,
  });
}
