import { eq, desc, and, sql, ilike } from 'drizzle-orm';
import { trace, SpanStatusCode } from '@opentelemetry/api';
import { db } from '../db/index.js';
import { articles, users, favorites, Article, NewArticle } from '../db/schema.js';
import {
  enqueueArticleCreatedNotification,
  enqueueArticleFavoritedNotification,
} from '../jobs/tasks/notification.js';
import { createLogger } from './logger.js';

const logger = createLogger('article-service');
const tracer = trace.getTracer('article-service');

export interface CreateArticleInput {
  title: string;
  description?: string;
  body: string;
}

export interface UpdateArticleInput {
  title?: string;
  description?: string;
  body?: string;
}

export interface ArticleListParams {
  limit?: number;
  offset?: number;
  author?: string;
}

export interface ArticleResponse {
  id: number;
  slug: string;
  title: string;
  description: string | null;
  body: string;
  favoritesCount: number;
  createdAt: Date;
  updatedAt: Date;
  author: {
    id: number;
    name: string;
    bio: string | null;
    image: string | null;
  };
  favorited: boolean;
}

function generateSlug(title: string): string {
  const baseSlug = title
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-|-$/g, '');
  const uniqueSuffix = Date.now().toString(36);
  return `${baseSlug}-${uniqueSuffix}`;
}

async function toArticleResponse(
  article: Article & { author: { id: number; name: string; bio: string | null; image: string | null } },
  userId?: number
): Promise<ArticleResponse> {
  let favorited = false;

  if (userId) {
    const [fav] = await db
      .select()
      .from(favorites)
      .where(and(eq(favorites.userId, userId), eq(favorites.articleId, article.id)))
      .limit(1);
    favorited = !!fav;
  }

  return {
    id: article.id,
    slug: article.slug,
    title: article.title,
    description: article.description,
    body: article.body,
    favoritesCount: article.favoritesCount,
    createdAt: article.createdAt,
    updatedAt: article.updatedAt,
    author: article.author,
    favorited,
  };
}

export async function createArticle(
  authorId: number,
  input: CreateArticleInput
): Promise<ArticleResponse> {
  return tracer.startActiveSpan('article.create', async (span) => {
    try {
      span.setAttribute('user.id', authorId);

      const slug = generateSlug(input.title);

      const [newArticle] = await db
        .insert(articles)
        .values({
          slug,
          title: input.title,
          description: input.description || null,
          body: input.body,
          authorId,
        } satisfies NewArticle)
        .returning();

      const [author] = await db
        .select({
          id: users.id,
          name: users.name,
          bio: users.bio,
          image: users.image,
        })
        .from(users)
        .where(eq(users.id, authorId))
        .limit(1);

      span.setAttribute('article.id', newArticle.id);
      span.setAttribute('article.slug', newArticle.slug);
      span.setStatus({ code: SpanStatusCode.OK });

      enqueueArticleCreatedNotification({
        articleId: newArticle.id,
        articleSlug: newArticle.slug,
        authorId: author.id,
        authorName: author.name,
        title: newArticle.title,
      }).catch((err) => {
        logger.error({ error: err }, 'Failed to enqueue article created notification');
      });

      return toArticleResponse({ ...newArticle, author }, authorId);
    } catch (error) {
      span.recordException(error as Error);
      span.setStatus({ code: SpanStatusCode.ERROR, message: (error as Error).message });
      throw error;
    } finally {
      span.end();
    }
  });
}

