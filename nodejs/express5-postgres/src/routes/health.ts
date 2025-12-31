import { Router } from 'express';
import { checkDatabaseConnection } from '../db/index.js';
import { Redis } from 'ioredis';

const router = Router();

const redis = new Redis(process.env.REDIS_URL || 'redis://localhost:6379', {
  maxRetriesPerRequest: 1,
  lazyConnect: true,
});

async function checkRedisConnection(): Promise<boolean> {
  try {
    await redis.ping();
    return true;
  } catch {
    return false;
  }
}

router.get('/health', async (req, res) => {
  const [dbHealthy, redisHealthy] = await Promise.all([
    checkDatabaseConnection(),
    checkRedisConnection(),
  ]);

  const status = dbHealthy && redisHealthy ? 'healthy' : 'unhealthy';
  const statusCode = status === 'healthy' ? 200 : 503;

  res.status(statusCode).json({
    status,
    timestamp: new Date().toISOString(),
    services: {
      database: dbHealthy ? 'up' : 'down',
      redis: redisHealthy ? 'up' : 'down',
    },
  });
});

export { router as healthRouter };
