import {
  ExceptionFilter,
  Catch,
  ArgumentsHost,
  HttpException,
  HttpStatus,
} from '@nestjs/common';
import { Request, Response } from 'express';
import { trace, SpanStatusCode } from '@opentelemetry/api';
import { logs, SeverityNumber } from '@opentelemetry/api-logs';

const logger = logs.getLogger('http-exception-filter');

@Catch()
export class HttpExceptionFilter implements ExceptionFilter {
  catch(exception: unknown, host: ArgumentsHost) {
    const ctx = host.switchToHttp();
    const response = ctx.getResponse<Response>();
    const request = ctx.getRequest<Request>();

    const status =
      exception instanceof HttpException
        ? exception.getStatus()
        : HttpStatus.INTERNAL_SERVER_ERROR;

    const message =
      exception instanceof HttpException
        ? exception.message
        : 'Internal server error';

    const errorResponse = {
      statusCode: status,
      message,
      timestamp: new Date().toISOString(),
      path: request.url,
    };

    const currentSpan = trace.getActiveSpan();
    const spanContext = currentSpan?.spanContext();

    if (status >= 500) {
      logger.emit({
        severityNumber: SeverityNumber.ERROR,
        severityText: 'ERROR',
        body: message,
        attributes: {
          'http.method': request.method,
          'http.url': request.url,
          'http.status_code': status,
          'error.type': exception instanceof Error ? exception.name : 'Error',
          'error.message': message,
          'error.stack':
            exception instanceof Error ? exception.stack : undefined,
          ...(spanContext && {
            'trace.id': spanContext.traceId,
            'span.id': spanContext.spanId,
          }),
        },
      });

      if (currentSpan) {
        currentSpan.setStatus({
          code: SpanStatusCode.ERROR,
          message,
        });
        currentSpan.recordException(
          exception instanceof Error ? exception : new Error(String(exception)),
        );
      }
    } else if (status >= 400) {
      logger.emit({
        severityNumber: SeverityNumber.WARN,
        severityText: 'WARN',
        body: message,
        attributes: {
          'http.method': request.method,
          'http.url': request.url,
          'http.status_code': status,
          ...(spanContext && {
            'trace.id': spanContext.traceId,
            'span.id': spanContext.spanId,
          }),
        },
      });
    }

    response.status(status).json(errorResponse);
  }
}
