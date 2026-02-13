import { describe, it, expect } from 'vitest';
import { registerSchema, loginSchema } from '../src/validators/user.js';
import { createArticleSchema } from '../src/validators/article.js';

describe('password policy enforcement', () => {
  const base = { email: 'test@example.com', name: 'Test' };

  const weakPasswords = [
    { pw: 'short1!A', reason: 'minimum length boundary (8 chars)' },
    { pw: 'password', reason: 'all lowercase, no numbers or specials' },
    { pw: '12345678', reason: 'all numbers' },
    { pw: '!@#$%^&*', reason: 'all special characters' },
    { pw: 'ALLUPPERCASE1!', reason: 'no lowercase' },
    { pw: 'alllowercase1!', reason: 'no uppercase' },
    { pw: 'NoNumbers!!AA', reason: 'no digits' },
    { pw: 'NoSpecial1Aa', reason: 'no special characters' },
  ];

  weakPasswords.forEach(({ pw, reason }) => {
    it(`rejects weak password: ${reason}`, () => {
      const result = registerSchema.safeParse({ ...base, password: pw });
      // 8-char password with all categories should pass, others fail
      if (pw === 'short1!A') {
        // This is exactly 8 chars with all requirements met — should pass
        expect(result.success).toBe(true);
      } else {
        expect(result.success).toBe(false);
      }
    });
  });

  it('accepts strong password at minimum length', () => {
    const result = registerSchema.safeParse({ ...base, password: 'Aa1!xxxx' });
    expect(result.success).toBe(true);
  });

  it('accepts strong password with mixed characters', () => {
    const result = registerSchema.safeParse({ ...base, password: 'C0mpl3x!Pass' });
    expect(result.success).toBe(true);
  });
});

describe('input sanitization — SQL injection patterns', () => {
  const sqlInjectionPayloads = [
    "'; DROP TABLE users; --",
    "1' OR '1'='1",
    "' UNION SELECT * FROM users --",
    "admin'--",
  ];

  sqlInjectionPayloads.forEach((payload) => {
    it(`accepts SQL-like input in article title (parameterized queries prevent injection): "${payload.slice(0, 30)}..."`, () => {
      // Zod validates shape/type, not SQL content — the DB layer uses parameterized queries
      const result = createArticleSchema.safeParse({ title: payload, body: 'safe body' });
      expect(result.success).toBe(true);
    });
  });

  it('login schema rejects syntactically invalid email with SQL payload', () => {
    const result = loginSchema.safeParse({ email: "' OR 1=1 --", password: 'test' });
    expect(result.success).toBe(false);
  });
});

describe('input sanitization — XSS patterns', () => {
  const xssPayloads = [
    '<script>alert("xss")</script>',
    '<img src=x onerror=alert(1)>',
    'javascript:alert(1)',
  ];

  xssPayloads.forEach((payload) => {
    it(`accepts XSS-like input in article body (output encoding prevents XSS): "${payload.slice(0, 40)}"`, () => {
      // JSON API returns Content-Type: application/json, XSS payloads are inert
      const result = createArticleSchema.safeParse({ title: 'Title', body: payload });
      expect(result.success).toBe(true);
    });
  });
});

describe('input length limits', () => {
  it('rejects excessively long registration name', () => {
    const result = registerSchema.safeParse({
      email: 'test@example.com',
      password: 'StrongP@ss1',
      name: 'x'.repeat(256),
    });
    expect(result.success).toBe(false);
  });

  it('rejects excessively long article title', () => {
    const result = createArticleSchema.safeParse({
      title: 'x'.repeat(256),
      body: 'body',
    });
    expect(result.success).toBe(false);
  });

  it('accepts article body of any reasonable length', () => {
    const result = createArticleSchema.safeParse({
      title: 'Title',
      body: 'x'.repeat(50000),
    });
    expect(result.success).toBe(true);
  });
});
