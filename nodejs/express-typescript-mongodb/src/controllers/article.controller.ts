import type { Request, Response, NextFunction } from 'express';
import type { Server } from 'socket.io';
import { propagation, context as otelContext } from '@opentelemetry/api';
import { Article } from '../models/Article.js';
import { Favorite } from '../models/Favorite.js';
import { publishQueue } from '../jobs/queue.js';
import { articleMetrics, jobMetrics } from '../utils/metrics.js';
import { emitArticleEvent } from '../utils/socketEmitter.js';
import { withSpan, setSpanError } from '../utils/tracing.js';
import {
  AuthenticationError,
  AuthorizationError,
  NotFoundError,
  ValidationError,
  ConflictError,
} from '../utils/errors.js';

const TRACER_NAME = 'article-controller';

export async function createArticle(
  req: Request,
  res: Response,
  next: NextFunction
): Promise<void> {
  try {
    await withSpan(TRACER_NAME, 'article.create', async (span) => {
      const user = req.user;
      if (!user) {
        setSpanError(span, 'User not authenticated');
        throw new AuthenticationError();
      }

      const { title, content, tags } = req.body;
      const article = new Article({
        title,
        content,
        author: user._id,
        tags,
      });
      await article.save();

      articleMetrics.created.add(1, { 'user.id': user._id.toString() });
      articleMetrics.total.add(1);
      articleMetrics.contentSize.record(content.length, {
        'article.id': article._id.toString(),
      });

      span.setAttributes({
        'article.id': article._id.toString(),
        'article.title': article.title,
        'article.author_id': user._id.toString(),
        'article.published': article.published,
      });

      span.addEvent('article_created', {
        'article.id': article._id.toString(),
        'article.tags_count': article.tags.length,
      });

      const io = req.app.get('io') as Server | undefined;
      if (io) {
        emitArticleEvent(io, {
          event: 'article:created',
          data: {
            id: article._id.toString(),
            title: article.title,
            authorId: user._id.toString(),
            published: article.published,
            timestamp: new Date(),
          },
        });
      }

      res.status(201).json(article);
    });
  } catch (error) {
    next(error);
  }
}

export async function listArticles(
  req: Request,
  res: Response,
  next: NextFunction
): Promise<void> {
  try {
    await withSpan(TRACER_NAME, 'article.list', async (span) => {
      const page = Number(req.query.page) || 1;
      const limit = Number(req.query.limit) || 10;
      const skip = (page - 1) * limit;

      span.setAttributes({
        'article.list.page': page,
        'article.list.limit': limit,
      });

      const [articles, total] = await Promise.all([
        Article.find().sort({ createdAt: -1 }).skip(skip).limit(limit),
        Article.countDocuments(),
      ]);

      span.setAttributes({
        'article.list.total': total,
        'article.list.returned': articles.length,
      });

      res.json({
        articles,
        pagination: {
          page,
          limit,
          total,
          pages: Math.ceil(total / limit),
        },
      });
    });
  } catch (error) {
    next(error);
  }
}

export async function getArticle(
  req: Request,
  res: Response,
  next: NextFunction
): Promise<void> {
  try {
    await withSpan(TRACER_NAME, 'article.get', async (span) => {
      const { id } = req.params;
      span.setAttributes({ 'article.id': id ?? '' });

      const article = await Article.findByIdAndUpdate(
        id,
        { $inc: { viewCount: 1 } },
        { new: true }
      );

      if (!article) {
        setSpanError(span, 'Article not found');
        throw new NotFoundError('Article');
      }

      span.setAttributes({
        'article.title': article.title,
        'article.view_count': article.viewCount,
      });

      res.json(article);
    });
  } catch (error) {
    next(error);
  }
}

