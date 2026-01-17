import { NextRequest, NextResponse } from 'next/server';
import { connectDB } from '@/lib/db';
import { Article } from '@/models/Article';
import { Comment } from '@/models/Comment';
import { getUserFromRequest } from '@/lib/auth';
import { NotFoundError, AuthorizationError } from '@/lib/errors';
import { withSpan } from '@/lib/telemetry';
import { logger, logError } from '@/lib/logger';
import { recordComment } from '@/lib/metrics';
import type { ApiResponse, JwtPayload } from '@/types';

type RouteContext = { params: Promise<{ slug: string; commentId: string }> };

export async function DELETE(
  request: NextRequest,
  context: RouteContext
): Promise<NextResponse<ApiResponse<{ deleted: boolean }>>> {
  let user: JwtPayload | null = null;
  try {
    user = getUserFromRequest(request);
  } catch {
    recordComment('delete', false);
    return NextResponse.json(
      { success: false, error: 'Authentication required' },
      { status: 401 }
    );
  }

  return withSpan('comments.delete', async () => {
    try {
      await connectDB();

      const { slug, commentId } = await context.params;

      const article = await Article.findBySlug(slug);
      if (!article) {
        throw new NotFoundError('Article');
      }

      const comment = await Comment.findById(commentId);
      if (!comment) {
        throw new NotFoundError('Comment');
      }

      if (comment.articleId.toString() !== article._id.toString()) {
        throw new NotFoundError('Comment');
      }

      if (comment.authorId.toString() !== user!.userId) {
        throw new AuthorizationError('You can only delete your own comments');
      }

      const deletedCommentId = comment._id.toString();
      await comment.deleteOne();

      recordComment('delete', true);
      logger.info('Comment deleted', { commentId: deletedCommentId, articleId: article._id.toString(), userId: user!.userId });
      return NextResponse.json({
        success: true,
        data: { deleted: true },
      });
    } catch (error) {
      recordComment('delete', false);
      if (error instanceof NotFoundError || error instanceof AuthorizationError) {
        return NextResponse.json(
          { success: false, error: error.message },
          { status: error.statusCode }
        );
      }
      logError('Failed to delete comment', error, { operation: 'comments.delete' });
      return NextResponse.json(
        { success: false, error: 'Failed to delete comment' },
        { status: 500 }
      );
    }
  });
}
