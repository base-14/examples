import IORedis from 'ioredis';
import { config } from './config';

const redis = new IORedis({
  host: config.redisHost,
  port: config.redisPort,
  maxRetriesPerRequest: 1,
  lazyConnect: true,
});

interface RateLimitResult {
  success: boolean;
  remaining: number;
  reset: number;
}

export async function checkRateLimit(
  key: string,
  limit: number,
  windowMs: number
): Promise<RateLimitResult> {
  const now = Date.now();
  const windowStart = now - windowMs;
  const redisKey = `ratelimit:${key}`;

  try {
    await redis.zremrangebyscore(redisKey, 0, windowStart);

    const count = await redis.zcard(redisKey);

    if (count >= limit) {
      const oldestEntry = await redis.zrange(redisKey, 0, 0, 'WITHSCORES');
      const reset = oldestEntry.length >= 2
        ? Math.ceil((parseInt(oldestEntry[1], 10) + windowMs - now) / 1000)
        : Math.ceil(windowMs / 1000);

      return {
        success: false,
        remaining: 0,
        reset,
      };
    }

    await redis.zadd(redisKey, now, `${now}:${Math.random()}`);
    await redis.pexpire(redisKey, windowMs);

    return {
      success: true,
      remaining: limit - count - 1,
      reset: Math.ceil(windowMs / 1000),
    };
  } catch {
    return {
      success: true,
      remaining: limit,
      reset: Math.ceil(windowMs / 1000),
    };
  }
}

export function getRateLimitKey(ip: string | null, endpoint: string): string {
  return `${endpoint}:${ip || 'unknown'}`;
}

export const AUTH_RATE_LIMIT = {
  limit: 5,
  windowMs: 60 * 1000,
};

export const API_RATE_LIMIT = {
  limit: 100,
  windowMs: 60 * 1000,
};
