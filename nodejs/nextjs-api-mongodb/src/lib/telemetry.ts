import { NodeSDK } from '@opentelemetry/sdk-node';
import { getNodeAutoInstrumentations } from '@opentelemetry/auto-instrumentations-node';
import { OTLPTraceExporter } from '@opentelemetry/exporter-trace-otlp-http';
import { OTLPMetricExporter } from '@opentelemetry/exporter-metrics-otlp-http';
import { resourceFromAttributes } from '@opentelemetry/resources';
import { ATTR_SERVICE_NAME, ATTR_SERVICE_VERSION } from '@opentelemetry/semantic-conventions';
import { MeterProvider, PeriodicExportingMetricReader } from '@opentelemetry/sdk-metrics';
import { PrometheusExporter } from '@opentelemetry/exporter-prometheus';
import { trace, metrics, SpanStatusCode } from '@opentelemetry/api';

const serviceName = process.env.OTEL_SERVICE_NAME || 'nextjs-api-mongodb';
const otlpEndpoint = process.env.OTEL_EXPORTER_OTLP_ENDPOINT || 'http://localhost:4318';

const resource = resourceFromAttributes({
  [ATTR_SERVICE_NAME]: serviceName,
  [ATTR_SERVICE_VERSION]: '1.0.0',
  'deployment.environment': process.env.NODE_ENV || 'development',
});

const traceExporter = new OTLPTraceExporter({
  url: `${otlpEndpoint}/v1/traces`,
});

const otlpMetricReader = new PeriodicExportingMetricReader({
  exporter: new OTLPMetricExporter({
    url: `${otlpEndpoint}/v1/metrics`,
  }),
  exportIntervalMillis: 60000,
});

const prometheusExporter = new PrometheusExporter({
  preventServerStart: true,
});

const meterProvider = new MeterProvider({
  resource,
  readers: [otlpMetricReader, prometheusExporter],
});

metrics.setGlobalMeterProvider(meterProvider);

const sdk = new NodeSDK({
  resource,
  traceExporter,
  instrumentations: [
    getNodeAutoInstrumentations({
      '@opentelemetry/instrumentation-http': {
        ignoreIncomingRequestHook: (request) => {
          const url = request.url || '';
          return url.startsWith('/_next') || url === '/favicon.ico';
        },
      },
      '@opentelemetry/instrumentation-fs': {
        enabled: false,
      },
      '@opentelemetry/instrumentation-dns': {
        enabled: false,
      },
      '@opentelemetry/instrumentation-net': {
        enabled: false,
      },
      '@opentelemetry/instrumentation-ioredis': {
        enabled: false,
      },
    }),
  ],
});

sdk.start();

process.on('SIGTERM', () => {
  Promise.all([sdk.shutdown(), meterProvider.shutdown()])
    .then(() => console.log('Telemetry SDK shut down successfully'))
    .catch((error) => console.error('Error shutting down SDK', error))
    .finally(() => process.exit(0));
});

console.log(`OpenTelemetry initialized for service: ${serviceName}`);

export function getTracer(name: string = 'api') {
  return trace.getTracer(name);
}

export function getMeter(name: string = 'api') {
  return metrics.getMeter(name);
}

export async function withSpan<T>(
  spanName: string,
  fn: () => Promise<T>,
  attributes?: Record<string, string | number | boolean>
): Promise<T> {
  const tracer = getTracer();
  return tracer.startActiveSpan(spanName, async (span) => {
    try {
      if (attributes) {
        Object.entries(attributes).forEach(([key, value]) => {
          span.setAttribute(key, value);
        });
      }
      const result = await fn();
      span.setStatus({ code: SpanStatusCode.OK });
      return result;
    } catch (error) {
      span.recordException(error as Error);
      span.setStatus({
        code: SpanStatusCode.ERROR,
        message: error instanceof Error ? error.message : 'Unknown error',
      });
      throw error;
    } finally {
      span.end();
    }
  });
}

export function getPrometheusExporter(): PrometheusExporter {
  return prometheusExporter;
}

export { SpanStatusCode };
