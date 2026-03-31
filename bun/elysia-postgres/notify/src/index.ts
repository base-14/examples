import { Elysia, t } from "elysia";
import { trace, SpanKind, context, propagation } from "@opentelemetry/api";
import { logger } from "./logger";

const tracer = trace.getTracer("elysia-notify");
const PORT = parseInt(process.env.PORT || "8081");

const app = new Elysia()
  .get("/api/health", () => ({ status: "healthy", service: "elysia-notify" }))
  .post("/notify", async ({ body, request }) => {
    const carrier: Record<string, string> = {};
    request.headers.forEach((value, key) => {
      carrier[key] = value;
    });

    const parentCtx = propagation.extract(context.active(), carrier);

    return trace.getTracer("elysia-notify").startActiveSpan(
      "POST /notify",
      { kind: SpanKind.SERVER },
      parentCtx,
      async (span) => {
        logger.info("Notification received", {
          event: String(body.event),
          article_id: Number(body.article_id),
        });
        span.setAttribute("notification.event", String(body.event));
        span.setAttribute("notification.article_id", Number(body.article_id));
        span.end();
        return { status: "received" };
      }
    );
  })
  .listen(PORT);

logger.info("Notify service started", { port: PORT });
