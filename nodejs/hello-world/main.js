/**
 * Node.js Hello World — OpenTelemetry
 */

const api = require("@opentelemetry/api");
const { SeverityNumber } = require("@opentelemetry/api-logs");
const {
  detectResources, hostDetector, osDetector, processDetector, resourceFromAttributes,
} = require("@opentelemetry/resources");
const { NodeTracerProvider } = require("@opentelemetry/sdk-trace-node");
const { BatchSpanProcessor } = require("@opentelemetry/sdk-trace-base");
const { OTLPTraceExporter } = require("@opentelemetry/exporter-trace-otlp-http");
const { LoggerProvider, BatchLogRecordProcessor } = require("@opentelemetry/sdk-logs");
const { OTLPLogExporter } = require("@opentelemetry/exporter-logs-otlp-http");
const { MeterProvider, PeriodicExportingMetricReader } = require("@opentelemetry/sdk-metrics");
const { OTLPMetricExporter } = require("@opentelemetry/exporter-metrics-otlp-http");

// -- Configuration ----------------------------------------------------------
// The collector endpoint. Set this to where your OTel collector accepts
// OTLP/HTTP traffic (default port 4318).
const endpoint = process.env.OTEL_EXPORTER_OTLP_ENDPOINT;
if (!endpoint) {
  console.error("Set OTEL_EXPORTER_OTLP_ENDPOINT (e.g. http://localhost:4318)");
  process.exit(1);
}

// -- Application Logic ------------------------------------------------------

function sayHello(tracer, otelLogger, helloCounter) {
  // A span represents a unit of work. Everything inside this callback
  // is part of the "say-hello" span.
  tracer.startActiveSpan("say-hello", (span) => {
    // This log is emitted inside the span, so it carries the span's trace ID.
    // In Scout, you can jump to the trace from a log detail.
    otelLogger.emit({ severityText: "INFO", severityNumber: SeverityNumber.INFO, body: "Hello, World!" });
    helloCounter.add(1);
    span.setAttribute("greeting", "Hello, World!");
    span.end();
  });
}

function checkDiskSpace(tracer, otelLogger) {
  // Warnings show up in Scout with a distinct severity level, making
  // them easy to filter and spot before they become errors.
  tracer.startActiveSpan("check-disk-space", (span) => {
    otelLogger.emit({ severityText: "WARN", severityNumber: SeverityNumber.WARN, body: "Disk usage above 90%" });
    span.setAttribute("disk.usage_percent", 92);
    span.end();
  });
}

function parseConfig(tracer, otelLogger) {
  // recordException attaches the stack trace to the span.
  // setStatus marks the span as errored so it stands out in TraceX.
  tracer.startActiveSpan("parse-config", (span) => {
    const error = new Error("invalid config: missing 'database_url'");
    span.recordException(error);
    span.setStatus({ code: api.SpanStatusCode.ERROR, message: error.message });
    otelLogger.emit({
      severityText: "ERROR",
      severityNumber: SeverityNumber.ERROR,
      body: `Failed to parse configuration: ${error.message}`,
    });
    span.end();
  });
}

// -- Run --------------------------------------------------------------------

async function main() {
  // A Resource identifies your application in the telemetry backend.
  // Every span, log, and metric carries this identity.
  // Resource detectors auto-populate host, OS, and process attributes.
  const detected = await detectResources({ detectors: [hostDetector, osDetector, processDetector] });
  const resource = resourceFromAttributes({ "service.name": "hello-world-nodejs" }).merge(detected);

  // -- Traces ---------------------------------------------------------------
  // A TracerProvider manages the lifecycle of traces. It batches spans and
  // sends them to the collector via the OTLP/HTTP exporter.
  const tracerProvider = new NodeTracerProvider({
    resource,
    spanProcessors: [
      new BatchSpanProcessor(new OTLPTraceExporter({ url: `${endpoint}/v1/traces` })),
    ],
  });
  tracerProvider.register();
  const tracer = api.trace.getTracer("hello-world-nodejs");

  // -- Logs -----------------------------------------------------------------
  // A LoggerProvider sends structured logs to the collector. Logs emitted
  // inside a span automatically carry the span's trace ID and span ID —
  // this is called log-trace correlation.
  const loggerProvider = new LoggerProvider({
    resource,
    processors: [
      new BatchLogRecordProcessor(new OTLPLogExporter({ url: `${endpoint}/v1/logs` })),
    ],
  });
  const otelLogger = loggerProvider.getLogger("hello-world-nodejs");

  // -- Metrics --------------------------------------------------------------
  // A MeterProvider manages metrics. The PeriodicExportingMetricReader collects
  // and exports metric data at regular intervals.
  const meterProvider = new MeterProvider({
    resource,
    readers: [
      new PeriodicExportingMetricReader({
        exporter: new OTLPMetricExporter({ url: `${endpoint}/v1/metrics` }),
        exportIntervalMillis: 5000,
      }),
    ],
  });
  const meter = meterProvider.getMeter("hello-world-nodejs");

  // A counter tracks how many times something happens.
  const helloCounter = meter.createCounter("hello.count", {
    description: "Number of times the hello-world app has run",
  });

  // -- Run application logic ------------------------------------------------
  sayHello(tracer, otelLogger, helloCounter);
  checkDiskSpace(tracer, otelLogger);
  parseConfig(tracer, otelLogger);

  // -- Shutdown -------------------------------------------------------------
  // Flush all buffered telemetry to the collector before exiting.
  // Without this, the last batch of spans/logs/metrics may be lost.
  await tracerProvider.shutdown();
  await loggerProvider.shutdown();
  await meterProvider.shutdown();

  console.log("Done. Check Scout for your trace, log, and metric.");
}

main();
