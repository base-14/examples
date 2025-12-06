import type { Request, Response, NextFunction } from 'express';
import { trace, SpanStatusCode } from '@opentelemetry/api';
import mongoose from 'mongoose';
import { getLogger } from '../utils/logger.js';
import { AppError } from '../utils/errors.js';
import { config } from '../config.js';

const logger = getLogger('error-handler');

export function errorHandler(
  err: Error,
  req: Request,
  res: Response,
  _next: NextFunction
): void {
  const span = trace.getActiveSpan();

  if (span) {
    span.recordException(err);
    span.setStatus({ code: SpanStatusCode.ERROR, message: err.message });
  }

  if (err instanceof AppError) {
    logger.warn('Request error', {
      path: req.path,
      method: req.method,
      statusCode: err.statusCode,
      code: err.code,
      error: err.message,
    });

    res.status(err.statusCode).json({
      error: err.message,
      code: err.code,
    });
    return;
  }

  // Handle Mongoose CastError (invalid ObjectId)
  if (err instanceof mongoose.Error.CastError) {
    logger.warn('Invalid ID format', {
      path: req.path,
      method: req.method,
      value: err.value,
      kind: err.kind,
    });

    res.status(400).json({
      error: 'Invalid ID format',
      message: `Invalid ${err.kind}: ${err.value}`,
    });
    return;
  }

  // Handle Mongoose ValidationError
  if (err instanceof mongoose.Error.ValidationError) {
    logger.warn('Validation error', {
      path: req.path,
      method: req.method,
      errors: err.errors,
    });

    res.status(400).json({
      error: 'Validation failed',
      details: Object.values(err.errors).map((e) => e.message),
    });
    return;
  }

  logger.error('Unhandled error', err, {
    path: req.path,
    method: req.method,
    statusCode: 500,
  });

  res.status(500).json({
    error: 'Internal server error',
    message: config.app.env === 'development' ? err.message : undefined,
  });
}

export function notFoundHandler(req: Request, res: Response): void {
  logger.warn('Route not found', {
    path: req.path,
    method: req.method,
  });

  res.status(404).json({
    error: 'Not found',
    path: req.path,
  });
}
