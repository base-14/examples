import { DiagConsoleLogger, DiagLogLevel, diag } from "@opentelemetry/api";
import { logs } from "@opentelemetry/api-logs";
import { OTLPLogExporter } from "@opentelemetry/exporter-logs-otlp-http";
import { OTLPMetricExporter } from "@opentelemetry/exporter-metrics-otlp-http";
import { OTLPTraceExporter } from "@opentelemetry/exporter-trace-otlp-http";
import { PgInstrumentation } from "@opentelemetry/instrumentation-pg";
import { BatchLogRecordProcessor, LoggerProvider } from "@opentelemetry/sdk-logs";
import { PeriodicExportingMetricReader } from "@opentelemetry/sdk-metrics";
import { NodeSDK } from "@opentelemetry/sdk-node";

// Read config directly from env — avoids circular import with config.ts
const otelEnabled = Bun.env.OTEL_ENABLED !== "false";
const endpoint = Bun.env.OTEL_EXPORTER_OTLP_ENDPOINT ?? "http://localhost:4318";
const serviceName = Bun.env.OTEL_SERVICE_NAME ?? "ai-contract-analyzer";

if (otelEnabled) {
  diag.setLogger(new DiagConsoleLogger(), DiagLogLevel.WARN);

  // ── Traces + Metrics ───────────────────────────────────────────────────────
  // NodeSDK owns the global MeterProvider when metricReader is passed here —
  // avoids the duplicate-registration error that occurs when a separate
  // MeterProvider is created after sdk.start() registers one internally.
  // NodeSDK also handles SIGTERM (flushes pending spans/metrics before exit)
  // and bootstraps PgInstrumentation before pg is imported.
  const sdk = new NodeSDK({
    serviceName,
    traceExporter: new OTLPTraceExporter({ url: `${endpoint}/v1/traces` }),
    metricReaders: [
      new PeriodicExportingMetricReader({
        exporter: new OTLPMetricExporter({ url: `${endpoint}/v1/metrics` }),
        exportIntervalMillis: 15_000,
        exportTimeoutMillis: 10_000,
      }),
    ],
    instrumentations: [new PgInstrumentation()],
  });
  sdk.start();

  // ── Logs ───────────────────────────────────────────────────────────────────
  // Logs are exported to the collector so Scout can correlate them with traces
  // via trace_id / span_id injected by logger.ts.
  const loggerProvider = new LoggerProvider({
    processors: [new BatchLogRecordProcessor(new OTLPLogExporter({ url: `${endpoint}/v1/logs` }))],
  });
  logs.setGlobalLoggerProvider(loggerProvider);
}
