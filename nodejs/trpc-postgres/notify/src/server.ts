import http from "node:http";
import { context, trace } from "@opentelemetry/api";
import pino from "pino";

const logger = pino({
  level: process.env.LOG_LEVEL || "info",
  mixin() {
    const span = trace.getSpan(context.active());
    if (!span) return {};
    const ctx = span.spanContext();
    return { trace_id: ctx.traceId, span_id: ctx.spanId };
  },
  formatters: {
    level(label) {
      return { level: label.toUpperCase() };
    },
  },
  timestamp: pino.stdTimeFunctions.isoTime,
});

const server = http.createServer(async (req, res) => {
  const method = req.method || "GET";
  const url = req.url || "/";

  if (url === "/api/health" && method === "GET") {
    res.writeHead(200, { "Content-Type": "application/json" });
    return res.end(JSON.stringify({ status: "healthy", service: "trpc-notify" }));
  }

  if (url === "/notify" && method === "POST") {
    const chunks: Buffer[] = [];
    for await (const chunk of req) chunks.push(chunk as Buffer);
    let body: Record<string, unknown>;
    try {
      body = JSON.parse(Buffer.concat(chunks).toString());
    } catch {
      res.writeHead(400, { "Content-Type": "application/json" });
      return res.end(JSON.stringify({ error: "Invalid JSON" }));
    }
    logger.info({ event: body.event, article_id: body.article_id }, "Notification received");
    res.writeHead(200, { "Content-Type": "application/json" });
    return res.end(JSON.stringify({ status: "received" }));
  }

  res.writeHead(404, { "Content-Type": "application/json" });
  res.end(JSON.stringify({ error: "Not found" }));
});

const PORT = parseInt(process.env.PORT || "8081");
server.listen(PORT, () => {
  logger.info({ port: PORT }, "Notify service started");
});
