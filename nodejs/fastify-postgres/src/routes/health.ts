import { FastifyPluginAsync } from 'fastify';
import { checkDatabaseHealth } from '../db/index.js';
import { checkRedisHealth } from '../services/redis.js';
import { notificationQueue } from '../jobs/queue.js';

interface ComponentStatus {
  status: 'healthy' | 'unhealthy';
  latencyMs?: number;
  error?: string;
}

interface HealthResponse {
  status: 'healthy' | 'unhealthy';
  timestamp: string;
  version: string;
  uptime: number;
  components: {
    database: ComponentStatus;
    redis: ComponentStatus;
    queue: ComponentStatus;
  };
}

const healthResponseSchema = {
  type: 'object',
  properties: {
    status: { type: 'string', enum: ['healthy', 'unhealthy'] },
    timestamp: { type: 'string' },
    version: { type: 'string' },
    uptime: { type: 'number' },
    components: {
      type: 'object',
      properties: {
        database: {
          type: 'object',
          properties: {
            status: { type: 'string', enum: ['healthy', 'unhealthy'] },
            latencyMs: { type: 'number' },
            error: { type: 'string' },
          },
          required: ['status'],
        },
        redis: {
          type: 'object',
          properties: {
            status: { type: 'string', enum: ['healthy', 'unhealthy'] },
            latencyMs: { type: 'number' },
            error: { type: 'string' },
          },
          required: ['status'],
        },
        queue: {
          type: 'object',
          properties: {
            status: { type: 'string', enum: ['healthy', 'unhealthy'] },
            latencyMs: { type: 'number' },
            error: { type: 'string' },
          },
          required: ['status'],
        },
      },
      required: ['database', 'redis', 'queue'],
    },
  },
  required: ['status', 'timestamp', 'version', 'uptime', 'components'],
} as const;

async function checkComponentWithLatency(
  name: string,
  checkFn: () => Promise<boolean>
): Promise<ComponentStatus> {
  const start = Date.now();
  try {
    const healthy = await checkFn();
    return {
      status: healthy ? 'healthy' : 'unhealthy',
      latencyMs: Date.now() - start,
    };
  } catch (error) {
    return {
      status: 'unhealthy',
      latencyMs: Date.now() - start,
      error: error instanceof Error ? error.message : String(error),
    };
  }
}

async function checkQueueHealth(): Promise<boolean> {
  try {
    const counts = await notificationQueue.getJobCounts();
    return counts !== undefined;
  } catch {
    return false;
  }
}

const healthRoutes: FastifyPluginAsync = async (fastify) => {
  const startTime = Date.now();

  fastify.get('/health', {
    schema: {
      response: {
        200: healthResponseSchema,
        503: healthResponseSchema,
      },
    },
  }, async (request, reply) => {
    const [database, redis, queue] = await Promise.all([
      checkComponentWithLatency('database', checkDatabaseHealth),
      checkComponentWithLatency('redis', checkRedisHealth),
      checkComponentWithLatency('queue', checkQueueHealth),
    ]);

    const allHealthy = database.status === 'healthy' &&
      redis.status === 'healthy' &&
      queue.status === 'healthy';

    const health: HealthResponse = {
      status: allHealthy ? 'healthy' : 'unhealthy',
      timestamp: new Date().toISOString(),
      version: process.env.npm_package_version || '1.0.0',
      uptime: Math.floor((Date.now() - startTime) / 1000),
      components: { database, redis, queue },
    };

    if (allHealthy) {
      return reply.code(200).send(health);
    }
    return reply.code(503).send(health);
  });

  fastify.get('/health/live', {
    schema: {
      response: {
        200: { type: 'object', properties: { status: { type: 'string' } } },
      },
    },
  }, async () => {
    return { status: 'ok' };
  });

  fastify.get('/health/ready', {
    schema: {
      response: {
        200: { type: 'object', properties: { status: { type: 'string' } } },
        503: { type: 'object', properties: { status: { type: 'string' }, reason: { type: 'string' } } },
      },
    },
  }, async (request, reply) => {
    const dbHealthy = await checkDatabaseHealth();
    if (dbHealthy) {
      return { status: 'ready' };
    }
    return reply.code(503).send({ status: 'not ready', reason: 'database unavailable' });
  });
};

export default healthRoutes;
