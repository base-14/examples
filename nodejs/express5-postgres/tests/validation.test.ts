import { describe, it, expect } from 'vitest';
import { z } from 'zod';

const registerSchema = z.object({
  email: z.string().email(),
  password: z.string().min(8),
  name: z.string().min(1).max(255),
});

const createArticleSchema = z.object({
  title: z.string().min(1).max(255),
  description: z.string().optional(),
  body: z.string().min(1),
});

describe('Zod 4 validation schemas', () => {
  describe('registerSchema', () => {
    it('accepts valid input', () => {
      const result = registerSchema.safeParse({
        email: 'user@example.com',
        password: 'securepassword',
        name: 'Test User',
      });
      expect(result.success).toBe(true);
    });

    it('rejects invalid email', () => {
      const result = registerSchema.safeParse({
        email: 'not-an-email',
        password: 'securepassword',
        name: 'Test',
      });
      expect(result.success).toBe(false);
      if (!result.success) {
        expect(result.error.issues[0]?.message).toEqual(expect.any(String));
      }
    });

    it('rejects password shorter than 8 characters', () => {
      const result = registerSchema.safeParse({
        email: 'user@example.com',
        password: 'short',
        name: 'Test',
      });
      expect(result.success).toBe(false);
      if (!result.success) {
        expect(result.error.issues.length).toBeGreaterThan(0);
      }
    });
  });

  describe('createArticleSchema', () => {
    it('accepts valid input with optional description', () => {
      const result = createArticleSchema.safeParse({
        title: 'My Article',
        body: 'Article body content',
      });
      expect(result.success).toBe(true);
      if (result.success) {
        expect(result.data.description).toBeUndefined();
      }
    });
  });

  describe('z.coerce.number', () => {
    it('parses string to number (used in config)', () => {
      const schema = z.coerce.number();
      const result = schema.safeParse('8000');
      expect(result.success).toBe(true);
      if (result.success) {
        expect(result.data).toBe(8000);
      }
    });
  });
});
