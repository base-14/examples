const { NodeSDK } = require('@opentelemetry/sdk-node');

const {Resource } = require('@opentelemetry/resources');
const { OTLPTraceExporter } = require('@opentelemetry/exporter-trace-otlp-http'); 
const {OTLPMetricExporter} = require('@opentelemetry/exporter-metrics-otlp-http')
const {PeriodicExportingMetricReader} = require('@opentelemetry/sdk-metrics');
const { BatchSpanProcessor } = require('@opentelemetry/sdk-trace-base');
const { BatchLogRecordProcessor } = require('@opentelemetry/sdk-logs');
const { OTLPLogExporter } = require('@opentelemetry/exporter-logs-otlp-http');
// Define your service information
const resource = new Resource({
  'service.name': 'course-management-app-backend',
  'service.version': '1.0.0',
});

// This creates a tracer that outputs to your console
const sdk = new NodeSDK({
  resource,
  spanProcessor: new BatchSpanProcessor( new OTLPTraceExporter({
    url: 'http://localhost:4318/v1/traces'
  })),
  metricReader: new PeriodicExportingMetricReader({
    exporter: new OTLPMetricExporter({
      url: 'http://localhost:4318/v1/metrics'
    }),
  }),

  logRecordProcessor: new BatchLogRecordProcessor(new OTLPLogExporter({
    url: 'http://localhost:4318/v1/logs'
  })),
});

// Start the tracer
sdk.start();

// Gracefully shut down SDK on process exit
process.on('SIGTERM', () => {
  sdk.shutdown()
    .then(() => console.log('Tracing terminated'))
    .catch((error) => console.log('Error terminating tracing', error))
    .finally(() => process.exit(0));
});