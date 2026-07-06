import { NodeSDK } from '@opentelemetry/sdk-node';
import { getNodeAutoInstrumentations } from '@opentelemetry/auto-instrumentations-node';
import { OTLPTraceExporter } from '@opentelemetry/exporter-trace-otlp-proto';
import { OTLPMetricExporter } from '@opentelemetry/exporter-metrics-otlp-proto';
import { OTLPLogExporter } from '@opentelemetry/exporter-logs-otlp-proto';
import { PeriodicExportingMetricReader } from '@opentelemetry/sdk-metrics';
import { BatchLogRecordProcessor } from '@opentelemetry/sdk-logs';
import { resourceFromAttributes } from '@opentelemetry/resources';
import { ATTR_SERVICE_NAME, ATTR_SERVICE_VERSION } from '@opentelemetry/semantic-conventions';

const env = process.env.DEPLOY_ENV || 'development';
const base = process.env.OTEL_EXPORTER_OTLP_ENDPOINT || 'http://localhost:4318';

// http.server.request.duration + runtime-node metrics and pino log-bridging are
// automatic once a reader/processor exists. Stable metric name needs
// OTEL_SEMCONV_STABILITY_OPT_IN=http (compose.yaml).
const sdk = new NodeSDK({
  resource: resourceFromAttributes({
    [ATTR_SERVICE_NAME]: 'angular-items-api',
    [ATTR_SERVICE_VERSION]: '1.0.0',
    'deployment.environment.name': env,
    environment: env,
  }),
  traceExporter: new OTLPTraceExporter({ url: `${base}/v1/traces` }),
  metricReaders: [
    new PeriodicExportingMetricReader({
      exporter: new OTLPMetricExporter({ url: `${base}/v1/metrics` }),
      exportIntervalMillis: 10000,
    }),
  ],
  logRecordProcessors: [
    new BatchLogRecordProcessor(new OTLPLogExporter({ url: `${base}/v1/logs` })),
  ],
  instrumentations: [
    getNodeAutoInstrumentations({
      '@opentelemetry/instrumentation-runtime-node': { enabled: true },
    }),
  ],
});

sdk.start();
