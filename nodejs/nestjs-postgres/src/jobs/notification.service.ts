import { Injectable } from '@nestjs/common';
import { InjectQueue } from '@nestjs/bullmq';
import { Queue } from 'bullmq';
import { trace, context, propagation } from '@opentelemetry/api';

export interface ArticlePublishedPayload {
  articleId: string;
  title: string;
  authorId: string;
  authorEmail: string;
  traceContext: Record<string, string>;
}

@Injectable()
export class NotificationService {
  constructor(
    @InjectQueue('notifications') private notificationsQueue: Queue,
  ) {}

  async notifyArticlePublished(
    articleId: string,
    title: string,
    authorId: string,
    authorEmail: string,
  ): Promise<string | undefined> {
    const carrier: Record<string, string> = {};
    propagation.inject(context.active(), carrier);

    const payload: ArticlePublishedPayload = {
      articleId,
      title,
      authorId,
      authorEmail,
      traceContext: carrier,
    };

    const currentSpan = trace.getActiveSpan();
    currentSpan?.setAttribute('job.queue', 'notifications');
    currentSpan?.setAttribute('job.type', 'article.published');

    const job = await this.notificationsQueue.add(
      'article.published',
      payload,
      {
        attempts: 3,
        backoff: {
          type: 'exponential',
          delay: 1000,
        },
      },
    );

    currentSpan?.setAttribute('job.id', job.id ?? '');
    return job.id;
  }
}
