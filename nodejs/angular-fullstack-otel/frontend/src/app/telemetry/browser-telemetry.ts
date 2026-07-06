import { WebTracerProvider, BatchSpanProcessor } from '@opentelemetry/sdk-trace-web';
import { OTLPTraceExporter } from '@opentelemetry/exporter-trace-otlp-http';
import {
  MeterProvider,
  PeriodicExportingMetricReader,
  AggregationType,
  type ViewOptions,
} from '@opentelemetry/sdk-metrics';
import { OTLPMetricExporter } from '@opentelemetry/exporter-metrics-otlp-http';
import { LoggerProvider, BatchLogRecordProcessor } from '@opentelemetry/sdk-logs';
import { OTLPLogExporter } from '@opentelemetry/exporter-logs-otlp-http';
import { metrics } from '@opentelemetry/api';
import { logs } from '@opentelemetry/api-logs';
import { resourceFromAttributes } from '@opentelemetry/resources';
import { ATTR_SERVICE_NAME, ATTR_SERVICE_VERSION } from '@opentelemetry/semantic-conventions';
import { registerInstrumentations } from '@opentelemetry/instrumentation';
import { getWebAutoInstrumentations } from '@opentelemetry/auto-instrumentations-web';
import { environment } from '../../environments/environment';
import { setupWebVitals } from './web-vitals';

let initialized = false;

// Default buckets (0, 5, 10, 25, ...) suit neither CLS (a ~0-1 score) nor the ms
// timings; tune boundaries per instrument for useful p75/p95.
const VITAL_VIEWS: ViewOptions[] = [
  {
    instrumentName: 'web_vitals.cls',
    aggregation: {
      type: AggregationType.EXPLICIT_BUCKET_HISTOGRAM,
      options: { boundaries: [0.05, 0.1, 0.15, 0.25, 0.5, 1] },
    },
  },
  {
    instrumentName: 'web_vitals.lcp',
    aggregation: {
      type: AggregationType.EXPLICIT_BUCKET_HISTOGRAM,
      options: { boundaries: [500, 1000, 1500, 2000, 2500, 3000, 4000, 5000, 7500, 10000] },
    },
  },
  {
    instrumentName: 'web_vitals.inp',
    aggregation: {
      type: AggregationType.EXPLICIT_BUCKET_HISTOGRAM,
      options: { boundaries: [50, 100, 150, 200, 300, 500, 750, 1000] },
    },
  },
  {
    instrumentName: 'web_vitals.fcp',
    aggregation: {
      type: AggregationType.EXPLICIT_BUCKET_HISTOGRAM,
      options: { boundaries: [500, 1000, 1500, 1800, 2500, 3000, 4000, 6000] },
    },
  },
  {
    instrumentName: 'web_vitals.ttfb',
    aggregation: {
      type: AggregationType.EXPLICIT_BUCKET_HISTOGRAM,
      options: { boundaries: [100, 200, 400, 600, 800, 1200, 1800, 3000] },
    },
  },
];

// Call once before Angular bootstraps so document-load + early interactions are
// captured.
export function initBrowserTelemetry(): void {
  if (initialized || typeof window === 'undefined') {
    return;
  }
  initialized = true;

  const resource = resourceFromAttributes({
    [ATTR_SERVICE_NAME]: environment.otelServiceName,
    [ATTR_SERVICE_VERSION]: '1.0.0',
    'deployment.environment.name': environment.deploymentEnvironment,
    environment: environment.deploymentEnvironment,
  });

  // --- Traces ---
  const tracerProvider = new WebTracerProvider({
    resource,
    spanProcessors: [
      new BatchSpanProcessor(
        new OTLPTraceExporter({ url: `${environment.otelCollectorUrl}/v1/traces` }),
      ),
    ],
  });
  // Zoneless: installs the StackContextManager + W3C propagator and sets the
  // global TracerProvider.
  tracerProvider.register();

  // --- Metrics ---
  const meterProvider = new MeterProvider({
    resource,
    readers: [
      new PeriodicExportingMetricReader({
        exporter: new OTLPMetricExporter({ url: `${environment.otelCollectorUrl}/v1/metrics` }),
        exportIntervalMillis: 10000,
      }),
    ],
    views: VITAL_VIEWS,
  });
  // No register() sugar for metrics/logs: without setGlobal*, getMeter/getLogger
  // return Noop and every data point is silently dropped.
  metrics.setGlobalMeterProvider(meterProvider);

  // --- Logs ---
  const loggerProvider = new LoggerProvider({
    resource,
    processors: [
      new BatchLogRecordProcessor(
        new OTLPLogExporter({ url: `${environment.otelCollectorUrl}/v1/logs` }),
      ),
    ],
  });
  logs.setGlobalLoggerProvider(loggerProvider);

  // Vitals and last-moment error logs emit as the page hides; flush all signals
  // then so nothing is lost with the tab.
  const flush = (): void => {
    void tracerProvider.forceFlush();
    void meterProvider.forceFlush();
    void loggerProvider.forceFlush();
  };
  window.addEventListener('visibilitychange', () => {
    if (document.visibilityState === 'hidden') {
      flush();
    }
  });
  window.addEventListener('pagehide', flush);

  registerInstrumentations({
    instrumentations: [
      getWebAutoInstrumentations({
        '@opentelemetry/instrumentation-user-interaction': {
          eventNames: ['click', 'submit'],
        },
        '@opentelemetry/instrumentation-fetch': {
          propagateTraceHeaderCorsUrls: environment.apiTraceUrls,
        },
        '@opentelemetry/instrumentation-xml-http-request': {
          propagateTraceHeaderCorsUrls: environment.apiTraceUrls,
        },
      }),
    ],
  });

  setupWebVitals();
}
