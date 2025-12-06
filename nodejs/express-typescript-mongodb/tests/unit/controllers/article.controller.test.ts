import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import type { Request, Response, NextFunction } from 'express';
import type { Server } from 'socket.io';
import {
  createArticle,
  listArticles,
  getArticle,
  updateArticle,
  deleteArticle,
  publishArticle,
} from '../../../src/controllers/article.controller.js';
import { Article } from '../../../src/models/Article.js';
import { User, type IUser } from '../../../src/models/User.js';
import { clearDatabase } from '../../helpers/db.helper.js';
import { publishQueue } from '../../../src/jobs/queue.js';
import * as socketEmitter from '../../../src/utils/socketEmitter.js';
import {
  ValidationError,
  AuthenticationError,
  AuthorizationError,
  NotFoundError,
} from '../../../src/utils/errors.js';

vi.mock('../../../src/jobs/queue', () => ({
  publishQueue: {
    add: vi.fn(),
  },
}));

vi.mock('../../../src/utils/socketEmitter', () => ({
  emitArticleEvent: vi.fn(),
}));

describe('Article Controller', () => {
  let mockReq: Partial<Request>;
  let mockRes: Partial<Response>;
  let mockNext: NextFunction;
  let testUser: IUser;
  let mockIo: Partial<Server>;

  beforeEach(async () => {
    await clearDatabase();

    testUser = await User.create({
      email: 'testuser@example.com',
      password: 'password123',
      name: 'Test User',
    });

    mockIo = {
      to: vi.fn().mockReturnThis(),
      emit: vi.fn(),
    } as any;

    mockReq = {
      body: {},
      params: {},
      query: {},
      user: testUser as any,
      app: {
        get: vi.fn((key: string) => {
          if (key === 'io') return mockIo;
          return undefined;
        }),
      } as any,
    };

    mockRes = {
      status: vi.fn().mockReturnThis(),
      json: vi.fn().mockReturnThis(),
      send: vi.fn().mockReturnThis(),
    };

    mockNext = vi.fn();

    vi.clearAllMocks();
  });

  afterEach(async () => {
    await clearDatabase();
  });

  describe('createArticle', () => {
    it('should create article with valid data', async () => {
      mockReq.body = {
        title: 'Test Article',
        content: 'This is test content',
        tags: ['test', 'vitest'],
      };

      await createArticle(mockReq as Request, mockRes as Response, mockNext);

      expect(mockRes.status).toHaveBeenCalledWith(201);
      expect(mockRes.json).toHaveBeenCalledWith(
        expect.objectContaining({
          title: 'Test Article',
          content: 'This is test content',
          tags: ['test', 'vitest'],
          author: testUser._id,
        })
      );

      const article = await Article.findOne({ title: 'Test Article' });
      expect(article).toBeDefined();
      expect(article?.author.toString()).toBe(testUser._id.toString());
    });

    it('should create article without tags', async () => {
      mockReq.body = {
        title: 'Test Article',
        content: 'This is test content',
      };

      await createArticle(mockReq as Request, mockRes as Response, mockNext);

      expect(mockRes.status).toHaveBeenCalledWith(201);
      expect(mockRes.json).toHaveBeenCalledWith(
        expect.objectContaining({
          tags: [],
        })
      );
    });

    it('should call next with AuthenticationError when user is not authenticated', async () => {
      mockReq.user = undefined;
      mockReq.body = {
        title: 'Test Article',
        content: 'Test content',
      };

      await createArticle(mockReq as Request, mockRes as Response, mockNext);

      expect(mockNext).toHaveBeenCalledWith(expect.any(AuthenticationError));
    });

    it('should emit Socket.io event on creation', async () => {
      mockReq.body = {
        title: 'Test Article',
        content: 'Test content',
      };

      await createArticle(mockReq as Request, mockRes as Response, mockNext);

      expect(socketEmitter.emitArticleEvent).toHaveBeenCalledWith(
        mockIo,
        expect.objectContaining({
          event: 'article:created',
          data: expect.objectContaining({
            title: 'Test Article',
            authorId: testUser._id.toString(),
          }),
        })
      );
    });

    it('should call next with error when database error occurs', async () => {
      const dbError = new Error('Database error');
      vi.spyOn(Article.prototype, 'save').mockRejectedValueOnce(dbError);

      mockReq.body = {
        title: 'Test Article',
        content: 'Test content',
      };

      await createArticle(mockReq as Request, mockRes as Response, mockNext);

      expect(mockNext).toHaveBeenCalledWith(dbError);
    });
  });

  describe('listArticles', () => {
    beforeEach(async () => {
      await Article.create([
        {
          title: 'Article 1',
          content: 'Content 1',
          author: testUser._id,
        },
        {
          title: 'Article 2',
          content: 'Content 2',
          author: testUser._id,
        },
        {
          title: 'Article 3',
          content: 'Content 3',
          author: testUser._id,
        },
      ]);
    });

    it('should list articles with default pagination', async () => {
      await listArticles(mockReq as Request, mockRes as Response, mockNext);

      expect(mockRes.json).toHaveBeenCalledWith(
        expect.objectContaining({
          articles: expect.arrayContaining([
            expect.objectContaining({ title: 'Article 1' }),
            expect.objectContaining({ title: 'Article 2' }),
            expect.objectContaining({ title: 'Article 3' }),
          ]),
          pagination: {
            page: 1,
            limit: 10,
            total: 3,
            pages: 1,
          },
        })
      );
    });

    it('should list articles with custom pagination', async () => {
      mockReq.query = {
        page: '2',
        limit: '2',
      };

      await listArticles(mockReq as Request, mockRes as Response, mockNext);

      expect(mockRes.json).toHaveBeenCalledWith(
        expect.objectContaining({
          articles: expect.any(Array),
          pagination: {
            page: 2,
            limit: 2,
            total: 3,
            pages: 2,
          },
        })
      );
    });

    it('should return empty array when no articles exist', async () => {
      await clearDatabase();

      await listArticles(mockReq as Request, mockRes as Response, mockNext);

      expect(mockRes.json).toHaveBeenCalledWith(
        expect.objectContaining({
          articles: [],
          pagination: {
            page: 1,
            limit: 10,
            total: 0,
            pages: 0,
          },
        })
      );
    });

    it('should call next with error when database error occurs', async () => {
      const dbError = new Error('Database error');
      vi.spyOn(Article, 'find').mockReturnValueOnce({
        sort: vi.fn().mockReturnThis(),
        skip: vi.fn().mockReturnThis(),
        limit: vi.fn().mockRejectedValueOnce(dbError),
      } as any);

      await listArticles(mockReq as Request, mockRes as Response, mockNext);

      expect(mockNext).toHaveBeenCalledWith(dbError);
    });
  });

  describe('getArticle', () => {
    it('should get article by ID and increment view count', async () => {
      const article = await Article.create({
        title: 'Test Article',
        content: 'Test content',
        author: testUser._id,
        viewCount: 5,
      });

      mockReq.params = { id: article._id.toString() };

      await getArticle(mockReq as Request, mockRes as Response, mockNext);

      expect(mockRes.json).toHaveBeenCalledWith(
        expect.objectContaining({
          title: 'Test Article',
          viewCount: 6,
        })
      );

      const updatedArticle = await Article.findById(article._id);
      expect(updatedArticle?.viewCount).toBe(6);
    });

    it('should call next with NotFoundError when article not found', async () => {
      mockReq.params = { id: '507f1f77bcf86cd799439011' };

      await getArticle(mockReq as Request, mockRes as Response, mockNext);

      expect(mockNext).toHaveBeenCalledWith(expect.any(NotFoundError));
    });

    it('should call next with error when database error occurs', async () => {
      const article = await Article.create({
        title: 'Test Article',
        content: 'Test content',
        author: testUser._id,
      });

      const dbError = new Error('Database error');
      vi.spyOn(Article, 'findByIdAndUpdate').mockRejectedValueOnce(dbError);

      mockReq.params = { id: article._id.toString() };

      await getArticle(mockReq as Request, mockRes as Response, mockNext);

      expect(mockNext).toHaveBeenCalledWith(dbError);
    });
  });

  describe('updateArticle', () => {
    let article: any;

    beforeEach(async () => {
      article = await Article.create({
        title: 'Original Title',
        content: 'Original content',
        author: testUser._id,
        tags: ['original'],
      });
    });

    it('should update article with valid data', async () => {
      mockReq.params = { id: article._id.toString() };
      mockReq.body = {
        title: 'Updated Title',
        content: 'Updated content',
        tags: ['updated', 'test'],
      };

      await updateArticle(mockReq as Request, mockRes as Response, mockNext);

      expect(mockRes.json).toHaveBeenCalledWith(
        expect.objectContaining({
          title: 'Updated Title',
          content: 'Updated content',
          tags: ['updated', 'test'],
        })
      );

      const updatedArticle = await Article.findById(article._id);
      expect(updatedArticle?.title).toBe('Updated Title');
    });

    it('should update only provided fields', async () => {
      mockReq.params = { id: article._id.toString() };
      mockReq.body = {
        title: 'Updated Title Only',
      };

      await updateArticle(mockReq as Request, mockRes as Response, mockNext);

      expect(mockRes.json).toHaveBeenCalledWith(
        expect.objectContaining({
          title: 'Updated Title Only',
          content: 'Original content',
        })
      );
    });

    it('should call next with AuthenticationError when user is not authenticated', async () => {
      mockReq.user = undefined;
      mockReq.params = { id: article._id.toString() };

      await updateArticle(mockReq as Request, mockRes as Response, mockNext);

      expect(mockNext).toHaveBeenCalledWith(expect.any(AuthenticationError));
    });

    it('should call next with NotFoundError when article not found', async () => {
      mockReq.params = { id: '507f1f77bcf86cd799439011' };
      mockReq.body = { title: 'Updated' };

      await updateArticle(mockReq as Request, mockRes as Response, mockNext);

      expect(mockNext).toHaveBeenCalledWith(expect.any(NotFoundError));
    });

    it('should call next with AuthorizationError when user is not the author', async () => {
      const anotherUser = await User.create({
        email: 'another@example.com',
        password: 'password123',
        name: 'Another User',
      });

      mockReq.user = anotherUser as any;
      mockReq.params = { id: article._id.toString() };
      mockReq.body = { title: 'Updated' };

      await updateArticle(mockReq as Request, mockRes as Response, mockNext);

      expect(mockNext).toHaveBeenCalledWith(expect.any(AuthorizationError));
    });

    it('should emit Socket.io event on update', async () => {
      mockReq.params = { id: article._id.toString() };
      mockReq.body = { title: 'Updated Title' };

      await updateArticle(mockReq as Request, mockRes as Response, mockNext);

      expect(socketEmitter.emitArticleEvent).toHaveBeenCalledWith(
        mockIo,
        expect.objectContaining({
          event: 'article:updated',
        })
      );
    });
  });

  describe('deleteArticle', () => {
    let article: any;

    beforeEach(async () => {
      article = await Article.create({
        title: 'Article to Delete',
        content: 'Content to delete',
        author: testUser._id,
      });
    });

    it('should delete article', async () => {
      mockReq.params = { id: article._id.toString() };

      await deleteArticle(mockReq as Request, mockRes as Response, mockNext);

      expect(mockRes.status).toHaveBeenCalledWith(204);
      expect(mockRes.send).toHaveBeenCalled();

      const deletedArticle = await Article.findById(article._id);
      expect(deletedArticle).toBeNull();
    });

    it('should call next with AuthenticationError when user is not authenticated', async () => {
      mockReq.user = undefined;
      mockReq.params = { id: article._id.toString() };

      await deleteArticle(mockReq as Request, mockRes as Response, mockNext);

      expect(mockNext).toHaveBeenCalledWith(expect.any(AuthenticationError));
    });

    it('should call next with NotFoundError when article not found', async () => {
      mockReq.params = { id: '507f1f77bcf86cd799439011' };

      await deleteArticle(mockReq as Request, mockRes as Response, mockNext);

      expect(mockNext).toHaveBeenCalledWith(expect.any(NotFoundError));
    });

    it('should call next with AuthorizationError when user is not the author', async () => {
      const anotherUser = await User.create({
        email: 'another@example.com',
        password: 'password123',
        name: 'Another User',
      });

      mockReq.user = anotherUser as any;
      mockReq.params = { id: article._id.toString() };

      await deleteArticle(mockReq as Request, mockRes as Response, mockNext);

      expect(mockNext).toHaveBeenCalledWith(expect.any(AuthorizationError));
    });

    it('should emit Socket.io event on delete', async () => {
      mockReq.params = { id: article._id.toString() };

      await deleteArticle(mockReq as Request, mockRes as Response, mockNext);

      expect(socketEmitter.emitArticleEvent).toHaveBeenCalledWith(
        mockIo,
        expect.objectContaining({
          event: 'article:deleted',
        })
      );
    });
  });

  describe('publishArticle', () => {
    let article: any;

    beforeEach(async () => {
      article = await Article.create({
        title: 'Article to Publish',
        content: 'Content to publish',
        author: testUser._id,
        published: false,
      });

      vi.mocked(publishQueue.add).mockResolvedValue({
        id: 'test-job-id',
      } as any);
    });

    it('should enqueue publish job for unpublished article', async () => {
      mockReq.params = { id: article._id.toString() };

      await publishArticle(mockReq as Request, mockRes as Response, mockNext);

      expect(publishQueue.add).toHaveBeenCalledWith(
        'publish-article',
        expect.objectContaining({
          articleId: article._id.toString(),
          traceContext: expect.any(Object),
        })
      );

      expect(mockRes.json).toHaveBeenCalledWith(
        expect.objectContaining({
          message: 'Article publishing job enqueued',
          jobId: 'test-job-id',
          articleId: article._id,
        })
      );
    });

    it('should call next with AuthenticationError when user is not authenticated', async () => {
      mockReq.user = undefined;
      mockReq.params = { id: article._id.toString() };

      await publishArticle(mockReq as Request, mockRes as Response, mockNext);

      expect(mockNext).toHaveBeenCalledWith(expect.any(AuthenticationError));
    });

    it('should call next with NotFoundError when article not found', async () => {
      mockReq.params = { id: '507f1f77bcf86cd799439011' };

      await publishArticle(mockReq as Request, mockRes as Response, mockNext);

      expect(mockNext).toHaveBeenCalledWith(expect.any(NotFoundError));
    });

    it('should call next with AuthorizationError when user is not the author', async () => {
      const anotherUser = await User.create({
        email: 'another@example.com',
        password: 'password123',
        name: 'Another User',
      });

      mockReq.user = anotherUser as any;
      mockReq.params = { id: article._id.toString() };

      await publishArticle(mockReq as Request, mockRes as Response, mockNext);

      expect(mockNext).toHaveBeenCalledWith(expect.any(AuthorizationError));
    });

    it('should call next with ValidationError when article is already published', async () => {
      article.published = true;
      await article.save();

      mockReq.params = { id: article._id.toString() };

      await publishArticle(mockReq as Request, mockRes as Response, mockNext);

      expect(mockNext).toHaveBeenCalledWith(expect.any(ValidationError));
    });

    it('should call next with error when queue error occurs', async () => {
      const queueError = new Error('Queue error');
      vi.mocked(publishQueue.add).mockRejectedValueOnce(queueError);

      mockReq.params = { id: article._id.toString() };

      await publishArticle(mockReq as Request, mockRes as Response, mockNext);

      expect(mockNext).toHaveBeenCalledWith(queueError);
    });
  });
});
