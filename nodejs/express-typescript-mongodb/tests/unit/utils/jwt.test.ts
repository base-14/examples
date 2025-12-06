import { describe, it, expect } from 'vitest';
import { generateToken, verifyToken } from '../../../src/utils/jwt';

describe('JWT Utils', () => {
  describe.concurrent('generateToken', () => {
    it('should generate valid JWT with correct payload', () => {
      const payload = {
        userId: 'user-123',
        email: 'test@example.com',
        role: 'user',
      };

      const token = generateToken(payload);

      expect(token).toBeDefined();
      expect(typeof token).toBe('string');
      expect(token.split('.')).toHaveLength(3);
    });

    it.each([
      { userId: '1', email: 'user1@test.com', role: 'user' },
      { userId: '2', email: 'admin@test.com', role: 'admin' },
    ])('should generate token for payload: $userId', (payload) => {
      const token = generateToken(payload);
      const decoded = verifyToken(token);

      expect(decoded).toMatchObject(payload);
    });
  });

  describe('verifyToken', () => {
    it('should verify and decode valid token', () => {
      const payload = {
        userId: 'user-123',
        email: 'test@example.com',
        role: 'user',
      };

      const token = generateToken(payload);
      const decoded = verifyToken(token);

      expect(decoded).toMatchObject(payload);
      expect(decoded).toHaveProperty('userId', payload.userId);
    });

    it('should throw on invalid token', () => {
      expect(() => verifyToken('invalid-token')).toThrow(/jwt malformed|invalid token/i);
    });

    it('should throw on malformed token', () => {
      expect(() => verifyToken('not.a.token')).toThrow();
    });
  });
});
