import type { Request, Response, NextFunction } from 'express';
import { metrics } from '@opentelemetry/api';

const meter = metrics.getMeter('http-middleware');

const requestCounter = meter.createCounter('http_requests_total', {
  description: 'Total number of HTTP requests',
  unit: '1',
});

const requestDurationHistogram = meter.createHistogram('http_request_duration_ms', {
  description: 'HTTP request duration in milliseconds',
  unit: 'ms',
});

export function metricsMiddleware(req: Request, res: Response, next: NextFunction) {
  const startTime = Date.now();

  res.on('finish', () => {
    const duration = Date.now() - startTime;
    const route = req.route?.path || req.path;
    const method = req.method;
    const statusCode = res.statusCode;

    requestCounter.add(1, {
      method,
      route,
      status_code: String(statusCode),
    });

    requestDurationHistogram.record(duration, {
      method,
      route,
      status_code: String(statusCode),
    });
  });

  next();
}
