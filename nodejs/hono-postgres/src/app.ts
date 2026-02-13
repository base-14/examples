import { Hono } from 'hono';
import { cors } from 'hono/cors';
import { logger as honoLogger } from 'hono/logger';
import { secureHeaders } from 'hono/secure-headers';
import { httpInstrumentationMiddleware } from '@hono/otel';
import { trace } from '@opentelemetry/api';
import client from 'prom-client';
import { config } from './config/index.js';
import { createLogger } from './services/logger.js';
import healthRouter from './routes/health.js';
import authRouter from './routes/auth.js';
import articlesRouter from './routes/articles.js';
import type { Variables } from './types/index.js';

const logger = createLogger('hono-app');

const app = new Hono<{ Variables: Variables }>();

// Prometheus metrics
const register = new client.Registry();
register.setDefaultLabels({ app: 'hono-postgres' });
client.collectDefaultMetrics({ register });

const httpRequestsTotal = new client.Counter({
  name: 'http_requests_total',
  help: 'Total HTTP requests',
  labelNames: ['method', 'route', 'status_code'] as const,
  registers: [register],
});

const httpRequestDuration = new client.Histogram({
  name: 'http_request_duration_seconds',
  help: 'HTTP request duration in seconds',
  labelNames: ['method', 'route', 'status_code'] as const,
  buckets: [0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10],
  registers: [register],
});

// Global middleware
app.use('*', httpInstrumentationMiddleware());
app.use('*', honoLogger());
app.use('*', secureHeaders());
app.use(
  '*',
  cors({
    origin:
      config.environment === 'development'
        ? '*'
        : (process.env.ALLOWED_ORIGINS?.split(',') || ['https://yourdomain.com']),
    allowMethods: ['GET', 'POST', 'PUT', 'DELETE', 'PATCH', 'OPTIONS'],
    allowHeaders: ['Content-Type', 'Authorization', 'X-Request-ID'],
    exposeHeaders: ['X-Request-ID'],
    credentials: true,
    maxAge: 86400,
  })
);

// Metrics collection middleware
app.use('*', async (c, next) => {
  const start = performance.now();
  await next();
  const duration = (performance.now() - start) / 1000;
  const route = c.req.routePath || c.req.path;
  const method = c.req.method;
  const statusCode = c.res.status.toString();

  httpRequestsTotal.inc({ method, route, status_code: statusCode });
  httpRequestDuration.observe({ method, route, status_code: statusCode }, duration);
});

// Prometheus metrics endpoint
app.get('/metrics', async (c) => {
  const metrics = await register.metrics();
  return c.text(metrics, 200, { 'Content-Type': register.contentType });
});

// Routes
app.route('/health', healthRouter);
app.route('/api', authRouter);
app.route('/api/articles', articlesRouter);

// 404 handler
app.notFound((c) => {
  return c.json({ error: 'Not Found' }, 404);
});

// Global error handler
app.onError((err, c) => {
  const span = trace.getActiveSpan();
  const traceId = span?.spanContext()?.traceId;

  logger.error(
    { error: err.message, stack: err.stack, path: c.req.path, method: c.req.method },
    'Unhandled request error'
  );

  const statusCode = 500;
  return c.json(
    {
      error: err.message,
      statusCode,
      ...(traceId && { traceId }),
    },
    statusCode
  );
});

export { app, register };
