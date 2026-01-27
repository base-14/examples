import Fastify, { FastifyInstance, FastifyError } from 'fastify';
import cors from '@fastify/cors';
import helmet from '@fastify/helmet';
import rateLimit from '@fastify/rate-limit';
import { trace } from '@opentelemetry/api';
import { config } from './config/index.js';
import authPlugin from './plugins/auth.js';
import metricsPlugin from './plugins/metrics.js';
import healthRoutes from './routes/health.js';
import authRoutes from './routes/auth.js';
import articleRoutes from './routes/articles.js';
import { closeDatabase } from './db/index.js';
import { closeQueues } from './jobs/queue.js';
import { closeRedis } from './services/redis.js';
import { createFastifyLoggerConfig } from './services/logger.js';

export async function createApp(): Promise<FastifyInstance> {
  const fastify = Fastify({
    logger: createFastifyLoggerConfig(),
    requestIdLogLabel: 'requestId',
    genReqId: () => crypto.randomUUID(),
  });

  // Security plugins
  await fastify.register(helmet);
  await fastify.register(cors, {
    origin:
      config.environment === 'development'
        ? true
        : (process.env.ALLOWED_ORIGINS?.split(',') || ['https://yourdomain.com']),
    credentials: true,
    methods: ['GET', 'POST', 'PUT', 'DELETE', 'PATCH', 'OPTIONS'],
    allowedHeaders: ['Content-Type', 'Authorization', 'X-Request-ID'],
    exposedHeaders: ['X-Request-ID'],
    maxAge: 86400,
  });
  await fastify.register(rateLimit, {
    max: 100,
    timeWindow: '1 minute',
  });

  // Metrics plugin
  await fastify.register(metricsPlugin);

  // Authentication plugin
  await fastify.register(authPlugin);

  // Routes
  await fastify.register(healthRoutes);
  await fastify.register(authRoutes, { prefix: '/api' });
  await fastify.register(articleRoutes, { prefix: '/api/articles' });

  fastify.setErrorHandler((error: FastifyError, request, reply) => {
    const span = trace.getActiveSpan();
    const traceId = span?.spanContext()?.traceId;

    fastify.log.error({ err: error, traceId }, 'Request error');

    const statusCode = error.statusCode ?? 500;
    reply.code(statusCode).send({
      error: error.message,
      statusCode,
      ...(traceId && { traceId }),
    });
  });

  const closeGracefully = async (signal: string) => {
    fastify.log.info(`Received ${signal}, closing gracefully...`);

    const shutdownTimeout = setTimeout(() => {
      fastify.log.error('Graceful shutdown timed out, forcing exit');
      process.exit(1);
    }, 30000);

    try {
      await fastify.close();
      fastify.log.info('HTTP server closed');

      await Promise.allSettled([
        closeQueues().then(() => fastify.log.info('Queues closed')),
        closeRedis().then(() => fastify.log.info('Redis closed')),
        closeDatabase().then(() => fastify.log.info('Database closed')),
      ]);

      clearTimeout(shutdownTimeout);
      fastify.log.info('Graceful shutdown complete');
      process.exit(0);
    } catch (error) {
      fastify.log.error({ error }, 'Error during graceful shutdown');
      clearTimeout(shutdownTimeout);
      process.exit(1);
    }
  };

  process.on('SIGTERM', () => closeGracefully('SIGTERM'));
  process.on('SIGINT', () => closeGracefully('SIGINT'));

  return fastify;
}
