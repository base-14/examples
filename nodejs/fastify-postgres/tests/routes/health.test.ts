import { describe, it, expect, vi, beforeEach } from 'vitest';
import Fastify from 'fastify';
import healthRoutes from '../../src/routes/health.js';

vi.mock('../../src/db/index.js', () => ({
  checkDatabaseHealth: vi.fn(),
}));

vi.mock('../../src/services/redis.js', () => ({
  checkRedisHealth: vi.fn(),
}));

vi.mock('../../src/jobs/queue.js', () => ({
  notificationQueue: {
    getJobCounts: vi.fn(),
  },
}));

import { checkDatabaseHealth } from '../../src/db/index.js';
import { checkRedisHealth } from '../../src/services/redis.js';
import { notificationQueue } from '../../src/jobs/queue.js';

describe('Health Routes', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe('GET /health', () => {
    it('should return healthy when all components are up', async () => {
      vi.mocked(checkDatabaseHealth).mockResolvedValue(true);
      vi.mocked(checkRedisHealth).mockResolvedValue(true);
      vi.mocked(notificationQueue.getJobCounts).mockResolvedValue({
        waiting: 0,
        active: 0,
        completed: 0,
        failed: 0,
        delayed: 0,
        paused: 0,
        prioritized: 0,
      });

      const fastify = Fastify();
      await fastify.register(healthRoutes);

      const response = await fastify.inject({
        method: 'GET',
        url: '/health',
      });

      expect(response.statusCode).toBe(200);
      const body = JSON.parse(response.body);
      expect(body.status).toBe('healthy');
      expect(body.components.database.status).toBe('healthy');
      expect(body.components.redis.status).toBe('healthy');
      expect(body.components.queue.status).toBe('healthy');

      await fastify.close();
    });

    it('should return unhealthy when database is down', async () => {
      vi.mocked(checkDatabaseHealth).mockResolvedValue(false);
      vi.mocked(checkRedisHealth).mockResolvedValue(true);
      vi.mocked(notificationQueue.getJobCounts).mockResolvedValue({
        waiting: 0,
        active: 0,
        completed: 0,
        failed: 0,
        delayed: 0,
        paused: 0,
        prioritized: 0,
      });

      const fastify = Fastify();
      await fastify.register(healthRoutes);

      const response = await fastify.inject({
        method: 'GET',
        url: '/health',
      });

      expect(response.statusCode).toBe(503);
      const body = JSON.parse(response.body);
      expect(body.status).toBe('unhealthy');
      expect(body.components.database.status).toBe('unhealthy');

      await fastify.close();
    });

    it('should return unhealthy when redis is down', async () => {
      vi.mocked(checkDatabaseHealth).mockResolvedValue(true);
      vi.mocked(checkRedisHealth).mockResolvedValue(false);
      vi.mocked(notificationQueue.getJobCounts).mockResolvedValue({
        waiting: 0,
        active: 0,
        completed: 0,
        failed: 0,
        delayed: 0,
        paused: 0,
        prioritized: 0,
      });

      const fastify = Fastify();
      await fastify.register(healthRoutes);

      const response = await fastify.inject({
        method: 'GET',
        url: '/health',
      });

      expect(response.statusCode).toBe(503);
      const body = JSON.parse(response.body);
      expect(body.status).toBe('unhealthy');
      expect(body.components.redis.status).toBe('unhealthy');

      await fastify.close();
    });

    it('should include latency measurements', async () => {
      vi.mocked(checkDatabaseHealth).mockResolvedValue(true);
      vi.mocked(checkRedisHealth).mockResolvedValue(true);
      vi.mocked(notificationQueue.getJobCounts).mockResolvedValue({
        waiting: 0,
        active: 0,
        completed: 0,
        failed: 0,
        delayed: 0,
        paused: 0,
        prioritized: 0,
      });

      const fastify = Fastify();
      await fastify.register(healthRoutes);

      const response = await fastify.inject({
        method: 'GET',
        url: '/health',
      });

      const body = JSON.parse(response.body);
      expect(typeof body.components.database.latencyMs).toBe('number');
      expect(typeof body.components.redis.latencyMs).toBe('number');
      expect(typeof body.components.queue.latencyMs).toBe('number');

      await fastify.close();
    });
  });

  describe('GET /health/live', () => {
    it('should always return ok for liveness probe', async () => {
      const fastify = Fastify();
      await fastify.register(healthRoutes);

      const response = await fastify.inject({
        method: 'GET',
        url: '/health/live',
      });

      expect(response.statusCode).toBe(200);
      const body = JSON.parse(response.body);
      expect(body.status).toBe('ok');

      await fastify.close();
    });
  });

  describe('GET /health/ready', () => {
    it('should return ready when database is healthy', async () => {
      vi.mocked(checkDatabaseHealth).mockResolvedValue(true);

      const fastify = Fastify();
      await fastify.register(healthRoutes);

      const response = await fastify.inject({
        method: 'GET',
        url: '/health/ready',
      });

      expect(response.statusCode).toBe(200);
      const body = JSON.parse(response.body);
      expect(body.status).toBe('ready');

      await fastify.close();
    });

    it('should return not ready when database is down', async () => {
      vi.mocked(checkDatabaseHealth).mockResolvedValue(false);

      const fastify = Fastify();
      await fastify.register(healthRoutes);

      const response = await fastify.inject({
        method: 'GET',
        url: '/health/ready',
      });

      expect(response.statusCode).toBe(503);
      const body = JSON.parse(response.body);
      expect(body.status).toBe('not ready');
      expect(body.reason).toBe('database unavailable');

      await fastify.close();
    });
  });
});