export async function updateArticle(
  req: Request,
  res: Response,
  next: NextFunction
): Promise<void> {
  try {
    await withSpan(TRACER_NAME, 'article.update', async (span) => {
      const { id } = req.params;
      const user = req.user;

      if (!user) {
        setSpanError(span, 'User not authenticated');
        throw new AuthenticationError();
      }

      span.setAttributes({
        'article.id': id ?? '',
        'user.id': user._id.toString(),
      });

      const article = await Article.findById(id);
      if (!article) {
        setSpanError(span, 'Article not found');
        throw new NotFoundError('Article');
      }

      if (article.author.toString() !== user._id.toString()) {
        setSpanError(span, 'Not authorized to update this article');
        throw new AuthorizationError('Not authorized to update this article');
      }

      const { title, content, tags } = req.body;
      if (title !== undefined) article.title = title;
      if (content !== undefined) article.content = content;
      if (tags !== undefined) article.tags = tags;

      await article.save();

      span.setAttributes({ 'article.author_id': article.author.toString() });
      span.addEvent('article_updated', {
        'article.id': article._id.toString(),
        'article.title': article.title,
      });

      const io = req.app.get('io') as Server | undefined;
      if (io) {
        emitArticleEvent(io, {
          event: 'article:updated',
          data: {
            id: article._id.toString(),
            title: article.title,
            authorId: user._id.toString(),
            published: article.published,
            timestamp: new Date(),
          },
        });
      }

      res.json(article);
    });
  } catch (error) {
    next(error);
  }
}

export async function deleteArticle(
  req: Request,
  res: Response,
  next: NextFunction
): Promise<void> {
  try {
    await withSpan(TRACER_NAME, 'article.delete', async (span) => {
      const { id } = req.params;
      const user = req.user;

      if (!user) {
        setSpanError(span, 'User not authenticated');
        throw new AuthenticationError();
      }

      span.setAttributes({
        'article.id': id ?? '',
        'user.id': user._id.toString(),
      });

      const article = await Article.findById(id);
      if (!article) {
        setSpanError(span, 'Article not found');
        throw new NotFoundError('Article');
      }

      if (article.author.toString() !== user._id.toString()) {
        setSpanError(span, 'Not authorized to delete this article');
        throw new AuthorizationError('Not authorized to delete this article');
      }

      await Article.findByIdAndDelete(id);

      articleMetrics.deleted.add(1, { 'user.id': user._id.toString() });
      articleMetrics.total.add(-1);

      span.setAttributes({ 'article.author_id': article.author.toString() });
      span.addEvent('article_deleted', {
        'article.id': article._id.toString(),
        'article.title': article.title,
      });

      const io = req.app.get('io') as Server | undefined;
      if (io) {
        emitArticleEvent(io, {
          event: 'article:deleted',
          data: {
            id: article._id.toString(),
            title: article.title,
            authorId: user._id.toString(),
            timestamp: new Date(),
          },
        });
      }

      res.status(204).send();
    });
  } catch (error) {
    next(error);
  }
}

export async function publishArticle(
  req: Request,
  res: Response,
  next: NextFunction
): Promise<void> {
  try {
    await withSpan(TRACER_NAME, 'article.publish', async (span) => {
      const { id } = req.params;
      const user = req.user;

      if (!user) {
        setSpanError(span, 'User not authenticated');
        throw new AuthenticationError();
      }

      span.setAttributes({
        'article.id': id ?? '',
        'user.id': user._id.toString(),
      });

      const article = await Article.findById(id);
      if (!article) {
        setSpanError(span, 'Article not found');
        throw new NotFoundError('Article');
      }

      if (article.author.toString() !== user._id.toString()) {
        setSpanError(span, 'Not authorized to publish this article');
        throw new AuthorizationError('Not authorized to publish this article');
      }

      if (article.published) {
        setSpanError(span, 'Article already published');
        throw new ValidationError('Article already published');
      }

      const carrier: Record<string, string> = {};
      propagation.inject(otelContext.active(), carrier);

      const job = await publishQueue.add('publish-article', {
        articleId: article._id.toString(),
        traceContext: carrier,
      });

      jobMetrics.enqueued.add(1, {
        'job.name': 'publish-article',
        'article.id': article._id.toString(),
      });

      span.setAttributes({
        'article.author_id': article.author.toString(),
        'job.id': job.id ?? '',
      });

      span.addEvent('job_enqueued', {
        'article.id': article._id.toString(),
        'job.id': job.id ?? '',
      });

      res.json({
        message: 'Article publishing job enqueued',
        jobId: job.id,
        articleId: article._id,
      });
    });
  } catch (error) {
    next(error);
  }
}

