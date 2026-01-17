import { Job } from 'bullmq';
import {
  trace,
  context,
  propagation,
  SpanStatusCode,
  Context,
} from '@opentelemetry/api';
import {
  createEmailWorker,
  createAnalyticsWorker,
  EmailJobData,
  AnalyticsJobData,
} from '../lib/queue';
import { logger } from '../lib/logger';

logger.info('Worker starting...');

const tracer = trace.getTracer('worker');

interface JobDataWithTrace {
  traceContext?: Record<string, string>;
}

function extractTraceContext(jobData: JobDataWithTrace): Context {
  if (jobData.traceContext) {
    return propagation.extract(context.active(), jobData.traceContext);
  }
  return context.active();
}

async function processWithSpan<T>(
  spanName: string,
  job: Job,
  parentContext: Context,
  processor: () => Promise<T>
): Promise<T> {
  return context.with(parentContext, async () => {
    return tracer.startActiveSpan(spanName, async (span) => {
      try {
        span.setAttribute('job.id', job.id || 'unknown');
        span.setAttribute('job.name', job.name);
        span.setAttribute('job.queue', job.queueName);
        span.setAttribute('job.attempt', job.attemptsMade);

        const result = await processor();

        span.setStatus({ code: SpanStatusCode.OK });
        return result;
      } catch (error) {
        span.recordException(error as Error);
        span.setStatus({
          code: SpanStatusCode.ERROR,
          message: error instanceof Error ? error.message : 'Unknown error',
        });
        throw error;
      } finally {
        span.end();
      }
    });
  });
}

logger.info('Starting background job workers...');

const emailWorker = createEmailWorker(async (job: Job<EmailJobData & JobDataWithTrace>) => {
  const parentContext = extractTraceContext(job.data);

  await processWithSpan('job.email.send', job, parentContext, async () => {
    logger.info('Processing email job', {
      jobId: job.id,
      to: job.data.to,
      subject: job.data.subject,
    });

    // Simulate email sending
    await new Promise((resolve) => setTimeout(resolve, 100));

    logger.info('Email job completed', { jobId: job.id });
  });
});

const analyticsWorker = createAnalyticsWorker(async (job: Job<AnalyticsJobData & JobDataWithTrace>) => {
  const parentContext = extractTraceContext(job.data);

  await processWithSpan('job.analytics.track', job, parentContext, async () => {
    logger.info('Processing analytics job', {
      jobId: job.id,
      event: job.data.event,
      userId: job.data.userId,
    });

    // Simulate analytics processing
    await new Promise((resolve) => setTimeout(resolve, 50));

    logger.info('Analytics job completed', { jobId: job.id });
  });
});

emailWorker.on('completed', (job) => {
  logger.info('Email job completed event', { jobId: job.id });
});

emailWorker.on('failed', (job, err) => {
  logger.error('Email job failed', {
    jobId: job?.id,
    errorMessage: err.message,
  });
});

analyticsWorker.on('completed', (job) => {
  logger.info('Analytics job completed event', { jobId: job.id });
});

analyticsWorker.on('failed', (job, err) => {
  logger.error('Analytics job failed', {
    jobId: job?.id,
    errorMessage: err.message,
  });
});

async function shutdown(): Promise<void> {
  logger.info('Shutting down workers...');
  await Promise.all([emailWorker.close(), analyticsWorker.close()]);
  logger.info('Workers shut down successfully');
  process.exit(0);
}

process.on('SIGTERM', shutdown);
process.on('SIGINT', shutdown);

logger.info('Workers started and listening for jobs');
