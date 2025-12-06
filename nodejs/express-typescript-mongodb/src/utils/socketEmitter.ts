import type { Server } from 'socket.io';
import { getLogger } from './logger.js';
import { withSpan } from './tracing.js';

const logger = getLogger('socket-emitter');

export interface ArticleEvent {
  event: 'article:created' | 'article:updated' | 'article:deleted' | 'article:published' | 'article:favorited' | 'article:unfavorited';
  data: {
    id: string;
    title?: string;
    authorId?: string;
    userId?: string;
    published?: boolean;
    favoritesCount?: number;
    timestamp: Date;
  };
}

export function emitArticleEvent(io: Server, event: ArticleEvent): void {
  withSpan('socket-emitter', 'socket.emit_article_event', (span) => {
    span.setAttributes({
      'socket.event': event.event,
      'article.id': event.data.id,
      'article.title': event.data.title,
      'article.author_id': event.data.authorId,
    });

    io.to('articles').emit(event.event, event.data);

    logger.info('Article event emitted', {
      event: event.event,
      articleId: event.data.id,
      articleTitle: event.data.title,
    });

    span.addEvent('event_emitted', {
      'event.name': event.event,
      'article.id': event.data.id,
    });

    return Promise.resolve();
  }).catch((error) => {
    logger.error('Failed to emit article event', error as Error, {
      event: event.event,
      articleId: event.data.id,
    });
  });
}
