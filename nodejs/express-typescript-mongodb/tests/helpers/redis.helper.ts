import RedisMock from 'ioredis-mock';
import { vi } from 'vitest';

export function createMockRedis(): RedisMock {
  return new RedisMock({
    data: {},
  });
}

// For BullMQ mocking
export function createMockQueue() {
  return {
    add: vi.fn().mockResolvedValue({ id: 'test-job-id' }),
    close: vi.fn(),
    getJob: vi.fn(),
    getJobs: vi.fn().mockResolvedValue([]),
  };
}

export function createMockWorker() {
  return {
    on: vi.fn(),
    close: vi.fn(),
  };
}
