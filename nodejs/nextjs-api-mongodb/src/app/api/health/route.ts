import { NextResponse } from 'next/server';
import { getConnectionStatus } from '@/lib/db';
import { withSpan } from '@/lib/telemetry';
import { emailQueue, analyticsQueue, getQueueStats } from '@/lib/queue';
import { config } from '@/lib/config';
import IORedis from 'ioredis';

export const dynamic = 'force-dynamic';

interface QueueHealth {
  waiting: number;
  active: number;
  completed: number;
  failed: number;
}

interface HealthStatus {
  status: 'healthy' | 'degraded' | 'unhealthy';
  timestamp: string;
  version: string;
  uptime: number;
  checks: {
    mongodb: {
      status: string;
      readyState: number;
    };
    redis: {
      status: 'connected' | 'disconnected' | 'error';
      latencyMs?: number;
      error?: string;
    };
    queues: {
      email: QueueHealth;
      analytics: QueueHealth;
    };
  };
}

async function checkRedis(): Promise<{
  status: 'connected' | 'disconnected' | 'error';
  latencyMs?: number;
  error?: string;
}> {
  const redis = new IORedis({
    host: config.redisHost,
    port: config.redisPort,
    maxRetriesPerRequest: 1,
    lazyConnect: true,
    connectTimeout: 3000,
  });

  try {
    const start = Date.now();
    await redis.connect();
    await redis.ping();
    const latencyMs = Date.now() - start;
    await redis.quit();
    return { status: 'connected', latencyMs };
  } catch (error) {
    try {
      await redis.quit();
    } catch {
      // ignore
    }
    return {
      status: 'error',
      error: error instanceof Error ? error.message : 'Unknown error',
    };
  }
}

export async function GET(): Promise<NextResponse<HealthStatus>> {
  return withSpan('health.check', async () => {
    const [mongoStatus, redisStatus, emailStats, analyticsStats] = await Promise.all([
      Promise.resolve(getConnectionStatus()),
      checkRedis(),
      getQueueStats(emailQueue).catch(() => ({ waiting: 0, active: 0, completed: 0, failed: 0 })),
      getQueueStats(analyticsQueue).catch(() => ({ waiting: 0, active: 0, completed: 0, failed: 0 })),
    ]);

    const mongoHealthy = mongoStatus.readyState === 1;
    const redisHealthy = redisStatus.status === 'connected';

    let status: 'healthy' | 'degraded' | 'unhealthy' = 'healthy';
    if (!mongoHealthy) {
      status = 'unhealthy';
    } else if (!redisHealthy) {
      status = 'degraded';
    }

    const health: HealthStatus = {
      status,
      timestamp: new Date().toISOString(),
      version: process.env.npm_package_version || '1.0.0',
      uptime: process.uptime(),
      checks: {
        mongodb: mongoStatus,
        redis: redisStatus,
        queues: {
          email: emailStats,
          analytics: analyticsStats,
        },
      },
    };

    const httpStatus = status === 'unhealthy' ? 503 : 200;
    return NextResponse.json(health, { status: httpStatus });
  });
}
