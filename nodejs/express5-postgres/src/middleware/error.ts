import type { Request, Response, NextFunction, ErrorRequestHandler } from 'express';
import { trace } from '@opentelemetry/api';
import { logger } from '../logger.js';

interface ApiError extends Error {
  statusCode?: number;
}

export const errorHandler: ErrorRequestHandler = (
  err: ApiError,
  req: Request,
  res: Response,
  _next: NextFunction
) => {
  const span = trace.getActiveSpan();
  const spanContext = span?.spanContext();

  const statusCode = err.statusCode || 500;
  const message = err.message || 'Internal Server Error';

  const response: Record<string, unknown> = {
    error: message,
  };

  if (spanContext?.traceId) {
    response.trace_id = spanContext.traceId;
  }

  if (statusCode >= 500) {
    logger.error({ err, path: req.path, method: req.method }, 'Server error');
  }

  res.status(statusCode).json(response);
};

export function notFoundHandler(req: Request, res: Response) {
  const span = trace.getActiveSpan();
  const spanContext = span?.spanContext();

  const response: Record<string, unknown> = {
    error: 'Not Found',
  };

  if (spanContext?.traceId) {
    response.trace_id = spanContext.traceId;
  }

  res.status(404).json(response);
}
