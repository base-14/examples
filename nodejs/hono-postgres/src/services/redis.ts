import { Redis } from 'ioredis';
import { config } from '../config/index.js';
import { createLogger } from './logger.js';

const logger = createLogger('redis');
let redisClient: Redis | null = null;

export function getRedisClient(): Redis {
  if (!redisClient) {
    redisClient = new Redis(config.redis.url, {
      maxRetriesPerRequest: null,
      lazyConnect: true,
    });
  }
  return redisClient;
}

export async function checkRedisHealth(): Promise<boolean> {
  try {
    const client = getRedisClient();
    if (client.status !== 'ready') {
      await client.connect();
    }
    const result = await client.ping();
    return result === 'PONG';
  } catch (error) {
    logger.error({ error }, 'Redis health check failed');
    return false;
  }
}

export async function closeRedis(): Promise<void> {
  if (redisClient) {
    await redisClient.quit();
    redisClient = null;
  }
}
