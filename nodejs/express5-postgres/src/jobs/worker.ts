/**
 * BullMQ Worker with OpenTelemetry trace propagation.
 *
 * CRITICAL: telemetry.ts MUST be imported first.
 */

import '../telemetry.js';

import { Worker, Job } from 'bullmq';
import { Redis } from 'ioredis';
import { trace, context, propagation, SpanStatusCode, metrics } from '@opentelemetry/api';
import { logger } from '../logger.js';

const tracer = trace.getTracer('worker');
const meter = metrics.getMeter('worker');

const jobsCompletedCounter = meter.createCounter('jobs.completed', {
  description: 'Number of completed jobs',
  unit: '1',
});

const jobsFailedCounter = meter.createCounter('jobs.failed', {
  description: 'Number of failed jobs',
  unit: '1',
});

const jobDurationHistogram = meter.createHistogram('jobs.duration_ms', {
  description: 'Job processing duration in milliseconds',
  unit: 'ms',
});

interface NotificationJobData {
  articleId: number;
  event: string;
  traceContext?: Record<string, string>;
}

const redisUrl = process.env.REDIS_URL || 'redis://localhost:6379';

const connection = new Redis(redisUrl, {
  maxRetriesPerRequest: null,
});

async function processNotificationJob(job: Job<NotificationJobData>) {
  const { articleId, event, traceContext } = job.data;
  const startTime = Date.now();

  // Extract parent context if available
  const parentContext = traceContext
    ? propagation.extract(context.active(), traceContext)
    : context.active();

  return context.with(parentContext, async () => {
    return tracer.startActiveSpan('job.send_article_notification', async (span) => {
      try {
        span.setAttribute('job.id', job.id || 'unknown');
        span.setAttribute('job.name', job.name);
        span.setAttribute('job.queue', 'notifications');
        span.setAttribute('job.attempt', job.attemptsMade);
        span.setAttribute('article.id', articleId);
        span.setAttribute('event.type', event);

        logger.info({ jobId: job.id, articleId, event }, 'Processing notification job');

        // Simulate sending notification (replace with actual logic)
        await new Promise((resolve) => setTimeout(resolve, 100));

        const duration = Date.now() - startTime;

        span.setStatus({ code: SpanStatusCode.OK });
        jobsCompletedCounter.add(1, { queue: 'notifications', event });
        jobDurationHistogram.record(duration, { queue: 'notifications', event });

        logger.info({ jobId: job.id, articleId, event, duration }, 'Notification job completed');

        return { success: true };
      } catch (error) {
        span.recordException(error as Error);
        span.setStatus({ code: SpanStatusCode.ERROR });
        jobsFailedCounter.add(1, { queue: 'notifications', event });

        logger.error({ jobId: job.id, error }, 'Notification job failed');

        throw error;
      } finally {
        span.end();
      }
    });
  });
}

const worker = new Worker<NotificationJobData>('notifications', processNotificationJob, {
  connection,
  concurrency: 5,
});

worker.on('ready', () => {
  logger.info('Worker ready and listening for jobs');
});

worker.on('error', (error) => {
  logger.error({ error }, 'Worker error');
});

async function gracefulShutdown(signal: string) {
  logger.info({ signal }, 'Received shutdown signal');

  await worker.close();
  await connection.quit();

  logger.info('Worker shut down gracefully');
  process.exit(0);
}

process.on('SIGTERM', () => gracefulShutdown('SIGTERM'));
process.on('SIGINT', () => gracefulShutdown('SIGINT'));
