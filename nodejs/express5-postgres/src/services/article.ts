import { eq, sql, ilike, desc, and } from 'drizzle-orm';
import { trace, SpanStatusCode, metrics } from '@opentelemetry/api';
import { db } from '../db/index.js';
import { articles, favorites, type Article } from '../db/schema.js';
import { logger } from '../logger.js';
import type { PaginationParams, PaginatedResponse } from '../types/index.js';

const tracer = trace.getTracer('article-service');
const meter = metrics.getMeter('article-service');

const articlesCreatedCounter = meter.createCounter('articles.created', {
  description: 'Number of articles created',
  unit: '1',
});

function generateSlug(title: string): string {
  return (
    title
      .toLowerCase()
      .replace(/[^a-z0-9]+/g, '-')
      .replace(/^-|-$/g, '') +
    '-' +
    Date.now().toString(36)
  );
}

export class ArticleService {
  async create(
    authorId: number,
    data: { title: string; description?: string; body: string }
  ): Promise<Article> {
    return tracer.startActiveSpan('article.create', async (span) => {
      try {
        span.setAttribute('user.id', authorId);

        const slug = generateSlug(data.title);

        const [article] = await db
          .insert(articles)
          .values({
            slug,
            title: data.title,
            description: data.description || '',
            body: data.body,
            authorId,
          })
          .returning();

        if (!article) {
          throw new Error('Failed to create article');
        }

        span.setAttribute('article.id', article.id);
        span.setAttribute('article.slug', article.slug);
        span.setStatus({ code: SpanStatusCode.OK });

        articlesCreatedCounter.add(1, { author_id: String(authorId) });
        logger.info({ articleId: article.id, slug: article.slug }, 'Article created');

        return article;
      } catch (error) {
        span.recordException(error as Error);
        span.setStatus({ code: SpanStatusCode.ERROR });
        throw error;
      } finally {
        span.end();
      }
    });
  }

  async findBySlug(slug: string): Promise<Article | null> {
    const article = await db.query.articles.findFirst({
      where: eq(articles.slug, slug),
      with: { author: true },
    });
    return article || null;
  }

  async list(
    params: PaginationParams & { search?: string }
  ): Promise<PaginatedResponse<Article & { author: { id: number; name: string; email: string } }>> {
    const { page, perPage, search } = params;
    const offset = (page - 1) * perPage;

    const whereClause = search ? ilike(articles.title, `%${search}%`) : undefined;

    const [articleList, countResult] = await Promise.all([
      db.query.articles.findMany({
        where: whereClause,
        with: {
          author: {
            columns: { id: true, name: true, email: true },
          },
        },
        orderBy: [desc(articles.createdAt)],
        limit: perPage,
        offset,
      }),
      db
        .select({ count: sql<number>`count(*)` })
        .from(articles)
        .where(whereClause),
    ]);

    const total = countResult[0]?.count ?? 0;

    return {
      data: articleList,
      total: Number(total),
      page,
      perPage,
    };
  }

  async update(
    slug: string,
    authorId: number,
    data: { title?: string; description?: string; body?: string }
  ): Promise<Article> {
    return tracer.startActiveSpan('article.update', async (span) => {
      try {
        span.setAttribute('article.slug', slug);
        span.setAttribute('user.id', authorId);

        const existing = await this.findBySlug(slug);

        if (!existing) {
          span.setStatus({ code: SpanStatusCode.ERROR, message: 'Article not found' });
          throw Object.assign(new Error('Article not found'), { statusCode: 404 });
        }

        if (existing.authorId !== authorId) {
          span.setAttribute('auth.status', 'forbidden');
          span.setStatus({ code: SpanStatusCode.ERROR, message: 'Forbidden' });
          throw Object.assign(new Error('You can only update your own articles'), {
            statusCode: 403,
          });
        }

        const [updated] = await db
          .update(articles)
          .set({
            ...data,
            updatedAt: new Date(),
          })
          .where(eq(articles.slug, slug))
          .returning();

        if (!updated) {
          throw new Error('Failed to update article');
        }

        span.setAttribute('article.id', updated.id);
        span.setStatus({ code: SpanStatusCode.OK });

        logger.info({ articleId: updated.id, slug }, 'Article updated');

        return updated;
      } catch (error) {
        span.recordException(error as Error);
        span.setStatus({ code: SpanStatusCode.ERROR });
        throw error;
      } finally {
        span.end();
      }
    });
  }

