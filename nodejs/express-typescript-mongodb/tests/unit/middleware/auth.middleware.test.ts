import { describe, it, expect, beforeEach, vi } from 'vitest';
import type { Request, Response, NextFunction } from 'express';
import { authenticate } from '../../../src/middleware/auth.middleware';
import { User } from '../../../src/models/User';
import * as jwtUtils from '../../../src/utils/jwt';
import { trace, type Span } from '@opentelemetry/api';

// Mock dependencies
vi.mock('../../../src/models/User');
vi.mock('../../../src/utils/jwt');

describe('Auth Middleware', () => {
  let mockReq: Partial<Request>;
  let mockRes: Partial<Response>;
  let mockNext: NextFunction;
  let mockSpan: Partial<Span>;

  beforeEach(() => {
    // Mock request
    mockReq = {
      headers: {},
    };

    // Mock response
    mockRes = {
      status: vi.fn().mockReturnThis(),
      json: vi.fn().mockReturnThis(),
    };

    // Mock next function
    mockNext = vi.fn();

    // Mock OpenTelemetry span
    mockSpan = {
      addEvent: vi.fn(),
      setAttributes: vi.fn(),
      recordException: vi.fn(),
      setStatus: vi.fn(),
    };

    // Setup default span mock
    vi.spyOn(trace, 'getActiveSpan').mockReturnValue(mockSpan as Span);

    // Clear all mocks
    vi.clearAllMocks();
  });

  describe('Missing or Invalid Authorization Header', () => {
    it('should return 401 when Authorization header is missing', async () => {
      await authenticate(mockReq as Request, mockRes as Response, mockNext);

      expect(mockRes.status).toHaveBeenCalledWith(401);
      expect(mockRes.json).toHaveBeenCalledWith({ error: 'Authentication required' });
      expect(mockNext).not.toHaveBeenCalled();
      expect(mockSpan.addEvent).toHaveBeenCalledWith('auth_failed', { reason: 'missing_token' });
    });

    it('should return 401 when Authorization header is malformed (no Bearer)', async () => {
      mockReq.headers = { authorization: 'InvalidToken123' };

      await authenticate(mockReq as Request, mockRes as Response, mockNext);

      expect(mockRes.status).toHaveBeenCalledWith(401);
      expect(mockRes.json).toHaveBeenCalledWith({ error: 'Authentication required' });
      expect(mockNext).not.toHaveBeenCalled();
      expect(mockSpan.addEvent).toHaveBeenCalledWith('auth_failed', { reason: 'missing_token' });
    });

    it('should return 401 when Authorization header has Bearer but no token', async () => {
      mockReq.headers = { authorization: 'Bearer ' };

      vi.spyOn(jwtUtils, 'verifyToken').mockImplementation(() => {
        throw new Error('jwt malformed');
      });

      await authenticate(mockReq as Request, mockRes as Response, mockNext);

      expect(mockRes.status).toHaveBeenCalledWith(401);
      expect(mockRes.json).toHaveBeenCalledWith({ error: 'Invalid or expired token' });
      expect(mockNext).not.toHaveBeenCalled();
    });
  });

  describe('Invalid or Expired Token', () => {
    it('should return 401 when token is invalid', async () => {
      mockReq.headers = { authorization: 'Bearer invalid.token.here' };

      vi.spyOn(jwtUtils, 'verifyToken').mockImplementation(() => {
        throw new Error('jwt malformed');
      });

      await authenticate(mockReq as Request, mockRes as Response, mockNext);

      expect(mockRes.status).toHaveBeenCalledWith(401);
      expect(mockRes.json).toHaveBeenCalledWith({ error: 'Invalid or expired token' });
      expect(mockNext).not.toHaveBeenCalled();
      expect(mockSpan.addEvent).toHaveBeenCalledWith('auth_failed', { reason: 'invalid_token' });
    });

    it('should return 401 when token is expired', async () => {
      mockReq.headers = { authorization: 'Bearer expired.token.here' };

      vi.spyOn(jwtUtils, 'verifyToken').mockImplementation(() => {
        throw new Error('jwt expired');
      });

      await authenticate(mockReq as Request, mockRes as Response, mockNext);

      expect(mockRes.status).toHaveBeenCalledWith(401);
      expect(mockRes.json).toHaveBeenCalledWith({ error: 'Invalid or expired token' });
      expect(mockNext).not.toHaveBeenCalled();
      expect(mockSpan.addEvent).toHaveBeenCalledWith('auth_failed', { reason: 'invalid_token' });
    });
  });

  describe('User Not Found', () => {
    it('should return 401 when user is not found in database', async () => {
      mockReq.headers = { authorization: 'Bearer valid.token.here' };

      vi.spyOn(jwtUtils, 'verifyToken').mockReturnValue({
        userId: 'nonexistent-user-id',
        email: 'test@example.com',
        role: 'user',
      });

      vi.mocked(User.findById).mockResolvedValue(null);

      await authenticate(mockReq as Request, mockRes as Response, mockNext);

      expect(mockRes.status).toHaveBeenCalledWith(401);
      expect(mockRes.json).toHaveBeenCalledWith({ error: 'User not found' });
      expect(mockNext).not.toHaveBeenCalled();
      expect(mockSpan.addEvent).toHaveBeenCalledWith('auth_failed', { reason: 'user_not_found' });
    });
  });

  describe('Successful Authentication', () => {
    it('should authenticate valid token and attach user to request', async () => {
      const mockUser = {
        _id: 'user-123',
        email: 'test@example.com',
        name: 'Test User',
        role: 'user',
        comparePassword: vi.fn(),
      };

      mockReq.headers = { authorization: 'Bearer valid.token.here' };

      vi.spyOn(jwtUtils, 'verifyToken').mockReturnValue({
        userId: 'user-123',
        email: 'test@example.com',
        role: 'user',
      });

      vi.mocked(User.findById).mockResolvedValue(mockUser as never);

      await authenticate(mockReq as Request, mockRes as Response, mockNext);

      expect(mockReq.user).toEqual(mockUser);
      expect(mockNext).toHaveBeenCalled();
      expect(mockRes.status).not.toHaveBeenCalled();
      expect(mockRes.json).not.toHaveBeenCalled();
    });

    it('should set OpenTelemetry span attributes on success', async () => {
      const mockUser = {
        _id: 'user-123',
        email: 'test@example.com',
        name: 'Test User',
        role: 'user',
        comparePassword: vi.fn(),
      };

      mockReq.headers = { authorization: 'Bearer valid.token.here' };

      vi.spyOn(jwtUtils, 'verifyToken').mockReturnValue({
        userId: 'user-123',
        email: 'test@example.com',
        role: 'user',
      });

      vi.mocked(User.findById).mockResolvedValue(mockUser as never);

      await authenticate(mockReq as Request, mockRes as Response, mockNext);

      expect(mockSpan.setAttributes).toHaveBeenCalledWith({
        'user.id': 'user-123',
        'user.email': 'test@example.com',
        'user.role': 'user',
      });
    });

    it('should work when no active span exists', async () => {
      vi.spyOn(trace, 'getActiveSpan').mockReturnValue(undefined);

      const mockUser = {
        _id: 'user-123',
        email: 'test@example.com',
        name: 'Test User',
        role: 'user',
        comparePassword: vi.fn(),
      };

      mockReq.headers = { authorization: 'Bearer valid.token.here' };

      vi.spyOn(jwtUtils, 'verifyToken').mockReturnValue({
        userId: 'user-123',
        email: 'test@example.com',
        role: 'user',
      });

      vi.mocked(User.findById).mockResolvedValue(mockUser as never);

      await authenticate(mockReq as Request, mockRes as Response, mockNext);

      expect(mockReq.user).toEqual(mockUser);
      expect(mockNext).toHaveBeenCalled();
    });
  });

  describe('Error Handling', () => {
    it('should call next with error when unexpected error occurs', async () => {
      const mockError = new Error('Database connection failed');

      mockReq.headers = { authorization: 'Bearer valid.token.here' };

      vi.spyOn(jwtUtils, 'verifyToken').mockReturnValue({
        userId: 'user-123',
        email: 'test@example.com',
        role: 'user',
      });

      vi.mocked(User.findById).mockRejectedValue(mockError);

      await authenticate(mockReq as Request, mockRes as Response, mockNext);

      expect(mockNext).toHaveBeenCalledWith(mockError);
      expect(mockSpan.recordException).toHaveBeenCalledWith(mockError);
      expect(mockSpan.setStatus).toHaveBeenCalledWith({
        code: 2, // SpanStatusCode.ERROR
        message: 'Database connection failed',
      });
    });
  });

  describe('User Roles', () => {
    it.each([
      { role: 'user', expected: 'user' },
      { role: 'admin', expected: 'admin' },
    ])('should authenticate user with $role role', async ({ role, expected }) => {
      const mockUser = {
        _id: 'user-123',
        email: 'test@example.com',
        name: 'Test User',
        role,
        comparePassword: vi.fn(),
      };

      mockReq.headers = { authorization: 'Bearer valid.token.here' };

      vi.spyOn(jwtUtils, 'verifyToken').mockReturnValue({
        userId: 'user-123',
        email: 'test@example.com',
        role,
      });

      vi.mocked(User.findById).mockResolvedValue(mockUser as never);

      await authenticate(mockReq as Request, mockRes as Response, mockNext);

      expect(mockReq.user).toEqual(mockUser);
      expect(mockSpan.setAttributes).toHaveBeenCalledWith(
        expect.objectContaining({
          'user.role': expected,
        })
      );
    });
  });
});
