import { NextRequest, NextResponse } from 'next/server';
import { z } from 'zod';
import { connectDB } from '@/lib/db';
import { Article } from '@/models/Article';
import { withAuth, optionalAuth, getUserFromRequest } from '@/lib/auth';
import {
  ValidationError,
  NotFoundError,
  AuthorizationError,
} from '@/lib/errors';
import { formatZodErrors } from '@/lib/validators';
import { withSpan } from '@/lib/telemetry';
import { logger, logError } from '@/lib/logger';
import { recordArticle } from '@/lib/metrics';
import type { ApiResponse, JwtPayload } from '@/types';

const updateArticleSchema = z.object({
  title: z
    .string()
    .min(1, 'Title is required')
    .max(200, 'Title must be at most 200 characters')
    .optional(),
  description: z
    .string()
    .min(1, 'Description is required')
    .max(500, 'Description must be at most 500 characters')
    .optional(),
  body: z.string().min(1, 'Body is required').optional(),
  tags: z.array(z.string()).optional(),
});

interface ArticleResponse {
  id: string;
  slug: string;
  title: string;
  description: string;
  body: string;
  tags: string[];
  favoritesCount: number;
  author: {
    id: string;
    username: string;
    bio: string;
    image: string;
  };
  createdAt: string;
  updatedAt: string;
}

type RouteContext = { params: Promise<{ slug: string }> };

export async function GET(
  request: NextRequest,
  context: RouteContext
): Promise<NextResponse<ApiResponse<ArticleResponse>>> {
  return optionalAuth<ArticleResponse>(
    async (
      _req: NextRequest,
      _user: JwtPayload | null
    ): Promise<NextResponse<ApiResponse<ArticleResponse>>> => {
      return withSpan('articles.get', async () => {
        try {
          await connectDB();

          // Next.js 16: await params
          const { slug } = await context.params;

          const article = await Article.findBySlug(slug);
          if (!article) {
            throw new NotFoundError('Article');
          }

          await article.populate('authorId', 'username bio image');

          const authorData = article.authorId as unknown as {
            _id: { toString: () => string };
            username: string;
            bio?: string;
            image?: string;
          };

          recordArticle('view', true);
          return NextResponse.json({
            success: true,
            data: {
              id: article._id.toString(),
              slug: article.slug,
              title: article.title,
              description: article.description,
              body: article.body,
              tags: article.tags,
              favoritesCount: article.favoritesCount,
              author: {
                id: authorData._id.toString(),
                username: authorData.username,
                bio: authorData.bio || '',
                image: authorData.image || '',
              },
              createdAt: article.createdAt.toISOString(),
              updatedAt: article.updatedAt.toISOString(),
            },
          });
        } catch (error) {
          recordArticle('view', false);
          if (error instanceof NotFoundError) {
            return NextResponse.json(
              { success: false, error: error.message },
              { status: error.statusCode }
            );
          }
          logError('Failed to get article', error, { operation: 'articles.get' });
          return NextResponse.json(
            { success: false, error: 'Failed to get article' },
            { status: 500 }
          );
        }
      });
    }
  )(request);
}

export async function PUT(
  request: NextRequest,
  context: RouteContext
): Promise<NextResponse<ApiResponse<ArticleResponse>>> {
  return withAuth<ArticleResponse>(
    async (
      req: NextRequest,
      user: JwtPayload
    ): Promise<NextResponse<ApiResponse<ArticleResponse>>> => {
      return withSpan('articles.update', async () => {
        try {
          await connectDB();

          // Next.js 16: await params
          const { slug } = await context.params;

          const article = await Article.findBySlug(slug);
          if (!article) {
            throw new NotFoundError('Article');
          }

          if (article.authorId.toString() !== user.userId) {
            throw new AuthorizationError('You can only edit your own articles');
          }

          const body = await req.json();
          const validation = updateArticleSchema.safeParse(body);

          if (!validation.success) {
            const errors = formatZodErrors(validation.error);
            throw new ValidationError('Validation failed', errors);
          }

          const updateData = validation.data;
          Object.assign(article, updateData);
          await article.save();

          await article.populate('authorId', 'username bio image');

          const authorData = article.authorId as unknown as {
            _id: { toString: () => string };
            username: string;
            bio?: string;
            image?: string;
          };

          recordArticle('update', true);
          logger.info('Article updated', { articleId: article._id.toString(), slug: article.slug, userId: user.userId });
          return NextResponse.json({
            success: true,
            data: {
              id: article._id.toString(),
              slug: article.slug,
              title: article.title,
              description: article.description,
              body: article.body,
              tags: article.tags,
              favoritesCount: article.favoritesCount,
              author: {
                id: authorData._id.toString(),
                username: authorData.username,
                bio: authorData.bio || '',
                image: authorData.image || '',
              },
              createdAt: article.createdAt.toISOString(),
              updatedAt: article.updatedAt.toISOString(),
            },
          });
        } catch (error) {
          recordArticle('update', false);
          if (
            error instanceof NotFoundError ||
            error instanceof AuthorizationError ||
            error instanceof ValidationError
          ) {
            return NextResponse.json(
              {
                success: false,
                error: error.message,
                details: error instanceof ValidationError ? error.details : undefined,
              },
              { status: error.statusCode }
            );
          }
          logError('Failed to update article', error, { operation: 'articles.update' });
          return NextResponse.json(
            { success: false, error: 'Failed to update article' },
            { status: 500 }
          );
        }
      });
    }
  )(request);
}

export async function DELETE(
  request: NextRequest,
  context: RouteContext
): Promise<NextResponse<ApiResponse<{ deleted: boolean }>>> {
  try {
    const user = getUserFromRequest(request);

    return withSpan('articles.delete', async () => {
      try {
        await connectDB();

        // Next.js 16: await params
        const { slug } = await context.params;

        const article = await Article.findBySlug(slug);
        if (!article) {
          throw new NotFoundError('Article');
        }

        if (article.authorId.toString() !== user.userId) {
          throw new AuthorizationError(
            'You can only delete your own articles'
          );
        }

        const articleId = article._id.toString();
        const articleSlug = article.slug;
        await article.deleteOne();

        recordArticle('delete', true);
        logger.info('Article deleted', { articleId, slug: articleSlug, userId: user.userId });
        return NextResponse.json({
          success: true,
          data: { deleted: true },
        });
      } catch (error) {
        recordArticle('delete', false);
        if (
          error instanceof NotFoundError ||
          error instanceof AuthorizationError
        ) {
          return NextResponse.json(
            { success: false, error: error.message },
            { status: error.statusCode }
          );
        }
        logError('Failed to delete article', error, { operation: 'articles.delete' });
        return NextResponse.json(
          { success: false, error: 'Failed to delete article' },
          { status: 500 }
        );
      }
    });
  } catch {
    recordArticle('delete', false);
    return NextResponse.json(
      { success: false, error: 'Authentication required' },
      { status: 401 }
    );
  }
}
