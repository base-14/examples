import { describe, it, expect, beforeEach, vi } from 'vitest';
import { Job } from 'bullmq';
import { processPublishArticle } from '../../../src/jobs/processors/publishArticle.processor';
import { Article } from '../../../src/models/Article';
import { User, type IUser } from '../../../src/models/User';
import { clearDatabase } from '../../helpers/db.helper';
import * as socketInstance from '../../../src/utils/socketInstance';
import * as socketEmitter from '../../../src/utils/socketEmitter';

vi.mock('../../../src/utils/socketInstance');
vi.mock('../../../src/utils/socketEmitter');

describe('Publish Article Job Processor Integration', () => {
  let testUser: IUser;

  beforeEach(async () => {
    await clearDatabase();
    vi.clearAllMocks();

    testUser = await User.create({
      email: 'author@example.com',
      password: 'password123',
      name: 'Test Author',
    });

    vi.mocked(socketInstance.getSocketIO).mockReturnValue({
      to: vi.fn().mockReturnThis(),
      emit: vi.fn(),
    } as any);
  });

  it('should publish article and set publishedAt timestamp', async () => {
    const article = await Article.create({
      title: 'Test Article',
      content: 'Test content for article',
      author: testUser._id,
      published: false,
    });

    const mockJob = {
      id: 'test-job-123',
      attemptsMade: 1,
      data: {
        articleId: article._id.toString(),
        traceContext: {},
      },
    } as Job;

    await processPublishArticle(mockJob);

    const publishedArticle = await Article.findById(article._id);
    expect(publishedArticle?.published).toBe(true);
    expect(publishedArticle?.publishedAt).toBeInstanceOf(Date);
    expect(publishedArticle?.publishedAt?.getTime()).toBeGreaterThan(0);
  });

  it('should emit socket event when article is published', async () => {
    const article = await Article.create({
      title: 'Test Article',
      content: 'Test content',
      author: testUser._id,
      published: false,
    });

    const mockJob = {
      id: 'test-job-123',
      attemptsMade: 1,
      data: {
        articleId: article._id.toString(),
        traceContext: {},
      },
    } as Job;

    await processPublishArticle(mockJob);

    expect(socketEmitter.emitArticleEvent).toHaveBeenCalledWith(
      expect.anything(),
      expect.objectContaining({
        event: 'article:published',
        data: expect.objectContaining({
          id: article._id.toString(),
          title: 'Test Article',
          published: true,
        }),
      })
    );
  });

  it('should throw error when article not found', async () => {
    const fakeArticleId = '507f1f77bcf86cd799439011';

    const mockJob = {
      id: 'test-job-123',
      attemptsMade: 1,
      data: {
        articleId: fakeArticleId,
        traceContext: {},
      },
    } as Job;

    await expect(processPublishArticle(mockJob)).rejects.toThrow(/not found/i);
  });

  it('should update article in database with correct values', async () => {
    const article = await Article.create({
      title: 'Integration Test Article',
      content: 'This is a comprehensive integration test',
      author: testUser._id,
      published: false,
      tags: ['integration', 'test'],
    });

    const originalCreatedAt = article.createdAt;
    const originalUpdatedAt = article.updatedAt;

    const mockJob = {
      id: 'test-job-456',
      attemptsMade: 1,
      data: {
        articleId: article._id.toString(),
        traceContext: {},
      },
    } as Job;

    await processPublishArticle(mockJob);

    const publishedArticle = await Article.findById(article._id);

    expect(publishedArticle).toBeDefined();
    expect(publishedArticle?.published).toBe(true);
    expect(publishedArticle?.publishedAt).toBeDefined();
    expect(publishedArticle?.title).toBe('Integration Test Article');
    expect(publishedArticle?.content).toBe('This is a comprehensive integration test');
    expect(publishedArticle?.tags).toEqual(['integration', 'test']);
    expect(publishedArticle?.author.toString()).toBe(testUser._id.toString());
    expect(publishedArticle?.createdAt.getTime()).toBe(originalCreatedAt.getTime());
    expect(publishedArticle?.updatedAt.getTime()).toBeGreaterThanOrEqual(
      originalUpdatedAt.getTime()
    );
  });

  it('should handle multiple job attempts correctly', async () => {
    const article = await Article.create({
      title: 'Retry Test Article',
      content: 'Testing job retry logic',
      author: testUser._id,
      published: false,
    });

    const mockJob = {
      id: 'test-job-retry',
      attemptsMade: 3,
      data: {
        articleId: article._id.toString(),
        traceContext: {},
      },
    } as Job;

    await processPublishArticle(mockJob);

    const publishedArticle = await Article.findById(article._id);
    expect(publishedArticle?.published).toBe(true);
  });

  it('should not fail if socket.io is unavailable', async () => {
    vi.mocked(socketInstance.getSocketIO).mockReturnValue(null);

    const article = await Article.create({
      title: 'Test Article',
      content: 'Test content',
      author: testUser._id,
      published: false,
    });

    const mockJob = {
      id: 'test-job-123',
      attemptsMade: 1,
      data: {
        articleId: article._id.toString(),
        traceContext: {},
      },
    } as Job;

    await expect(processPublishArticle(mockJob)).resolves.not.toThrow();

    const publishedArticle = await Article.findById(article._id);
    expect(publishedArticle?.published).toBe(true);
  });
});