export async function findArticles(
  params: ArticleListParams,
  userId?: number
): Promise<{ articles: ArticleResponse[]; articlesCount: number }> {
  return tracer.startActiveSpan('article.list', async (span) => {
    try {
      const limit = params.limit || 20;
      const offset = params.offset || 0;

      span.setAttribute('query.limit', limit);
      span.setAttribute('query.offset', offset);

      let query = db
        .select({
          article: articles,
          author: {
            id: users.id,
            name: users.name,
            bio: users.bio,
            image: users.image,
          },
        })
        .from(articles)
        .innerJoin(users, eq(articles.authorId, users.id))
        .orderBy(desc(articles.createdAt))
        .limit(limit)
        .offset(offset);

      if (params.author) {
        query = query.where(ilike(users.name, `%${params.author}%`)) as typeof query;
      }

      const results = await query;

      const [countResult] = await db
        .select({ count: sql<number>`count(*)::int` })
        .from(articles);

      const articleResponses = await Promise.all(
        results.map((r) => toArticleResponse({ ...r.article, author: r.author }, userId))
      );

      span.setAttribute('results.count', articleResponses.length);
      span.setStatus({ code: SpanStatusCode.OK });

      return {
        articles: articleResponses,
        articlesCount: countResult.count,
      };
    } catch (error) {
      span.recordException(error as Error);
      span.setStatus({ code: SpanStatusCode.ERROR });
      throw error;
    } finally {
      span.end();
    }
  });
}

export async function findBySlug(
  slug: string,
  userId?: number
): Promise<ArticleResponse | null> {
  return tracer.startActiveSpan('article.get', async (span) => {
    try {
      span.setAttribute('article.slug', slug);

      const [result] = await db
        .select({
          article: articles,
          author: {
            id: users.id,
            name: users.name,
            bio: users.bio,
            image: users.image,
          },
        })
        .from(articles)
        .innerJoin(users, eq(articles.authorId, users.id))
        .where(eq(articles.slug, slug))
        .limit(1);

      if (!result) {
        span.setStatus({ code: SpanStatusCode.OK });
        return null;
      }

      span.setAttribute('article.id', result.article.id);
      span.setStatus({ code: SpanStatusCode.OK });

      return toArticleResponse({ ...result.article, author: result.author }, userId);
    } catch (error) {
      span.recordException(error as Error);
      span.setStatus({ code: SpanStatusCode.ERROR });
      throw error;
    } finally {
      span.end();
    }
  });
}

export async function updateArticle(
  slug: string,
  userId: number,
  input: UpdateArticleInput
): Promise<ArticleResponse | null> {
  return tracer.startActiveSpan('article.update', async (span) => {
    try {
      span.setAttribute('article.slug', slug);
      span.setAttribute('user.id', userId);

      const [existing] = await db
        .select()
        .from(articles)
        .where(eq(articles.slug, slug))
        .limit(1);

      if (!existing) {
        span.setStatus({ code: SpanStatusCode.OK });
        return null;
      }

      if (existing.authorId !== userId) {
        span.setStatus({ code: SpanStatusCode.ERROR, message: 'Forbidden' });
        throw new Error('Forbidden');
      }

      const updateData: Partial<Article> = {
        ...input,
        updatedAt: new Date(),
      };

      if (input.title && input.title !== existing.title) {
        updateData.slug = generateSlug(input.title);
      }

      const [updated] = await db
        .update(articles)
        .set(updateData)
        .where(eq(articles.id, existing.id))
        .returning();

      const [author] = await db
        .select({
          id: users.id,
          name: users.name,
          bio: users.bio,
          image: users.image,
        })
        .from(users)
        .where(eq(users.id, userId))
        .limit(1);

      span.setAttribute('article.id', updated.id);
      span.setStatus({ code: SpanStatusCode.OK });

      return toArticleResponse({ ...updated, author }, userId);
    } catch (error) {
      span.recordException(error as Error);
      span.setStatus({ code: SpanStatusCode.ERROR, message: (error as Error).message });
      throw error;
    } finally {
      span.end();
    }
  });
}

export async function deleteArticle(slug: string, userId: number): Promise<boolean> {
  return tracer.startActiveSpan('article.delete', async (span) => {
    try {
      span.setAttribute('article.slug', slug);
      span.setAttribute('user.id', userId);

      const [existing] = await db
        .select()
        .from(articles)
        .where(eq(articles.slug, slug))
        .limit(1);

      if (!existing) {
        span.setStatus({ code: SpanStatusCode.OK });
        return false;
      }

      if (existing.authorId !== userId) {
        span.setStatus({ code: SpanStatusCode.ERROR, message: 'Forbidden' });
        throw new Error('Forbidden');
      }

      await db.delete(articles).where(eq(articles.id, existing.id));

      span.setAttribute('article.id', existing.id);
      span.setStatus({ code: SpanStatusCode.OK });

      return true;
    } catch (error) {
      span.recordException(error as Error);
      span.setStatus({ code: SpanStatusCode.ERROR, message: (error as Error).message });
      throw error;
    } finally {
      span.end();
    }
  });
}

