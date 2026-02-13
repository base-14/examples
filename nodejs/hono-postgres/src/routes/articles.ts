import { Hono } from 'hono';
import { zValidator } from '@hono/zod-validator';
import * as articleService from '../services/article.js';
import { createArticleSchema, updateArticleSchema } from '../validators/article.js';
import { authenticate, optionalAuth } from '../middleware/auth.js';
import { createLogger } from '../services/logger.js';
import type { Variables } from '../types/index.js';

const logger = createLogger('article-routes');
const articlesRouter = new Hono<{ Variables: Variables }>();

articlesRouter.get('/', optionalAuth, async (c) => {
  const limit = parseInt(c.req.query('limit') || '20', 10);
  const offset = parseInt(c.req.query('offset') || '0', 10);
  const author = c.req.query('author');
  const userId = c.get('user')?.id;

  const result = await articleService.findArticles({ limit, offset, author }, userId);
  return c.json(result);
});

articlesRouter.get('/:slug', optionalAuth, async (c) => {
  const slug = c.req.param('slug');
  const userId = c.get('user')?.id;
  const article = await articleService.findBySlug(slug, userId);

  if (!article) {
    return c.json({ error: 'Not Found', message: 'Article not found' }, 404);
  }

  return c.json({ article });
});

articlesRouter.post('/', authenticate, zValidator('json', createArticleSchema), async (c) => {
  const { id: userId } = c.get('user');
  const data = c.req.valid('json');
  const article = await articleService.createArticle(userId, data);

  return c.json({ article }, 201);
});

articlesRouter.put('/:slug', authenticate, zValidator('json', updateArticleSchema), async (c) => {
  const slug = c.req.param('slug');
  const { id: userId } = c.get('user');
  const data = c.req.valid('json');

  try {
    const article = await articleService.updateArticle(slug, userId, data);

    if (!article) {
      return c.json({ error: 'Not Found', message: 'Article not found' }, 404);
    }

    return c.json({ article });
  } catch (error) {
    if ((error as Error).message === 'Forbidden') {
      logger.warn({ slug, userId }, 'Article update forbidden: not owner');
      return c.json({ error: 'Forbidden', message: 'You can only edit your own articles' }, 403);
    }
    throw error;
  }
});

articlesRouter.delete('/:slug', authenticate, async (c) => {
  const slug = c.req.param('slug');
  const { id: userId } = c.get('user');

  try {
    const deleted = await articleService.deleteArticle(slug, userId);

    if (!deleted) {
      return c.json({ error: 'Not Found', message: 'Article not found' }, 404);
    }

    return c.body(null, 204);
  } catch (error) {
    if ((error as Error).message === 'Forbidden') {
      logger.warn({ slug, userId }, 'Article delete forbidden: not owner');
      return c.json({ error: 'Forbidden', message: 'You can only delete your own articles' }, 403);
    }
    throw error;
  }
});

articlesRouter.post('/:slug/favorite', authenticate, async (c) => {
  const slug = c.req.param('slug');
  const { id: userId } = c.get('user');
  const article = await articleService.favoriteArticle(slug, userId);

  if (!article) {
    return c.json({ error: 'Not Found', message: 'Article not found' }, 404);
  }

  return c.json({ article });
});

articlesRouter.delete('/:slug/favorite', authenticate, async (c) => {
  const slug = c.req.param('slug');
  const { id: userId } = c.get('user');
  const article = await articleService.unfavoriteArticle(slug, userId);

  if (!article) {
    return c.json({ error: 'Not Found', message: 'Article not found' }, 404);
  }

  return c.json({ article });
});

export default articlesRouter;
