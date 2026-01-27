import { describe, it, expect } from 'vitest';
import Ajv from 'ajv';
import addFormats from 'ajv-formats';
import { registerSchema } from '../src/schemas/user.js';

const ajv = new Ajv({ allErrors: true });
addFormats(ajv);

describe('Security Tests', () => {
  describe('Password Policy', () => {
    const validate = ajv.compile(registerSchema.body);

    const testCases = [
      { password: 'password', description: 'all lowercase', shouldFail: true },
      { password: 'PASSWORD', description: 'all uppercase', shouldFail: true },
      { password: '12345678', description: 'only numbers', shouldFail: true },
      { password: '!@#$%^&*', description: 'only special chars', shouldFail: true },
      { password: 'Password1', description: 'no special char', shouldFail: true },
      { password: 'Password!', description: 'no number', shouldFail: true },
      { password: 'password1!', description: 'no uppercase', shouldFail: true },
      { password: 'PASSWORD1!', description: 'no lowercase', shouldFail: true },
      { password: 'Pass1!', description: 'too short', shouldFail: true },
      { password: 'Password1!', description: 'valid password', shouldFail: false },
      { password: 'MySecure@Pass123', description: 'complex valid password', shouldFail: false },
      { password: 'Test#123abc', description: 'another valid password', shouldFail: false },
    ];

    testCases.forEach(({ password, description, shouldFail }) => {
      it(`should ${shouldFail ? 'reject' : 'accept'} ${description}`, () => {
        const data = {
          email: 'test@example.com',
          password,
          name: 'Test User',
        };
        const result = validate(data);
        expect(result).toBe(!shouldFail);
      });
    });
  });

  describe('Input Sanitization', () => {
    const validate = ajv.compile(registerSchema.body);

    it('should reject email with script injection', () => {
      const data = {
        email: '<script>alert("xss")</script>@example.com',
        password: 'SecurePass123!',
        name: 'Test User',
      };
      expect(validate(data)).toBe(false);
    });

    it('should reject excessively long passwords', () => {
      const data = {
        email: 'test@example.com',
        password: 'A'.repeat(129) + 'a1!',
        name: 'Test User',
      };
      expect(validate(data)).toBe(false);
    });

    it('should reject name exceeding max length', () => {
      const data = {
        email: 'test@example.com',
        password: 'SecurePass123!',
        name: 'x'.repeat(256),
      };
      expect(validate(data)).toBe(false);
    });

    it('should reject additional unexpected fields', () => {
      const data = {
        email: 'test@example.com',
        password: 'SecurePass123!',
        name: 'Test User',
        isAdmin: true,
        role: 'admin',
      };
      expect(validate(data)).toBe(false);
    });
  });

  describe('SQL Injection Prevention', () => {
    const validate = ajv.compile(registerSchema.body);

    const sqlInjectionAttempts = [
      "'; DROP TABLE users; --",
      "' OR '1'='1",
      "1; DELETE FROM users",
      "admin'--",
      "' UNION SELECT * FROM users --",
    ];

    sqlInjectionAttempts.forEach((attempt) => {
      it(`should handle SQL injection attempt in name: ${attempt.substring(0, 20)}...`, () => {
        const data = {
          email: 'test@example.com',
          password: 'SecurePass123!',
          name: attempt,
        };
        expect(validate(data)).toBe(true);
      });
    });
  });
});
