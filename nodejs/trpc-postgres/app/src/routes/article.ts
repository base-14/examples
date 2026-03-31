import { z } from "zod";
import { TRPCError } from "@trpc/server";
import { PrismaClient } from "@prisma/client";
import { router, publicProcedure } from "../router";
import { metrics } from "@opentelemetry/api";
import logger from "../lib/logger";
import { notifyArticleCreated } from "../service/notification";

const meter = metrics.getMeter("trpc-articles");
const articlesCreatedCounter = meter.createCounter("articles.created", {
  description: "Number of articles created",
});

export function createArticleRouter(prisma: PrismaClient) {
  return router({
    list: publicProcedure
      .input(
        z.object({
          page: z.coerce.number().min(1).default(1),
          per_page: z.coerce.number().min(1).max(100).default(20),
        })
      )
      .query(async ({ input }) => {
        const { page, per_page } = input;
        const skip = (page - 1) * per_page;
        const [articles, total] = await Promise.all([
          prisma.article.findMany({
            skip,
            take: per_page,
            orderBy: { createdAt: "desc" },
          }),
          prisma.article.count(),
        ]);
        logger.info({ page, per_page, total }, "Listed articles");
        return {
          data: articles,
          meta: {
            page,
            per_page,
            total,
            total_pages: Math.ceil(total / per_page),
          },
        };
      }),

    getById: publicProcedure
      .input(z.object({ id: z.coerce.number().int().positive() }))
      .query(async ({ input }) => {
        const article = await prisma.article.findUnique({
          where: { id: input.id },
        });
        if (!article) {
          logger.warn({ article_id: input.id }, "Article not found");
          throw new TRPCError({
            code: "NOT_FOUND",
            message: `Article ${input.id} not found`,
          });
        }
        return { data: article };
      }),

    create: publicProcedure
      .input(
        z.object({
          title: z.string().min(1).max(255),
          body: z.string().min(1),
        })
      )
      .mutation(async ({ input }) => {
        const article = await prisma.article.create({
          data: { title: input.title, body: input.body },
        });
        articlesCreatedCounter.add(1);
        logger.info(
          { article_id: article.id, title: article.title },
          "Article created"
        );
        notifyArticleCreated(article).catch((err) =>
          logger.error({ err }, "Failed to notify")
        );
        return { data: article };
      }),

    update: publicProcedure
      .input(
        z.object({
          id: z.coerce.number().int().positive(),
          title: z.string().min(1).max(255).optional(),
          body: z.string().min(1).optional(),
        })
      )
      .mutation(async ({ input }) => {
        const { id, ...data } = input;
        const existing = await prisma.article.findUnique({ where: { id } });
        if (!existing) {
          logger.warn({ article_id: id }, "Article not found for update");
          throw new TRPCError({
            code: "NOT_FOUND",
            message: `Article ${id} not found`,
          });
        }
        const updateData: Record<string, string> = {};
        if (data.title !== undefined) updateData.title = data.title;
        if (data.body !== undefined) updateData.body = data.body;
        if (Object.keys(updateData).length === 0) {
          return { data: existing };
        }
        const article = await prisma.article.update({
          where: { id },
          data: updateData,
        });
        logger.info({ article_id: id }, "Article updated");
        return { data: article };
      }),

    delete: publicProcedure
      .input(z.object({ id: z.coerce.number().int().positive() }))
      .mutation(async ({ input }) => {
        const existing = await prisma.article.findUnique({
          where: { id: input.id },
        });
        if (!existing) {
          logger.warn({ article_id: input.id }, "Article not found for delete");
          throw new TRPCError({
            code: "NOT_FOUND",
            message: `Article ${input.id} not found`,
          });
        }
        await prisma.article.delete({ where: { id: input.id } });
        logger.info({ article_id: input.id }, "Article deleted");
        return null;
      }),
  });
}
