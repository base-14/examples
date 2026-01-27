import fp from 'fastify-plugin';
import { FastifyPluginAsync } from 'fastify';
import client from 'prom-client';

declare module 'fastify' {
  interface FastifyInstance {
    metricsRegistry: client.Registry;
  }
}

const metricsPlugin: FastifyPluginAsync = async (fastify) => {
  const register = new client.Registry();

  register.setDefaultLabels({
    app: 'fastify-postgres',
  });

  client.collectDefaultMetrics({ register });

  const httpRequestsTotal = new client.Counter({
    name: 'http_requests_total',
    help: 'Total HTTP requests',
    labelNames: ['method', 'route', 'status_code'],
    registers: [register],
  });

  const httpRequestDuration = new client.Histogram({
    name: 'http_request_duration_seconds',
    help: 'HTTP request duration in seconds',
    labelNames: ['method', 'route', 'status_code'],
    buckets: [0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10],
    registers: [register],
  });

  const httpRequestSize = new client.Histogram({
    name: 'http_request_size_bytes',
    help: 'HTTP request size in bytes',
    labelNames: ['method', 'route'],
    buckets: [100, 1000, 10000, 100000, 1000000],
    registers: [register],
  });

  const httpResponseSize = new client.Histogram({
    name: 'http_response_size_bytes',
    help: 'HTTP response size in bytes',
    labelNames: ['method', 'route', 'status_code'],
    buckets: [100, 1000, 10000, 100000, 1000000],
    registers: [register],
  });

  fastify.decorate('metricsRegistry', register);

  fastify.addHook('onRequest', async (request) => {
    request.startTime = process.hrtime.bigint();
  });

  fastify.addHook('onResponse', async (request, reply) => {
    const route = request.routeOptions?.url || request.url || 'unknown';
    const method = request.method;
    const statusCode = reply.statusCode.toString();

    httpRequestsTotal.inc({ method, route, status_code: statusCode });

    if (request.startTime) {
      const duration = Number(process.hrtime.bigint() - request.startTime) / 1e9;
      httpRequestDuration.observe({ method, route, status_code: statusCode }, duration);
    }

    const contentLength = request.headers['content-length'];
    if (contentLength) {
      httpRequestSize.observe({ method, route }, parseInt(contentLength, 10));
    }

    const responseSize = reply.getHeader('content-length');
    if (responseSize && typeof responseSize === 'string') {
      httpResponseSize.observe(
        { method, route, status_code: statusCode },
        parseInt(responseSize, 10)
      );
    } else if (typeof responseSize === 'number') {
      httpResponseSize.observe(
        { method, route, status_code: statusCode },
        responseSize
      );
    }
  });

  fastify.get('/metrics', async (request, reply) => {
    reply.header('Content-Type', register.contentType);
    return register.metrics();
  });
};

declare module 'fastify' {
  interface FastifyRequest {
    startTime?: bigint;
  }
}

export default fp(metricsPlugin, {
  name: 'metrics',
  fastify: '5.x',
});
