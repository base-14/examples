import { readFileSync } from "node:fs";
import { register } from "node:module";
import { OpenTelemetry } from "@ai-sdk/otel";
import { getNodeAutoInstrumentations } from "@opentelemetry/auto-instrumentations-node";
import { OTLPMetricExporter } from "@opentelemetry/exporter-metrics-otlp-http";
import { OTLPTraceExporter } from "@opentelemetry/exporter-trace-otlp-http";
import { resourceFromAttributes } from "@opentelemetry/resources";
import { NodeSDK, metrics as sdkMetrics } from "@opentelemetry/sdk-node";
import { BatchSpanProcessor } from "@opentelemetry/sdk-trace-base";
import { ATTR_SERVICE_NAME, ATTR_SERVICE_VERSION } from "@opentelemetry/semantic-conventions";
import { registerTelemetry } from "ai";
import { loadConfig } from "./config.js";
import { assertPriceModelIsKnown } from "./llm/cost.js";
import { enrichSpan, PlanCostSpanProcessor } from "./telemetry/enrich.js";

// Loaded with `node --import`, so this runs before the app's first import. Under ESM the HTTP
// server span is missing entirely unless the loader hook is registered before anything imports
// node:http; the agent spans look correct either way. Node 26 prints DEP0205 for
// module.register, which the otel hook is written for.
register("@opentelemetry/instrumentation/hook.mjs", import.meta.url);

const config = loadConfig();

// Read, not imported: package.json sits outside rootDir. dist/telemetry.js and src/telemetry.ts
// are the same depth below the package root, so the path resolves under tsc and tsx alike.
const { version } = JSON.parse(
  readFileSync(new URL("../package.json", import.meta.url), "utf8"),
) as { version: string };

// costOf throws on an unknown PRICE_MODEL, and PlanCostSpanProcessor calls it on the export
// path. Checking here turns that into a boot failure next to the variable that caused it.
assertPriceModelIsKnown(config);

const sdk = new NodeSDK({
  resource: resourceFromAttributes({
    [ATTR_SERVICE_NAME]: "ai-learning-path-planner",
    [ATTR_SERVICE_VERSION]: version,
  }),
  spanProcessors: [
    new PlanCostSpanProcessor(config),
    new BatchSpanProcessor(new OTLPTraceExporter()),
  ],
  metricReader: new sdkMetrics.PeriodicExportingMetricReader({
    exporter: new OTLPMetricExporter(),
  }),
  instrumentations: [getNodeAutoInstrumentations()],
});

sdk.start();

registerTelemetry(
  new OpenTelemetry({
    enrichSpan,
    usage: true,
  }),
);

// Both signals: a foreground service is stopped with Ctrl-C, and without SIGINT the shutdown
// flush never runs, losing the last span batch and up to a whole metric interval.
for (const signal of ["SIGTERM", "SIGINT"] as const) {
  process.on(signal, () => {
    void sdk.shutdown().finally(() => process.exit(0));
  });
}
