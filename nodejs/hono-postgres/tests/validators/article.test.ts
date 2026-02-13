import { describe, it, expect } from 'vitest';
import { createArticleSchema, updateArticleSchema } from '../../src/validators/article.js';

describe('createArticleSchema', () => {
  const validArticle = {
    title: 'My First Article',
    body: 'This is the body content of the article.',
  };

  it('accepts valid article with title and body', () => {
    const result = createArticleSchema.safeParse(validArticle);
    expect(result.success).toBe(true);
  });

  it('accepts article with optional description', () => {
    const result = createArticleSchema.safeParse({ ...validArticle, description: 'A short summary' });
    expect(result.success).toBe(true);
  });

  it('accepts article without description', () => {
    const result = createArticleSchema.safeParse({ title: 'Title', body: 'Body' });
    expect(result.success).toBe(true);
    if (result.success) {
      expect(result.data.description).toBeUndefined();
    }
  });

  it('rejects empty title', () => {
    const result = createArticleSchema.safeParse({ ...validArticle, title: '' });
    expect(result.success).toBe(false);
  });

  it('rejects title exceeding 255 characters', () => {
    const result = createArticleSchema.safeParse({ ...validArticle, title: 'x'.repeat(256) });
    expect(result.success).toBe(false);
  });

  it('rejects empty body', () => {
    const result = createArticleSchema.safeParse({ ...validArticle, body: '' });
    expect(result.success).toBe(false);
  });

  it('rejects description exceeding 1000 characters', () => {
    const result = createArticleSchema.safeParse({
      ...validArticle,
      description: 'x'.repeat(1001),
    });
    expect(result.success).toBe(false);
  });

  it('rejects missing required fields', () => {
    const result = createArticleSchema.safeParse({});
    expect(result.success).toBe(false);
  });

  it('rejects missing body', () => {
    const result = createArticleSchema.safeParse({ title: 'Title Only' });
    expect(result.success).toBe(false);
  });
});

describe('updateArticleSchema', () => {
  it('accepts partial update with title only', () => {
    const result = updateArticleSchema.safeParse({ title: 'Updated Title' });
    expect(result.success).toBe(true);
  });

  it('accepts partial update with body only', () => {
    const result = updateArticleSchema.safeParse({ body: 'Updated body content' });
    expect(result.success).toBe(true);
  });

  it('accepts partial update with description only', () => {
    const result = updateArticleSchema.safeParse({ description: 'Updated desc' });
    expect(result.success).toBe(true);
  });

  it('accepts full update', () => {
    const result = updateArticleSchema.safeParse({
      title: 'Updated',
      description: 'Updated desc',
      body: 'Updated body',
    });
    expect(result.success).toBe(true);
  });

  it('accepts empty object (no fields to update)', () => {
    const result = updateArticleSchema.safeParse({});
    expect(result.success).toBe(true);
  });

  it('rejects empty title string', () => {
    const result = updateArticleSchema.safeParse({ title: '' });
    expect(result.success).toBe(false);
  });

  it('rejects title exceeding 255 characters', () => {
    const result = updateArticleSchema.safeParse({ title: 'x'.repeat(256) });
    expect(result.success).toBe(false);
  });

  it('rejects empty body string', () => {
    const result = updateArticleSchema.safeParse({ body: '' });
    expect(result.success).toBe(false);
  });

  it('rejects description exceeding 1000 characters', () => {
    const result = updateArticleSchema.safeParse({ description: 'x'.repeat(1001) });
    expect(result.success).toBe(false);
  });
});
