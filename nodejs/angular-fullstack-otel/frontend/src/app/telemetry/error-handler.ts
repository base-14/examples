import { ErrorHandler, Injectable } from '@angular/core';
import { logs, SeverityNumber } from '@opentelemetry/api-logs';

// Single capture point for uncaught errors in a zoneless app (Angular errors +
// the window error/unhandledrejection events via provideBrowserGlobalErrorListeners).
// Correlation is best-effort: the span has usually unwound by the time an error
// lands here, so logs may have no trace id. For correlated HTTP-failure logs see
// error-interceptor.
@Injectable()
export class TelemetryErrorHandler implements ErrorHandler {
  private logger = logs.getLogger('browser-errors');

  handleError(error: unknown): void {
    const err = error instanceof Error ? error : new Error(String(error));
    this.logger.emit({
      severityNumber: SeverityNumber.ERROR,
      severityText: 'ERROR',
      body: err.message,
      attributes: {
        'exception.type': err.name,
        'exception.message': err.message,
        'exception.stacktrace': err.stack ?? '',
        'page.path': window.location.pathname,
      },
    });
    console.error(error);
  }
}
