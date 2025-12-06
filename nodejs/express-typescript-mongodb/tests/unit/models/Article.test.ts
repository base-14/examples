import { describe, it, expect, beforeEach, afterEach } from 'vitest';
import { Article, type IArticle } from '../../../src/models/Article';
import { User, type IUser } from '../../../src/models/User';
import { clearDatabase } from '../../helpers/db.helper';

describe('Article Model', () => {
  let testUser: IUser;

  beforeEach(async () => {
    await clearDatabase();

    // Create a test user for article author
    testUser = await User.create({
      email: 'author@example.com',
      password: 'password123',
      name: 'Test Author',
    });
  });

  afterEach(async () => {
    await clearDatabase();
  });

  describe('Article Creation', () => {
    it('should create article with required fields', async () => {
      const articleData = {
        title: 'Test Article',
        content: 'This is the article content.',
        author: testUser._id,
      };

      const article = await Article.create(articleData);

      expect(article).toBeDefined();
      expect(article.title).toBe('Test Article');
      expect(article.content).toBe('This is the article content.');
      expect(article.author.toString()).toBe(testUser._id.toString());
      expect(article.createdAt).toBeInstanceOf(Date);
      expect(article.updatedAt).toBeInstanceOf(Date);
    });

    it.each([
      { field: 'title', value: undefined, error: 'title' },
      { field: 'content', value: undefined, error: 'content' },
      { field: 'author', value: undefined, error: 'author' },
    ])('should fail validation when $field is missing', async ({ field, value }) => {
      const articleData: Record<string, unknown> = {
        title: 'Test Article',
        content: 'Article content',
        author: testUser._id,
      };

      articleData[field] = value;

      await expect(Article.create(articleData)).rejects.toThrow();
    });
  });

  describe('Default Values', () => {
    it('should set default published to false', async () => {
      const article = await Article.create({
        title: 'Test Article',
        content: 'Article content',
        author: testUser._id,
      });

      expect(article.published).toBe(false);
    });

    it('should set default viewCount to 0', async () => {
      const article = await Article.create({
        title: 'Test Article',
        content: 'Article content',
        author: testUser._id,
      });

      expect(article.viewCount).toBe(0);
    });

    it('should set default tags to empty array', async () => {
      const article = await Article.create({
        title: 'Test Article',
        content: 'Article content',
        author: testUser._id,
      });

      expect(article.tags).toEqual([]);
      expect(Array.isArray(article.tags)).toBe(true);
    });

    it('should allow custom tags array', async () => {
      const article = await Article.create({
        title: 'Test Article',
        content: 'Article content',
        author: testUser._id,
        tags: ['typescript', 'mongodb', 'testing'],
      });

      expect(article.tags).toEqual(['typescript', 'mongodb', 'testing']);
    });

    it('should not set publishedAt by default', async () => {
      const article = await Article.create({
        title: 'Test Article',
        content: 'Article content',
        author: testUser._id,
      });

      expect(article.publishedAt).toBeUndefined();
    });
  });

  describe('Field Validation', () => {
    it('should trim title whitespace', async () => {
      const article = await Article.create({
        title: '  Test Article  ',
        content: 'Article content',
        author: testUser._id,
      });

      expect(article.title).toBe('Test Article');
    });

    it('should enforce title max length of 200 characters', async () => {
      const longTitle = 'a'.repeat(201);

      await expect(
        Article.create({
          title: longTitle,
          content: 'Article content',
          author: testUser._id,
        })
      ).rejects.toThrow(/title.*longer/i);
    });

    it('should allow title with exactly 200 characters', async () => {
      const maxTitle = 'a'.repeat(200);

      const article = await Article.create({
        title: maxTitle,
        content: 'Article content',
        author: testUser._id,
      });

      expect(article.title).toHaveLength(200);
    });

    it('should enforce content max length of 50000 characters', async () => {
      const longContent = 'a'.repeat(50001);

      await expect(
        Article.create({
          title: 'Test Article',
          content: longContent,
          author: testUser._id,
        })
      ).rejects.toThrow(/content.*longer/i);
    });

    it('should allow content with exactly 50000 characters', async () => {
      const maxContent = 'a'.repeat(50000);

      const article = await Article.create({
        title: 'Test Article',
        content: maxContent,
        author: testUser._id,
      });

      expect(article.content).toHaveLength(50000);
    });
  });

  describe('Published Status', () => {
    it('should allow setting published to true', async () => {
      const article = await Article.create({
        title: 'Test Article',
        content: 'Article content',
        author: testUser._id,
        published: true,
        publishedAt: new Date(),
      });

      expect(article.published).toBe(true);
      expect(article.publishedAt).toBeInstanceOf(Date);
    });

    it('should update viewCount', async () => {
      const article = await Article.create({
        title: 'Test Article',
        content: 'Article content',
        author: testUser._id,
      });

      article.viewCount = 5;
      await article.save();

      expect(article.viewCount).toBe(5);
    });
  });

  describe('Author Relationship', () => {
    it('should require valid author reference', async () => {
      await expect(
        Article.create({
          title: 'Test Article',
          content: 'Article content',
          author: null,
        })
      ).rejects.toThrow();
    });

    it('should store author as ObjectId', async () => {
      const article = await Article.create({
        title: 'Test Article',
        content: 'Article content',
        author: testUser._id,
      });

      expect(article.author.toString()).toBe(testUser._id.toString());
    });
  });

  describe('Timestamps', () => {
    it('should automatically set createdAt and updatedAt', async () => {
      const article = await Article.create({
        title: 'Test Article',
        content: 'Article content',
        author: testUser._id,
      });

      expect(article.createdAt).toBeInstanceOf(Date);
      expect(article.updatedAt).toBeInstanceOf(Date);
      expect(article.createdAt.getTime()).toBe(article.updatedAt.getTime());
    });

    it('should update updatedAt on modification', async () => {
      const article = await Article.create({
        title: 'Test Article',
        content: 'Article content',
        author: testUser._id,
      });

      const originalUpdatedAt = article.updatedAt;

      // Wait a bit to ensure timestamp changes
      await new Promise((resolve) => setTimeout(resolve, 10));

      article.title = 'Updated Article Title';
      await article.save();

      expect(article.updatedAt.getTime()).toBeGreaterThan(originalUpdatedAt.getTime());
    });
  });

  describe('Edge Cases', () => {
    it.each([
      { tags: [], expected: [] },
      { tags: ['single'], expected: ['single'] },
      { tags: ['tag1', 'tag2', 'tag3'], expected: ['tag1', 'tag2', 'tag3'] },
    ])('should handle tags array: $tags', async ({ tags, expected }) => {
      const article = await Article.create({
        title: 'Test Article',
        content: 'Article content',
        author: testUser._id,
        tags,
      });

      expect(article.tags).toEqual(expected);
    });

    it.each([
      { viewCount: 0, expected: 0 },
      { viewCount: 1, expected: 1 },
      { viewCount: 100, expected: 100 },
      { viewCount: 999999, expected: 999999 },
    ])('should handle viewCount: $viewCount', async ({ viewCount, expected }) => {
      const article = await Article.create({
        title: 'Test Article',
        content: 'Article content',
        author: testUser._id,
        viewCount,
      });

      expect(article.viewCount).toBe(expected);
    });
  });
});
