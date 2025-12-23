/* eslint-disable @typescript-eslint/no-unsafe-assignment, @typescript-eslint/no-unsafe-member-access, @typescript-eslint/no-unsafe-argument */
import request from 'supertest';
import {
  createTestApp,
  closeTestApp,
  TestAppInstance,
} from '../helpers/test-app.helper';
import { clearDatabase } from '../helpers/db.helper';

describe('Auth (e2e)', () => {
  let testApp: TestAppInstance;
  const testEmail = 'test@example.com';
  const testPassword = 'Password123';
  const testName = 'Test User';

  beforeAll(async () => {
    testApp = await createTestApp();
  });

  afterAll(async () => {
    await closeTestApp(testApp);
  });

  beforeEach(async () => {
    await clearDatabase(testApp.app);
  });

  describe('POST /api/auth/register', () => {
    it('should register a new user', async () => {
      const response = await request(testApp.app.getHttpServer())
        .post('/api/auth/register')
        .send({
          email: testEmail,
          password: testPassword,
          name: testName,
        });

      expect(response.status).toBe(201);
      expect(response.body).toHaveProperty('token');
      expect(response.body.user).toMatchObject({
        email: testEmail,
        name: testName,
      });
      expect(response.body.user).not.toHaveProperty('password');
    });

    it('should return 400 for missing required fields', async () => {
      const response = await request(testApp.app.getHttpServer())
        .post('/api/auth/register')
        .send({
          email: testEmail,
        });

      expect(response.status).toBe(400);
    });

    it('should return 400 for invalid email format', async () => {
      const response = await request(testApp.app.getHttpServer())
        .post('/api/auth/register')
        .send({
          email: 'invalid-email',
          password: testPassword,
          name: testName,
        });

      expect(response.status).toBe(400);
    });

    it('should return 409 for duplicate email', async () => {
      await request(testApp.app.getHttpServer())
        .post('/api/auth/register')
        .send({
          email: testEmail,
          password: testPassword,
          name: testName,
        });

      const response = await request(testApp.app.getHttpServer())
        .post('/api/auth/register')
        .send({
          email: testEmail,
          password: testPassword,
          name: 'Another User',
        });

      expect(response.status).toBe(409);
    });
  });

  describe('POST /api/auth/login', () => {
    beforeEach(async () => {
      await request(testApp.app.getHttpServer())
        .post('/api/auth/register')
        .send({
          email: testEmail,
          password: testPassword,
          name: testName,
        });
    });

    it('should login with valid credentials', async () => {
      const response = await request(testApp.app.getHttpServer())
        .post('/api/auth/login')
        .send({
          email: testEmail,
          password: testPassword,
        });

      expect(response.status).toBe(200);
      expect(response.body).toHaveProperty('token');
      expect(response.body.user).toMatchObject({
        email: testEmail,
        name: testName,
      });
    });

    it('should return 401 for wrong password', async () => {
      const response = await request(testApp.app.getHttpServer())
        .post('/api/auth/login')
        .send({
          email: testEmail,
          password: 'wrongpassword',
        });

      expect(response.status).toBe(401);
    });

    it('should return 401 for non-existent user', async () => {
      const response = await request(testApp.app.getHttpServer())
        .post('/api/auth/login')
        .send({
          email: 'nouser@example.com',
          password: testPassword,
        });

      expect(response.status).toBe(401);
    });
  });

  describe('GET /api/auth/me', () => {
    let authToken: string;

    beforeEach(async () => {
      const registerResponse = await request(testApp.app.getHttpServer())
        .post('/api/auth/register')
        .send({
          email: testEmail,
          password: testPassword,
          name: testName,
        });

      authToken = registerResponse.body.token;
    });

    it('should return current user profile', async () => {
      const response = await request(testApp.app.getHttpServer())
        .get('/api/auth/me')
        .set('Authorization', `Bearer ${authToken}`);

      expect(response.status).toBe(200);
      expect(response.body).toMatchObject({
        email: testEmail,
        name: testName,
      });
      expect(response.body).not.toHaveProperty('password');
    });

    it('should return 401 without token', async () => {
      const response = await request(testApp.app.getHttpServer()).get(
        '/api/auth/me',
      );

      expect(response.status).toBe(401);
    });

    it('should return 401 with invalid token', async () => {
      const response = await request(testApp.app.getHttpServer())
        .get('/api/auth/me')
        .set('Authorization', 'Bearer invalid.token.here');

      expect(response.status).toBe(401);
    });
  });

  describe('POST /api/auth/logout', () => {
    let authToken: string;

    beforeEach(async () => {
      const registerResponse = await request(testApp.app.getHttpServer())
        .post('/api/auth/register')
        .send({
          email: testEmail,
          password: testPassword,
          name: testName,
        });

      authToken = registerResponse.body.token;
    });

    it('should logout successfully', async () => {
      const response = await request(testApp.app.getHttpServer())
        .post('/api/auth/logout')
        .set('Authorization', `Bearer ${authToken}`);

      expect(response.status).toBe(200);
      expect(response.body).toHaveProperty('message');
    });

    it('should return 401 without token', async () => {
      const response = await request(testApp.app.getHttpServer()).post(
        '/api/auth/logout',
      );

      expect(response.status).toBe(401);
    });
  });
});
