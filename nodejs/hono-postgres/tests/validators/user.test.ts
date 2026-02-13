import { describe, it, expect } from 'vitest';
import { registerSchema, loginSchema, updateUserSchema } from '../../src/validators/user.js';

describe('registerSchema', () => {
  const validUser = {
    email: 'test@example.com',
    password: 'StrongP@ss1',
    name: 'Test User',
  };

  it('accepts valid registration data', () => {
    const result = registerSchema.safeParse(validUser);
    expect(result.success).toBe(true);
  });

  it('rejects invalid email', () => {
    const result = registerSchema.safeParse({ ...validUser, email: 'not-an-email' });
    expect(result.success).toBe(false);
  });

  it('rejects empty email', () => {
    const result = registerSchema.safeParse({ ...validUser, email: '' });
    expect(result.success).toBe(false);
  });

  it('rejects short password', () => {
    const result = registerSchema.safeParse({ ...validUser, password: 'Ab1!' });
    expect(result.success).toBe(false);
  });

  it('rejects password without uppercase', () => {
    const result = registerSchema.safeParse({ ...validUser, password: 'lowercase1!' });
    expect(result.success).toBe(false);
  });

  it('rejects password without lowercase', () => {
    const result = registerSchema.safeParse({ ...validUser, password: 'UPPERCASE1!' });
    expect(result.success).toBe(false);
  });

  it('rejects password without number', () => {
    const result = registerSchema.safeParse({ ...validUser, password: 'NoNumber!@' });
    expect(result.success).toBe(false);
  });

  it('rejects password without special character', () => {
    const result = registerSchema.safeParse({ ...validUser, password: 'NoSpecial1' });
    expect(result.success).toBe(false);
  });

  it('rejects password exceeding 128 characters', () => {
    const longPass = 'Aa1!' + 'x'.repeat(125);
    const result = registerSchema.safeParse({ ...validUser, password: longPass });
    expect(result.success).toBe(false);
  });

  it('rejects empty name', () => {
    const result = registerSchema.safeParse({ ...validUser, name: '' });
    expect(result.success).toBe(false);
  });

  it('rejects name exceeding 255 characters', () => {
    const result = registerSchema.safeParse({ ...validUser, name: 'x'.repeat(256) });
    expect(result.success).toBe(false);
  });

  it('rejects missing fields', () => {
    const result = registerSchema.safeParse({});
    expect(result.success).toBe(false);
  });
});

describe('loginSchema', () => {
  it('accepts valid login data', () => {
    const result = loginSchema.safeParse({ email: 'test@example.com', password: 'password' });
    expect(result.success).toBe(true);
  });

  it('rejects invalid email', () => {
    const result = loginSchema.safeParse({ email: 'bad', password: 'password' });
    expect(result.success).toBe(false);
  });

  it('rejects empty password', () => {
    const result = loginSchema.safeParse({ email: 'test@example.com', password: '' });
    expect(result.success).toBe(false);
  });

  it('rejects missing fields', () => {
    const result = loginSchema.safeParse({});
    expect(result.success).toBe(false);
  });
});

describe('updateUserSchema', () => {
  it('accepts valid partial update', () => {
    const result = updateUserSchema.safeParse({ name: 'New Name' });
    expect(result.success).toBe(true);
  });

  it('accepts valid bio update', () => {
    const result = updateUserSchema.safeParse({ bio: 'I write code.' });
    expect(result.success).toBe(true);
  });

  it('accepts valid image URL', () => {
    const result = updateUserSchema.safeParse({ image: 'https://example.com/avatar.png' });
    expect(result.success).toBe(true);
  });

  it('accepts empty object (no updates)', () => {
    const result = updateUserSchema.safeParse({});
    expect(result.success).toBe(true);
  });

  it('rejects invalid image URL', () => {
    const result = updateUserSchema.safeParse({ image: 'not-a-url' });
    expect(result.success).toBe(false);
  });

  it('rejects name exceeding 255 characters', () => {
    const result = updateUserSchema.safeParse({ name: 'x'.repeat(256) });
    expect(result.success).toBe(false);
  });

  it('rejects bio exceeding 1000 characters', () => {
    const result = updateUserSchema.safeParse({ bio: 'x'.repeat(1001) });
    expect(result.success).toBe(false);
  });

  it('rejects image URL exceeding 500 characters', () => {
    const result = updateUserSchema.safeParse({ image: 'https://example.com/' + 'x'.repeat(490) });
    expect(result.success).toBe(false);
  });
});
