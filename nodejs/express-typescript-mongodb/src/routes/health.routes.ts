import { Router, type Request, type Response } from 'express';
import { checkDatabaseConnection } from '../database.js';
import { checkRedisConnection } from '../utils/redis.js';
import { config } from '../config.js';

const router = Router();

router.get('/health', async (_req: Request, res: Response) => {
  const [dbHealthy, redisHealthy] = await Promise.all([
    checkDatabaseConnection(),
    checkRedisConnection(),
  ]);

  const health = {
    status: dbHealthy && redisHealthy ? 'healthy' : 'unhealthy',
    timestamp: new Date().toISOString(),
    service: config.otel.serviceName,
    version: config.app.version,
    database: {
      connected: dbHealthy,
    },
    redis: {
      connected: redisHealthy,
    },
  };

  const statusCode = dbHealthy && redisHealthy ? 200 : 503;
  res.status(statusCode).json(health);
});

export default router;
