import { describe, it, expect } from 'vitest';
import { z } from 'zod';
import {
  emailSchema,
  passwordSchema,
  usernameSchema,
  formatZodErrors,
  validateOrThrow,
} from '@/lib/validators';

describe('validators', () => {
  describe('emailSchema', () => {
    it('accepts a valid email', () => {
      expect(emailSchema.safeParse('user@example.com').success).toBe(true);
    });

    it('rejects an invalid email', () => {
      const result = emailSchema.safeParse('not-email');
      expect(result.success).toBe(false);
    });
  });

  describe('passwordSchema', () => {
    it('accepts a password with 8+ characters', () => {
      expect(passwordSchema.safeParse('longpassword').success).toBe(true);
    });

    it('rejects a password shorter than 8 characters', () => {
      const result = passwordSchema.safeParse('short');
      expect(result.success).toBe(false);
    });
  });

  describe('usernameSchema', () => {
    it('accepts alphanumeric with underscores and hyphens', () => {
      expect(usernameSchema.safeParse('user_name-1').success).toBe(true);
    });

    it('rejects special characters and spaces', () => {
      expect(usernameSchema.safeParse('no spaces').success).toBe(false);
      expect(usernameSchema.safeParse('bad@name').success).toBe(false);
    });
  });

  describe('formatZodErrors', () => {
    it('returns readable string array from ZodError', () => {
      const schema = z.object({ email: z.string().email(), age: z.number() });
      const result = schema.safeParse({ email: 'bad', age: 'not-number' });
      if (!result.success) {
        const messages = formatZodErrors(result.error);
        expect(messages.length).toBeGreaterThan(0);
        expect(messages.every((m) => typeof m === 'string')).toBe(true);
      }
    });
  });

  describe('validateOrThrow', () => {
    it('returns data on valid input', () => {
      const result = validateOrThrow(emailSchema, 'valid@test.com');
      expect(result).toBe('valid@test.com');
    });

    it('throws on invalid input', () => {
      expect(() => validateOrThrow(emailSchema, 'bad')).toThrow();
    });
  });
});
