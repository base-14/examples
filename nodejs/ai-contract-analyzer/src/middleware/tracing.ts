/**
 * The inbound HTTP SERVER span for every request.
 *
 * Bun serves this app through `Bun.serve`, which the OTel HTTP instrumentation
 * does not patch, so the span is opened here instead. The span name becomes
 * `{METHOD} {route}` once Hono has matched a route.
 */
import { SpanKind, SpanStatusCode, trace } from "@opentelemetry/api";
import type { MiddlewareHandler } from "hono";

const tracer = trace.getTracer("ai-contract-analyzer");

export const httpTracing: MiddlewareHandler = async (c, next) => {
  const url = new URL(c.req.url);

  return tracer.startActiveSpan(
    `${c.req.method} ${url.pathname}`,
    {
      kind: SpanKind.SERVER,
      attributes: {
        "http.request.method": c.req.method,
        "url.path": url.pathname,
        "url.scheme": url.protocol.replace(":", ""),
        "server.address": url.hostname,
        "server.port": Number(url.port) || (url.protocol === "https:" ? 443 : 80),
      },
    },
    async (span) => {
      try {
        await next();
      } catch (err) {
        span.recordException(err as Error);
        span.setAttribute("error.type", (err as Error)?.constructor?.name ?? "UnknownError");
        span.setStatus({ code: SpanStatusCode.ERROR, message: (err as Error).message });
        span.end();
        throw err;
      }

      const route = c.req.routePath;
      if (route && route !== "/*") {
        span.setAttribute("http.route", route);
        span.updateName(`${c.req.method} ${route}`);
      }

      const status = c.res.status;
      span.setAttribute("http.response.status_code", status);
      if (status >= 400) {
        span.setAttribute("error.type", String(status));
        span.setStatus({ code: SpanStatusCode.ERROR, message: `HTTP ${status}` });
      }

      span.end();
    },
  );
};
