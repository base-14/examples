import { context, propagation, trace } from '@opentelemetry/api';
import { notificationQueue } from '../queue.js';

const tracer = trace.getTracer('notification-tasks');

export interface ArticleCreatedPayload {
  articleId: number;
  articleSlug: string;
  authorId: number;
  authorName: string;
  title: string;
}

export interface ArticleFavoritedPayload {
  articleId: number;
  articleSlug: string;
  userId: number;
  userName: string;
}

function getTraceContext(): Record<string, string> {
  const traceContext: Record<string, string> = {};
  propagation.inject(context.active(), traceContext);
  return traceContext;
}

export async function enqueueArticleCreatedNotification(
  payload: ArticleCreatedPayload
): Promise<void> {
  return tracer.startActiveSpan('job.enqueue.article-created', async (span) => {
    try {
      span.setAttribute('article.id', payload.articleId);
      span.setAttribute('article.slug', payload.articleSlug);

      const job = await notificationQueue.add('article-created', {
        ...payload,
        traceContext: getTraceContext(),
      });

      span.setAttribute('job.id', job.id || 'unknown');
      span.addEvent('job_enqueued');
    } finally {
      span.end();
    }
  });
}

export async function enqueueArticleFavoritedNotification(
  payload: ArticleFavoritedPayload
): Promise<void> {
  return tracer.startActiveSpan('job.enqueue.article-favorited', async (span) => {
    try {
      span.setAttribute('article.id', payload.articleId);
      span.setAttribute('user.id', payload.userId);

      const job = await notificationQueue.add('article-favorited', {
        ...payload,
        traceContext: getTraceContext(),
      });

      span.setAttribute('job.id', job.id || 'unknown');
      span.addEvent('job_enqueued');
    } finally {
      span.end();
    }
  });
}
