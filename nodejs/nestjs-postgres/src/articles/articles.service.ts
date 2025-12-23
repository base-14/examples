import {
  Injectable,
  NotFoundException,
  ForbiddenException,
  ConflictException,
  Inject,
  forwardRef,
} from '@nestjs/common';
import { InjectRepository } from '@nestjs/typeorm';
import { Repository } from 'typeorm';
import { trace, SpanStatusCode, metrics } from '@opentelemetry/api';
import { Article } from './entities/article.entity';
import { CreateArticleDto } from './dto/create-article.dto';
import { UpdateArticleDto } from './dto/update-article.dto';
import { NotificationService } from '../jobs/notification.service';
import { UsersService } from '../users/users.service';
import { EventsGateway } from '../events/events.gateway';

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
    private notificationService: NotificationService,
    private usersService: UsersService,
    @Inject(forwardRef(() => EventsGateway))
    private eventsGateway: EventsGateway,
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

        this.eventsGateway.emitArticleCreated({
          id: savedArticle.id,
          title: savedArticle.title,
          authorId: savedArticle.authorId,
          published: savedArticle.published,
          timestamp: new Date(),
        });

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

        this.eventsGateway.emitArticleUpdated({
          id: updatedArticle.id,
          title: updatedArticle.title,
          authorId: updatedArticle.authorId,
          published: updatedArticle.published,
          timestamp: new Date(),
        });

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

        const articleId = article.id;
        const articleTitle = article.title;
        const articleAuthorId = article.authorId;

        await this.articlesRepository.remove(article);

        this.eventsGateway.emitArticleDeleted({
          id: articleId,
          title: articleTitle,
          authorId: articleAuthorId,
          timestamp: new Date(),
        });

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

  async publish(
    id: string,
    userId: string,
  ): Promise<{ message: string; jobId?: string }> {
    return tracer.startActiveSpan('article.publish', async (span) => {
      try {
        span.setAttributes({
          'article.id': id,
          'user.id': userId,
        });

        const article = await this.findOne(id);

        if (article.authorId !== userId) {
          span.setStatus({ code: SpanStatusCode.ERROR, message: 'Forbidden' });
          throw new ForbiddenException(
            'You can only publish your own articles',
          );
        }

        if (article.published) {
          span.setAttribute('article.already_published', true);
          throw new ConflictException('Article is already published');
        }

        const author = await this.usersService.findById(userId);
        if (!author) {
          throw new NotFoundException('Author not found');
        }

        const jobId = await this.notificationService.notifyArticlePublished(
          article.id,
          article.title,
          userId,
          author.email,
        );

        span.setAttribute('job.id', jobId ?? '');
        span.setStatus({ code: SpanStatusCode.OK });

        return {
          message: 'Article publish job enqueued',
          jobId,
        };
      } catch (error) {
        if (
          !(error instanceof NotFoundException) &&
          !(error instanceof ForbiddenException) &&
          !(error instanceof ConflictException)
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
