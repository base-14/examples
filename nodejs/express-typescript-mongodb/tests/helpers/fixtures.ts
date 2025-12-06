import { Types } from 'mongoose';

export const mockUserId = new Types.ObjectId();
export const mockArticleId = new Types.ObjectId();

export const mockUserData = {
  email: 'test@example.com',
  password: 'password123',
  name: 'Test User',
  role: 'user' as const,
};

export const mockArticleData = {
  title: 'Test Article',
  content: 'This is test content for the article',
  tags: ['test', 'vitest'],
  author: mockUserId,
  published: false,
  viewCount: 0,
};

export const mockJWTPayload = {
  userId: mockUserId.toString(),
  email: 'test@example.com',
  role: 'user',
};