  async delete(slug: string, authorId: number): Promise<void> {
    return tracer.startActiveSpan('article.delete', async (span) => {
      try {
        span.setAttribute('article.slug', slug);
        span.setAttribute('user.id', authorId);

        const existing = await this.findBySlug(slug);

        if (!existing) {
          span.setStatus({ code: SpanStatusCode.ERROR, message: 'Article not found' });
          throw Object.assign(new Error('Article not found'), { statusCode: 404 });
        }

        if (existing.authorId !== authorId) {
          span.setAttribute('auth.status', 'forbidden');
          span.setStatus({ code: SpanStatusCode.ERROR, message: 'Forbidden' });
          throw Object.assign(new Error('You can only delete your own articles'), {
            statusCode: 403,
          });
        }

        await db.delete(articles).where(eq(articles.slug, slug));

        span.setStatus({ code: SpanStatusCode.OK });
        logger.info({ slug }, 'Article deleted');
      } catch (error) {
        span.recordException(error as Error);
        span.setStatus({ code: SpanStatusCode.ERROR });
        throw error;
      } finally {
        span.end();
      }
    });
  }

  async favorite(slug: string, userId: number): Promise<Article> {
    return tracer.startActiveSpan('article.favorite', async (span) => {
      try {
        span.setAttribute('article.slug', slug);
        span.setAttribute('user.id', userId);

        const article = await this.findBySlug(slug);

        if (!article) {
          span.setStatus({ code: SpanStatusCode.ERROR, message: 'Article not found' });
          throw Object.assign(new Error('Article not found'), { statusCode: 404 });
        }

        const existingFavorite = await db.query.favorites.findFirst({
          where: and(eq(favorites.userId, userId), eq(favorites.articleId, article.id)),
        });

        if (existingFavorite) {
          span.setStatus({ code: SpanStatusCode.OK });
          return article;
        }

        await db.transaction(async (tx) => {
          await tx.insert(favorites).values({
            userId,
            articleId: article.id,
          });

          await tx
            .update(articles)
            .set({
              favoritesCount: sql`${articles.favoritesCount} + 1`,
            })
            .where(eq(articles.id, article.id));
        });

        const updated = await this.findBySlug(slug);

        span.setStatus({ code: SpanStatusCode.OK });
        logger.info({ articleId: article.id, userId }, 'Article favorited');

        return updated!;
      } catch (error) {
        span.recordException(error as Error);
        span.setStatus({ code: SpanStatusCode.ERROR });
        throw error;
      } finally {
        span.end();
      }
    });
  }

  async unfavorite(slug: string, userId: number): Promise<Article> {
    return tracer.startActiveSpan('article.unfavorite', async (span) => {
      try {
        span.setAttribute('article.slug', slug);
        span.setAttribute('user.id', userId);

        const article = await this.findBySlug(slug);

        if (!article) {
          span.setStatus({ code: SpanStatusCode.ERROR, message: 'Article not found' });
          throw Object.assign(new Error('Article not found'), { statusCode: 404 });
        }

        const existingFavorite = await db.query.favorites.findFirst({
          where: and(eq(favorites.userId, userId), eq(favorites.articleId, article.id)),
        });

        if (existingFavorite) {
          await db.transaction(async (tx) => {
            await tx
              .delete(favorites)
              .where(and(eq(favorites.userId, userId), eq(favorites.articleId, article.id)));

            await tx
              .update(articles)
              .set({
                favoritesCount: sql`GREATEST(${articles.favoritesCount} - 1, 0)`,
              })
              .where(eq(articles.id, article.id));
          });
        }

        const updated = await this.findBySlug(slug);

        span.setStatus({ code: SpanStatusCode.OK });
        logger.info({ articleId: article.id, userId }, 'Article unfavorited');

        return updated!;
      } catch (error) {
        span.recordException(error as Error);
        span.setStatus({ code: SpanStatusCode.ERROR });
        throw error;
      } finally {
        span.end();
      }
    });
  }

  async isFavoritedBy(articleId: number, userId: number | undefined): Promise<boolean> {
    if (!userId) return false;

    const favorite = await db.query.favorites.findFirst({
      where: and(eq(favorites.userId, userId), eq(favorites.articleId, articleId)),
    });

    return !!favorite;
  }
}

export const articleService = new ArticleService();
