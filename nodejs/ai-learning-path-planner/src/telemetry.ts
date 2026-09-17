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

// Loaded with `node --import ./dist/telemetry.js`, so this whole module runs before the
// app's first import. The loader hook has to be registered here rather than left to the
// SDK: under ESM on Node 26 the HTTP server span is missing entirely unless the hook is
// in place before anything imports node:http, while the agent spans look correct either
// way (SPIKE-FINDINGS.md section 6). Node 26 prints DEP0205 for module.register; the
// otel hook is written for it and still works.
register("@opentelemetry/instrumentation/hook.mjs", import.meta.url);

const config = loadConfig();

// Read rather than imported: package.json sits outside rootDir, so a static import would
// not compile, and hardcoding the version means the next version bump ships the old one on
// every span. dist/telemetry.js and src/telemetry.ts are both one directory below the
// package root, so this resolves the same under tsc and under tsx.
const { version } = JSON.parse(
  readFileSync(new URL("../package.json", import.meta.url), "utf8"),
) as { version: string };

// costOf throws when PRICE_MODEL names a model the price table does not have, and
// PlanCostSpanProcessor calls it in onEnd, on the SDK's span-export path. Checking the
// same thing here turns that into a boot failure next to the variable that caused it.
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

// Both signals, not just SIGTERM. Shutting down flushes the pending span batch and the
// pending metric interval, and a service started in the foreground is stopped with Ctrl-C,
// which is SIGINT. Without this, a measured run ended that way loses its last batch and up
// to a whole metric interval of plan runs, silently.
for (const signal of ["SIGTERM", "SIGINT"] as const) {
  process.on(signal, () => {
    void sdk.shutdown().finally(() => process.exit(0));
  });
}