export async function favoriteArticle(
  req: Request,
  res: Response,
  next: NextFunction
): Promise<void> {
  try {
    await withSpan(TRACER_NAME, 'article.favorite', async (span) => {
      const { id } = req.params;
      const user = req.user;

      if (!user) {
        setSpanError(span, 'User not authenticated');
        throw new AuthenticationError();
      }

      span.setAttributes({
        'article.id': id ?? '',
        'user.id': user._id.toString(),
      });

      const article = await Article.findById(id);
      if (!article) {
        setSpanError(span, 'Article not found');
        throw new NotFoundError('Article');
      }

      const existingFavorite = await Favorite.findOne({
        user: user._id,
        article: article._id,
      });

      if (existingFavorite) {
        setSpanError(span, 'Article already favorited');
        throw new ConflictError('Article already favorited');
      }

      const favorite = new Favorite({
        user: user._id,
        article: article._id,
      });

      await Promise.all([
        favorite.save(),
        Article.findByIdAndUpdate(article._id, { $inc: { favoritesCount: 1 } }),
      ]);

      const newCount = article.favoritesCount + 1;

      articleMetrics.favorited.add(1, {
        'user.id': user._id.toString(),
        'article.id': article._id.toString(),
      });

      span.setAttributes({
        'article.author_id': article.author.toString(),
        'article.favorites_count': newCount,
      });

      span.addEvent('article_favorited', {
        'article.id': article._id.toString(),
        'user.id': user._id.toString(),
      });

      const io = req.app.get('io') as Server | undefined;
      if (io) {
        emitArticleEvent(io, {
          event: 'article:favorited',
          data: {
            id: article._id.toString(),
            userId: user._id.toString(),
            favoritesCount: newCount,
            timestamp: new Date(),
          },
        });
      }

      res.json({
        message: 'Article favorited successfully',
        articleId: article._id,
        favoritesCount: newCount,
      });
    });
  } catch (error) {
    next(error);
  }
}

export async function unfavoriteArticle(
  req: Request,
  res: Response,
  next: NextFunction
): Promise<void> {
  try {
    await withSpan(TRACER_NAME, 'article.unfavorite', async (span) => {
      const { id } = req.params;
      const user = req.user;

      if (!user) {
        setSpanError(span, 'User not authenticated');
        throw new AuthenticationError();
      }

      span.setAttributes({
        'article.id': id ?? '',
        'user.id': user._id.toString(),
      });

      const article = await Article.findById(id);
      if (!article) {
        setSpanError(span, 'Article not found');
        throw new NotFoundError('Article');
      }

      const favorite = await Favorite.findOneAndDelete({
        user: user._id,
        article: article._id,
      });

      if (!favorite) {
        setSpanError(span, 'Favorite not found');
        throw new NotFoundError('Favorite');
      }

      await Article.findByIdAndUpdate(article._id, { $inc: { favoritesCount: -1 } });
      const newCount = Math.max(0, article.favoritesCount - 1);

      articleMetrics.unfavorited.add(1, {
        'user.id': user._id.toString(),
        'article.id': article._id.toString(),
      });

      span.setAttributes({
        'article.author_id': article.author.toString(),
        'article.favorites_count': newCount,
      });

      span.addEvent('article_unfavorited', {
        'article.id': article._id.toString(),
        'user.id': user._id.toString(),
      });

      const io = req.app.get('io') as Server | undefined;
      if (io) {
        emitArticleEvent(io, {
          event: 'article:unfavorited',
          data: {
            id: article._id.toString(),
            userId: user._id.toString(),
            favoritesCount: newCount,
            timestamp: new Date(),
          },
        });
      }

      res.json({
        message: 'Article unfavorited successfully',
        articleId: article._id,
        favoritesCount: newCount,
      });
    });
  } catch (error) {
    next(error);
  }
}
