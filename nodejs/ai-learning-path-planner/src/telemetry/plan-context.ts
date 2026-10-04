import { type Context, context, createContextKey } from "@opentelemetry/api";
import type { ReadableSpan, Span, SpanProcessor } from "@opentelemetry/sdk-trace-base";
import { MASTRA_SCOPE, type PlanRuntimeContext, planAttributes } from "./enrich.js";

const PLAN_CONTEXT_KEY = createContextKey("base14.plan.runtime-context");

// No Mastra import here: telemetry.ts registers the processor in every mode, and Mastra itself
// is loaded only when PLANNER_FRAMEWORK=mastra.
// Mastra has no hook that runs at span creation, so the plan id and role travel in the
// OpenTelemetry context and MastraPlanSpanProcessor reads them back.
export function withPlanContext<T>(
  runtimeContext: PlanRuntimeContext | undefined,
  run: () => Promise<T>,
): Promise<T> {
  if (runtimeContext === undefined) {
    return run();
  }
  return context.with(context.active().setValue(PLAN_CONTEXT_KEY, runtimeContext), run);
}

// What Mastra puts on a span whether or not content capture is on.
const CONTENT_ATTRIBUTES = [
  "gen_ai.input.messages",
  "gen_ai.output.messages",
  "gen_ai.system_instructions",
  "gen_ai.tool.call.arguments",
  "gen_ai.tool.call.result",
];
const CONTENT_ATTRIBUTE_PATTERN = /^mastra\.[a-z_]+\.(input|output)$/;

// The Mastra counterpart of enrichSpan. Registered ahead of the cost processor, which reads
// base14.plan.id from the span.
export class MastraPlanSpanProcessor implements SpanProcessor {
  constructor(private readonly captureMessageContent: boolean) {}

  onStart(span: Span, parentContext: Context): void {
    if (span.instrumentationScope.name !== MASTRA_SCOPE) {
      return;
    }
    const attributes = planAttributes(
      parentContext.getValue(PLAN_CONTEXT_KEY) as PlanRuntimeContext | undefined,
    );
    if (attributes !== undefined) {
      span.setAttributes(attributes);
    }
  }

  onEnd(span: ReadableSpan): void {
    if (this.captureMessageContent || span.instrumentationScope.name !== MASTRA_SCOPE) {
      return;
    }
    for (const key of Object.keys(span.attributes)) {
      if (CONTENT_ATTRIBUTES.includes(key) || CONTENT_ATTRIBUTE_PATTERN.test(key)) {
        delete span.attributes[key];
      }
    }
  }

  forceFlush(): Promise<void> {
    return Promise.resolve();
  }

  shutdown(): Promise<void> {
    return Promise.resolve();
  }
}
