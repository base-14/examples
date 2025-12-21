import {
  Injectable,
  NotFoundException,
  ForbiddenException,
} from '@nestjs/common';
import { InjectRepository } from '@nestjs/typeorm';
import { Repository } from 'typeorm';
import { trace, SpanStatusCode, metrics } from '@opentelemetry/api';
import { Article } from './entities/article.entity';
import { CreateArticleDto } from './dto/create-article.dto';
import { UpdateArticleDto } from './dto/update-article.dto';

const tracer = trace.getTracer('articles-service');
const meter = metrics.getMeter('articles-service');

const articlesCreatedCounter = meter.createCounter('articles.created', {
  description: 'Number of articles created',
});

export interface PaginationOptions {
  page: number;
  limit: number;
}

export interface PaginatedResult<T> {
  data: T[];
  meta: {
    page: number;
    limit: number;
    total: number;
    totalPages: number;
  };
}

@Injectable()
export class ArticlesService {
  constructor(
    @InjectRepository(Article)
    private articlesRepository: Repository<Article>,
  ) {}

  async create(dto: CreateArticleDto, userId: string): Promise<Article> {
    return tracer.startActiveSpan('article.create', async (span) => {
      try {
        span.setAttributes({
          'user.id': userId,
          'article.title': dto.title,
        });

        const article = this.articlesRepository.create({
          ...dto,
          authorId: userId,
        });

        const savedArticle = await this.articlesRepository.save(article);
        span.setAttribute('article.id', savedArticle.id);
        articlesCreatedCounter.add(1);

        span.setStatus({ code: SpanStatusCode.OK });
        return savedArticle;
      } catch (error) {
        span.setStatus({ code: SpanStatusCode.ERROR, message: String(error) });
        throw error;
      } finally {
        span.end();
      }
    });
  }

  async findAll(options: PaginationOptions): Promise<PaginatedResult<Article>> {
    return tracer.startActiveSpan('article.findAll', async (span) => {
      try {
        span.setAttributes({
          'pagination.page': options.page,
          'pagination.limit': options.limit,
        });

        const [data, total] = await this.articlesRepository.findAndCount({
          order: { createdAt: 'DESC' },
          skip: (options.page - 1) * options.limit,
          take: options.limit,
        });

        span.setAttribute('articles.count', data.length);
        span.setStatus({ code: SpanStatusCode.OK });

        return {
          data,
          meta: {
            page: options.page,
            limit: options.limit,
            total,
            totalPages: Math.ceil(total / options.limit),
          },
        };
      } catch (error) {
        span.setStatus({ code: SpanStatusCode.ERROR, message: String(error) });
        throw error;
      } finally {
        span.end();
      }
    });
  }

  async findOne(id: string): Promise<Article> {
    return tracer.startActiveSpan('article.findOne', async (span) => {
      try {
        span.setAttribute('article.id', id);

        const article = await this.articlesRepository.findOne({
          where: { id },
        });

        if (!article) {
          span.setStatus({ code: SpanStatusCode.ERROR, message: 'Not found' });
          throw new NotFoundException('Article not found');
        }

        span.setStatus({ code: SpanStatusCode.OK });
        return article;
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

  async update(
    id: string,
    dto: UpdateArticleDto,
    userId: string,
  ): Promise<Article> {
    return tracer.startActiveSpan('article.update', async (span) => {
      try {
        span.setAttributes({
          'article.id': id,
          'user.id': userId,
        });

        const article = await this.findOne(id);

        if (article.authorId !== userId) {
          span.setStatus({ code: SpanStatusCode.ERROR, message: 'Forbidden' });
          throw new ForbiddenException('You can only update your own articles');
        }

        Object.assign(article, dto);
        const updatedArticle = await this.articlesRepository.save(article);

        span.setStatus({ code: SpanStatusCode.OK });
        return updatedArticle;
      } catch (error) {
        if (
          !(error instanceof NotFoundException) &&
          !(error instanceof ForbiddenException)
        ) {
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

  async remove(id: string, userId: string): Promise<void> {
    return tracer.startActiveSpan('article.delete', async (span) => {
      try {
        span.setAttributes({
          'article.id': id,
          'user.id': userId,
        });

        const article = await this.findOne(id);

        if (article.authorId !== userId) {
          span.setStatus({ code: SpanStatusCode.ERROR, message: 'Forbidden' });
          throw new ForbiddenException('You can only delete your own articles');
        }

        await this.articlesRepository.remove(article);
        span.setStatus({ code: SpanStatusCode.OK });
      } catch (error) {
        if (
          !(error instanceof NotFoundException) &&
          !(error instanceof ForbiddenException)
        ) {
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

  async incrementFavoritesCount(id: string): Promise<void> {
    await this.articlesRepository.increment({ id }, 'favoritesCount', 1);
  }

  async decrementFavoritesCount(id: string): Promise<void> {
    await this.articlesRepository.decrement({ id }, 'favoritesCount', 1);
  }
}
