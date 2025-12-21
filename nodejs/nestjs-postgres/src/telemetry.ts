import { NodeSDK } from '@opentelemetry/sdk-node';
import { HttpInstrumentation } from '@opentelemetry/instrumentation-http';
import {
  ExpressInstrumentation,
  ExpressLayerType,
} from '@opentelemetry/instrumentation-express';
import { NestInstrumentation } from '@opentelemetry/instrumentation-nestjs-core';
import { PgInstrumentation } from '@opentelemetry/instrumentation-pg';
import { OTLPTraceExporter } from '@opentelemetry/exporter-trace-otlp-http';
import { OTLPLogExporter } from '@opentelemetry/exporter-logs-otlp-http';
import { PrometheusExporter } from '@opentelemetry/exporter-prometheus';
import {
  LoggerProvider,
  BatchLogRecordProcessor,
} from '@opentelemetry/sdk-logs';
import { logs } from '@opentelemetry/api-logs';
import { resourceFromAttributes } from '@opentelemetry/resources';
import {
  ATTR_SERVICE_NAME,
  ATTR_SERVICE_VERSION,
} from '@opentelemetry/semantic-conventions';

const serviceName = process.env.OTEL_SERVICE_NAME || 'nestjs-postgres-app';
const serviceVersion = process.env.APP_VERSION || '1.0.0';
const environment = process.env.NODE_ENV || 'development';
const otlpEndpoint =
  process.env.OTEL_EXPORTER_OTLP_ENDPOINT || 'http://localhost:4318';
const prometheusPort = parseInt(process.env.PROMETHEUS_PORT || '9464', 10);

export function setupTelemetry(): NodeSDK {
  const prometheusExporter = new PrometheusExporter({
    port: prometheusPort,
  });

  const resource = resourceFromAttributes({
    [ATTR_SERVICE_NAME]: serviceName,
    [ATTR_SERVICE_VERSION]: serviceVersion,
    'deployment.environment': environment,
  });

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
    metricReader: prometheusExporter,
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
    ],
  });

  sdk.start();
  console.log(`OpenTelemetry SDK initialized for ${serviceName}`);
  console.log(
    `Prometheus metrics available at http://localhost:${prometheusPort}/metrics`,
  );

  process.on('SIGTERM', () => {
    sdk
      .shutdown()
      .then(() => console.log('OpenTelemetry SDK shut down successfully'))
      .catch((error) =>
        console.error('Error shutting down OpenTelemetry SDK', error),
      )
      .finally(() => process.exit(0));
  });

  return sdk;
}
