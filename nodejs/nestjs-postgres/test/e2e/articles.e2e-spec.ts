/* eslint-disable @typescript-eslint/no-unsafe-assignment, @typescript-eslint/no-unsafe-member-access, @typescript-eslint/no-unsafe-argument */
import request from 'supertest';
import {
  createTestApp,
  closeTestApp,
  TestAppInstance,
} from '../helpers/test-app.helper';
import { clearDatabase } from '../helpers/db.helper';
import { createTestUser, authHeader, TestUser } from '../helpers/auth.helper';

describe('Articles (e2e)', () => {
  let testApp: TestAppInstance;
  let testUser: TestUser;

  beforeAll(async () => {
    testApp = await createTestApp();
  });

  afterAll(async () => {
    await closeTestApp(testApp);
  });

  beforeEach(async () => {
    await clearDatabase(testApp.app);
    testUser = await createTestUser(testApp.app, {
      email: 'author@example.com',
      password: 'Password123',
      name: 'Test Author',
    });
  });

  describe('POST /api/articles', () => {
    it('should create article with valid data', async () => {
      const response = await request(testApp.app.getHttpServer())
        .post('/api/articles')
        .set(authHeader(testUser.token))
        .send({
          title: 'Test Article',
          content: 'This is test content for the article',
          tags: ['test', 'jest'],
        });

      expect(response.status).toBe(201);
      expect(response.body).toMatchObject({
        title: 'Test Article',
        content: 'This is test content for the article',
        tags: ['test', 'jest'],
        published: false,
        favoritesCount: 0,
      });
      expect(response.body).toHaveProperty('id');
    });

    it('should return 401 when not authenticated', async () => {
      const response = await request(testApp.app.getHttpServer())
        .post('/api/articles')
        .send({
          title: 'Test Article',
          content: 'Test content',
        });

      expect(response.status).toBe(401);
    });

    it('should return 400 when title is missing', async () => {
      const response = await request(testApp.app.getHttpServer())
        .post('/api/articles')
        .set(authHeader(testUser.token))
        .send({
          content: 'Test content',
        });

      expect(response.status).toBe(400);
    });

    it('should return 400 when content is missing', async () => {
      const response = await request(testApp.app.getHttpServer())
        .post('/api/articles')
        .set(authHeader(testUser.token))
        .send({
          title: 'Test Article',
        });

      expect(response.status).toBe(400);
    });
  });

  describe('GET /api/articles', () => {
    it('should list articles with default pagination', async () => {
      // Create 15 articles
      for (let i = 1; i <= 15; i++) {
        const res = await request(testApp.app.getHttpServer())
          .post('/api/articles')
          .set(authHeader(testUser.token))
          .send({
            title: `Article ${i}`,
            content: `Content ${i} - This is test content that meets the minimum length requirement for article content validation.`,
          });
        expect(res.status).toBe(201);
      }

      const response = await request(testApp.app.getHttpServer()).get(
        '/api/articles',
      );

      expect(response.status).toBe(200);
      expect(response.body.data).toHaveLength(10);
      expect(response.body.meta).toMatchObject({
        page: 1,
        limit: 10,
        total: 15,
        totalPages: 2,
      });
    });

    it('should support custom pagination', async () => {
      // Create 15 articles
      for (let i = 1; i <= 15; i++) {
        const res = await request(testApp.app.getHttpServer())
          .post('/api/articles')
          .set(authHeader(testUser.token))
          .send({
            title: `Article ${i}`,
            content: `Content ${i} - This is test content that meets the minimum length requirement for article content validation.`,
          });
        expect(res.status).toBe(201);
      }

      const response = await request(testApp.app.getHttpServer()).get(
        '/api/articles?page=2&limit=5',
      );

      expect(response.status).toBe(200);
      expect(response.body.data).toHaveLength(5);
      expect(response.body.meta).toMatchObject({
        page: 2,
        limit: 5,
        total: 15,
        totalPages: 3,
      });
    });

    it('should return empty array when no articles', async () => {
      const response = await request(testApp.app.getHttpServer()).get(
        '/api/articles',
      );

      expect(response.status).toBe(200);
      expect(response.body.data).toHaveLength(0);
      expect(response.body.meta.total).toBe(0);
    });
  });

  describe('GET /api/articles/:id', () => {
    let articleId: string;

    beforeEach(async () => {
      const createResponse = await request(testApp.app.getHttpServer())
        .post('/api/articles')
        .set(authHeader(testUser.token))
        .send({
          title: 'Test Article',
          content: 'Test content',
        });

      articleId = createResponse.body.id;
    });

    it('should get article by id', async () => {
      const response = await request(testApp.app.getHttpServer()).get(
        `/api/articles/${articleId}`,
      );

      expect(response.status).toBe(200);
      expect(response.body).toMatchObject({
        id: articleId,
        title: 'Test Article',
        content: 'Test content',
      });
    });

    it('should return 404 when article not found', async () => {
      const fakeId = '00000000-0000-0000-0000-000000000000';
      const response = await request(testApp.app.getHttpServer()).get(
        `/api/articles/${fakeId}`,
      );

      expect(response.status).toBe(404);
    });

    it('should return 400 for invalid UUID', async () => {
      const response = await request(testApp.app.getHttpServer()).get(
        '/api/articles/not-a-uuid',
      );

      expect(response.status).toBe(400);
    });
  });

  describe('PUT /api/articles/:id', () => {
    let articleId: string;

    beforeEach(async () => {
      const createResponse = await request(testApp.app.getHttpServer())
        .post('/api/articles')
        .set(authHeader(testUser.token))
        .send({
          title: 'Original Title',
          content: 'Original content',
        });

      articleId = createResponse.body.id;
    });

    it('should update article when owner', async () => {
      const response = await request(testApp.app.getHttpServer())
        .put(`/api/articles/${articleId}`)
        .set(authHeader(testUser.token))
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
    });

    it('should return 401 when not authenticated', async () => {
      const response = await request(testApp.app.getHttpServer())
        .put(`/api/articles/${articleId}`)
        .send({
          title: 'Updated Title',
        });

      expect(response.status).toBe(401);
    });

    it('should return 403 when not article owner', async () => {
      const otherUser = await createTestUser(testApp.app, {
        email: 'other@example.com',
        password: 'Password123',
        name: 'Other User',
      });

      const response = await request(testApp.app.getHttpServer())
        .put(`/api/articles/${articleId}`)
        .set(authHeader(otherUser.token))
        .send({
          title: 'Updated Title',
        });

      expect(response.status).toBe(403);
    });
  });

  describe('DELETE /api/articles/:id', () => {
    let articleId: string;

    beforeEach(async () => {
      const createResponse = await request(testApp.app.getHttpServer())
        .post('/api/articles')
        .set(authHeader(testUser.token))
        .send({
          title: 'Test Article',
          content: 'Test content',
        });

      articleId = createResponse.body.id;
    });

    it('should delete article when owner', async () => {
      const response = await request(testApp.app.getHttpServer())
        .delete(`/api/articles/${articleId}`)
        .set(authHeader(testUser.token));

      expect(response.status).toBe(204);

      const getResponse = await request(testApp.app.getHttpServer()).get(
        `/api/articles/${articleId}`,
      );
      expect(getResponse.status).toBe(404);
    });

    it('should return 401 when not authenticated', async () => {
      const response = await request(testApp.app.getHttpServer()).delete(
        `/api/articles/${articleId}`,
      );

      expect(response.status).toBe(401);
    });

    it('should return 403 when not article owner', async () => {
      const otherUser = await createTestUser(testApp.app, {
        email: 'other@example.com',
        password: 'Password123',
        name: 'Other User',
      });

      const response = await request(testApp.app.getHttpServer())
        .delete(`/api/articles/${articleId}`)
        .set(authHeader(otherUser.token));

      expect(response.status).toBe(403);
    });
  });

  describe('POST /api/articles/:id/publish', () => {
    let articleId: string;

    beforeEach(async () => {
      const createResponse = await request(testApp.app.getHttpServer())
        .post('/api/articles')
        .set(authHeader(testUser.token))
        .send({
          title: 'Test Article',
          content: 'Test content',
        });

      articleId = createResponse.body.id;
    });

    it('should enqueue publish job for unpublished article', async () => {
      const response = await request(testApp.app.getHttpServer())
        .post(`/api/articles/${articleId}/publish`)
        .set(authHeader(testUser.token));

      expect(response.status).toBe(201);
      expect(response.body).toMatchObject({
        message: 'Article publish job enqueued',
      });
      expect(response.body).toHaveProperty('jobId');
    });

    it('should return 403 when not article owner', async () => {
      const otherUser = await createTestUser(testApp.app, {
        email: 'other@example.com',
        password: 'Password123',
        name: 'Other User',
      });

      const response = await request(testApp.app.getHttpServer())
        .post(`/api/articles/${articleId}/publish`)
        .set(authHeader(otherUser.token));

      expect(response.status).toBe(403);
    });
  });

  describe('Favorites', () => {
    let articleId: string;

    beforeEach(async () => {
      const createResponse = await request(testApp.app.getHttpServer())
        .post('/api/articles')
        .set(authHeader(testUser.token))
        .send({
          title: 'Test Article',
          content: 'Test content',
        });

      articleId = createResponse.body.id;
    });

    describe('POST /api/articles/:id/favorite', () => {
      it('should favorite an article', async () => {
        const response = await request(testApp.app.getHttpServer())
          .post(`/api/articles/${articleId}/favorite`)
          .set(authHeader(testUser.token));

        expect(response.status).toBe(201);

        const getResponse = await request(testApp.app.getHttpServer()).get(
          `/api/articles/${articleId}`,
        );
        expect(getResponse.body.favoritesCount).toBe(1);
      });

      it('should return 401 when not authenticated', async () => {
        const response = await request(testApp.app.getHttpServer()).post(
          `/api/articles/${articleId}/favorite`,
        );

        expect(response.status).toBe(401);
      });

      it('should be idempotent (no error on duplicate)', async () => {
        await request(testApp.app.getHttpServer())
          .post(`/api/articles/${articleId}/favorite`)
          .set(authHeader(testUser.token));

        const response = await request(testApp.app.getHttpServer())
          .post(`/api/articles/${articleId}/favorite`)
          .set(authHeader(testUser.token));

        expect(response.status).toBe(201);

        const getResponse = await request(testApp.app.getHttpServer()).get(
          `/api/articles/${articleId}`,
        );
        expect(getResponse.body.favoritesCount).toBe(1);
      });
    });

    describe('DELETE /api/articles/:id/favorite', () => {
      beforeEach(async () => {
        await request(testApp.app.getHttpServer())
          .post(`/api/articles/${articleId}/favorite`)
          .set(authHeader(testUser.token));
      });

      it('should unfavorite an article', async () => {
        const response = await request(testApp.app.getHttpServer())
          .delete(`/api/articles/${articleId}/favorite`)
          .set(authHeader(testUser.token));

        expect(response.status).toBe(200);

        const getResponse = await request(testApp.app.getHttpServer()).get(
          `/api/articles/${articleId}`,
        );
        expect(getResponse.body.favoritesCount).toBe(0);
      });

      it('should return 401 when not authenticated', async () => {
        const response = await request(testApp.app.getHttpServer()).delete(
          `/api/articles/${articleId}/favorite`,
        );

        expect(response.status).toBe(401);
      });
    });
  });
});
