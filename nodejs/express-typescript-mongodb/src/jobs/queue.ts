import { Queue } from 'bullmq';
import { redisConnection } from '../utils/redis.js';

export const publishQueue = new Queue('article-publishing', {
  connection: redisConnection,
  defaultJobOptions: {
    attempts: 3,
    backoff: {
      type: 'exponential',
      delay: 2000,
    },
    removeOnComplete: {
      count: 100,
      age: 24 * 3600,
    },
    removeOnFail: {
      age: 7 * 24 * 3600,
    },
  },
});

export interface PublishArticleJobData {
  articleId: string;
  traceContext: Record<string, string>;
}
