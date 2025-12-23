/* eslint-disable @typescript-eslint/no-unsafe-assignment, @typescript-eslint/no-unsafe-member-access, @typescript-eslint/no-unsafe-argument */
import request from 'supertest';
import { INestApplication } from '@nestjs/common';

export interface TestUser {
  id: string;
  email: string;
  name: string;
  token: string;
}

export async function createTestUser(
  app: INestApplication,
  userData: { email: string; password: string; name: string },
): Promise<TestUser> {
  const response = await request(app.getHttpServer())
    .post('/api/auth/register')
    .send(userData);

  if (response.status !== 201 || !response.body.user) {
    throw new Error(
      `Failed to create test user: ${response.status} - ${JSON.stringify(response.body)}`,
    );
  }

  return {
    id: response.body.user.id,
    email: response.body.user.email,
    name: response.body.user.name,
    token: response.body.token,
  };
}

export async function loginTestUser(
  app: INestApplication,
  credentials: { email: string; password: string },
): Promise<TestUser> {
  const response = await request(app.getHttpServer())
    .post('/api/auth/login')
    .send(credentials);

  return {
    id: response.body.user.id,
    email: response.body.user.email,
    name: response.body.user.name,
    token: response.body.token,
  };
}

export function authHeader(token: string): { Authorization: string } {
  return { Authorization: `Bearer ${token}` };
}
