import { NodeSDK } from '@opentelemetry/sdk-node';
import { OTLPTraceExporter } from '@opentelemetry/exporter-trace-otlp-http';
import { OTLPMetricExporter } from '@opentelemetry/exporter-metrics-otlp-http';
import { OTLPLogExporter } from '@opentelemetry/exporter-logs-otlp-http';
import { resourceFromAttributes } from '@opentelemetry/resources';
import { ATTR_SERVICE_NAME, ATTR_SERVICE_VERSION } from '@opentelemetry/semantic-conventions';
import { getNodeAutoInstrumentations } from '@opentelemetry/auto-instrumentations-node';
import { BatchSpanProcessor } from '@opentelemetry/sdk-trace-base';
import { PeriodicExportingMetricReader } from '@opentelemetry/sdk-metrics';
import { BatchLogRecordProcessor, LoggerProvider } from '@opentelemetry/sdk-logs';
import { logs, SeverityNumber } from '@opentelemetry/api-logs';

const OTEL_ENDPOINT = process.env.OTEL_EXPORTER_OTLP_ENDPOINT || 'http://localhost:4318';

const resource = resourceFromAttributes({
  [ATTR_SERVICE_NAME]: process.env.OTEL_SERVICE_NAME || 'sample-nextjs-app',
  [ATTR_SERVICE_VERSION]: '1.0.0',
  'deployment.environment': process.env.NODE_ENV || 'development',
});

const sdk = new NodeSDK({
  resource,

  // Traces — batch and export via OTLP HTTP
  spanProcessor: new BatchSpanProcessor(
    new OTLPTraceExporter({
      url: `${OTEL_ENDPOINT}/v1/traces`,
    })
  ),

  // Metrics — periodic export every 10s
  metricReader: new PeriodicExportingMetricReader({
    exporter: new OTLPMetricExporter({
      url: `${OTEL_ENDPOINT}/v1/metrics`,
    }),
    exportIntervalMillis: 10_000,
  }),

  // Logs — batch and export via OTLP HTTP
  logRecordProcessors: [
    new BatchLogRecordProcessor(
      new OTLPLogExporter({
        url: `${OTEL_ENDPOINT}/v1/logs`,
      })
    ),
  ],

  // Auto-instrument HTTP, fetch, etc. Disable noisy ones.
  instrumentations: [
    getNodeAutoInstrumentations({
      '@opentelemetry/instrumentation-http': {
        ignoreIncomingRequestHook: (request) => {
          const url = request.url || '';
          // Skip static assets and health checks
          return url.startsWith('/_next') || url === '/favicon.ico';
        },
      },
      // Disable noisy low-level instrumentations
      '@opentelemetry/instrumentation-fs': { enabled: false },
      '@opentelemetry/instrumentation-dns': { enabled: false },
      '@opentelemetry/instrumentation-net': { enabled: false },
    }),
  ],
});

sdk.start();

// ============================================================
// Console bridge — captures console.log/warn/error as OTel logs.
// This catches Next.js internal error output (e.g. "⨯ Error: ...")
// that happens when uncaught exceptions occur during SSR.
// ============================================================

const loggerProvider = logs.getLoggerProvider() as LoggerProvider;
if (loggerProvider) {
  const otelLogger = loggerProvider.getLogger('console-bridge');

  const originalConsoleLog = console.log;
  const originalConsoleWarn = console.warn;
  const originalConsoleError = console.error;

  console.log = (...args: unknown[]) => {
    originalConsoleLog.apply(console, args);
    otelLogger.emit({
      severityNumber: SeverityNumber.INFO,
      severityText: 'INFO',
      body: args.map(String).join(' '),
      attributes: { 'log.source': 'console.log' },
    });
  };

  console.warn = (...args: unknown[]) => {
    originalConsoleWarn.apply(console, args);
    otelLogger.emit({
      severityNumber: SeverityNumber.WARN,
      severityText: 'WARN',
      body: args.map(String).join(' '),
      attributes: { 'log.source': 'console.warn' },
    });
  };

  console.error = (...args: unknown[]) => {
    originalConsoleError.apply(console, args);
    otelLogger.emit({
      severityNumber: SeverityNumber.ERROR,
      severityText: 'ERROR',
      body: args.map(String).join(' '),
      attributes: { 'log.source': 'console.error' },
    });
  };
}

// Graceful shutdown
process.on('SIGTERM', () => {
  sdk.shutdown().then(
    () => console.log('OTel SDK shut down'),
    (err) => console.error('Error shutting down OTel SDK', err)
  );
});

console.log(`[OTel] Server-side instrumentation initialized — exporting to ${OTEL_ENDPOINT}`);
