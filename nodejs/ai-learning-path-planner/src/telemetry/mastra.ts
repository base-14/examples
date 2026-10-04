import { Mastra } from "@mastra/core";
import { Observability } from "@mastra/observability";
import { OtelBridge } from "@mastra/otel-bridge";

let instance: Mastra | undefined;

// One instance for the process. The bridge hands Mastra's spans to the OpenTelemetry SDK that
// telemetry.ts started, so they join the request's trace and pass through its span processors.
// Agents are built per request and point at this instance; none is registered on it.
export function mastraInstance(): Mastra {
  // Mastra reports anonymous usage analytics to its maintainers unless this is set. Off by
  // default here; set MASTRA_TELEMETRY_DISABLED=0 to send them.
  process.env.MASTRA_TELEMETRY_DISABLED ??= "1";
  instance ??= new Mastra({
    observability: new Observability({
      configs: {
        default: { serviceName: "ai-learning-path-planner", bridge: new OtelBridge() },
      },
    }),
  });
  return instance;
}
