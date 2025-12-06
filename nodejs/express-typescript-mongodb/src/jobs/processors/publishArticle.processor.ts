import type { Job } from 'bullmq';
import { trace, SpanStatusCode, context as otelContext, propagation } from '@opentelemetry/api';
import { Article } from '../../models/Article.js';
import type { PublishArticleJobData } from '../queue.js';
import { articleMetrics, jobMetrics } from '../../utils/metrics.js';
import { getSocketIO } from '../../utils/socketInstance.js';
import { emitArticleEvent } from '../../utils/socketEmitter.js';

const tracer = trace.getTracer('job-processor');

export async function processPublishArticle(job: Job<PublishArticleJobData>): Promise<void> {
  const { articleId, traceContext } = job.data;
  const startTime = Date.now();

  const parentContext = propagation.extract(otelContext.active(), traceContext);
  const span = tracer.startSpan(
    'job.publishArticle.process',
    {
      attributes: {
        'job.id': job.id ?? '',
        'job.attempt': job.attemptsMade,
        'article.id': articleId,
      },
    },
    parentContext
  );

  try {
    await otelContext.with(trace.setSpan(otelContext.active(), span), async () => {
      span.addEvent('job_started', {
        'job.id': job.id ?? '',
        'article.id': articleId,
      });

      const article = await Article.findById(articleId);

      if (!article) {
        span.setStatus({ code: SpanStatusCode.ERROR, message: 'Article not found' });
        throw new Error(`Article ${articleId} not found`);
      }

      article.published = true;
      article.publishedAt = new Date();
      await article.save();

      const duration = Date.now() - startTime;
      articleMetrics.published.add(1, { 'article.id': articleId });
      jobMetrics.completed.add(1, { 'job.name': 'publish-article' });
      jobMetrics.processingTime.record(duration, {
        'job.name': 'publish-article',
        'job.attempt': job.attemptsMade,
      });
      articleMetrics.publishDuration.record(duration, { 'article.id': articleId });

      span.setAttributes({
        'article.title': article.title,
        'article.published': article.published,
        'job.duration_ms': duration,
      });

      span.addEvent('job_completed', {
        'job.id': job.id ?? '',
        'article.id': articleId,
        duration_ms: duration,
      });

      const io = getSocketIO();
      if (io) {
        emitArticleEvent(io, {
          event: 'article:published',
          data: {
            id: article._id.toString(),
            title: article.title,
            authorId: article.author.toString(),
            published: article.published,
            timestamp: new Date(),
          },
        });
      }

      span.setStatus({ code: SpanStatusCode.OK });
    });
  } catch (error) {
    jobMetrics.failed.add(1, {
      'job.name': 'publish-article',
      'error.type': (error as Error).name,
    });

    span.recordException(error as Error);
    span.setStatus({ code: SpanStatusCode.ERROR, message: (error as Error).message });
    span.addEvent('job_failed', {
      'job.id': job.id ?? '',
      'error.message': (error as Error).message,
    });
    throw error;
  } finally {
    span.end();
  }
}
