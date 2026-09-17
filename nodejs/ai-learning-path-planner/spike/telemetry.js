import { NodeSDK } from '@opentelemetry/sdk-node';
import { ConsoleSpanExporter, SimpleSpanProcessor } from '@opentelemetry/sdk-trace-base';
import { HttpInstrumentation } from '@opentelemetry/instrumentation-http';
import { resourceFromAttributes } from '@opentelemetry/resources';
import { trace } from '@opentelemetry/api';
import { registerTelemetry } from 'ai';
import { OpenTelemetry } from '@ai-sdk/otel';

export const collected = [];

class CollectingProcessor {
  onStart() {}
  onEnd(span) {
    collected.push({
      name: span.name,
      kind: span.kind,
      traceId: span.spanContext().traceId,
      spanId: span.spanContext().spanId,
      parentSpanId: span.parentSpanContext?.spanId ?? span.parentSpanId,
      startMs: span.startTime[0] * 1e3 + span.startTime[1] / 1e6,
      endMs: span.endTime[0] * 1e3 + span.endTime[1] / 1e6,
      attributes: { ...span.attributes },
    });
  }
  shutdown() { return Promise.resolve(); }
  forceFlush() { return Promise.resolve(); }
}

export const enrichSpanCalls = [];

const processors = [new CollectingProcessor()];
if (process.env.SPIKE_CONSOLE === '1') {
  processors.push(new SimpleSpanProcessor(new ConsoleSpanExporter()));
}

const sdk = new NodeSDK({
  resource: resourceFromAttributes({ 'service.name': 'learning-path-planner-spike' }),
  spanProcessors: processors,
  instrumentations: [new HttpInstrumentation()],
});
sdk.start();

registerTelemetry(
  new OpenTelemetry({
    tracer: trace.getTracer('learning-path-planner-spike'),
    usage: true,
    providerMetadata: true,
    runtimeContext: true,
    enrichSpan: (options) => {
      enrichSpanCalls.push({
        spanType: options.spanType,
        operationId: options.operationId,
        callId: options.callId,
        runtimeContext: options.runtimeContext,
        argKeys: Object.keys(options),
      });
      return { 'base14.spike.span_type': options.spanType };
    },
  }),
);

export async function shutdown() {
  await sdk.shutdown();
}
