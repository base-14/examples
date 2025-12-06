import { NodeSDK } from '@opentelemetry/sdk-node';
import { getNodeAutoInstrumentations } from '@opentelemetry/auto-instrumentations-node';
import { MongooseInstrumentation } from '@opentelemetry/instrumentation-mongoose';
import { WinstonInstrumentation } from '@opentelemetry/instrumentation-winston';
import { OTLPTraceExporter } from '@opentelemetry/exporter-trace-otlp-http';
import { OTLPMetricExporter } from '@opentelemetry/exporter-metrics-otlp-http';
import { OTLPLogExporter } from '@opentelemetry/exporter-logs-otlp-http';
import { PeriodicExportingMetricReader } from '@opentelemetry/sdk-metrics';
import { LoggerProvider, BatchLogRecordProcessor } from '@opentelemetry/sdk-logs';
import { logs } from '@opentelemetry/api-logs';
import { resourceFromAttributes } from '@opentelemetry/resources';
import {
  ATTR_SERVICE_NAME,
  ATTR_SERVICE_VERSION,
} from '@opentelemetry/semantic-conventions';
import { config } from './config.js';
import { getLogger } from './utils/logger.js';

const logger = getLogger('telemetry');

export function setupTelemetry(): NodeSDK {
  const resource = resourceFromAttributes({
    [ATTR_SERVICE_NAME]: config.otel.serviceName,
    [ATTR_SERVICE_VERSION]: config.app.version,
    'deployment.environment': config.app.env,
  });

  const logExporter = new OTLPLogExporter({
    url: `${config.otel.endpoint}/v1/logs`,
  });

  const loggerProvider = new LoggerProvider({
    resource,
    processors: [new BatchLogRecordProcessor(logExporter)],
  });

  logs.setGlobalLoggerProvider(loggerProvider);

  const sdk = new NodeSDK({
    resource,
    traceExporter: new OTLPTraceExporter({
      url: `${config.otel.endpoint}/v1/traces`,
    }),
    metricReader: new PeriodicExportingMetricReader({
      exporter: new OTLPMetricExporter({
        url: `${config.otel.endpoint}/v1/metrics`,
      }),
      exportIntervalMillis: 60000,
    }),
    instrumentations: [
      getNodeAutoInstrumentations({
        '@opentelemetry/instrumentation-fs': {
          enabled: false,
        },
        '@opentelemetry/instrumentation-mongodb': {
          enabled: true,
        },
        '@opentelemetry/instrumentation-express': {
          enabled: true,
        },
        '@opentelemetry/instrumentation-http': {
          enabled: true,
        },
        '@opentelemetry/instrumentation-ioredis': {
          enabled: true,
        },
      }),
      new MongooseInstrumentation({
        requireParentSpan: false,
      }),
      new WinstonInstrumentation(),
    ],
  });

  sdk.start();
  logger.info('OpenTelemetry SDK initialized', {
    service: config.otel.serviceName,
    version: config.app.version,
  });

  process.on('SIGTERM', () => {
    sdk
      .shutdown()
      .then(() => logger.info('OpenTelemetry SDK shut down successfully'))
      .catch((error) => logger.error('Error shutting down OpenTelemetry SDK', error as Error))
      .finally(() => process.exit(0));
  });

  return sdk;
}
