import type { User } from '../db/schema.js';

declare global {
  namespace Express {
    interface Request {
      user?: User;
    }
  }
}

export interface JwtPayload {
  userId: number;
  email: string;
  iat?: number;
  exp?: number;
}

export interface ApiError extends Error {
  statusCode: number;
  traceId?: string;
}

export interface PaginationParams {
  page: number;
  perPage: number;
}

export interface PaginatedResponse<T> {
  data: T[];
  total: number;
  page: number;
  perPage: number;
}
