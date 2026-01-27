import { FastifyPluginAsync } from 'fastify';
import * as articleService from '../services/article.js';
import {
  listArticlesSchema,
  getArticleSchema,
  createArticleSchema,
  updateArticleSchema,
  deleteArticleSchema,
  favoriteArticleSchema,
} from '../schemas/article.js';

interface ListArticlesQuery {
  limit?: number;
  offset?: number;
  author?: string;
  favorited?: string;
}

interface ArticleParams {
  slug: string;
}

interface CreateArticleBody {
  title: string;
  description?: string;
  body: string;
}

interface UpdateArticleBody {
  title?: string;
  description?: string;
  body?: string;
}

const articleRoutes: FastifyPluginAsync = async (fastify) => {
  // List articles
  fastify.get<{ Querystring: ListArticlesQuery }>(
    '/',
    { schema: listArticlesSchema },
    async (request) => {
      const userId = request.user?.id;
      const result = await articleService.findArticles(request.query, userId);
      return result;
    }
  );

  // Get single article
  fastify.get<{ Params: ArticleParams }>(
    '/:slug',
    { schema: getArticleSchema },
    async (request, reply) => {
      const userId = request.user?.id;
      const article = await articleService.findBySlug(request.params.slug, userId);

      if (!article) {
        return reply.code(404).send({
          error: 'Not Found',
          message: 'Article not found',
        });
      }

      return { article };
    }
  );

  // Create article (auth required)
  fastify.post<{ Body: CreateArticleBody }>(
    '/',
    {
      schema: createArticleSchema,
      onRequest: [fastify.authenticate],
    },
    async (request, reply) => {
      const article = await articleService.createArticle(request.user.id, request.body);
      return reply.code(201).send({ article });
    }
  );

  // Update article (auth required, owner only)
  fastify.put<{ Params: ArticleParams; Body: UpdateArticleBody }>(
    '/:slug',
    {
      schema: updateArticleSchema,
      onRequest: [fastify.authenticate],
    },
    async (request, reply) => {
      try {
        const article = await articleService.updateArticle(
          request.params.slug,
          request.user.id,
          request.body
        );

        if (!article) {
          return reply.code(404).send({
            error: 'Not Found',
            message: 'Article not found',
          });
        }

        return { article };
      } catch (error) {
        if ((error as Error).message === 'Forbidden') {
          return reply.code(403).send({
            error: 'Forbidden',
            message: 'You can only edit your own articles',
          });
        }
        throw error;
      }
    }
  );

  // Delete article (auth required, owner only)
  fastify.delete<{ Params: ArticleParams }>(
    '/:slug',
    {
      schema: deleteArticleSchema,
      onRequest: [fastify.authenticate],
    },
    async (request, reply) => {
      try {
        const deleted = await articleService.deleteArticle(
          request.params.slug,
          request.user.id
        );

        if (!deleted) {
          return reply.code(404).send({
            error: 'Not Found',
            message: 'Article not found',
          });
        }

        return reply.code(204).send();
      } catch (error) {
        if ((error as Error).message === 'Forbidden') {
          return reply.code(403).send({
            error: 'Forbidden',
            message: 'You can only delete your own articles',
          });
        }
        throw error;
      }
    }
  );

  // Favorite article (auth required)
  fastify.post<{ Params: ArticleParams }>(
    '/:slug/favorite',
    {
      schema: favoriteArticleSchema,
      onRequest: [fastify.authenticate],
    },
    async (request, reply) => {
      const article = await articleService.favoriteArticle(
        request.params.slug,
        request.user.id
      );

      if (!article) {
        return reply.code(404).send({
          error: 'Not Found',
          message: 'Article not found',
        });
      }

      return { article };
    }
  );

  // Unfavorite article (auth required)
  fastify.delete<{ Params: ArticleParams }>(
    '/:slug/favorite',
    {
      schema: favoriteArticleSchema,
      onRequest: [fastify.authenticate],
    },
    async (request, reply) => {
      const article = await articleService.unfavoriteArticle(
        request.params.slug,
        request.user.id
      );

      if (!article) {
        return reply.code(404).send({
          error: 'Not Found',
          message: 'Article not found',
        });
      }

      return { article };
    }
  );
};

export default articleRoutes;
