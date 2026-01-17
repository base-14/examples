import { NextRequest, NextResponse } from 'next/server';
import { z } from 'zod';
import { connectDB } from '@/lib/db';
import { Article } from '@/models/Article';
import { User } from '@/models/User';
import { withAuth, optionalAuth } from '@/lib/auth';
import { ValidationError } from '@/lib/errors';
import { formatZodErrors, paginationSchema } from '@/lib/validators';
import { withSpan } from '@/lib/telemetry';
import { logger, logError } from '@/lib/logger';
import { recordArticle } from '@/lib/metrics';
import type { ApiResponse, JwtPayload, PaginatedResponse } from '@/types';

const createArticleSchema = z.object({
  title: z
    .string()
    .min(1, 'Title is required')
    .max(200, 'Title must be at most 200 characters'),
  description: z
    .string()
    .min(1, 'Description is required')
    .max(500, 'Description must be at most 500 characters'),
  body: z.string().min(1, 'Body is required'),
  tags: z.array(z.string()).default([]),
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

export const GET = optionalAuth<PaginatedResponse<ArticleResponse>>(
  async (
    request: NextRequest,
    _user: JwtPayload | null
  ): Promise<NextResponse<ApiResponse<PaginatedResponse<ArticleResponse>>>> => {
    return withSpan('articles.list', async () => {
      try {
        await connectDB();

        const { searchParams } = new URL(request.url);
        const paginationResult = paginationSchema.safeParse({
          page: searchParams.get('page'),
          limit: searchParams.get('limit'),
        });

        if (!paginationResult.success) {
          const errors = formatZodErrors(paginationResult.error);
          throw new ValidationError('Invalid pagination', errors);
        }

        const { page, limit } = paginationResult.data;
        const skip = (page - 1) * limit;

        const tag = searchParams.get('tag');
        const author = searchParams.get('author');

        const query: Record<string, unknown> = {};

        if (tag) {
          query.tags = tag;
        }

        if (author) {
          const authorUser = await User.findOne({ username: author });
          if (authorUser) {
            query.authorId = authorUser._id;
          } else {
            return NextResponse.json({
              success: true,
              data: {
                data: [],
                pagination: {
                  page,
                  limit,
                  total: 0,
                  totalPages: 0,
                  hasNext: false,
                  hasPrev: false,
                },
              },
            });
          }
        }

        const [articles, total] = await Promise.all([
          Article.find(query)
            .sort({ createdAt: -1 })
            .skip(skip)
            .limit(limit)
            .populate('authorId', 'username bio image'),
          Article.countDocuments(query),
        ]);

        const totalPages = Math.ceil(total / limit);

        const articleResponses: ArticleResponse[] = articles.map((article) => {
          const authorData = article.authorId as unknown as {
            _id: { toString: () => string };
            username: string;
            bio?: string;
            image?: string;
          };

          return {
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
          };
        });

        recordArticle('list', true);
        return NextResponse.json({
          success: true,
          data: {
            data: articleResponses,
            pagination: {
              page,
              limit,
              total,
              totalPages,
              hasNext: page < totalPages,
              hasPrev: page > 1,
            },
          },
        });
      } catch (error) {
        recordArticle('list', false);
        if (error instanceof ValidationError) {
          return NextResponse.json(
            { success: false, error: error.message, details: error.details },
            { status: error.statusCode }
          );
        }
        logError('Failed to list articles', error, { operation: 'articles.list' });
        return NextResponse.json(
          { success: false, error: 'Failed to list articles' },
          { status: 500 }
        );
      }
    });
  }
);

export const POST = withAuth<ArticleResponse>(
  async (
    request: NextRequest,
    user: JwtPayload
  ): Promise<NextResponse<ApiResponse<ArticleResponse>>> => {
    return withSpan('articles.create', async () => {
      try {
        await connectDB();

        const body = await request.json();
        const validation = createArticleSchema.safeParse(body);

        if (!validation.success) {
          const errors = formatZodErrors(validation.error);
          throw new ValidationError('Validation failed', errors);
        }

        const { title, description, body: articleBody, tags } = validation.data;

        const article = await Article.create({
          title,
          description,
          body: articleBody,
          tags,
          authorId: user.userId,
        });

        const authorData = await User.findById(user.userId);

        recordArticle('create', true);
        logger.info('Article created', { articleId: article._id.toString(), slug: article.slug, authorId: user.userId });
        return NextResponse.json(
          {
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
                id: authorData?._id.toString() || user.userId,
                username: authorData?.username || '',
                bio: authorData?.bio || '',
                image: authorData?.image || '',
              },
              createdAt: article.createdAt.toISOString(),
              updatedAt: article.updatedAt.toISOString(),
            },
          },
          { status: 201 }
        );
      } catch (error) {
        recordArticle('create', false);
        if (error instanceof ValidationError) {
          return NextResponse.json(
            { success: false, error: error.message, details: error.details },
            { status: error.statusCode }
          );
        }
        logError('Failed to create article', error, { operation: 'articles.create' });
        return NextResponse.json(
          { success: false, error: 'Failed to create article' },
          { status: 500 }
        );
      }
    });
  }
);
