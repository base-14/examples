import { describe, it, expect } from 'vitest';
import {
  AppError,
  ValidationError,
  AuthenticationError,
  AuthorizationError,
  NotFoundError,
  ConflictError,
} from '@/lib/errors';

describe('error classes', () => {
  describe('AppError', () => {
    it('sets statusCode, message, and isOperational', () => {
      const err = new AppError('something broke', 500);
      expect(err.message).toBe('something broke');
      expect(err.statusCode).toBe(500);
      expect(err.isOperational).toBe(true);
      expect(err).toBeInstanceOf(Error);
    });
  });

  describe('ValidationError', () => {
    it('defaults to 400 with details array', () => {
      const err = new ValidationError('bad input', ['field required']);
      expect(err.statusCode).toBe(400);
      expect(err.details).toEqual(['field required']);
      expect(err).toBeInstanceOf(AppError);
    });
  });

  describe('AuthenticationError', () => {
    it('defaults to 401 with default message', () => {
      const err = new AuthenticationError();
      expect(err.statusCode).toBe(401);
      expect(err.message).toBe('Authentication required');
    });
  });

  describe('AuthorizationError', () => {
    it('defaults to 403 with default message', () => {
      const err = new AuthorizationError();
      expect(err.statusCode).toBe(403);
      expect(err.message).toBe('Access denied');
    });
  });

  describe('NotFoundError', () => {
    it('formats resource name into message with 404', () => {
      const err = new NotFoundError('Article');
      expect(err.statusCode).toBe(404);
      expect(err.message).toBe('Article not found');
    });
  });

  describe('ConflictError', () => {
    it('defaults to 409 and preserves instanceof chain', () => {
      const err = new ConflictError();
      expect(err.statusCode).toBe(409);
      expect(err.message).toBe('Resource already exists');
      expect(err).toBeInstanceOf(AppError);
      expect(err).toBeInstanceOf(Error);
    });
  });
});
