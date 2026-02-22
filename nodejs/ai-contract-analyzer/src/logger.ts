import { trace } from "@opentelemetry/api";
import { logs, SeverityNumber } from "@opentelemetry/api-logs";

const otelLogger = logs.getLogger("ai-contract-analyzer");

type LogAttrs = Record<string, string | number | boolean | undefined>;

function emit(
  severityNumber: SeverityNumber,
  severityText: string,
  message: string,
  attrs?: LogAttrs,
) {
  const span = trace.getActiveSpan();
  const ctx = span?.spanContext();

  otelLogger.emit({
    severityNumber,
    severityText,
    body: message,
    attributes: {
      ...attrs,
      ...(ctx
        ? {
            trace_id: ctx.traceId,
            span_id: ctx.spanId,
          }
        : {}),
    },
  });

  // Mirror to stdout so local dev sees logs without needing a backend
  const record: Record<string, unknown> = {
    ts: new Date().toISOString(),
    level: severityText,
    msg: message,
    ...attrs,
    ...(ctx ? { trace_id: ctx.traceId, span_id: ctx.spanId } : {}),
  };
  const line = JSON.stringify(record);
  if (severityNumber >= SeverityNumber.ERROR) {
    process.stderr.write(`${line}\n`);
  } else {
    process.stdout.write(`${line}\n`);
  }
}

export const logger = {
  info: (msg: string, attrs?: LogAttrs) => emit(SeverityNumber.INFO, "INFO", msg, attrs),
  warn: (msg: string, attrs?: LogAttrs) => emit(SeverityNumber.WARN, "WARN", msg, attrs),
  error: (msg: string, attrs?: LogAttrs) => emit(SeverityNumber.ERROR, "ERROR", msg, attrs),
};
