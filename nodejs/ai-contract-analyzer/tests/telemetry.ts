/**
 * In-memory OTel providers for the tests.
 *
 * `tests/setup.ts` imports this before any test file loads, so the instruments
 * in `src/llm/instruments.ts` bind to the providers registered here rather than
 * to the no-op defaults.
 */
import { type Attributes, context, metrics, trace } from "@opentelemetry/api";
import { AsyncLocalStorageContextManager } from "@opentelemetry/context-async-hooks";
import {
  AggregationTemporality,
  DataPointType,
  type Histogram,
  InMemoryMetricExporter,
  MeterProvider,
  PeriodicExportingMetricReader,
} from "@opentelemetry/sdk-metrics";
import {
  BasicTracerProvider,
  InMemorySpanExporter,
  type ReadableSpan,
  SimpleSpanProcessor,
} from "@opentelemetry/sdk-trace-base";

export const spanExporter = new InMemorySpanExporter();

const tracerProvider = new BasicTracerProvider({
  spanProcessors: [new SimpleSpanProcessor(spanExporter)],
});

context.setGlobalContextManager(new AsyncLocalStorageContextManager().enable());
trace.setGlobalTracerProvider(tracerProvider);

const metricReader = new PeriodicExportingMetricReader({
  exporter: new InMemoryMetricExporter(AggregationTemporality.CUMULATIVE),
  exportIntervalMillis: 600_000,
  exportTimeoutMillis: 5_000,
});

const meterProvider = new MeterProvider({ readers: [metricReader] });
metrics.setGlobalMeterProvider(meterProvider);

export function finishedSpans(): ReadableSpan[] {
  return spanExporter.getFinishedSpans();
}

export function findSpan(name: string): ReadableSpan {
  const match = finishedSpans().find((s) => s.name === name);
  if (!match) {
    throw new Error(`span '${name}' not found in [${finishedSpans().map((s) => s.name)}]`);
  }
  return match;
}

export function resetTelemetry(): void {
  spanExporter.reset();
}

export async function shutdownTelemetry(): Promise<void> {
  await meterProvider.shutdown();
  await tracerProvider.shutdown();
}

function matches(pointAttrs: Attributes, wanted: Attributes): boolean {
  return Object.entries(wanted).every(([k, v]) => pointAttrs[k] === v);
}

/** Cumulative value of a counter, or the summed observations of a histogram. */
export async function metricTotal(name: string, attrs: Attributes = {}): Promise<number> {
  let total = 0;
  const { resourceMetrics } = await metricReader.collect();
  for (const scope of resourceMetrics.scopeMetrics) {
    for (const metric of scope.metrics) {
      if (metric.descriptor.name !== name) continue;
      for (const point of metric.dataPoints) {
        if (!matches(point.attributes, attrs)) continue;
        if (metric.dataPointType === DataPointType.SUM) {
          total += point.value as number;
        } else if (metric.dataPointType === DataPointType.HISTOGRAM) {
          total += (point.value as Histogram).sum ?? 0;
        }
      }
    }
  }
  return total;
}

/** Number of histogram observations matching the given attributes. */
export async function metricCount(name: string, attrs: Attributes = {}): Promise<number> {
  let count = 0;
  const { resourceMetrics } = await metricReader.collect();
  for (const scope of resourceMetrics.scopeMetrics) {
    for (const metric of scope.metrics) {
      if (metric.descriptor.name !== name || metric.dataPointType !== DataPointType.HISTOGRAM) {
        continue;
      }
      for (const point of metric.dataPoints) {
        if (matches(point.attributes, attrs)) count += (point.value as Histogram).count;
      }
    }
  }
  return count;
}
