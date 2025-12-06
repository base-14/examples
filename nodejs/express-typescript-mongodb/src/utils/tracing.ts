import { trace, SpanStatusCode, context as otelContext, type Span } from '@opentelemetry/api';

type AsyncSpanFn<T> = (span: Span) => Promise<T>;

export function withSpan<T>(tracerName: string, spanName: string, fn: AsyncSpanFn<T>): Promise<T> {
  const tracer = trace.getTracer(tracerName);
  const span = tracer.startSpan(spanName);

  return otelContext
    .with(trace.setSpan(otelContext.active(), span), async () => {
      try {
        const result = await fn(span);
        span.setStatus({ code: SpanStatusCode.OK });
        return result;
      } catch (error) {
        span.recordException(error as Error);
        span.setStatus({ code: SpanStatusCode.ERROR, message: (error as Error).message });
        throw error;
      } finally {
        span.end();
      }
    });
}

export function setSpanError(span: Span, message: string): void {
  span.setStatus({ code: SpanStatusCode.ERROR, message });
}
