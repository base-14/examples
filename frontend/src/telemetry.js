import { WebTracerProvider } from '@opentelemetry/sdk-trace-web';
import { registerInstrumentations } from '@opentelemetry/instrumentation';
import { BatchSpanProcessor } from '@opentelemetry/sdk-trace-base';
import { OTLPTraceExporter } from '@opentelemetry/exporter-trace-otlp-http';
import { OTLPMetricExporter } from '@opentelemetry/exporter-metrics-otlp-http';
import { OTLPLogExporter } from '@opentelemetry/exporter-logs-otlp-http';
import { defaultResource, resourceFromAttributes } from '@opentelemetry/resources';
import { getWebAutoInstrumentations } from '@opentelemetry/auto-instrumentations-web';
import { MeterProvider, PeriodicExportingMetricReader } from '@opentelemetry/sdk-metrics';
import { LoggerProvider, SimpleLogRecordProcessor } from '@opentelemetry/sdk-logs';
import * as logsAPI from '@opentelemetry/api-logs';
import * as api from '@opentelemetry/api';

export const setupTelemetry = () => {
  // Create resource
  const resource = defaultResource().merge(
    resourceFromAttributes({
      'service.name': 'course-management-app',
      'service.version': '1.0.0',
    })
  );
  

  //  Configure Traces
  const traceExporter = new OTLPTraceExporter({
    url: 'http://localhost:4318/v1/traces',
  });
  
  const traceProvider = new WebTracerProvider({
    resource,
    spanProcessors: [new BatchSpanProcessor(traceExporter)],
  });
  
  api.trace.setGlobalTracerProvider(traceProvider);

  //  Configure Metrics
  const metricExporter = new OTLPMetricExporter({
    url: 'http://localhost:4318/v1/metrics',
  });
  
  const meterProvider = new MeterProvider({
    resource,
    readers: [
      new PeriodicExportingMetricReader({
        exporter: metricExporter,
        exportIntervalMillis: 10000, // 10 seconds
      })
    ],
  });

  api.metrics.setGlobalMeterProvider(meterProvider);
  
  // Configure Logs
  const logExporter = new OTLPLogExporter({
    url: 'http://localhost:4318/v1/logs',
  });
  
  const loggerProvider = new LoggerProvider({
    resource,
    processors: [new SimpleLogRecordProcessor(logExporter)],
  });
  
  logsAPI.logs.setGlobalLoggerProvider(loggerProvider);

  // Auto-instrumentation
  registerInstrumentations({
    instrumentations: [
      getWebAutoInstrumentations({
        '@opentelemetry/instrumentation-xml-http-request': {
          propagateTraceHeaderCorsUrls: [/.+/g],
        },
        '@opentelemetry/instrumentation-fetch': {
          propagateTraceHeaderCorsUrls: [/.+/g],
        },
      }),
    ],
  });
};
