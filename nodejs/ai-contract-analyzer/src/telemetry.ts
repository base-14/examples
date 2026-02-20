import { metrics } from "@opentelemetry/api";
import { OTLPMetricExporter } from "@opentelemetry/exporter-metrics-otlp-http";
import { OTLPTraceExporter } from "@opentelemetry/exporter-trace-otlp-http";
import { registerInstrumentations } from "@opentelemetry/instrumentation";
import { PgInstrumentation } from "@opentelemetry/instrumentation-pg";
import { MeterProvider, PeriodicExportingMetricReader } from "@opentelemetry/sdk-metrics";
import * as traceloop from "@traceloop/node-server-sdk";

// Read config directly from env — avoids circular import with config.ts
const otelEnabled = Bun.env.OTEL_ENABLED !== "false";
const endpoint = Bun.env.OTEL_EXPORTER_OTLP_ENDPOINT ?? "http://localhost:4318";
const serviceName = Bun.env.OTEL_SERVICE_NAME ?? "ai-contract-analyzer";

if (otelEnabled) {
  // OpenLLMetry auto-instruments all Vercel AI SDK + Anthropic + OpenAI calls,
  // emitting GenAI semantic convention spans without manual wiring.
  traceloop.initialize({
    appName: serviceName,
    disableBatch: false,
    exporter: new OTLPTraceExporter({
      url: `${endpoint}/v1/traces`,
    }),
  });

  // Add PostgreSQL auto-instrumentation to the global TracerProvider set by traceloop
  registerInstrumentations({
    instrumentations: [new PgInstrumentation()],
  });

  // Separate metrics provider for custom business metrics (pipeline stage
  // durations, clause counts, risk scores, token usage, cost).
  const meterProvider = new MeterProvider({
    readers: [
      new PeriodicExportingMetricReader({
        exporter: new OTLPMetricExporter({
          url: `${endpoint}/v1/metrics`,
        }),
        exportIntervalMillis: 15_000,
      }),
    ],
  });

  metrics.setGlobalMeterProvider(meterProvider);
}
