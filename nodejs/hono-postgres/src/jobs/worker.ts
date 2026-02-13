import '../telemetry.js';

import { Worker, Job } from 'bullmq';
import { trace, context, propagation, SpanStatusCode, SpanKind } from '@opentelemetry/api';
import { createLogger } from '../services/logger.js';

const logger = createLogger('notification-worker');

const redisUrl = new URL(process.env.REDIS_URL || 'redis://localhost:6379');
const connection = {
  host: redisUrl.hostname,
  port: parseInt(redisUrl.port || '6379', 10),
};

const tracer = trace.getTracer('notification-worker');

interface ArticleCreatedData {
  articleId: number;
  articleSlug: string;
  authorId: number;
  authorName: string;
  title: string;
  traceContext?: Record<string, string>;
}

interface ArticleFavoritedData {
  articleId: number;
  articleSlug: string;
  userId: number;
  userName: string;
  traceContext?: Record<string, string>;
}

type JobData = ArticleCreatedData | ArticleFavoritedData;

async function processArticleCreated(job: Job<ArticleCreatedData>): Promise<void> {
  const { articleId, articleSlug, authorName, title } = job.data;

  logger.info(
    { articleId, articleSlug, authorName },
    `Processing article created notification: "${title}"`
  );

  await new Promise((resolve) => setTimeout(resolve, 100));

  logger.info(
    { articleId, jobId: job.id },
    'Article created notification sent successfully'
  );
}

async function processArticleFavorited(job: Job<ArticleFavoritedData>): Promise<void> {
  const { articleId, articleSlug, userName } = job.data;

  logger.info(
    { articleId, articleSlug, userName },
    'Processing article favorited notification'
  );

  await new Promise((resolve) => setTimeout(resolve, 50));

  logger.info(
    { articleId, jobId: job.id },
    'Article favorited notification sent successfully'
  );
}

const worker = new Worker<JobData>(
  'notifications',
  async (job) => {
    const parentContext = job.data.traceContext
      ? propagation.extract(context.active(), job.data.traceContext)
      : context.active();

    return context.with(parentContext, async () => {
      return tracer.startActiveSpan(
        `job.${job.name}`,
        {
          kind: SpanKind.CONSUMER,
          attributes: {
            'job.id': job.id || 'unknown',
            'job.name': job.name,
            'job.queue': 'notifications',
            'job.attempt': job.attemptsMade + 1,
            'messaging.system': 'bullmq',
            'messaging.destination.name': 'notifications',
            'messaging.operation.type': 'process',
          },
        },
        async (span) => {
          const startTime = Date.now();

          try {
            logger.info(
              { jobId: job.id, jobName: job.name, attempt: job.attemptsMade + 1 },
              'Processing job'
            );

            switch (job.name) {
              case 'article-created':
                await processArticleCreated(job as Job<ArticleCreatedData>);
                break;
              case 'article-favorited':
                await processArticleFavorited(job as Job<ArticleFavoritedData>);
                break;
              default:
                logger.warn({ jobName: job.name }, 'Unknown job type');
            }

            const duration = Date.now() - startTime;
            span.setAttribute('job.duration_ms', duration);
            span.setStatus({ code: SpanStatusCode.OK });

            logger.info(
              { jobId: job.id, jobName: job.name, durationMs: duration },
              'Job completed successfully'
            );
          } catch (error) {
            span.recordException(error as Error);
            span.setStatus({
              code: SpanStatusCode.ERROR,
              message: (error as Error).message,
            });

            logger.error(
              { jobId: job.id, jobName: job.name, error: (error as Error).message },
              'Job failed'
            );

            throw error;
          } finally {
            span.end();
          }
        }
      );
    });
  },
  {
    connection,
    concurrency: 5,
  }
);

worker.on('completed', (job) => {
  logger.info({ jobId: job.id, jobName: job.name }, 'Job completed');
});

worker.on('failed', (job, err) => {
  logger.error(
    { jobId: job?.id, jobName: job?.name, error: err.message },
    'Job failed'
  );
});

worker.on('error', (err) => {
  logger.error({ error: err.message }, 'Worker error');
});

logger.info('Notification worker started');

const shutdown = async (signal: string) => {
  logger.info({ signal }, 'Shutting down worker...');
  await worker.close();
  process.exit(0);
};

process.on('SIGTERM', () => shutdown('SIGTERM'));
process.on('SIGINT', () => shutdown('SIGINT'));
