import { Elysia } from "elysia";
import { trace, SpanKind, SpanStatusCode } from "@opentelemetry/api";
import { logger } from "./logger";
import { healthRoutes } from "./routes/health";
import { articleRoutes } from "./routes/article";

const tracer = trace.getTracer("elysia-articles");
const PORT = parseInt(process.env.PORT || "8080");

const app = new Elysia()
  .onError(({ code, error, set, request }) => {
    const url = new URL(request.url);
    return tracer.startActiveSpan(
      `${request.method} ${url.pathname}`,
      { kind: SpanKind.SERVER },
      (span) => {
        if (code === "VALIDATION") {
          logger.warn("Validation failed", { path: url.pathname });
          span.setAttribute("http.response.status_code", 422);
          span.setStatus({ code: SpanStatusCode.ERROR, message: "Validation failed" });
          span.end();
          set.status = 422;
          return {
            error: "Validation failed",
            details: error.message,
            meta: { trace_id: span.spanContext().traceId },
          };
        }
        logger.error("Unhandled error", { error: String(error) });
        span.setAttribute("http.response.status_code", 500);
        span.setStatus({ code: SpanStatusCode.ERROR, message: String(error) });
        span.end();
        set.status = 500;
        return {
          error: "Internal server error",
          meta: { trace_id: span.spanContext().traceId },
        };
      }
    );
  })
  .use(healthRoutes)
  .use(articleRoutes)
  .listen(PORT);

logger.info("Elysia articles server started", { port: PORT });
