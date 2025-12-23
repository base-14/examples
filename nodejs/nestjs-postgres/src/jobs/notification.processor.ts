import { Processor, WorkerHost } from '@nestjs/bullmq';
import { Inject, forwardRef } from '@nestjs/common';
import { InjectRepository } from '@nestjs/typeorm';
import { Repository } from 'typeorm';
import { Job } from 'bullmq';
import {
  trace,
  context,
  propagation,
  SpanStatusCode,
  SpanKind,
  metrics,
} from '@opentelemetry/api';
import { logs, SeverityNumber } from '@opentelemetry/api-logs';
import { ArticlePublishedPayload } from './notification.service';
import { Article } from '../articles/entities/article.entity';
import { EventsGateway } from '../events/events.gateway';

const tracer = trace.getTracer('notification-processor');
const meter = metrics.getMeter('notification-processor');
const logger = logs.getLogger('notification-processor');

const jobsEnqueuedCounter = meter.createCounter('jobs.enqueued', {
  description: 'Number of jobs enqueued',
});

const jobsCompletedCounter = meter.createCounter('jobs.completed', {
  description: 'Number of jobs completed successfully',
});

const jobsFailedCounter = meter.createCounter('jobs.failed', {
  description: 'Number of jobs that failed',
});

const jobDurationHistogram = meter.createHistogram('jobs.duration', {
  description: 'Duration of job processing in milliseconds',
  unit: 'ms',
});

const articlesPublishedCounter = meter.createCounter('articles.published', {
  description: 'Number of articles published via background job',
});

@Processor('notifications')
export class NotificationProcessor extends WorkerHost {
  constructor(
    @InjectRepository(Article)
    private articlesRepository: Repository<Article>,
    @Inject(forwardRef(() => EventsGateway))
    private eventsGateway: EventsGateway,
  ) {
    super();
  }

  async process(job: Job<ArticlePublishedPayload>): Promise<void> {
    const startTime = Date.now();
    const { traceContext, ...payload } = job.data;

    const parentContext = propagation.extract(context.active(), traceContext);

    await context.with(parentContext, async () => {
      await tracer.startActiveSpan(
        'job.process',
        {
          kind: SpanKind.CONSUMER,
          attributes: {
            'job.id': job.id,
            'job.name': job.name,
            'job.queue': 'notifications',
            'job.attempt': job.attemptsMade + 1,
            'article.id': payload.articleId,
            'article.title': payload.title,
            'user.id': payload.authorId,
          },
        },
        async (span) => {
          try {
            jobsEnqueuedCounter.add(1, { queue: 'notifications' });

            await this.publishArticle(
              payload.articleId,
              payload.title,
              payload.authorId,
            );
            await this.sendNotification(payload);

            articlesPublishedCounter.add(1);
            span.setStatus({ code: SpanStatusCode.OK });
            jobsCompletedCounter.add(1, { queue: 'notifications' });
          } catch (error) {
            span.setStatus({
              code: SpanStatusCode.ERROR,
              message: error instanceof Error ? error.message : String(error),
            });
            span.recordException(
              error instanceof Error ? error : new Error(String(error)),
            );
            jobsFailedCounter.add(1, { queue: 'notifications' });
            throw error;
          } finally {
            const duration = Date.now() - startTime;
            jobDurationHistogram.record(duration, { queue: 'notifications' });
            span.setAttribute('job.duration_ms', duration);
            span.end();
          }
        },
      );
    });
  }

  private async publishArticle(
    articleId: string,
    title: string,
    authorId: string,
  ): Promise<void> {
    await tracer.startActiveSpan(
      'article.publish.update',
      {
        attributes: {
          'article.id': articleId,
        },
      },
      async (span) => {
        try {
          const now = new Date();
          await this.articlesRepository.update(articleId, {
            published: true,
            publishedAt: now,
          });

          this.eventsGateway.emitArticlePublished({
            id: articleId,
            title,
            authorId,
            published: true,
            timestamp: now,
          });

          span.setAttribute('article.publishedAt', now.toISOString());
          span.setStatus({ code: SpanStatusCode.OK });
        } finally {
          span.end();
        }
      },
    );
  }

  private async sendNotification(
    payload: Omit<ArticlePublishedPayload, 'traceContext'>,
  ): Promise<void> {
    await tracer.startActiveSpan(
      'notification.send',
      {
        attributes: {
          'notification.type': 'article.published',
          'notification.recipient': payload.authorEmail,
        },
      },
      async (span) => {
        try {
          await new Promise((resolve) => setTimeout(resolve, 100));

          logger.emit({
            severityNumber: SeverityNumber.INFO,
            severityText: 'INFO',
            body: `Article "${payload.title}" published`,
            attributes: {
              'article.id': payload.articleId,
              'article.title': payload.title,
              'notification.recipient': payload.authorEmail,
              'trace.id': span.spanContext().traceId,
              'span.id': span.spanContext().spanId,
            },
          });

          span.setStatus({ code: SpanStatusCode.OK });
        } finally {
          span.end();
        }
      },
    );
  }
}
