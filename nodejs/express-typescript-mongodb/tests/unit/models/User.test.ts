import { describe, it, expect, beforeEach, afterEach } from 'vitest';
import { User, type IUser } from '../../../src/models/User';
import { clearDatabase } from '../../helpers/db.helper';

describe('User Model', () => {
  beforeEach(async () => {
    await clearDatabase();
  });

  afterEach(async () => {
    await clearDatabase();
  });

  describe('User Creation', () => {
    it('should create user with required fields', async () => {
      const userData = {
        email: 'test@example.com',
        password: 'password123',
        name: 'Test User',
      };

      const user = await User.create(userData);

      expect(user).toBeDefined();
      expect(user.email).toBe('test@example.com');
      expect(user.name).toBe('Test User');
      expect(user.password).not.toBe('password123'); // Should be hashed
      expect(user.role).toBe('user'); // Default role
      expect(user.createdAt).toBeInstanceOf(Date);
      expect(user.updatedAt).toBeInstanceOf(Date);
    });

    it.each([
      { field: 'email', value: undefined, error: 'email' },
      { field: 'password', value: undefined, error: 'password' },
      { field: 'name', value: undefined, error: 'name' },
    ])('should fail validation when $field is missing', async ({ field, value }) => {
      const userData: Record<string, unknown> = {
        email: 'test@example.com',
        password: 'password123',
        name: 'Test User',
      };

      userData[field] = value;

      await expect(User.create(userData)).rejects.toThrow();
    });

    it('should set default role to user', async () => {
      const user = await User.create({
        email: 'test@example.com',
        password: 'password123',
        name: 'Test User',
      });

      expect(user.role).toBe('user');
    });

    it('should allow admin role', async () => {
      const user = await User.create({
        email: 'admin@example.com',
        password: 'password123',
        name: 'Admin User',
        role: 'admin',
      });

      expect(user.role).toBe('admin');
    });
  });

  describe('Email Normalization', () => {
    it('should normalize email to lowercase', async () => {
      const user = await User.create({
        email: 'Test@EXAMPLE.COM',
        password: 'password123',
        name: 'Test User',
      });

      expect(user.email).toBe('test@example.com');
    });

    it('should trim email whitespace', async () => {
      const user = await User.create({
        email: '  test@example.com  ',
        password: 'password123',
        name: 'Test User',
      });

      expect(user.email).toBe('test@example.com');
    });
  });

  describe('Email Uniqueness', () => {
    it('should enforce unique email constraint', async () => {
      await User.create({
        email: 'test@example.com',
        password: 'password123',
        name: 'User One',
      });

      await expect(
        User.create({
          email: 'test@example.com',
          password: 'password456',
          name: 'User Two',
        })
      ).rejects.toThrow(/duplicate key|E11000/i);
    });
  });

  describe('Password Handling', () => {
    it('should hash password on save', async () => {
      const plainPassword = 'password123';
      const user = await User.create({
        email: 'test@example.com',
        password: plainPassword,
        name: 'Test User',
      });

      expect(user.password).not.toBe(plainPassword);
      expect(user.password).toMatch(/^\$2[ayb]\$.{56}$/); // bcrypt hash format
    });

    it('should not re-hash password if unchanged', async () => {
      const user = await User.create({
        email: 'test@example.com',
        password: 'password123',
        name: 'Test User',
      });

      const originalHash = user.password;

      // Update name, not password
      user.name = 'Updated Name';
      await user.save();

      expect(user.password).toBe(originalHash);
    });

    it('should re-hash password when changed', async () => {
      const user = await User.create({
        email: 'test@example.com',
        password: 'password123',
        name: 'Test User',
      });

      const originalHash = user.password;

      // Change password
      user.password = 'newpassword456';
      await user.save();

      expect(user.password).not.toBe(originalHash);
      expect(user.password).toMatch(/^\$2[ayb]\$.{56}$/);
    });

    it('should validate minimum password length', async () => {
      await expect(
        User.create({
          email: 'test@example.com',
          password: '12345', // Only 5 characters
          name: 'Test User',
        })
      ).rejects.toThrow(/password.*shorter/i);
    });
  });

  describe('comparePassword Method', () => {
    it('should return true for valid password', async () => {
      const plainPassword = 'password123';
      const user = await User.create({
        email: 'test@example.com',
        password: plainPassword,
        name: 'Test User',
      });

      const isMatch = await user.comparePassword(plainPassword);

      expect(isMatch).toBe(true);
    });

    it('should return false for invalid password', async () => {
      const user = await User.create({
        email: 'test@example.com',
        password: 'password123',
        name: 'Test User',
      });

      const isMatch = await user.comparePassword('wrongpassword');

      expect(isMatch).toBe(false);
    });

    it.each([
      { correct: 'password123', attempt: 'password123', expected: true },
      { correct: 'password123', attempt: 'Password123', expected: false },
      { correct: 'password123', attempt: 'password124', expected: false },
      { correct: 'password123', attempt: '', expected: false },
    ])(
      'should return $expected when password is "$attempt"',
      async ({ correct, attempt, expected }) => {
        const user = await User.create({
          email: 'test@example.com',
          password: correct,
          name: 'Test User',
        });

        const isMatch = await user.comparePassword(attempt);

        expect(isMatch).toBe(expected);
      }
    );
  });

  describe('Field Trimming', () => {
    it('should trim name field', async () => {
      const user = await User.create({
        email: 'test@example.com',
        password: 'password123',
        name: '  Test User  ',
      });

      expect(user.name).toBe('Test User');
    });
  });
});
