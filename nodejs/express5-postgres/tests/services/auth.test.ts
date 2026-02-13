import { describe, it, expect, vi, beforeEach } from 'vitest';

const mockSpan = {
  setAttribute: vi.fn(),
  setStatus: vi.fn(),
  recordException: vi.fn(),
  end: vi.fn(),
};

vi.mock('@opentelemetry/api', () => ({
  trace: {
    getTracer: () => ({
      startActiveSpan: (_name: string, fn: (span: typeof mockSpan) => unknown) => fn(mockSpan),
    }),
  },
  metrics: {
    getMeter: () => ({
      createCounter: () => ({ add: vi.fn() }),
    }),
  },
  SpanStatusCode: { OK: 1, ERROR: 2 },
}));

const mockFindFirst = vi.fn();
const mockReturning = vi.fn();
const mockValues = vi.fn(() => ({ returning: mockReturning }));
const mockInsert = vi.fn(() => ({ values: mockValues }));

vi.mock('../../src/db/index.js', () => ({
  db: {
    query: { users: { findFirst: (...args: unknown[]) => mockFindFirst(...args) } },
    insert: (...args: unknown[]) => mockInsert(...args),
  },
}));

vi.mock('../../src/db/schema.js', () => ({
  users: { email: 'email', id: 'id' },
}));

const mockHash = vi.fn();
const mockCompare = vi.fn();
vi.mock('bcrypt', () => ({ default: { hash: mockHash, compare: mockCompare } }));

const mockSign = vi.fn();
const mockVerify = vi.fn();
vi.mock('jsonwebtoken', () => ({ default: { sign: mockSign, verify: mockVerify } }));

vi.mock('../../src/logger.js', () => ({
  logger: { info: vi.fn(), error: vi.fn(), warn: vi.fn() },
}));

const { AuthService } = await import('../../src/services/auth.js');

describe('AuthService', () => {
  let service: InstanceType<typeof AuthService>;

  beforeEach(() => {
    vi.clearAllMocks();
    process.env.JWT_SECRET = 'test-secret';
    process.env.JWT_EXPIRES_IN = '7d';
    service = new AuthService();
  });

  describe('register', () => {
    it('hashes password, inserts user, and returns user + token', async () => {
      mockFindFirst.mockResolvedValue(undefined);
      mockHash.mockResolvedValue('hashed-pw');
      const user = { id: 1, email: 'a@b.com', name: 'A', passwordHash: 'hashed-pw' };
      mockReturning.mockResolvedValue([user]);
      mockSign.mockReturnValue('jwt-token');

      const result = await service.register('a@b.com', 'password123', 'A');

      expect(mockHash).toHaveBeenCalledWith('password123', 12);
      expect(mockValues).toHaveBeenCalledWith({ email: 'a@b.com', passwordHash: 'hashed-pw', name: 'A' });
      expect(result.user).toEqual(user);
      expect(result.token).toBe('jwt-token');
    });

    it('throws 409 when email already exists', async () => {
      mockFindFirst.mockResolvedValue({ id: 1, email: 'a@b.com' });

      await expect(service.register('a@b.com', 'password123', 'A')).rejects.toThrow('Email already registered');

      try {
        await service.register('a@b.com', 'password123', 'A');
      } catch (e: unknown) {
        expect((e as { statusCode: number }).statusCode).toBe(409);
      }
    });
  });

  describe('login', () => {
    it('returns user and token on valid credentials', async () => {
      const user = { id: 1, email: 'a@b.com', name: 'A', passwordHash: 'hashed-pw' };
      mockFindFirst.mockResolvedValue(user);
      mockCompare.mockResolvedValue(true);
      mockSign.mockReturnValue('jwt-token');

      const result = await service.login('a@b.com', 'password123');

      expect(mockCompare).toHaveBeenCalledWith('password123', 'hashed-pw');
      expect(result.user).toEqual(user);
      expect(result.token).toBe('jwt-token');
    });

    it('throws 401 when user not found', async () => {
      mockFindFirst.mockResolvedValue(undefined);

      await expect(service.login('a@b.com', 'pass')).rejects.toThrow('Invalid credentials');

      try {
        await service.login('a@b.com', 'pass');
      } catch (e: unknown) {
        expect((e as { statusCode: number }).statusCode).toBe(401);
      }
    });

    it('throws 401 when password is wrong', async () => {
      mockFindFirst.mockResolvedValue({ id: 1, email: 'a@b.com', passwordHash: 'hashed-pw' });
      mockCompare.mockResolvedValue(false);

      await expect(service.login('a@b.com', 'wrong')).rejects.toThrow('Invalid credentials');
    });
  });

  describe('getUserById', () => {
    it('returns user when found', async () => {
      const user = { id: 1, email: 'a@b.com', name: 'A' };
      mockFindFirst.mockResolvedValue(user);

      const result = await service.getUserById(1);
      expect(result).toEqual(user);
    });

    it('returns null when not found', async () => {
      mockFindFirst.mockResolvedValue(undefined);

      const result = await service.getUserById(999);
      expect(result).toBeNull();
    });
  });

  describe('verifyToken', () => {
    it('returns decoded payload for valid token', () => {
      const payload = { userId: 1, email: 'a@b.com' };
      mockVerify.mockReturnValue(payload);

      expect(service.verifyToken('valid-token')).toEqual(payload);
      expect(mockVerify).toHaveBeenCalledWith('valid-token', 'test-secret');
    });

    it('propagates error for invalid token', () => {
      mockVerify.mockImplementation(() => { throw new Error('jwt malformed'); });

      expect(() => service.verifyToken('bad')).toThrow('jwt malformed');
    });
  });

  describe('generateToken (via register)', () => {
    it('signs with userId and email', async () => {
      mockFindFirst.mockResolvedValue(undefined);
      mockHash.mockResolvedValue('hashed');
      const user = { id: 42, email: 'u@e.com', name: 'U', passwordHash: 'hashed' };
      mockReturning.mockResolvedValue([user]);
      mockSign.mockReturnValue('tok');

      await service.register('u@e.com', 'password123', 'U');

      expect(mockSign).toHaveBeenCalledWith(
        { userId: 42, email: 'u@e.com' },
        'test-secret',
        { expiresIn: '7d' },
      );
    });
  });
});
