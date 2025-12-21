import { Injectable, NotFoundException } from '@nestjs/common';
import { InjectRepository } from '@nestjs/typeorm';
import { Repository } from 'typeorm';
import { trace, SpanStatusCode, metrics } from '@opentelemetry/api';
import { Favorite } from './entities/favorite.entity';
import { ArticlesService } from '../articles/articles.service';

const tracer = trace.getTracer('favorites-service');
const meter = metrics.getMeter('favorites-service');

const articlesFavoritedCounter = meter.createCounter('articles.favorited', {
  description: 'Number of times articles have been favorited',
});

@Injectable()
export class FavoritesService {
  constructor(
    @InjectRepository(Favorite)
    private favoritesRepository: Repository<Favorite>,
    private articlesService: ArticlesService,
  ) {}

  async favorite(
    articleId: string,
    userId: string,
  ): Promise<{ message: string }> {
    return tracer.startActiveSpan('article.favorite', async (span) => {
      try {
        span.setAttributes({
          'article.id': articleId,
          'user.id': userId,
        });

        const article = await this.articlesService.findOne(articleId);
        if (!article) {
          span.setStatus({ code: SpanStatusCode.ERROR, message: 'Not found' });
          throw new NotFoundException('Article not found');
        }

        const existingFavorite = await this.favoritesRepository.findOne({
          where: { userId, articleId },
        });

        if (existingFavorite) {
          span.setAttribute('action', 'already_favorited');
          span.setStatus({ code: SpanStatusCode.OK });
          return { message: 'Article already favorited' };
        }

        const favorite = this.favoritesRepository.create({
          userId,
          articleId,
        });

        await this.favoritesRepository.save(favorite);
        await this.articlesService.incrementFavoritesCount(articleId);

        articlesFavoritedCounter.add(1);
        span.setAttribute('action', 'favorited');
        span.setStatus({ code: SpanStatusCode.OK });
        return { message: 'Article favorited' };
      } catch (error) {
        if (!(error instanceof NotFoundException)) {
          span.setStatus({
            code: SpanStatusCode.ERROR,
            message: String(error),
          });
        }
        throw error;
      } finally {
        span.end();
      }
    });
  }

  async unfavorite(
    articleId: string,
    userId: string,
  ): Promise<{ message: string }> {
    return tracer.startActiveSpan('article.unfavorite', async (span) => {
      try {
        span.setAttributes({
          'article.id': articleId,
          'user.id': userId,
        });

        const article = await this.articlesService.findOne(articleId);
        if (!article) {
          span.setStatus({ code: SpanStatusCode.ERROR, message: 'Not found' });
          throw new NotFoundException('Article not found');
        }

        const favorite = await this.favoritesRepository.findOne({
          where: { userId, articleId },
        });

        if (!favorite) {
          span.setAttribute('action', 'not_favorited');
          span.setStatus({ code: SpanStatusCode.OK });
          return { message: 'Article was not favorited' };
        }

        await this.favoritesRepository.remove(favorite);
        await this.articlesService.decrementFavoritesCount(articleId);

        span.setAttribute('action', 'unfavorited');
        span.setStatus({ code: SpanStatusCode.OK });
        return { message: 'Article unfavorited' };
      } catch (error) {
        if (!(error instanceof NotFoundException)) {
          span.setStatus({
            code: SpanStatusCode.ERROR,
            message: String(error),
          });
        }
        throw error;
      } finally {
        span.end();
      }
    });
  }
}
