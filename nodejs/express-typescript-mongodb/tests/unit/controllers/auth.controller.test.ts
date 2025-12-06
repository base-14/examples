import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import type { Request, Response, NextFunction } from 'express';
import { register, login, getCurrentUser } from '../../../src/controllers/auth.controller.js';
import { User } from '../../../src/models/User.js';
import { clearDatabase } from '../../helpers/db.helper.js';
import * as jwtUtils from '../../../src/utils/jwt.js';
import {
  ValidationError,
  AuthenticationError,
  ConflictError,
} from '../../../src/utils/errors.js';

vi.mock('../../../src/utils/jwt');

describe('Auth Controller', () => {
  let mockReq: Partial<Request>;
  let mockRes: Partial<Response>;
  let mockNext: NextFunction;

  beforeEach(async () => {
    await clearDatabase();

    mockReq = {
      body: {},
    };

    mockRes = {
      status: vi.fn().mockReturnThis(),
      json: vi.fn().mockReturnThis(),
    };

    mockNext = vi.fn();

    vi.spyOn(jwtUtils, 'generateToken').mockReturnValue('mock-jwt-token');

    vi.clearAllMocks();
  });

  afterEach(async () => {
    await clearDatabase();
  });

  describe('register', () => {
    it('should register user with valid data and return token', async () => {
      mockReq.body = {
        email: 'newuser@example.com',
        password: 'password123',
        name: 'New User',
      };

      await register(mockReq as Request, mockRes as Response, mockNext);

      expect(mockRes.status).toHaveBeenCalledWith(201);
      expect(mockRes.json).toHaveBeenCalledWith(
        expect.objectContaining({
          token: 'mock-jwt-token',
          user: expect.objectContaining({
            email: 'newuser@example.com',
            name: 'New User',
            role: 'user',
          }),
        })
      );

      const user = await User.findOne({ email: 'newuser@example.com' });
      expect(user).toBeDefined();
      expect(user?.name).toBe('New User');
    });

    it('should call next with ConflictError when email already exists', async () => {
      await User.create({
        email: 'existing@example.com',
        password: 'password123',
        name: 'Existing User',
      });

      mockReq.body = {
        email: 'existing@example.com',
        password: 'newpassword',
        name: 'New User',
      };

      await register(mockReq as Request, mockRes as Response, mockNext);

      expect(mockNext).toHaveBeenCalledWith(expect.any(ConflictError));
      const error = (mockNext as ReturnType<typeof vi.fn>).mock.calls[0]?.[0] as ConflictError;
      expect(error.statusCode).toBe(409);
    });

    it('should hash password before saving', async () => {
      const plainPassword = 'password123';
      mockReq.body = {
        email: 'newuser@example.com',
        password: plainPassword,
        name: 'New User',
      };

      await register(mockReq as Request, mockRes as Response, mockNext);

      const user = await User.findOne({ email: 'newuser@example.com' });
      expect(user?.password).not.toBe(plainPassword);
      expect(user?.password).toMatch(/^\$2[ayb]\$.{56}$/);
    });

    it('should generate JWT token with correct payload', async () => {
      mockReq.body = {
        email: 'newuser@example.com',
        password: 'password123',
        name: 'New User',
      };

      await register(mockReq as Request, mockRes as Response, mockNext);

      expect(jwtUtils.generateToken).toHaveBeenCalledWith(
        expect.objectContaining({
          email: 'newuser@example.com',
          role: 'user',
          userId: expect.any(String),
        })
      );
    });

    it('should call next with error when database error occurs', async () => {
      const dbError = new Error('Database connection failed');

      vi.spyOn(User, 'create').mockRejectedValueOnce(dbError);

      mockReq.body = {
        email: 'newuser@example.com',
        password: 'password123',
        name: 'New User',
      };

      await register(mockReq as Request, mockRes as Response, mockNext);

      expect(mockNext).toHaveBeenCalledWith(dbError);
    });
  });

  describe('login', () => {
    beforeEach(async () => {
      await User.create({
        email: 'testuser@example.com',
        password: 'password123',
        name: 'Test User',
      });
    });

    it('should login with valid credentials and return token', async () => {
      mockReq.body = {
        email: 'testuser@example.com',
        password: 'password123',
      };

      await login(mockReq as Request, mockRes as Response, mockNext);

      expect(mockRes.json).toHaveBeenCalledWith(
        expect.objectContaining({
          token: 'mock-jwt-token',
          user: expect.objectContaining({
            email: 'testuser@example.com',
            name: 'Test User',
            role: 'user',
          }),
        })
      );
      expect(mockRes.status).not.toHaveBeenCalled();
    });

    it('should call next with AuthenticationError when user is not found', async () => {
      mockReq.body = {
        email: 'nonexistent@example.com',
        password: 'password123',
      };

      await login(mockReq as Request, mockRes as Response, mockNext);

      expect(mockNext).toHaveBeenCalledWith(expect.any(AuthenticationError));
      const error = (mockNext as ReturnType<typeof vi.fn>).mock.calls[0]?.[0] as AuthenticationError;
      expect(error.statusCode).toBe(401);
    });

    it('should call next with AuthenticationError when password is invalid', async () => {
      mockReq.body = {
        email: 'testuser@example.com',
        password: 'wrongpassword',
      };

      await login(mockReq as Request, mockRes as Response, mockNext);

      expect(mockNext).toHaveBeenCalledWith(expect.any(AuthenticationError));
    });

    it('should generate JWT token on successful login', async () => {
      mockReq.body = {
        email: 'testuser@example.com',
        password: 'password123',
      };

      await login(mockReq as Request, mockRes as Response, mockNext);

      expect(jwtUtils.generateToken).toHaveBeenCalledWith(
        expect.objectContaining({
          email: 'testuser@example.com',
          role: 'user',
          userId: expect.any(String),
        })
      );
    });

    it('should call next with error when database error occurs', async () => {
      const dbError = new Error('Database connection failed');

      vi.spyOn(User, 'findOne').mockRejectedValueOnce(dbError);

      mockReq.body = {
        email: 'testuser@example.com',
        password: 'password123',
      };

      await login(mockReq as Request, mockRes as Response, mockNext);

      expect(mockNext).toHaveBeenCalledWith(dbError);
    });
  });

  describe('getCurrentUser', () => {
    it('should return current user when authenticated', async () => {
      const mockUser = {
        _id: 'user-123',
        email: 'test@example.com',
        name: 'Test User',
        role: 'user',
      };

      mockReq.user = mockUser as any;

      await getCurrentUser(mockReq as Request, mockRes as Response, mockNext);

      expect(mockRes.json).toHaveBeenCalledWith({
        id: 'user-123',
        email: 'test@example.com',
        name: 'Test User',
        role: 'user',
      });
      expect(mockRes.status).not.toHaveBeenCalled();
    });

    it('should call next with AuthenticationError when user is not authenticated', async () => {
      await getCurrentUser(mockReq as Request, mockRes as Response, mockNext);

      expect(mockNext).toHaveBeenCalledWith(expect.any(AuthenticationError));
    });

    it('should call next with error when unexpected error occurs', async () => {
      const unexpectedError = new Error('Unexpected error');

      mockReq.user = {
        _id: {
          toString: () => {
            throw unexpectedError;
          },
        },
        email: 'test@example.com',
        name: 'Test User',
        role: 'user',
      } as any;

      await getCurrentUser(mockReq as Request, mockRes as Response, mockNext);

      expect(mockNext).toHaveBeenCalledWith(unexpectedError);
    });
  });

  describe('User Roles', () => {
    it.each([
      { role: 'user', expected: 'user' },
      { role: 'admin', expected: 'admin' },
    ])('should register user with $role role', async ({ role }) => {
      mockReq.body = {
        email: `${role}@example.com`,
        password: 'password123',
        name: `${role} User`,
      };

      await register(mockReq as Request, mockRes as Response, mockNext);

      expect(mockRes.json).toHaveBeenCalledWith(
        expect.objectContaining({
          user: expect.objectContaining({
            role: 'user',
          }),
        })
      );
    });
  });
});
