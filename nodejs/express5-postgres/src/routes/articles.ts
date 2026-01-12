import { Router } from 'express';
import { z } from 'zod';
import { trace, propagation, context } from '@opentelemetry/api';
import { articleService } from '../services/article.js';
import { requireAuth, optionalAuth } from '../middleware/auth.js';
import { Queue } from 'bullmq';
import { broadcastToChannel } from '../socket.js';

const router = Router();

const createArticleSchema = z.object({
  title: z.string().min(1).max(255),
  description: z.string().optional(),
  body: z.string().min(1),
});

const updateArticleSchema = z.object({
  title: z.string().min(1).max(255).optional(),
  description: z.string().optional(),
  body: z.string().min(1).optional(),
});

const redisUrl = new URL(process.env.REDIS_URL || 'redis://localhost:6379');
const notificationQueue = new Queue('notifications', {
  connection: {
    host: redisUrl.hostname,
    port: parseInt(redisUrl.port || '6379'),
  },
});

function errorResponse(message: string, statusCode: number, res: Express.Response) {
  const span = trace.getActiveSpan();
  const spanContext = span?.spanContext();

  const response: Record<string, unknown> = { error: message };
  if (spanContext?.traceId) {
    response.trace_id = spanContext.traceId;
  }

  // @ts-expect-error - Express response type
  return res.status(statusCode).json(response);
}

async function formatArticleResponse(
  article: { id: number; slug: string; title: string; description?: string | null; body: string; favoritesCount: number; createdAt: Date; updatedAt: Date; author?: { id: number; name: string; email: string } },
  userId?: number
) {
  const favorited = await articleService.isFavoritedBy(article.id, userId);

  return {
    id: article.id,
    slug: article.slug,
    title: article.title,
    description: article.description || '',
    body: article.body,
    favoritesCount: article.favoritesCount,
    favorited,
    createdAt: article.createdAt.toISOString(),
    updatedAt: article.updatedAt.toISOString(),
    author: article.author
      ? {
          id: article.author.id,
          name: article.author.name,
          email: article.author.email,
        }
      : undefined,
  };
}

router.get('/', optionalAuth, async (req, res) => {
  const page = parseInt(req.query.page as string) || 1;
  const perPage = parseInt(req.query.per_page as string) || 20;
  const searchQuery = req.query.search as string | undefined;

  const listParams: { page: number; perPage: number; search?: string } = { page, perPage };
  if (searchQuery) {
    listParams.search = searchQuery;
  }

  const result = await articleService.list(listParams);

  const articlesWithFavorited = await Promise.all(
    result.data.map((article) => formatArticleResponse(article, req.user?.id))
  );

  res.json({
    articles: articlesWithFavorited,
    total: result.total,
    page: result.page,
    per_page: result.perPage,
  });
});

router.post('/', requireAuth, async (req, res) => {
  const result = createArticleSchema.safeParse(req.body);

  if (!result.success) {
    return errorResponse(result.error.errors[0]?.message || 'Validation failed', 400, res);
  }

  try {
    const createData: { title: string; body: string; description?: string } = {
      title: result.data.title,
      body: result.data.body,
    };
    if (result.data.description) {
      createData.description = result.data.description;
    }

    const article = await articleService.create(req.user!.id, createData);

    // Enqueue notification job with trace context
    const traceContext: Record<string, string> = {};
    propagation.inject(context.active(), traceContext);

    await notificationQueue.add('article_created', {
      articleId: article.id,
      event: 'created',
      traceContext,
    });

    const response = await formatArticleResponse(
      { ...article, author: { id: req.user!.id, name: req.user!.name, email: req.user!.email } },
      req.user!.id
    );

    broadcastToChannel('articles', 'article:created', {
      article: response,
    }, traceContext);

    res.status(201).json(response);
  } catch (error) {
    const err = error as Error & { statusCode?: number };
    return errorResponse(err.message, err.statusCode || 500, res);
  }
});

router.get('/:slug', optionalAuth, async (req, res) => {
  const slug = req.params.slug as string;
  if (!slug) {
    return errorResponse('Slug is required', 400, res);
  }

  const article = await articleService.findBySlug(slug);

  if (!article) {
    return errorResponse('Article not found', 404, res);
  }

  const response = await formatArticleResponse(article as any, req.user?.id);

  res.json(response);
});

router.put('/:slug', requireAuth, async (req, res) => {
  const slug = req.params.slug as string;
  if (!slug) {
    return errorResponse('Slug is required', 400, res);
  }

  const result = updateArticleSchema.safeParse(req.body);

  if (!result.success) {
    return errorResponse(result.error.errors[0]?.message || 'Validation failed', 400, res);
  }

  try {
    const updateData: { title?: string; body?: string; description?: string } = {};
    if (result.data.title) updateData.title = result.data.title;
    if (result.data.body) updateData.body = result.data.body;
    if (result.data.description) updateData.description = result.data.description;

    const article = await articleService.update(slug, req.user!.id, updateData);

    const response = await formatArticleResponse(
      { ...article, author: { id: req.user!.id, name: req.user!.name, email: req.user!.email } },
      req.user!.id
    );

    const traceContext: Record<string, string> = {};
    propagation.inject(context.active(), traceContext);

    broadcastToChannel('articles', 'article:updated', {
      article: response,
    }, traceContext);

    res.json(response);
  } catch (error) {
    const err = error as Error & { statusCode?: number };
    return errorResponse(err.message, err.statusCode || 500, res);
  }
});

router.delete('/:slug', requireAuth, async (req, res) => {
  const slug = req.params.slug as string;
  if (!slug) {
    return errorResponse('Slug is required', 400, res);
  }

  try {
    await articleService.delete(slug, req.user!.id);

    const traceContext: Record<string, string> = {};
    propagation.inject(context.active(), traceContext);

    broadcastToChannel('articles', 'article:deleted', {
      slug,
    }, traceContext);

    res.status(204).send();
  } catch (error) {
    const err = error as Error & { statusCode?: number };
    return errorResponse(err.message, err.statusCode || 500, res);
  }
});

router.post('/:slug/favorite', requireAuth, async (req, res) => {
  const slug = req.params.slug as string;
  if (!slug) {
    return errorResponse('Slug is required', 400, res);
  }

  try {
    const article = await articleService.favorite(slug, req.user!.id);

    const response = await formatArticleResponse(article as any, req.user!.id);

    res.json(response);
  } catch (error) {
    const err = error as Error & { statusCode?: number };
    return errorResponse(err.message, err.statusCode || 500, res);
  }
});

router.delete('/:slug/favorite', requireAuth, async (req, res) => {
  const slug = req.params.slug as string;
  if (!slug) {
    return errorResponse('Slug is required', 400, res);
  }

  try {
    const article = await articleService.unfavorite(slug, req.user!.id);

    const response = await formatArticleResponse(article as any, req.user!.id);

    res.json(response);
  } catch (error) {
    const err = error as Error & { statusCode?: number };
    return errorResponse(err.message, err.statusCode || 500, res);
  }
});

export { router as articlesRouter };
