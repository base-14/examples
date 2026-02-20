import { metrics } from "@opentelemetry/api";
import type { MiddlewareHandler } from "hono";

const meter = metrics.getMeter("ai-contract-analyzer");

const httpRequestDuration = meter.createHistogram("http.server.request.duration", {
  description: "HTTP server request duration",
  unit: "s",
});

const httpRequestCount = meter.createCounter("http.server.request.count", {
  description: "HTTP server request count",
});

export const requestMetrics: MiddlewareHandler = async (c, next) => {
  const start = Date.now();
  await next();
  const duration = (Date.now() - start) / 1000;

  const attrs = {
    "http.request.method": c.req.method,
    "http.response.status_code": String(c.res.status),
    "url.path": c.req.path,
  };

  httpRequestDuration.record(duration, attrs);
  httpRequestCount.add(1, attrs);
};
