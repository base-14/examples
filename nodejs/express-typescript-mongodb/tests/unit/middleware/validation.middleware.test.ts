import { describe, it, expect, vi, beforeEach } from 'vitest';
import type { Request, Response, NextFunction } from 'express';
import { validateBody, validateQuery } from '../../../src/middleware/validation.middleware';
import {
  registerInputSchema,
  loginInputSchema,
  articleInputSchema,
  paginationSchema,
} from '../../../src/validation/zod-schemas';
import { ValidationError } from '../../../src/utils/errors';

describe('Validation Middleware', () => {
  let mockReq: Partial<Request>;
  let mockRes: Partial<Response>;
  let mockNext: NextFunction;

  beforeEach(() => {
    mockReq = {
      body: {},
      query: {},
    };
    mockRes = {};
    mockNext = vi.fn();
  });

  describe('validateBody', () => {
    describe('registerInputSchema', () => {
      it('should pass validation with valid register data', () => {
        mockReq.body = {
          email: 'test@example.com',
          password: 'password123',
          name: 'Test User',
        };

        const middleware = validateBody(registerInputSchema);
        middleware(mockReq as Request, mockRes as Response, mockNext);

        expect(mockNext).toHaveBeenCalledWith();
        expect(mockReq.body).toEqual({
          email: 'test@example.com',
          password: 'password123',
          name: 'Test User',
        });
      });

      it('should call next with ValidationError when email is missing', () => {
        mockReq.body = {
          password: 'password123',
          name: 'Test User',
        };

        const middleware = validateBody(registerInputSchema);
        middleware(mockReq as Request, mockRes as Response, mockNext);

        expect(mockNext).toHaveBeenCalledWith(expect.any(ValidationError));
        const error = (mockNext as ReturnType<typeof vi.fn>).mock.calls[0]?.[0] as ValidationError;
        expect(error.message).toMatch(/email/i);
        expect(error.statusCode).toBe(400);
      });

      it('should call next with ValidationError when password is missing', () => {
        mockReq.body = {
          email: 'test@example.com',
          name: 'Test User',
        };

        const middleware = validateBody(registerInputSchema);
        middleware(mockReq as Request, mockRes as Response, mockNext);

        expect(mockNext).toHaveBeenCalledWith(expect.any(ValidationError));
        const error = (mockNext as ReturnType<typeof vi.fn>).mock.calls[0]?.[0] as ValidationError;
        expect(error.message).toMatch(/password/i);
      });

      it('should call next with ValidationError when name is missing', () => {
        mockReq.body = {
          email: 'test@example.com',
          password: 'password123',
        };

        const middleware = validateBody(registerInputSchema);
        middleware(mockReq as Request, mockRes as Response, mockNext);

        expect(mockNext).toHaveBeenCalledWith(expect.any(ValidationError));
        const error = (mockNext as ReturnType<typeof vi.fn>).mock.calls[0]?.[0] as ValidationError;
        expect(error.message).toMatch(/name/i);
      });

      it('should call next with ValidationError when password is too short', () => {
        mockReq.body = {
          email: 'test@example.com',
          password: '1234567',
          name: 'Test User',
        };

        const middleware = validateBody(registerInputSchema);
        middleware(mockReq as Request, mockRes as Response, mockNext);

        expect(mockNext).toHaveBeenCalledWith(expect.any(ValidationError));
        const error = (mockNext as ReturnType<typeof vi.fn>).mock.calls[0]?.[0] as ValidationError;
        expect(error.message).toMatch(/(8|password)/i);
      });
    });

    describe('loginInputSchema', () => {
      it('should pass validation with valid login data', () => {
        mockReq.body = {
          email: 'test@example.com',
          password: 'password123',
        };

        const middleware = validateBody(loginInputSchema);
        middleware(mockReq as Request, mockRes as Response, mockNext);

        expect(mockNext).toHaveBeenCalledWith();
      });

      it('should call next with ValidationError when email is missing', () => {
        mockReq.body = {
          password: 'password123',
        };

        const middleware = validateBody(loginInputSchema);
        middleware(mockReq as Request, mockRes as Response, mockNext);

        expect(mockNext).toHaveBeenCalledWith(expect.any(ValidationError));
        const error = (mockNext as ReturnType<typeof vi.fn>).mock.calls[0]?.[0] as ValidationError;
        expect(error.message).toMatch(/email/i);
      });

      it('should call next with ValidationError when password is missing', () => {
        mockReq.body = {
          email: 'test@example.com',
        };

        const middleware = validateBody(loginInputSchema);
        middleware(mockReq as Request, mockRes as Response, mockNext);

        expect(mockNext).toHaveBeenCalledWith(expect.any(ValidationError));
        const error = (mockNext as ReturnType<typeof vi.fn>).mock.calls[0]?.[0] as ValidationError;
        expect(error.message).toMatch(/password/i);
      });
    });

    describe('articleInputSchema', () => {
      it('should pass validation with valid article data', () => {
        mockReq.body = {
          title: 'Test Article',
          content: 'Test content',
          tags: ['test', 'example'],
        };

        const middleware = validateBody(articleInputSchema);
        middleware(mockReq as Request, mockRes as Response, mockNext);

        expect(mockNext).toHaveBeenCalledWith();
      });

      it('should call next with ValidationError when title is missing', () => {
        mockReq.body = {
          content: 'Test content',
        };

        const middleware = validateBody(articleInputSchema);
        middleware(mockReq as Request, mockRes as Response, mockNext);

        expect(mockNext).toHaveBeenCalledWith(expect.any(ValidationError));
        const error = (mockNext as ReturnType<typeof vi.fn>).mock.calls[0]?.[0] as ValidationError;
        expect(error.message).toMatch(/title/i);
      });

      it('should call next with ValidationError when content is missing', () => {
        mockReq.body = {
          title: 'Test Article',
        };

        const middleware = validateBody(articleInputSchema);
        middleware(mockReq as Request, mockRes as Response, mockNext);

        expect(mockNext).toHaveBeenCalledWith(expect.any(ValidationError));
        const error = (mockNext as ReturnType<typeof vi.fn>).mock.calls[0]?.[0] as ValidationError;
        expect(error.message).toMatch(/content/i);
      });
    });
  });

  describe('validateQuery', () => {
    describe('paginationSchema', () => {
      it('should apply defaults when no query params provided', () => {
        mockReq.query = {};

        const middleware = validateQuery(paginationSchema);
        middleware(mockReq as Request, mockRes as Response, mockNext);

        expect(mockNext).toHaveBeenCalledWith();
        expect(mockReq.query).toEqual({
          page: 1,
          limit: 10,
        });
      });

      it('should parse and validate query parameters', () => {
        mockReq.query = { page: '2', limit: '20' };

        const middleware = validateQuery(paginationSchema);
        middleware(mockReq as Request, mockRes as Response, mockNext);

        expect(mockNext).toHaveBeenCalledWith();
        expect(mockReq.query).toEqual({
          page: 2,
          limit: 20,
        });
      });

      it('should use defaults for partial query params', () => {
        mockReq.query = { page: '3' };

        const middleware = validateQuery(paginationSchema);
        middleware(mockReq as Request, mockRes as Response, mockNext);

        expect(mockNext).toHaveBeenCalledWith();
        expect(mockReq.query).toMatchObject({
          page: 3,
          limit: 10,
        });
      });
    });
  });
});
