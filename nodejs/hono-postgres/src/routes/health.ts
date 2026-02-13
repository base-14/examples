import { Hono } from 'hono';
import { checkDatabaseHealth } from '../db/index.js';
import { checkRedisHealth } from '../services/redis.js';
import { notificationQueue } from '../jobs/queue.js';

interface ComponentStatus {
  status: 'healthy' | 'unhealthy';
  latencyMs?: number;
  error?: string;
}

async function checkComponentWithLatency(
  _name: string,
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

const startTime = Date.now();

const healthRouter = new Hono();

healthRouter.get('/', async (c) => {
  const [database, redis, queue] = await Promise.all([
    checkComponentWithLatency('database', checkDatabaseHealth),
    checkComponentWithLatency('redis', checkRedisHealth),
    checkComponentWithLatency('queue', checkQueueHealth),
  ]);

  const allHealthy = database.status === 'healthy' &&
    redis.status === 'healthy' &&
    queue.status === 'healthy';

  const health = {
    status: allHealthy ? 'healthy' : 'unhealthy',
    timestamp: new Date().toISOString(),
    version: process.env.npm_package_version || '1.0.0',
    uptime: Math.floor((Date.now() - startTime) / 1000),
    components: { database, redis, queue },
  };

  return c.json(health, allHealthy ? 200 : 503);
});

healthRouter.get('/live', (c) => {
  return c.json({ status: 'ok' });
});

healthRouter.get('/ready', async (c) => {
  const dbHealthy = await checkDatabaseHealth();
  if (dbHealthy) {
    return c.json({ status: 'ready' });
  }
  return c.json({ status: 'not ready', reason: 'database unavailable' }, 503);
});

export default healthRouter;
