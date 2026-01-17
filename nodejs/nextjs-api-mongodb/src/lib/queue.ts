import { Queue, Worker, Job } from 'bullmq';
import { context, propagation } from '@opentelemetry/api';
import { config } from './config';

const connectionConfig = {
  host: config.redisHost,
  port: config.redisPort,
};

export const emailQueue = new Queue('email', { connection: connectionConfig });
export const analyticsQueue = new Queue('analytics', { connection: connectionConfig });

export interface EmailJobData {
  to: string;
  subject: string;
  body: string;
  template?: string;
}

export interface AnalyticsJobData {
  event: string;
  userId?: string;
  data: Record<string, unknown>;
  timestamp: string;
}

function injectTraceContext(): Record<string, string> {
  const traceContext: Record<string, string> = {};
  propagation.inject(context.active(), traceContext);
  return traceContext;
}

export async function addEmailJob(
  data: EmailJobData
): Promise<Job<EmailJobData & { traceContext: Record<string, string> }>> {
  const traceContext = injectTraceContext();
  return emailQueue.add(
    'send-email',
    { ...data, traceContext },
    {
      attempts: 3,
      backoff: {
        type: 'exponential',
        delay: 1000,
      },
    }
  );
}

export async function addAnalyticsJob(
  data: AnalyticsJobData
): Promise<Job<AnalyticsJobData & { traceContext: Record<string, string> }>> {
  const traceContext = injectTraceContext();
  return analyticsQueue.add(
    'track-event',
    { ...data, traceContext },
    {
      attempts: 2,
      removeOnComplete: true,
      removeOnFail: 100,
    }
  );
}

export function createEmailWorker(
  processor: (job: Job<EmailJobData>) => Promise<void>
): Worker<EmailJobData> {
  return new Worker('email', processor, {
    connection: connectionConfig,
    concurrency: 5,
  });
}

export function createAnalyticsWorker(
  processor: (job: Job<AnalyticsJobData>) => Promise<void>
): Worker<AnalyticsJobData> {
  return new Worker('analytics', processor, {
    connection: connectionConfig,
    concurrency: 10,
  });
}

export async function getQueueStats(queue: Queue): Promise<{
  waiting: number;
  active: number;
  completed: number;
  failed: number;
}> {
  const [waiting, active, completed, failed] = await Promise.all([
    queue.getWaitingCount(),
    queue.getActiveCount(),
    queue.getCompletedCount(),
    queue.getFailedCount(),
  ]);

  return { waiting, active, completed, failed };
}
