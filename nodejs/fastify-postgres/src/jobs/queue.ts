import { Queue } from 'bullmq';
import { Redis } from 'ioredis';
import { config } from '../config/index.js';

const connection = new Redis(config.redis.url, {
  maxRetriesPerRequest: null,
});

export const notificationQueue = new Queue('notifications', {
  connection,
  defaultJobOptions: {
    attempts: 3,
    backoff: {
      type: 'exponential',
      delay: 1000,
    },
    removeOnComplete: 100,
    removeOnFail: 500,
  },
});

export async function closeQueues(): Promise<void> {
  await notificationQueue.close();
  connection.disconnect();
}
