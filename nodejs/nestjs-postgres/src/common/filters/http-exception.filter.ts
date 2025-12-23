import {
  ExceptionFilter,
  Catch,
  ArgumentsHost,
  HttpException,
  HttpStatus,
  NotFoundException,
  UnauthorizedException,
  ForbiddenException,
  ConflictException,
  BadRequestException,
} from '@nestjs/common';
import { ThrottlerException } from '@nestjs/throttler';
import { Request, Response } from 'express';
import { trace, SpanStatusCode, metrics } from '@opentelemetry/api';
import { logs, SeverityNumber } from '@opentelemetry/api-logs';

const logger = logs.getLogger('http-exception-filter');
const meter = metrics.getMeter('http-errors');

const httpErrorsCounter = meter.createCounter('http_errors_total', {
  description: 'Total HTTP errors by status code, route, and error code',
});

export enum ErrorCode {
  RESOURCE_NOT_FOUND = 'RESOURCE_NOT_FOUND',
  UNAUTHORIZED = 'UNAUTHORIZED',
  FORBIDDEN = 'FORBIDDEN',
  CONFLICT = 'CONFLICT',
  BAD_REQUEST = 'BAD_REQUEST',
  VALIDATION_ERROR = 'VALIDATION_ERROR',
  INTERNAL_SERVER_ERROR = 'INTERNAL_SERVER_ERROR',
  RATE_LIMIT_EXCEEDED = 'RATE_LIMIT_EXCEEDED',
}

interface ErrorResponse {
  error: {
    code: ErrorCode;
    message: string;
    statusCode: number;
    timestamp: string;
    path: string;
    traceId?: string;
    details?: unknown;
  };
}

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

    const errorCode = this.getErrorCode(exception, status);
    const currentSpan = trace.getActiveSpan();
    const spanContext = currentSpan?.spanContext();

    const errorResponse: ErrorResponse = {
      error: {
        code: errorCode,
        message,
        statusCode: status,
        timestamp: new Date().toISOString(),
        path: request.url,
        ...(spanContext && { traceId: spanContext.traceId }),
        ...this.getValidationDetails(exception),
      },
    };

    httpErrorsCounter.add(1, {
      'http.status_code': status,
      'http.method': request.method,
      'http.route': (request.route as { path?: string })?.path || request.url,
      'error.code': errorCode,
      'error.category': status >= 500 ? 'server' : 'client',
    });

    if (status >= 500) {
      logger.emit({
        severityNumber: SeverityNumber.ERROR,
        severityText: 'ERROR',
        body: message,
        attributes: {
          'http.method': request.method,
          'http.url': request.url,
          'http.status_code': status,
          'error.code': errorCode,
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
        currentSpan.setAttribute('error.code', errorCode);
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
          'error.code': errorCode,
          ...(spanContext && {
            'trace.id': spanContext.traceId,
            'span.id': spanContext.spanId,
          }),
        },
      });
    }

    response.status(status).json(errorResponse);
  }

  private getErrorCode(exception: unknown, status: number): ErrorCode {
    if (exception instanceof NotFoundException) {
      return ErrorCode.RESOURCE_NOT_FOUND;
    }
    if (exception instanceof UnauthorizedException) {
      return ErrorCode.UNAUTHORIZED;
    }
    if (exception instanceof ForbiddenException) {
      return ErrorCode.FORBIDDEN;
    }
    if (exception instanceof ConflictException) {
      return ErrorCode.CONFLICT;
    }
    if (exception instanceof ThrottlerException) {
      return ErrorCode.RATE_LIMIT_EXCEEDED;
    }
    if (exception instanceof BadRequestException) {
      const response = exception.getResponse();
      if (
        typeof response === 'object' &&
        response !== null &&
        'message' in response &&
        Array.isArray((response as { message: unknown }).message)
      ) {
        return ErrorCode.VALIDATION_ERROR;
      }
      return ErrorCode.BAD_REQUEST;
    }
    if (status >= 500) {
      return ErrorCode.INTERNAL_SERVER_ERROR;
    }
    return ErrorCode.BAD_REQUEST;
  }

  private getValidationDetails(exception: unknown): {
    details?: { validationErrors: string[] };
  } {
    if (exception instanceof BadRequestException) {
      const response = exception.getResponse();
      if (
        typeof response === 'object' &&
        response !== null &&
        'message' in response
      ) {
        const messages = (response as { message: unknown }).message;
        if (Array.isArray(messages)) {
          return {
            details: { validationErrors: messages.map((m) => String(m)) },
          };
        }
      }
    }
    return {};
  }
}
