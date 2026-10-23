import { OTLPLogExporter } from "@opentelemetry/exporter-logs-otlp-http";
import { OTLPMetricExporter } from "@opentelemetry/exporter-metrics-otlp-http";
import { OTLPTraceExporter } from "@opentelemetry/exporter-trace-otlp-http";
import { resourceFromAttributes } from "@opentelemetry/resources";
import { BatchLogRecordProcessor } from "@opentelemetry/sdk-logs";
import { PeriodicExportingMetricReader } from "@opentelemetry/sdk-metrics";
import { NodeSDK } from "@opentelemetry/sdk-node";
import {
  ATTR_SERVICE_NAME,
  ATTR_SERVICE_VERSION,
} from "@opentelemetry/semantic-conventions";

const endpoint =
  process.env.OTEL_EXPORTER_OTLP_ENDPOINT ?? "http://localhost:4318";

const resource = resourceFromAttributes({
  [ATTR_SERVICE_NAME]: process.env.OTEL_SERVICE_NAME ?? "elysia-notify",
  [ATTR_SERVICE_VERSION]: process.env.OTEL_SERVICE_VERSION ?? "1.0.0",
});

const sdk = new NodeSDK({
  resource,
  traceExporter: new OTLPTraceExporter({ url: `${endpoint}/v1/traces` }),
  metricReaders: [
    new PeriodicExportingMetricReader({
      exporter: new OTLPMetricExporter({ url: `${endpoint}/v1/metrics` }),
      exportIntervalMillis: parseInt(
        process.env.OTEL_METRIC_EXPORT_INTERVAL || "10000"
      ),
    }),
  ],
  logRecordProcessors: [
    new BatchLogRecordProcessor({
      exporter: new OTLPLogExporter({ url: `${endpoint}/v1/logs` }),
    }),
  ],
});
sdk.start();

process.on("SIGTERM", async () => {
  await sdk.shutdown();
  process.exit(0);
});
