import { describe, it, expect, vi, beforeEach } from 'vitest';

const mockSpan = {
  setAttribute: vi.fn(),
  setStatus: vi.fn(),
  recordException: vi.fn(),
  end: vi.fn(),
};

vi.mock('@opentelemetry/api', () => ({
  trace: {
    getTracer: () => ({
      startActiveSpan: (_name: string, fn: (span: typeof mockSpan) => unknown) => fn(mockSpan),
    }),
  },
  metrics: {
    getMeter: () => ({
      createCounter: () => ({ add: vi.fn() }),
    }),
  },
  SpanStatusCode: { OK: 1, ERROR: 2 },
}));

const mockFindFirst = vi.fn();
const mockReturning = vi.fn();
const mockValues = vi.fn(() => ({ returning: mockReturning }));
const mockInsert = vi.fn(() => ({ values: mockValues }));
const mockWhere = vi.fn(() => ({ returning: mockReturning }));
const mockSet = vi.fn(() => ({ where: mockWhere }));
const mockUpdate = vi.fn(() => ({ set: mockSet }));
const mockDeleteWhere = vi.fn();
const mockDelete = vi.fn(() => ({ where: mockDeleteWhere }));

vi.mock('../../src/db/index.js', () => ({
  db: {
    query: { articles: { findFirst: (...args: unknown[]) => mockFindFirst(...args) } },
    insert: (...args: unknown[]) => mockInsert(...args),
    update: (...args: unknown[]) => mockUpdate(...args),
    delete: (...args: unknown[]) => mockDelete(...args),
  },
}));

vi.mock('../../src/db/schema.js', () => ({
  articles: { slug: 'slug', id: 'id', authorId: 'authorId' },
  favorites: { userId: 'userId', articleId: 'articleId' },
}));

vi.mock('../../src/logger.js', () => ({
  logger: { info: vi.fn(), error: vi.fn(), warn: vi.fn() },
}));

const { ArticleService } = await import('../../src/services/article.js');

describe('ArticleService', () => {
  let service: InstanceType<typeof ArticleService>;

  beforeEach(() => {
    vi.clearAllMocks();
    service = new ArticleService();
  });

  describe('create', () => {
    it('generates a slug from the title', async () => {
      const article = { id: 1, slug: '', title: 'Hello World', body: 'body', authorId: 1 };
      mockReturning.mockResolvedValue([article]);

      await service.create(1, { title: 'Hello World', body: 'content' });

      const insertedValues = mockValues.mock.calls[0]![0] as { slug: string };
      expect(insertedValues.slug).toMatch(/^hello-world-[a-z0-9]+$/);
    });

    it('returns the created article', async () => {
      const article = { id: 1, slug: 'test-123', title: 'Test', body: 'b', authorId: 1 };
      mockReturning.mockResolvedValue([article]);

      const result = await service.create(1, { title: 'Test', body: 'b' });
      expect(result).toEqual(article);
    });
  });

  describe('findBySlug', () => {
    it('returns article when found', async () => {
      const article = { id: 1, slug: 'test', title: 'Test' };
      mockFindFirst.mockResolvedValue(article);

      const result = await service.findBySlug('test');
      expect(result).toEqual(article);
    });

    it('returns null when not found', async () => {
      mockFindFirst.mockResolvedValue(undefined);

      const result = await service.findBySlug('nonexistent');
      expect(result).toBeNull();
    });
  });

  describe('update', () => {
    it('updates when author matches', async () => {
      const existing = { id: 1, slug: 'test', authorId: 5 };
      mockFindFirst.mockResolvedValue(existing);
      const updated = { ...existing, title: 'New Title' };
      mockReturning.mockResolvedValue([updated]);

      const result = await service.update('test', 5, { title: 'New Title' });

      expect(mockUpdate).toHaveBeenCalled();
      expect(result).toEqual(updated);
    });

    it('throws 404 when article not found', async () => {
      mockFindFirst.mockResolvedValue(undefined);

      await expect(service.update('nope', 1, { title: 'x' })).rejects.toThrow('Article not found');

      try {
        await service.update('nope', 1, { title: 'x' });
      } catch (e: unknown) {
        expect((e as { statusCode: number }).statusCode).toBe(404);
      }
    });

    it('throws 403 when author does not match', async () => {
      mockFindFirst.mockResolvedValue({ id: 1, slug: 'test', authorId: 5 });

      await expect(service.update('test', 999, { title: 'x' })).rejects.toThrow('You can only update your own articles');

      try {
        await service.update('test', 999, { title: 'x' });
      } catch (e: unknown) {
        expect((e as { statusCode: number }).statusCode).toBe(403);
      }
    });
  });

  describe('delete', () => {
    it('throws 403 when author does not match', async () => {
      mockFindFirst.mockResolvedValue({ id: 1, slug: 'test', authorId: 5 });

      await expect(service.delete('test', 999)).rejects.toThrow('You can only delete your own articles');

      try {
        await service.delete('test', 999);
      } catch (e: unknown) {
        expect((e as { statusCode: number }).statusCode).toBe(403);
      }
    });
  });
});
