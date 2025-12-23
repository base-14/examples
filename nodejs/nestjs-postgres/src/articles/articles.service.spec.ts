/* eslint-disable @typescript-eslint/unbound-method */
import { Test, TestingModule } from '@nestjs/testing';
import { getRepositoryToken } from '@nestjs/typeorm';
import { Repository } from 'typeorm';
import {
  NotFoundException,
  ForbiddenException,
  ConflictException,
} from '@nestjs/common';
import { ArticlesService } from './articles.service';
import { Article } from './entities/article.entity';
import { NotificationService } from '../jobs/notification.service';
import { UsersService } from '../users/users.service';
import { EventsGateway } from '../events/events.gateway';
import { User, UserRole } from '../users/entities/user.entity';

describe('ArticlesService', () => {
  let service: ArticlesService;
  let articlesRepository: jest.Mocked<Repository<Article>>;
  let notificationService: jest.Mocked<NotificationService>;
  let usersService: jest.Mocked<UsersService>;
  let eventsGateway: jest.Mocked<EventsGateway>;

  const mockUser: User = {
    id: 'user-uuid',
    email: 'author@example.com',
    password: 'hashedpassword',
    name: 'Test Author',
    role: UserRole.USER,
    createdAt: new Date(),
    updatedAt: new Date(),
  };

  const mockArticle: Article = {
    id: 'article-uuid',
    title: 'Test Article',
    content: 'Test content',
    tags: ['test'],
    published: false,
    publishedAt: null,
    favoritesCount: 0,
    authorId: mockUser.id,
    createdAt: new Date(),
    updatedAt: new Date(),
  };

  beforeEach(async () => {
    const module: TestingModule = await Test.createTestingModule({
      providers: [
        ArticlesService,
        {
          provide: getRepositoryToken(Article),
          useValue: {
            create: jest.fn(),
            save: jest.fn(),
            findOne: jest.fn(),
            findAndCount: jest.fn(),
            remove: jest.fn(),
            update: jest.fn(),
            increment: jest.fn(),
            decrement: jest.fn(),
          },
        },
        {
          provide: NotificationService,
          useValue: {
            notifyArticlePublished: jest.fn(),
          },
        },
        {
          provide: UsersService,
          useValue: {
            findById: jest.fn(),
          },
        },
        {
          provide: EventsGateway,
          useValue: {
            emitArticleCreated: jest.fn(),
            emitArticleUpdated: jest.fn(),
            emitArticleDeleted: jest.fn(),
            emitArticlePublished: jest.fn(),
          },
        },
      ],
    }).compile();

    service = module.get<ArticlesService>(ArticlesService);
    articlesRepository = module.get(getRepositoryToken(Article));
    notificationService = module.get(NotificationService);
    usersService = module.get(UsersService);
    eventsGateway = module.get(EventsGateway);
  });

  afterEach(() => {
    jest.clearAllMocks();
  });

  describe('create', () => {
    const createDto = {
      title: 'New Article',
      content: 'New content',
      tags: ['new'],
    };

    it('should create an article', async () => {
      const newArticle = { ...mockArticle, ...createDto };
      articlesRepository.create.mockReturnValue(newArticle as Article);
      articlesRepository.save.mockResolvedValue(newArticle as Article);

      const result = await service.create(createDto, mockUser.id);

      expect(result.title).toBe(createDto.title);
      expect(articlesRepository.create).toHaveBeenCalledWith({
        ...createDto,
        authorId: mockUser.id,
      });
      expect(eventsGateway.emitArticleCreated).toHaveBeenCalled();
    });
  });

  describe('findAll', () => {
    it('should return paginated articles', async () => {
      const articles = [mockArticle];
      articlesRepository.findAndCount.mockResolvedValue([articles, 1]);

      const result = await service.findAll({ page: 1, limit: 10 });

      expect(result.data).toEqual(articles);
      expect(result.meta).toMatchObject({
        page: 1,
        limit: 10,
        total: 1,
        totalPages: 1,
      });
    });
  });

  describe('findOne', () => {
    it('should return an article', async () => {
      articlesRepository.findOne.mockResolvedValue(mockArticle);

      const result = await service.findOne(mockArticle.id);

      expect(result).toEqual(mockArticle);
    });

    it('should throw NotFoundException if article not found', async () => {
      articlesRepository.findOne.mockResolvedValue(null);

      await expect(service.findOne('unknown-id')).rejects.toThrow(
        NotFoundException,
      );
    });
  });

  describe('update', () => {
    const updateDto = { title: 'Updated Title' };

    it('should update an article when owner', async () => {
      const updatedArticle = { ...mockArticle, ...updateDto };
      articlesRepository.findOne.mockResolvedValue(mockArticle);
      articlesRepository.save.mockResolvedValue(updatedArticle as Article);

      const result = await service.update(
        mockArticle.id,
        updateDto,
        mockUser.id,
      );

      expect(result.title).toBe(updateDto.title);
      expect(eventsGateway.emitArticleUpdated).toHaveBeenCalled();
    });

    it('should throw ForbiddenException when not owner', async () => {
      articlesRepository.findOne.mockResolvedValue(mockArticle);

      await expect(
        service.update(mockArticle.id, updateDto, 'other-user-id'),
      ).rejects.toThrow(ForbiddenException);
    });
  });

  describe('remove', () => {
    it('should delete an article when owner', async () => {
      articlesRepository.findOne.mockResolvedValue(mockArticle);
      articlesRepository.remove.mockResolvedValue(mockArticle);

      await service.remove(mockArticle.id, mockUser.id);

      expect(articlesRepository.remove).toHaveBeenCalledWith(mockArticle);
      expect(eventsGateway.emitArticleDeleted).toHaveBeenCalled();
    });

    it('should throw ForbiddenException when not owner', async () => {
      articlesRepository.findOne.mockResolvedValue(mockArticle);

      await expect(
        service.remove(mockArticle.id, 'other-user-id'),
      ).rejects.toThrow(ForbiddenException);
    });
  });

  describe('publish', () => {
    it('should enqueue publish job', async () => {
      articlesRepository.findOne.mockResolvedValue(mockArticle);
      usersService.findById.mockResolvedValue(mockUser);
      notificationService.notifyArticlePublished.mockResolvedValue('job-id');

      const result = await service.publish(mockArticle.id, mockUser.id);

      expect(result.message).toBe('Article publish job enqueued');
      expect(result.jobId).toBe('job-id');
    });

    it('should throw ConflictException if already published', async () => {
      const publishedArticle = { ...mockArticle, published: true };
      articlesRepository.findOne.mockResolvedValue(publishedArticle as Article);

      await expect(
        service.publish(mockArticle.id, mockUser.id),
      ).rejects.toThrow(ConflictException);
    });

    it('should throw ForbiddenException when not owner', async () => {
      articlesRepository.findOne.mockResolvedValue(mockArticle);

      await expect(
        service.publish(mockArticle.id, 'other-user-id'),
      ).rejects.toThrow(ForbiddenException);
    });
  });

  describe('incrementFavoritesCount', () => {
    it('should increment favorites count', async () => {
      await service.incrementFavoritesCount(mockArticle.id);

      expect(articlesRepository.increment).toHaveBeenCalledWith(
        { id: mockArticle.id },
        'favoritesCount',
        1,
      );
    });
  });

  describe('decrementFavoritesCount', () => {
    it('should decrement favorites count', async () => {
      await service.decrementFavoritesCount(mockArticle.id);

      expect(articlesRepository.decrement).toHaveBeenCalledWith(
        { id: mockArticle.id },
        'favoritesCount',
        1,
      );
    });
  });
});
