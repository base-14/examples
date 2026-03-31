import { Elysia, t } from "elysia";
import { eq, desc, count, sql } from "drizzle-orm";
import { trace, SpanKind, SpanStatusCode } from "@opentelemetry/api";
import { metrics } from "@opentelemetry/api";
import { db } from "../db";
import { articles } from "../schema";
import { logger } from "../logger";
import { notifyArticleCreated } from "../notification";

const tracer = trace.getTracer("elysia-articles");
const meter = metrics.getMeter("elysia-articles");
const articlesCreated = meter.createCounter("articles.created", {
  description: "Number of articles created",
});

function getTraceId(): string {
  return trace.getActiveSpan()?.spanContext().traceId ?? "";
}

function traced<T>(
  name: string,
  set: { status?: number | string },
  fn: () => Promise<T>
): Promise<T> {
  return tracer.startActiveSpan(name, { kind: SpanKind.SERVER }, async (span) => {
    try {
      const result = await fn();
      const status = typeof set.status === "number" ? set.status : 200;
      span.setAttribute("http.response.status_code", status);
      if (status >= 400) span.setStatus({ code: SpanStatusCode.ERROR });
      span.end();
      return result;
    } catch (err) {
      span.setAttribute("http.response.status_code", 500);
      span.setStatus({ code: SpanStatusCode.ERROR, message: String(err) });
      span.end();
      throw err;
    }
  });
}

export const articleRoutes = new Elysia({ prefix: "/api/articles" })
  .get("/", async ({ query, set }) =>
    traced("GET /api/articles", set, async () => {
      const page = Number(query.page) || 1;
      const perPage = Number(query.per_page) || 20;
      const offset = (page - 1) * perPage;

      const [rows, [{ total }]] = await Promise.all([
        db
          .select()
          .from(articles)
          .orderBy(desc(articles.createdAt))
          .limit(perPage)
          .offset(offset),
        db.select({ total: count() }).from(articles),
      ]);

      logger.info("Listed articles", { page, per_page: perPage, total });
      return {
        data: rows,
        meta: {
          page,
          per_page: perPage,
          total,
          trace_id: getTraceId(),
        },
      };
    })
  )

  .post(
    "/",
    async ({ body, set }) =>
      traced("POST /api/articles", set, async () => {
        const [article] = await db
          .insert(articles)
          .values({ title: body.title, body: body.body })
          .returning();

        articlesCreated.add(1);
        logger.info("Article created", { id: article.id, title: article.title });

        await notifyArticleCreated(article.id, article.title);

        set.status = 201;
        return { data: article, meta: { trace_id: getTraceId() } };
      }),
    {
      body: t.Object({
        title: t.String({ minLength: 1 }),
        body: t.String({ minLength: 1 }),
      }),
    }
  )

  .get("/:id", async ({ params, set }) =>
    traced("GET /api/articles/:id", set, async () => {
      const id = Number(params.id);
      if (isNaN(id) || !Number.isInteger(id) || id < 1) {
        logger.warn("Invalid article ID format", { raw_id: params.id });
        set.status = 400;
        return {
          error: "Invalid ID format",
          details: "ID must be a positive integer",
          meta: { trace_id: getTraceId() },
        };
      }

      const [article] = await db
        .select()
        .from(articles)
        .where(eq(articles.id, id));

      if (!article) {
        logger.warn("Article not found", { id });
        set.status = 404;
        return { error: "Article not found", meta: { trace_id: getTraceId() } };
      }

      return { data: article, meta: { trace_id: getTraceId() } };
    })
  )

  .put(
    "/:id",
    async ({ params, body, set }) =>
      traced("PUT /api/articles/:id", set, async () => {
        const id = Number(params.id);
        if (isNaN(id) || !Number.isInteger(id) || id < 1) {
          set.status = 400;
          return {
            error: "Invalid ID format",
            meta: { trace_id: getTraceId() },
          };
        }

        const updates: Record<string, unknown> = {
          updatedAt: new Date(),
        };
        if (body.title) updates.title = body.title;
        if (body.body) updates.body = body.body;

        const [article] = await db
          .update(articles)
          .set(updates)
          .where(eq(articles.id, id))
          .returning();

        if (!article) {
          logger.warn("Article not found for update", { id });
          set.status = 404;
          return { error: "Article not found", meta: { trace_id: getTraceId() } };
        }

        logger.info("Article updated", { id });
        return { data: article, meta: { trace_id: getTraceId() } };
      }),
    {
      body: t.Partial(
        t.Object({
          title: t.String({ minLength: 1 }),
          body: t.String({ minLength: 1 }),
        })
      ),
    }
  )

  .delete("/:id", async ({ params, set }) =>
    traced("DELETE /api/articles/:id", set, async () => {
      const id = Number(params.id);
      if (isNaN(id) || !Number.isInteger(id) || id < 1) {
        set.status = 400;
        return { error: "Invalid ID format", meta: { trace_id: getTraceId() } };
      }

      const [article] = await db
        .delete(articles)
        .where(eq(articles.id, id))
        .returning();

      if (!article) {
        logger.warn("Article not found for delete", { id });
        set.status = 404;
        return { error: "Article not found", meta: { trace_id: getTraceId() } };
      }

      logger.info("Article deleted", { id });
      set.status = 204;
    })
  );
