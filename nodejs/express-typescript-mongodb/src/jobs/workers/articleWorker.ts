import { Worker } from 'bullmq';
import { redisConnection } from '../../utils/redis.js';
import { processPublishArticle } from '../processors/publishArticle.processor.js';
import { getLogger } from '../../utils/logger.js';

const logger = getLogger('article-worker');

export const articleWorker = new Worker('article-publishing', processPublishArticle, {
  connection: redisConnection,
  concurrency: 5,
});

articleWorker.on('completed', (job) => {
  logger.info('Job completed successfully', {
    'job.id': job.id,
    'job.name': job.name,
  });
});

articleWorker.on('failed', (job, err) => {
  logger.error('Job failed', err, {
    'job.id': job?.id,
    'job.name': job?.name,
  });
});

articleWorker.on('error', (err) => {
  logger.error('Worker error', err);
});

logger.info('Article worker started', {
  concurrency: 5,
});
