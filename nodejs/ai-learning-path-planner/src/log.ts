import { pino } from "pino";

// Imported after src/telemetry.ts has started the SDK, so the pino instrumentation has
// patched pino and each record also goes to the OpenTelemetry logs pipeline.
export const logger = pino({ level: process.env.LOG_LEVEL ?? "info" });
