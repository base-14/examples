import { NextRequest, NextResponse } from 'next/server';
import mongoose from 'mongoose';
import { connectDB } from '@/lib/db';
import { Article } from '@/models/Article';
import { Favorite } from '@/models/Favorite';
import { getUserFromRequest } from '@/lib/auth';
import { NotFoundError, ConflictError } from '@/lib/errors';
import { withSpan } from '@/lib/telemetry';
import { logger, logError } from '@/lib/logger';
import { recordFavorite } from '@/lib/metrics';
import type { ApiResponse } from '@/types';

interface FavoriteResponse {
  articleId: string;
  slug: string;
  favorited: boolean;
  favoritesCount: number;
}

type RouteContext = { params: Promise<{ slug: string }> };

export async function POST(
  request: NextRequest,
  context: RouteContext
): Promise<NextResponse<ApiResponse<FavoriteResponse>>> {
  try {
    const user = getUserFromRequest(request);

    return withSpan('articles.favorite', async () => {
      const session = await mongoose.startSession();
      try {
        await connectDB();

        const { slug } = await context.params;

        const article = await Article.findBySlug(slug);
        if (!article) {
          throw new NotFoundError('Article');
        }

        const existingFavorite = await Favorite.findOne({
          userId: user.userId,
          articleId: article._id,
        });

        if (existingFavorite) {
          throw new ConflictError('Article already favorited');
        }

        let updatedFavoritesCount = article.favoritesCount + 1;

        await session.withTransaction(async () => {
          await Favorite.create(
            [{ userId: user.userId, articleId: article._id }],
            { session }
          );
          const updatedArticle = await Article.findByIdAndUpdate(
            article._id,
            { $inc: { favoritesCount: 1 } },
            { session, new: true }
          );
          if (updatedArticle) {
            updatedFavoritesCount = updatedArticle.favoritesCount;
          }
        });

        recordFavorite('favorite', true);
        logger.info('Article favorited', { articleId: article._id.toString(), slug: article.slug, userId: user.userId });
        return NextResponse.json({
          success: true,
          data: {
            articleId: article._id.toString(),
            slug: article.slug,
            favorited: true,
            favoritesCount: updatedFavoritesCount,
          },
        });
      } catch (error) {
        recordFavorite('favorite', false);
        if (error instanceof NotFoundError || error instanceof ConflictError) {
          return NextResponse.json(
            { success: false, error: error.message },
            { status: error.statusCode }
          );
        }
        logError('Failed to favorite article', error, { operation: 'articles.favorite' });
        return NextResponse.json(
          { success: false, error: 'Failed to favorite article' },
          { status: 500 }
        );
      } finally {
        await session.endSession();
      }
    });
  } catch {
    recordFavorite('favorite', false);
    return NextResponse.json(
      { success: false, error: 'Authentication required' },
      { status: 401 }
    );
  }
}

export async function DELETE(
  request: NextRequest,
  context: RouteContext
): Promise<NextResponse<ApiResponse<FavoriteResponse>>> {
  try {
    const user = getUserFromRequest(request);

    return withSpan('articles.unfavorite', async () => {
      const session = await mongoose.startSession();
      try {
        await connectDB();

        const { slug } = await context.params;

        const article = await Article.findBySlug(slug);
        if (!article) {
          throw new NotFoundError('Article');
        }

        const favorite = await Favorite.findOne({
          userId: user.userId,
          articleId: article._id,
        });

        if (!favorite) {
          throw new NotFoundError('Favorite');
        }

        let updatedFavoritesCount = Math.max(0, article.favoritesCount - 1);

        await session.withTransaction(async () => {
          await Favorite.deleteOne({ _id: favorite._id }, { session });
          const updatedArticle = await Article.findByIdAndUpdate(
            article._id,
            { $inc: { favoritesCount: -1 } },
            { session, new: true }
          );
          if (updatedArticle) {
            updatedFavoritesCount = updatedArticle.favoritesCount;
          }
        });

        recordFavorite('unfavorite', true);
        logger.info('Article unfavorited', { articleId: article._id.toString(), slug: article.slug, userId: user.userId });
        return NextResponse.json({
          success: true,
          data: {
            articleId: article._id.toString(),
            slug: article.slug,
            favorited: false,
            favoritesCount: updatedFavoritesCount,
          },
        });
      } catch (error) {
        recordFavorite('unfavorite', false);
        if (error instanceof NotFoundError) {
          return NextResponse.json(
            { success: false, error: error.message },
            { status: error.statusCode }
          );
        }
        logError('Failed to unfavorite article', error, { operation: 'articles.unfavorite' });
        return NextResponse.json(
          { success: false, error: 'Failed to unfavorite article' },
          { status: 500 }
        );
      } finally {
        await session.endSession();
      }
    });
  } catch {
    recordFavorite('unfavorite', false);
    return NextResponse.json(
      { success: false, error: 'Authentication required' },
      { status: 401 }
    );
  }
}
