import { describe, it, expect, vi, beforeEach } from 'vitest';

vi.mock('@/lib/config', () => ({
  config: {
    jwtSecret: 'test-secret-32-chars-long-enough!!',
    jwtExpiresIn: '7d',
  },
}));

const mockSign = vi.fn();
const mockVerify = vi.fn();
vi.mock('jsonwebtoken', () => ({ default: { sign: mockSign, verify: mockVerify } }));

const { signToken, verifyToken, extractToken, getUserFromRequest } = await import('@/lib/auth');

describe('auth utilities', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe('signToken', () => {
    it('calls jwt.sign with payload, secret, and expiresIn', () => {
      mockSign.mockReturnValue('signed-token');

      const result = signToken({ userId: 'abc', email: 'u@e.com' });

      expect(result).toBe('signed-token');
      expect(mockSign).toHaveBeenCalledWith(
        { userId: 'abc', email: 'u@e.com' },
        'test-secret-32-chars-long-enough!!',
        { expiresIn: '7d' },
      );
    });
  });

  describe('verifyToken', () => {
    it('returns decoded payload for valid token', () => {
      const payload = { userId: 'abc', email: 'u@e.com' };
      mockVerify.mockReturnValue(payload);

      expect(verifyToken('valid-token')).toEqual(payload);
    });

    it('throws AuthenticationError for invalid token', () => {
      mockVerify.mockImplementation(() => { throw new Error('jwt malformed'); });

      expect(() => verifyToken('bad')).toThrow('Invalid or expired token');
    });
  });

  describe('extractToken', () => {
    it('returns token from valid Bearer header', () => {
      const request = { headers: { get: vi.fn().mockReturnValue('Bearer my-token') } };

      expect(extractToken(request as never)).toBe('my-token');
    });

    it('returns null when no authorization header', () => {
      const request = { headers: { get: vi.fn().mockReturnValue(null) } };

      expect(extractToken(request as never)).toBeNull();
    });

    it('returns null for non-Bearer scheme', () => {
      const request = { headers: { get: vi.fn().mockReturnValue('Basic abc123') } };

      expect(extractToken(request as never)).toBeNull();
    });
  });

  describe('getUserFromRequest', () => {
    it('returns payload from valid token', () => {
      const payload = { userId: 'abc', email: 'u@e.com' };
      mockVerify.mockReturnValue(payload);
      const request = { headers: { get: vi.fn().mockReturnValue('Bearer valid') } };

      expect(getUserFromRequest(request as never)).toEqual(payload);
    });

    it('throws AuthenticationError when no token', () => {
      const request = { headers: { get: vi.fn().mockReturnValue(null) } };

      expect(() => getUserFromRequest(request as never)).toThrow('No token provided');
    });
  });
});
