import { HttpErrorResponse, HttpInterceptorFn } from '@angular/common/http';
import { context } from '@opentelemetry/api';
import { logs, SeverityNumber } from '@opentelemetry/api-logs';
import { catchError, throwError } from 'rxjs';

// Trace-correlated ERROR log for every failed HttpClient request. catchError runs
// async, after the zoneless context has unwound, so we capture the context here
// (synchronous, caller's span still active) and re-enter it at emit - emit()
// stamps the trace id from the active context, so this is what keeps the log
// correlated.
export const errorLogInterceptor: HttpInterceptorFn = (req, next) => {
  const activeContext = context.active();
  return next(req).pipe(
    catchError((err: HttpErrorResponse) => {
      const logger = logs.getLogger('browser-http');
      context.with(activeContext, () => {
        logger.emit({
          severityNumber: SeverityNumber.ERROR,
          severityText: 'ERROR',
          body: `HTTP ${req.method} ${req.urlWithParams} failed: ${err.status} ${err.message}`,
          attributes: {
            'http.request.method': req.method,
            'url.full': req.urlWithParams,
            'http.response.status_code': err.status,
            'error.type': err.name,
          },
        });
      });
      return throwError(() => err);
    }),
  );
};
