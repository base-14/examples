import { NextRequest, NextResponse } from 'next/server';
import jwt from 'jsonwebtoken';
import { config } from './config';
import { AuthenticationError } from './errors';
import type { JwtPayload, ApiResponse } from '@/types';

export function signToken(payload: Omit<JwtPayload, 'iat' | 'exp'>): string {
  return jwt.sign(payload, config.jwtSecret, {
    expiresIn: config.jwtExpiresIn as `${number}d`,
  });
}

export function verifyToken(token: string): JwtPayload {
  try {
    return jwt.verify(token, config.jwtSecret) as JwtPayload;
  } catch {
    throw new AuthenticationError('Invalid or expired token');
  }
}

export function extractToken(request: NextRequest): string | null {
  const authHeader = request.headers.get('authorization');
  if (authHeader?.startsWith('Bearer ')) {
    return authHeader.slice(7);
  }
  return null;
}

export function getUserFromRequest(request: NextRequest): JwtPayload {
  const token = extractToken(request);
  if (!token) {
    throw new AuthenticationError('No token provided');
  }
  return verifyToken(token);
}

export type AuthenticatedHandler<T = unknown> = (
  request: NextRequest,
  user: JwtPayload,
  context?: { params: Promise<Record<string, string>> }
) => Promise<NextResponse<ApiResponse<T>>>;

export function withAuth<T = unknown>(
  handler: AuthenticatedHandler<T>
): (
  request: NextRequest,
  context?: { params: Promise<Record<string, string>> }
) => Promise<NextResponse<ApiResponse<T>>> {
  return async (request, context) => {
    try {
      const user = getUserFromRequest(request);
      return await handler(request, user, context);
    } catch (error) {
      if (error instanceof AuthenticationError) {
        return NextResponse.json(
          { success: false, error: error.message },
          { status: error.statusCode }
        );
      }
      return NextResponse.json(
        { success: false, error: 'Authentication failed' },
        { status: 401 }
      );
    }
  };
}

export function optionalAuth<T = unknown>(
  handler: (
    request: NextRequest,
    user: JwtPayload | null,
    context?: { params: Promise<Record<string, string>> }
  ) => Promise<NextResponse<ApiResponse<T>>>
): (
  request: NextRequest,
  context?: { params: Promise<Record<string, string>> }
) => Promise<NextResponse<ApiResponse<T>>> {
  return async (request, context) => {
    let user: JwtPayload | null = null;
    try {
      const token = extractToken(request);
      if (token) {
        user = verifyToken(token);
      }
    } catch {
      // Token invalid, continue without auth
    }
    return handler(request, user, context);
  };
}
