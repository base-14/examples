import { describe, it, expect } from 'vitest';
import Ajv from 'ajv';
import addFormats from 'ajv-formats';
import { registerSchema, loginSchema } from '../../src/schemas/user.js';

const ajv = new Ajv({ allErrors: true });
addFormats(ajv);

describe('User Schemas', () => {
  describe('registerSchema', () => {
    const validate = ajv.compile(registerSchema.body);

    it('should accept valid registration data', () => {
      const validData = {
        email: 'test@example.com',
        password: 'SecurePass123!',
        name: 'Test User',
      };
      expect(validate(validData)).toBe(true);
    });

    it('should reject missing email', () => {
      const invalidData = {
        password: 'SecurePass123!',
        name: 'Test User',
      };
      expect(validate(invalidData)).toBe(false);
      expect(validate.errors?.some(e => e.message?.includes('email'))).toBe(true);
    });

    it('should reject invalid email format', () => {
      const invalidData = {
        email: 'not-an-email',
        password: 'SecurePass123!',
        name: 'Test User',
      };
      expect(validate(invalidData)).toBe(false);
    });

    it('should reject password without uppercase', () => {
      const invalidData = {
        email: 'test@example.com',
        password: 'securepass123!',
        name: 'Test User',
      };
      expect(validate(invalidData)).toBe(false);
    });

    it('should reject password without lowercase', () => {
      const invalidData = {
        email: 'test@example.com',
        password: 'SECUREPASS123!',
        name: 'Test User',
      };
      expect(validate(invalidData)).toBe(false);
    });

    it('should reject password without number', () => {
      const invalidData = {
        email: 'test@example.com',
        password: 'SecurePass!!!',
        name: 'Test User',
      };
      expect(validate(invalidData)).toBe(false);
    });

    it('should reject password without special character', () => {
      const invalidData = {
        email: 'test@example.com',
        password: 'SecurePass123',
        name: 'Test User',
      };
      expect(validate(invalidData)).toBe(false);
    });

    it('should reject password shorter than 8 characters', () => {
      const invalidData = {
        email: 'test@example.com',
        password: 'Pass1!',
        name: 'Test User',
      };
      expect(validate(invalidData)).toBe(false);
    });

    it('should reject additional properties', () => {
      const invalidData = {
        email: 'test@example.com',
        password: 'SecurePass123!',
        name: 'Test User',
        extraField: 'should not be allowed',
      };
      expect(validate(invalidData)).toBe(false);
    });
  });

  describe('loginSchema', () => {
    const validate = ajv.compile(loginSchema.body);

    it('should accept valid login data', () => {
      const validData = {
        email: 'test@example.com',
        password: 'anypassword',
      };
      expect(validate(validData)).toBe(true);
    });

    it('should reject missing password', () => {
      const invalidData = {
        email: 'test@example.com',
      };
      expect(validate(invalidData)).toBe(false);
    });

    it('should reject empty password', () => {
      const invalidData = {
        email: 'test@example.com',
        password: '',
      };
      expect(validate(invalidData)).toBe(false);
    });

    it('should reject additional properties', () => {
      const invalidData = {
        email: 'test@example.com',
        password: 'anypassword',
        rememberMe: true,
      };
      expect(validate(invalidData)).toBe(false);
    });
  });
});
