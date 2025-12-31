import { Queue } from 'bullmq';
import { Redis } from 'ioredis';

const redisUrl = process.env.REDIS_URL || 'redis://localhost:6379';

export const connection = new Redis(redisUrl, {
  maxRetriesPerRequest: null,
});

export const notificationQueue = new Queue('notifications', { connection });

export async function closeQueues() {
  await notificationQueue.close();
  await connection.quit();
}
