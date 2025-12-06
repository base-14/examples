import Redis from 'ioredis';
import { config } from '../config.js';
import { getLogger } from './logger.js';

const logger = getLogger('redis');

export const redisConnection = new Redis.default(config.redis.url, {
  maxRetriesPerRequest: null,
  retryStrategy: (times) => {
    const delay = Math.min(times * 50, 2000);
    logger.warn('Redis connection retry', { attempt: times, delay });
    return delay;
  },
});

redisConnection.on('connect', () => {
  logger.info('Redis connected');
});

redisConnection.on('ready', () => {
  logger.info('Redis ready to accept commands');
});

redisConnection.on('error', (err) => {
  logger.error('Redis connection error', err);
});

redisConnection.on('close', () => {
  logger.warn('Redis connection closed');
});

redisConnection.on('reconnecting', (delay: number) => {
  logger.info('Redis reconnecting', { delay });
});

export async function checkRedisConnection(): Promise<boolean> {
  try {
    const result = await redisConnection.ping();
    return result === 'PONG';
  } catch (error) {
    logger.error('Redis health check failed', error as Error);
    return false;
  }
}
