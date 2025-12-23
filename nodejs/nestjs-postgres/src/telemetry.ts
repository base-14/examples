import { NodeSDK } from '@opentelemetry/sdk-node';
import { HttpInstrumentation } from '@opentelemetry/instrumentation-http';
import {
  ExpressInstrumentation,
  ExpressLayerType,
} from '@opentelemetry/instrumentation-express';
import { NestInstrumentation } from '@opentelemetry/instrumentation-nestjs-core';
import { PgInstrumentation } from '@opentelemetry/instrumentation-pg';
import { IORedisInstrumentation } from '@opentelemetry/instrumentation-ioredis';
import { OTLPTraceExporter } from '@opentelemetry/exporter-trace-otlp-http';
import { OTLPLogExporter } from '@opentelemetry/exporter-logs-otlp-http';
import { OTLPMetricExporter } from '@opentelemetry/exporter-metrics-otlp-http';
import { PrometheusExporter } from '@opentelemetry/exporter-prometheus';
import {
  PeriodicExportingMetricReader,
  MeterProvider,
} from '@opentelemetry/sdk-metrics';
import {
  LoggerProvider,
  BatchLogRecordProcessor,
} from '@opentelemetry/sdk-logs';
import { logs } from '@opentelemetry/api-logs';
import { metrics } from '@opentelemetry/api';
import { resourceFromAttributes } from '@opentelemetry/resources';
import {
  ATTR_SERVICE_NAME,
  ATTR_SERVICE_VERSION,
} from '@opentelemetry/semantic-conventions';

const serviceName = process.env.OTEL_SERVICE_NAME || 'nestjs-postgres-app';
const serviceVersion = process.env.APP_VERSION || '1.0.0';
const serviceEnvironment = process.env.NODE_ENV || 'development';
const otlpEndpoint =
  process.env.OTEL_EXPORTER_OTLP_ENDPOINT || 'http://localhost:4318';
const prometheusPort = parseInt(process.env.PROMETHEUS_PORT || '9464', 10);

export function setupTelemetry(): NodeSDK {
  const resource = resourceFromAttributes({
    [ATTR_SERVICE_NAME]: serviceName,
    [ATTR_SERVICE_VERSION]: serviceVersion,
    'deployment.environment': serviceEnvironment,
    'service.namespace': 'base14-examples',
    'service.instance.id':
      process.env.HOSTNAME || `${serviceName}-${process.pid}`,
  });

  const prometheusExporter = new PrometheusExporter({
    port: prometheusPort,
  });

  const otlpMetricExporter = new OTLPMetricExporter({
    url: `${otlpEndpoint}/v1/metrics`,
  });

  const otlpMetricReader = new PeriodicExportingMetricReader({
    exporter: otlpMetricExporter,
    exportIntervalMillis: 10000,
  });

  const meterProvider = new MeterProvider({
    resource,
    readers: [prometheusExporter, otlpMetricReader],
  });

  metrics.setGlobalMeterProvider(meterProvider);

  const logExporter = new OTLPLogExporter({
    url: `${otlpEndpoint}/v1/logs`,
  });

  const loggerProvider = new LoggerProvider({
    resource,
    processors: [new BatchLogRecordProcessor(logExporter)],
  });

  logs.setGlobalLoggerProvider(loggerProvider);

  const sdk = new NodeSDK({
    resource,
    traceExporter: new OTLPTraceExporter({
      url: `${otlpEndpoint}/v1/traces`,
    }),
    instrumentations: [
      new HttpInstrumentation({
        ignoreIncomingRequestHook: (req) => {
          const url = req.url || '';
          return (
            url.includes('/health') ||
            url.includes('/metrics') ||
            url.includes('/favicon')
          );
        },
      }),
      new ExpressInstrumentation({
        ignoreLayersType: [
          ExpressLayerType.MIDDLEWARE,
          ExpressLayerType.REQUEST_HANDLER,
        ],
      }),
      new NestInstrumentation(),
      new PgInstrumentation({
        enhancedDatabaseReporting: true,
      }),
      new IORedisInstrumentation({
        dbStatementSerializer: (cmdName, cmdArgs) => {
          return `${cmdName} ${cmdArgs.slice(0, 2).join(' ')}`;
        },
      }),
    ],
  });

  sdk.start();
  console.log(
    `OpenTelemetry SDK initialized for ${serviceName} (${serviceEnvironment})`,
  );
  console.log(`  - Traces: ${otlpEndpoint}/v1/traces`);
  console.log(
    `  - Metrics: ${otlpEndpoint}/v1/metrics (OTLP) + http://localhost:${prometheusPort}/metrics (Prometheus)`,
  );
  console.log(`  - Logs: ${otlpEndpoint}/v1/logs`);
  console.log(
    `  - Instrumentations: HTTP, Express, NestJS, PostgreSQL, Redis/IORedis`,
  );

  process.on('SIGTERM', () => {
    Promise.all([sdk.shutdown(), meterProvider.shutdown()])
      .then(() => console.log('OpenTelemetry SDK shut down successfully'))
      .catch((error) =>
        console.error('Error shutting down OpenTelemetry SDK', error),
      )
      .finally(() => process.exit(0));
  });

  return sdk;
}
