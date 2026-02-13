import { Queue } from 'bullmq';
import { config } from '../config/index.js';

const redisUrl = new URL(config.redis.url);
const connection = {
  host: redisUrl.hostname,
  port: parseInt(redisUrl.port || '6379', 10),
};

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
}
