import { describe, it, expect, beforeAll, afterAll, beforeEach } from 'vitest';
import request from 'supertest';
import { Application } from 'express';
import { createTestApp, type TestAppInstance } from '../helpers/app.helper';
import { clearDatabase } from '../helpers/db.helper';
import { User } from '../../src/models/User';

describe('Auth E2E', () => {
  let testApp: TestAppInstance;
  let app: Application;

  beforeAll(() => {
    testApp = createTestApp();
    app = testApp.app;
  });

  afterAll(async () => {
    await testApp.close();
  });

  beforeEach(async () => {
    await clearDatabase();
  });

  describe('POST /api/v1/auth/register', () => {
    it('should register user and return token', async () => {
      const response = await request(app).post('/api/v1/auth/register').send({
        email: 'newuser@example.com',
        password: 'password123',
        name: 'New User',
      });

      expect(response.status).toBe(201);
      expect(response.body).toHaveProperty('token');
      expect(response.body.user).toMatchObject({
        email: 'newuser@example.com',
        name: 'New User',
        role: 'user',
      });

      const user = await User.findOne({ email: 'newuser@example.com' });
      expect(user).toBeDefined();
    });

    it('should return 400 when email is missing', async () => {
      const response = await request(app).post('/api/v1/auth/register').send({
        password: 'password123',
        name: 'Test User',
      });

      expect(response.status).toBe(400);
      expect(response.body).toHaveProperty('error');
    });

    it('should return 400 when password is too short', async () => {
      const response = await request(app).post('/api/v1/auth/register').send({
        email: 'test@example.com',
        password: '1234567',
        name: 'Test User',
      });

      expect(response.status).toBe(400);
      expect(response.body.error).toMatch(/at least 8 characters/i);
    });

    it('should return 409 when email already exists', async () => {
      await User.create({
        email: 'existing@example.com',
        password: 'password123',
        name: 'Existing User',
      });

      const response = await request(app).post('/api/v1/auth/register').send({
        email: 'existing@example.com',
        password: 'newpassword',
        name: 'New User',
      });

      expect(response.status).toBe(409);
      expect(response.body.error).toMatch(/already exists/i);
    });
  });

  describe('POST /api/v1/auth/login', () => {
    beforeEach(async () => {
      await User.create({
        email: 'testuser@example.com',
        password: 'password123',
        name: 'Test User',
      });
    });

    it('should login with valid credentials', async () => {
      const response = await request(app).post('/api/v1/auth/login').send({
        email: 'testuser@example.com',
        password: 'password123',
      });

      expect(response.status).toBe(200);
      expect(response.body).toHaveProperty('token');
      expect(response.body.user).toMatchObject({
        email: 'testuser@example.com',
        name: 'Test User',
      });
    });

    it('should return 400 when email is missing', async () => {
      const response = await request(app).post('/api/v1/auth/login').send({
        password: 'password123',
      });

      expect(response.status).toBe(400);
      expect(response.body.error).toMatch(/email.*invalid.*input|required/i);
    });

    it('should return 401 when user not found', async () => {
      const response = await request(app).post('/api/v1/auth/login').send({
        email: 'nonexistent@example.com',
        password: 'password123',
      });

      expect(response.status).toBe(401);
      expect(response.body.error).toMatch(/invalid credentials/i);
    });

    it('should return 401 when password is invalid', async () => {
      const response = await request(app).post('/api/v1/auth/login').send({
        email: 'testuser@example.com',
        password: 'wrongpassword',
      });

      expect(response.status).toBe(401);
      expect(response.body.error).toMatch(/invalid credentials/i);
    });
  });

  describe('GET /api/v1/auth/me', () => {
    let token: string;

    beforeEach(async () => {
      const user = await User.create({
        email: 'testuser@example.com',
        password: 'password123',
        name: 'Test User',
      });

      const response = await request(app).post('/api/v1/auth/login').send({
        email: 'testuser@example.com',
        password: 'password123',
      });

      token = response.body.token;
    });

    it('should return current user when authenticated', async () => {
      const response = await request(app)
        .get('/api/v1/auth/me')
        .set('Authorization', `Bearer ${token}`);

      expect(response.status).toBe(200);
      expect(response.body).toMatchObject({
        email: 'testuser@example.com',
        name: 'Test User',
        role: 'user',
      });
    });

    it('should return 401 without token', async () => {
      const response = await request(app).get('/api/v1/auth/me');

      expect(response.status).toBe(401);
      expect(response.body.error).toMatch(/authentication required/i);
    });

    it('should return 401 with invalid token', async () => {
      const response = await request(app)
        .get('/api/v1/auth/me')
        .set('Authorization', 'Bearer invalid.token.here');

      expect(response.status).toBe(401);
      expect(response.body.error).toMatch(/invalid.*token/i);
    });
  });
});
