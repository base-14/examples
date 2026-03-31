import pino from "pino";
import { context, trace } from "@opentelemetry/api";

function getTraceContext() {
  const span = trace.getSpan(context.active());
  if (!span) return {};
  const ctx = span.spanContext();
  return {
    trace_id: ctx.traceId,
    span_id: ctx.spanId,
  };
}

const logger = pino({
  level: process.env.LOG_LEVEL || "info",
  mixin() {
    return getTraceContext();
  },
  formatters: {
    level(label) {
      return { level: label.toUpperCase() };
    },
  },
  timestamp: pino.stdTimeFunctions.isoTime,
});

export default logger;
