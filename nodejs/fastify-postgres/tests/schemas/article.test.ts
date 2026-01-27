import { describe, it, expect } from 'vitest';
import Ajv from 'ajv';
import addFormats from 'ajv-formats';
import { createArticleSchema, updateArticleSchema } from '../../src/schemas/article.js';

const ajv = new Ajv({ allErrors: true });
addFormats(ajv);

describe('Article Schemas', () => {
  describe('createArticleSchema', () => {
    const validate = ajv.compile(createArticleSchema.body);

    it('should accept valid article data', () => {
      const validData = {
        title: 'Test Article',
        description: 'A test article description',
        body: 'This is the body of the test article.',
      };
      expect(validate(validData)).toBe(true);
    });

    it('should accept article without description', () => {
      const validData = {
        title: 'Test Article',
        body: 'This is the body of the test article.',
      };
      expect(validate(validData)).toBe(true);
    });

    it('should reject missing title', () => {
      const invalidData = {
        body: 'This is the body of the test article.',
      };
      expect(validate(invalidData)).toBe(false);
    });

    it('should reject missing body', () => {
      const invalidData = {
        title: 'Test Article',
      };
      expect(validate(invalidData)).toBe(false);
    });

    it('should reject empty title', () => {
      const invalidData = {
        title: '',
        body: 'This is the body of the test article.',
      };
      expect(validate(invalidData)).toBe(false);
    });

    it('should reject title exceeding max length', () => {
      const invalidData = {
        title: 'x'.repeat(501),
        body: 'This is the body.',
      };
      expect(validate(invalidData)).toBe(false);
    });

    it('should reject description exceeding max length', () => {
      const invalidData = {
        title: 'Test Article',
        description: 'x'.repeat(1001),
        body: 'This is the body.',
      };
      expect(validate(invalidData)).toBe(false);
    });

    it('should reject additional properties', () => {
      const invalidData = {
        title: 'Test Article',
        body: 'This is the body.',
        authorId: 1,
      };
      expect(validate(invalidData)).toBe(false);
    });
  });

  describe('updateArticleSchema', () => {
    const validate = ajv.compile(updateArticleSchema.body);

    it('should accept partial update with title only', () => {
      const validData = {
        title: 'Updated Title',
      };
      expect(validate(validData)).toBe(true);
    });

    it('should accept partial update with body only', () => {
      const validData = {
        body: 'Updated body content.',
      };
      expect(validate(validData)).toBe(true);
    });

    it('should accept full update', () => {
      const validData = {
        title: 'Updated Title',
        description: 'Updated description',
        body: 'Updated body content.',
      };
      expect(validate(validData)).toBe(true);
    });

    it('should accept empty object (no updates)', () => {
      const validData = {};
      expect(validate(validData)).toBe(true);
    });

    it('should reject additional properties', () => {
      const invalidData = {
        title: 'Updated Title',
        slug: 'should-not-be-allowed',
      };
      expect(validate(invalidData)).toBe(false);
    });
  });
});