export async function favoriteArticle(
  slug: string,
  userId: number
): Promise<ArticleResponse | null> {
  return tracer.startActiveSpan('article.favorite', async (span) => {
    try {
      span.setAttribute('article.slug', slug);
      span.setAttribute('user.id', userId);

      const result = await db.transaction(async (tx) => {
        const [article] = await tx
          .select({
            article: articles,
            author: {
              id: users.id,
              name: users.name,
              bio: users.bio,
              image: users.image,
            },
          })
          .from(articles)
          .innerJoin(users, eq(articles.authorId, users.id))
          .where(eq(articles.slug, slug))
          .limit(1);

        if (!article) return null;

        const [existingFav] = await tx
          .select()
          .from(favorites)
          .where(and(eq(favorites.userId, userId), eq(favorites.articleId, article.article.id)))
          .limit(1);

        if (!existingFav) {
          await tx.insert(favorites).values({
            userId,
            articleId: article.article.id,
          });

          await tx
            .update(articles)
            .set({ favoritesCount: sql`${articles.favoritesCount} + 1` })
            .where(eq(articles.id, article.article.id));

          article.article.favoritesCount += 1;
        }

        return article;
      });

      if (!result) {
        span.setStatus({ code: SpanStatusCode.OK });
        return null;
      }

      span.setAttribute('article.id', result.article.id);
      span.addEvent('favorite_added');
      span.setStatus({ code: SpanStatusCode.OK });

      db.select({ name: users.name })
        .from(users)
        .where(eq(users.id, userId))
        .limit(1)
        .then(([user]) => {
          if (user) {
            return enqueueArticleFavoritedNotification({
              articleId: result.article.id,
              articleSlug: result.article.slug,
              userId,
              userName: user.name,
            });
          }
        })
        .catch((err) => {
          logger.error({ error: err }, 'Failed to enqueue article favorited notification');
        });

      return toArticleResponse({ ...result.article, author: result.author }, userId);
    } catch (error) {
      span.recordException(error as Error);
      span.setStatus({ code: SpanStatusCode.ERROR });
      throw error;
    } finally {
      span.end();
    }
  });
}

export async function unfavoriteArticle(
  slug: string,
  userId: number
): Promise<ArticleResponse | null> {
  return tracer.startActiveSpan('article.unfavorite', async (span) => {
    try {
      span.setAttribute('article.slug', slug);
      span.setAttribute('user.id', userId);

      const result = await db.transaction(async (tx) => {
        const [article] = await tx
          .select({
            article: articles,
            author: {
              id: users.id,
              name: users.name,
              bio: users.bio,
              image: users.image,
            },
          })
          .from(articles)
          .innerJoin(users, eq(articles.authorId, users.id))
          .where(eq(articles.slug, slug))
          .limit(1);

        if (!article) return null;

        const [existingFav] = await tx
          .select()
          .from(favorites)
          .where(and(eq(favorites.userId, userId), eq(favorites.articleId, article.article.id)))
          .limit(1);

        if (existingFav) {
          await tx
            .delete(favorites)
            .where(and(eq(favorites.userId, userId), eq(favorites.articleId, article.article.id)));

          await tx
            .update(articles)
            .set({ favoritesCount: sql`GREATEST(${articles.favoritesCount} - 1, 0)` })
            .where(eq(articles.id, article.article.id));

          article.article.favoritesCount = Math.max(0, article.article.favoritesCount - 1);
        }

        return article;
      });

      if (!result) {
        span.setStatus({ code: SpanStatusCode.OK });
        return null;
      }

      span.setAttribute('article.id', result.article.id);
      span.addEvent('favorite_removed');
      span.setStatus({ code: SpanStatusCode.OK });

      return toArticleResponse({ ...result.article, author: result.author }, userId);
    } catch (error) {
      span.recordException(error as Error);
      span.setStatus({ code: SpanStatusCode.ERROR });
      throw error;
    } finally {
      span.end();
    }
  });
}
