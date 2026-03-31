import http from "node:http";
import { PrismaPg } from "@prisma/adapter-pg";
import { PrismaClient } from "@prisma/client";
import { context, trace } from "@opentelemetry/api";
import { router, createCallerFactory } from "./router";
import { createArticleRouter } from "./routes/article";
import { createHealthRouter } from "./routes/health";
import logger from "./lib/logger";

const adapter = new PrismaPg(process.env.DATABASE_URL!);
const prisma = new PrismaClient({ adapter });

const appRouter = router({
  health: createHealthRouter(prisma),
  article: createArticleRouter(prisma),
});

export type AppRouter = typeof appRouter;

const createCaller = createCallerFactory(appRouter);
const caller = createCaller({});

function getTraceId(): string {
  const span = trace.getSpan(context.active());
  return span?.spanContext().traceId || "";
}

function json(res: http.ServerResponse, status: number, body: unknown) {
  res.writeHead(status, { "Content-Type": "application/json" });
  res.end(JSON.stringify(body));
}

async function parseBody(req: http.IncomingMessage): Promise<unknown> {
  return new Promise((resolve, reject) => {
    const chunks: Buffer[] = [];
    req.on("data", (chunk) => chunks.push(chunk));
    req.on("end", () => {
      const raw = Buffer.concat(chunks).toString();
      if (!raw) return resolve({});
      try {
        resolve(JSON.parse(raw));
      } catch {
        reject(new Error("Invalid JSON"));
      }
    });
    req.on("error", reject);
  });
}

function parseQuery(url: string): Record<string, string> {
  const idx = url.indexOf("?");
  if (idx === -1) return {};
  const params = new URLSearchParams(url.slice(idx + 1));
  const result: Record<string, string> = {};
  for (const [k, v] of params) result[k] = v;
  return result;
}

const server = http.createServer(async (req, res) => {
  const method = req.method || "GET";
  const url = req.url || "/";
  const path = url.split("?")[0];

  try {
    if (path === "/api/health" && method === "GET") {
      const result = await caller.health.check();
      return json(res, 200, { data: result, meta: { trace_id: getTraceId() } });
    }

    if (path === "/api/articles" && method === "GET") {
      const query = parseQuery(url);
      const result = await caller.article.list({
        page: query.page ? Number(query.page) : 1,
        per_page: query.per_page ? Number(query.per_page) : 20,
      });
      return json(res, 200, { ...result, meta: { ...result.meta, trace_id: getTraceId() } });
    }

    if (path === "/api/articles" && method === "POST") {
      const body = (await parseBody(req)) as Record<string, unknown>;
      if (!body.title && !body.body) {
        logger.warn("Validation failed: empty body");
        return json(res, 422, {
          error: "Validation failed",
          details: "title and body are required",
          meta: { trace_id: getTraceId() },
        });
      }
      if (!body.title || typeof body.title !== "string") {
        logger.warn("Validation failed: missing title");
        return json(res, 422, {
          error: "Validation failed",
          details: "title is required",
          meta: { trace_id: getTraceId() },
        });
      }
      if (!body.body || typeof body.body !== "string") {
        logger.warn("Validation failed: missing body");
        return json(res, 422, {
          error: "Validation failed",
          details: "body is required",
          meta: { trace_id: getTraceId() },
        });
      }
      const result = await caller.article.create({
        title: body.title,
        body: body.body,
      });
      return json(res, 201, { ...result, meta: { trace_id: getTraceId() } });
    }

    const articleMatch = path.match(/^\/api\/articles\/(.+)$/);
    if (articleMatch) {
      const rawId = articleMatch[1];
      const id = Number(rawId);
      if (isNaN(id) || !Number.isInteger(id) || id < 1) {
        logger.warn({ raw_id: rawId }, "Invalid article ID format");
        return json(res, 400, {
          error: "Invalid ID format",
          details: "ID must be a positive integer",
          meta: { trace_id: getTraceId() },
        });
      }

      if (method === "GET") {
        const result = await caller.article.getById({ id });
        return json(res, 200, { ...result, meta: { trace_id: getTraceId() } });
      }

      if (method === "PUT") {
        const body = (await parseBody(req)) as Record<string, unknown>;
        const result = await caller.article.update({
          id,
          title: body.title as string | undefined,
          body: body.body as string | undefined,
        });
        return json(res, 200, { ...result, meta: { trace_id: getTraceId() } });
      }

      if (method === "DELETE") {
        await caller.article.delete({ id });
        res.writeHead(204);
        return res.end();
      }
    }

    json(res, 404, { error: "Not found", meta: { trace_id: getTraceId() } });
  } catch (err: unknown) {
    const trpcErr = err as { code?: string; message?: string };
    if (trpcErr.code === "NOT_FOUND") {
      return json(res, 404, {
        error: trpcErr.message || "Not found",
        meta: { trace_id: getTraceId() },
      });
    }
    if (trpcErr.code === "BAD_REQUEST") {
      return json(res, 400, {
        error: trpcErr.message || "Bad request",
        meta: { trace_id: getTraceId() },
      });
    }
    logger.error({ err }, "Unhandled error");
    json(res, 500, {
      error: "Internal server error",
      meta: { trace_id: getTraceId() },
    });
  }
});

const PORT = parseInt(process.env.PORT || "8080");
server.listen(PORT, () => {
  logger.info({ port: PORT }, "tRPC articles server started");
});
