import { NextRequest, NextResponse } from 'next/server';
import { connectDB } from '@/lib/db';
import { Article } from '@/models/Article';
import { Comment } from '@/models/Comment';
import { getUserFromRequest } from '@/lib/auth';
import { NotFoundError, ValidationError } from '@/lib/errors';
import { formatZodErrors, createCommentSchema } from '@/lib/validators';
import { withSpan } from '@/lib/telemetry';
import { logger, logError } from '@/lib/logger';
import { recordComment } from '@/lib/metrics';
import type { ApiResponse, JwtPayload } from '@/types';

interface CommentResponse {
  id: string;
  body: string;
  author: {
    id: string;
    username: string;
    bio: string;
    image: string;
  };
  createdAt: string;
  updatedAt: string;
}

interface CommentsListResponse {
  comments: CommentResponse[];
}

type RouteContext = { params: Promise<{ slug: string }> };

export async function GET(
  request: NextRequest,
  context: RouteContext
): Promise<NextResponse<ApiResponse<CommentsListResponse>>> {
  return withSpan('comments.list', async () => {
    try {
      await connectDB();

      const { slug } = await context.params;

      const article = await Article.findBySlug(slug);
      if (!article) {
        throw new NotFoundError('Article');
      }

      const comments = await Comment.findByArticle(article._id);

      const commentsData = comments.map((comment) => {
        const authorData = comment.authorId as unknown as {
          _id: { toString: () => string };
          username: string;
          bio?: string;
          image?: string;
        };

        return {
          id: comment._id.toString(),
          body: comment.body,
          author: {
            id: authorData._id.toString(),
            username: authorData.username,
            bio: authorData.bio || '',
            image: authorData.image || '',
          },
          createdAt: comment.createdAt.toISOString(),
          updatedAt: comment.updatedAt.toISOString(),
        };
      });

      recordComment('list', true);
      return NextResponse.json({
        success: true,
        data: { comments: commentsData },
      });
    } catch (error) {
      recordComment('list', false);
      if (error instanceof NotFoundError) {
        return NextResponse.json(
          { success: false, error: error.message },
          { status: error.statusCode }
        );
      }
      logError('Failed to list comments', error, { operation: 'comments.list' });
      return NextResponse.json(
        { success: false, error: 'Failed to list comments' },
        { status: 500 }
      );
    }
  });
}

export async function POST(
  request: NextRequest,
  context: RouteContext
): Promise<NextResponse<ApiResponse<CommentResponse>>> {
  let user: JwtPayload | null = null;
  try {
    user = getUserFromRequest(request);
  } catch {
    recordComment('create', false);
    return NextResponse.json(
      { success: false, error: 'Authentication required' },
      { status: 401 }
    );
  }

  return withSpan('comments.create', async () => {
    try {
      await connectDB();

      const { slug } = await context.params;

      const article = await Article.findBySlug(slug);
      if (!article) {
        throw new NotFoundError('Article');
      }

      const body = await request.json();
      const validation = createCommentSchema.safeParse(body);

      if (!validation.success) {
        const errors = formatZodErrors(validation.error);
        throw new ValidationError('Validation failed', errors);
      }

      const comment = await Comment.create({
        articleId: article._id,
        authorId: user!.userId,
        body: validation.data.body,
      });

      await comment.populate('authorId', 'username bio image');

      const authorData = comment.authorId as unknown as {
        _id: { toString: () => string };
        username: string;
        bio?: string;
        image?: string;
      };

      recordComment('create', true);
      logger.info('Comment created', { commentId: comment._id.toString(), articleId: article._id.toString(), userId: user!.userId });
      return NextResponse.json(
        {
          success: true,
          data: {
            id: comment._id.toString(),
            body: comment.body,
            author: {
              id: authorData._id.toString(),
              username: authorData.username,
              bio: authorData.bio || '',
              image: authorData.image || '',
            },
            createdAt: comment.createdAt.toISOString(),
            updatedAt: comment.updatedAt.toISOString(),
          },
        },
        { status: 201 }
      );
    } catch (error) {
      recordComment('create', false);
      if (error instanceof NotFoundError || error instanceof ValidationError) {
        return NextResponse.json(
          {
            success: false,
            error: error.message,
            details: error instanceof ValidationError ? error.details : undefined,
          },
          { status: error.statusCode }
        );
      }
      logError('Failed to create comment', error, { operation: 'comments.create' });
      return NextResponse.json(
        { success: false, error: 'Failed to create comment' },
        { status: 500 }
      );
    }
  });
}
