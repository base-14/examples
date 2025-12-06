import { describe, it, expect, beforeAll, afterAll, beforeEach, vi } from 'vitest';
import request from 'supertest';
import { Application } from 'express';
import { createTestApp, type TestAppInstance } from '../helpers/app.helper';
import { clearDatabase } from '../helpers/db.helper';
import { User, type IUser } from '../../src/models/User';
import { Article } from '../../src/models/Article';
import * as queueModule from '../../src/jobs/queue';

vi.mock('../../src/jobs/queue', () => ({
  publishQueue: {
    add: vi.fn().mockResolvedValue({ id: 'test-job-id' }),
  },
}));

describe('Articles E2E', () => {
  let testApp: TestAppInstance;
  let app: Application;
  let testUser: IUser;
  let authToken: string;

  beforeAll(() => {
    testApp = createTestApp();
    app = testApp.app;
  });

  afterAll(async () => {
    await testApp.close();
  });

  beforeEach(async () => {
    await clearDatabase();
    vi.clearAllMocks();

    testUser = await User.create({
      email: 'author@example.com',
      password: 'password123',
      name: 'Test Author',
    });

    const loginResponse = await request(app).post('/api/v1/auth/login').send({
      email: 'author@example.com',
      password: 'password123',
    });

    authToken = loginResponse.body.token;
  });

  describe('POST /api/v1/articles', () => {
    it('should create article with valid data', async () => {
      const response = await request(app)
        .post('/api/v1/articles')
        .set('Authorization', `Bearer ${authToken}`)
        .send({
          title: 'Test Article',
          content: 'This is test content for the article',
          tags: ['test', 'vitest'],
        });

      expect(response.status).toBe(201);
      expect(response.body).toMatchObject({
        title: 'Test Article',
        content: 'This is test content for the article',
        tags: ['test', 'vitest'],
        published: false,
        viewCount: 0,
      });
      expect(response.body).toHaveProperty('_id');

      const article = await Article.findOne({ title: 'Test Article' });
      expect(article).toBeDefined();
      expect(article?.author.toString()).toBe(testUser._id.toString());
    });

    it('should return 401 when not authenticated', async () => {
      const response = await request(app).post('/api/v1/articles').send({
        title: 'Test Article',
        content: 'Test content',
      });

      expect(response.status).toBe(401);
    });

    it('should return 400 when title is missing', async () => {
      const response = await request(app)
        .post('/api/v1/articles')
        .set('Authorization', `Bearer ${authToken}`)
        .send({
          content: 'Test content',
        });

      expect(response.status).toBe(400);
      expect(response.body.error).toMatch(/title.*(required|invalid.*input)/i);
    });
  });

  describe('GET /api/v1/articles', () => {
    beforeEach(async () => {
      await Article.create([
        {
          title: 'Article 1',
          content: 'Content 1',
          author: testUser._id,
          published: true,
        },
        {
          title: 'Article 2',
          content: 'Content 2',
          author: testUser._id,
          published: true,
        },
        {
          title: 'Article 3',
          content: 'Content 3',
          author: testUser._id,
          published: false,
        },
      ]);
    });

    it('should list articles with pagination', async () => {
      const response = await request(app).get('/api/v1/articles');

      expect(response.status).toBe(200);
      expect(response.body.articles).toHaveLength(3);
      expect(response.body.pagination).toMatchObject({
        page: 1,
        pages: 1,
        total: 3,
      });
    });

    it('should support pagination parameters', async () => {
      const response = await request(app).get('/api/v1/articles?page=1&limit=2');

      expect(response.status).toBe(200);
      expect(response.body.articles).toHaveLength(2);
      expect(response.body.pagination).toMatchObject({
        page: 1,
        pages: 2,
        total: 3,
        limit: 2,
      });
    });
  });

  describe('GET /api/v1/articles/:id', () => {
    it('should get article by id', async () => {
      const article = await Article.create({
        title: 'Test Article',
        content: 'Test content',
        author: testUser._id,
      });

      const response = await request(app).get(`/api/v1/articles/${article._id}`);

      expect(response.status).toBe(200);
      expect(response.body).toMatchObject({
        title: 'Test Article',
        content: 'Test content',
        author: testUser._id.toString(),
      });
    });

    it('should return 404 when article not found', async () => {
      const fakeId = '507f1f77bcf86cd799439011';
      const response = await request(app).get(`/api/v1/articles/${fakeId}`);

      expect(response.status).toBe(404);
      expect(response.body.error).toMatch(/not found/i);
    });

    it('should increment view count', async () => {
      const article = await Article.create({
        title: 'Test Article',
        content: 'Test content',
        author: testUser._id,
        viewCount: 5,
      });

      const response = await request(app).get(`/api/v1/articles/${article._id}`);

      expect(response.status).toBe(200);
      expect(response.body.viewCount).toBe(6);

      const updatedArticle = await Article.findById(article._id);
      expect(updatedArticle?.viewCount).toBe(6);
    });
  });

  describe('PUT /api/v1/articles/:id', () => {
    it('should update article when owner', async () => {
      const article = await Article.create({
        title: 'Original Title',
        content: 'Original content',
        author: testUser._id,
      });

      const response = await request(app)
        .put(`/api/v1/articles/${article._id}`)
        .set('Authorization', `Bearer ${authToken}`)
        .send({
          title: 'Updated Title',
          content: 'Updated content',
          tags: ['updated'],
        });

      expect(response.status).toBe(200);
      expect(response.body).toMatchObject({
        title: 'Updated Title',
        content: 'Updated content',
        tags: ['updated'],
      });

      const updatedArticle = await Article.findById(article._id);
      expect(updatedArticle?.title).toBe('Updated Title');
    });

    it('should return 401 when not authenticated', async () => {
      const article = await Article.create({
        title: 'Test Article',
        content: 'Test content',
        author: testUser._id,
      });

      const response = await request(app)
        .put(`/api/v1/articles/${article._id}`)
        .send({
          title: 'Updated Title',
        });

      expect(response.status).toBe(401);
    });

    it('should return 403 when not article owner', async () => {
      const otherUser = await User.create({
        email: 'other@example.com',
        password: 'password123',
        name: 'Other User',
      });

      const article = await Article.create({
        title: 'Test Article',
        content: 'Test content',
        author: otherUser._id,
      });

      const response = await request(app)
        .put(`/api/v1/articles/${article._id}`)
        .set('Authorization', `Bearer ${authToken}`)
        .send({
          title: 'Updated Title',
        });

      expect(response.status).toBe(403);
      expect(response.body.error).toMatch(/not authorized/i);
    });
  });

  describe('DELETE /api/v1/articles/:id', () => {
    it('should delete article when owner', async () => {
      const article = await Article.create({
        title: 'Test Article',
        content: 'Test content',
        author: testUser._id,
      });

      const response = await request(app)
        .delete(`/api/v1/articles/${article._id}`)
        .set('Authorization', `Bearer ${authToken}`);

      expect(response.status).toBe(204);

      const deletedArticle = await Article.findById(article._id);
      expect(deletedArticle).toBeNull();
    });

    it('should return 401 when not authenticated', async () => {
      const article = await Article.create({
        title: 'Test Article',
        content: 'Test content',
        author: testUser._id,
      });

      const response = await request(app).delete(`/api/v1/articles/${article._id}`);

      expect(response.status).toBe(401);
    });

    it('should return 403 when not article owner', async () => {
      const otherUser = await User.create({
        email: 'other@example.com',
        password: 'password123',
        name: 'Other User',
      });

      const article = await Article.create({
        title: 'Test Article',
        content: 'Test content',
        author: otherUser._id,
      });

      const response = await request(app)
        .delete(`/api/v1/articles/${article._id}`)
        .set('Authorization', `Bearer ${authToken}`);

      expect(response.status).toBe(403);
    });
  });

  describe('POST /api/v1/articles/:id/publish', () => {
    it('should enqueue publish job for unpublished article', async () => {
      const article = await Article.create({
        title: 'Test Article',
        content: 'Test content',
        author: testUser._id,
        published: false,
      });

      const response = await request(app)
        .post(`/api/v1/articles/${article._id}/publish`)
        .set('Authorization', `Bearer ${authToken}`);

      expect(response.status).toBe(200);
      expect(response.body).toMatchObject({
        message: 'Article publishing job enqueued',
        jobId: 'test-job-id',
      });
      expect(queueModule.publishQueue.add).toHaveBeenCalledWith(
        'publish-article',
        expect.objectContaining({
          articleId: article._id.toString(),
        })
      );
    });

    it('should return 400 when article is already published', async () => {
      const article = await Article.create({
        title: 'Test Article',
        content: 'Test content',
        author: testUser._id,
        published: true,
      });

      const response = await request(app)
        .post(`/api/v1/articles/${article._id}/publish`)
        .set('Authorization', `Bearer ${authToken}`);

      expect(response.status).toBe(400);
      expect(response.body.error).toMatch(/already published/i);
    });

    it('should return 403 when not article owner', async () => {
      const otherUser = await User.create({
        email: 'other@example.com',
        password: 'password123',
        name: 'Other User',
      });

      const article = await Article.create({
        title: 'Test Article',
        content: 'Test content',
        author: otherUser._id,
        published: false,
      });

      const response = await request(app)
        .post(`/api/v1/articles/${article._id}/publish`)
        .set('Authorization', `Bearer ${authToken}`);

      expect(response.status).toBe(403);
    });
  });
});
