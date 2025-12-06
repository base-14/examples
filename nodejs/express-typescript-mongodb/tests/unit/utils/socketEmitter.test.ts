import { describe, it, expect, beforeEach, vi } from 'vitest';
import type { Server } from 'socket.io';
import { emitArticleEvent, type ArticleEvent } from '../../../src/utils/socketEmitter';

describe('Socket Emitter', () => {
  let mockIo: Partial<Server>;

  beforeEach(() => {
    // Mock Socket.io server
    mockIo = {
      to: vi.fn().mockReturnThis(),
      emit: vi.fn(),
    } as any;

    // Clear all mocks
    vi.clearAllMocks();
  });

  describe('emitArticleEvent', () => {
    it('should emit article:created event to articles room', () => {
      const event: ArticleEvent = {
        event: 'article:created',
        data: {
          id: 'article-123',
          title: 'Test Article',
          authorId: 'user-456',
          published: false,
          timestamp: new Date(),
        },
      };

      emitArticleEvent(mockIo as Server, event);

      expect(mockIo.to).toHaveBeenCalledWith('articles');
      expect(mockIo.emit).toHaveBeenCalledWith('article:created', event.data);
    });

    it('should emit article:updated event to articles room', () => {
      const event: ArticleEvent = {
        event: 'article:updated',
        data: {
          id: 'article-123',
          title: 'Updated Article',
          authorId: 'user-456',
          published: true,
          timestamp: new Date(),
        },
      };

      emitArticleEvent(mockIo as Server, event);

      expect(mockIo.to).toHaveBeenCalledWith('articles');
      expect(mockIo.emit).toHaveBeenCalledWith('article:updated', event.data);
    });

    it('should emit article:deleted event to articles room', () => {
      const event: ArticleEvent = {
        event: 'article:deleted',
        data: {
          id: 'article-123',
          title: 'Deleted Article',
          authorId: 'user-456',
          timestamp: new Date(),
        },
      };

      emitArticleEvent(mockIo as Server, event);

      expect(mockIo.to).toHaveBeenCalledWith('articles');
      expect(mockIo.emit).toHaveBeenCalledWith('article:deleted', event.data);
    });

    it('should emit article:published event to articles room', () => {
      const event: ArticleEvent = {
        event: 'article:published',
        data: {
          id: 'article-123',
          title: 'Published Article',
          authorId: 'user-456',
          published: true,
          timestamp: new Date(),
        },
      };

      emitArticleEvent(mockIo as Server, event);

      expect(mockIo.to).toHaveBeenCalledWith('articles');
      expect(mockIo.emit).toHaveBeenCalledWith('article:published', event.data);
    });

    it('should not throw on successful emission', () => {
      const event: ArticleEvent = {
        event: 'article:created',
        data: {
          id: 'article-123',
          title: 'Test Article',
          authorId: 'user-456',
          published: false,
          timestamp: new Date(),
        },
      };

      expect(() => emitArticleEvent(mockIo as Server, event)).not.toThrow();
    });

    it('should handle errors gracefully', () => {
      const emitError = new Error('Socket.io emit failed');
      mockIo.emit = vi.fn(() => {
        throw emitError;
      });

      const event: ArticleEvent = {
        event: 'article:created',
        data: {
          id: 'article-123',
          title: 'Test Article',
          authorId: 'user-456',
          published: false,
          timestamp: new Date(),
        },
      };

      // Should not throw - errors are caught and logged
      expect(() => emitArticleEvent(mockIo as Server, event)).not.toThrow();
    });

    it('should emit event with correct data structure', () => {
      const timestamp = new Date('2025-12-04T19:00:00Z');
      const event: ArticleEvent = {
        event: 'article:created',
        data: {
          id: 'article-123',
          title: 'Test Article',
          authorId: 'user-456',
          published: false,
          timestamp,
        },
      };

      emitArticleEvent(mockIo as Server, event);

      expect(mockIo.emit).toHaveBeenCalledWith('article:created', {
        id: 'article-123',
        title: 'Test Article',
        authorId: 'user-456',
        published: false,
        timestamp,
      });
    });

    it.each([
      { event: 'article:created' as const },
      { event: 'article:updated' as const },
      { event: 'article:deleted' as const },
      { event: 'article:published' as const },
    ])('should handle $event event type correctly', ({ event: eventType }) => {
      const event: ArticleEvent = {
        event: eventType,
        data: {
          id: 'article-123',
          title: 'Test Article',
          authorId: 'user-456',
          published: eventType === 'article:published',
          timestamp: new Date(),
        },
      };

      emitArticleEvent(mockIo as Server, event);

      expect(mockIo.to).toHaveBeenCalledWith('articles');
      expect(mockIo.emit).toHaveBeenCalledWith(eventType, event.data);
    });
  });
});
