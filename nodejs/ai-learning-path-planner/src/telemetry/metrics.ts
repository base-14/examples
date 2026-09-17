import { type Counter, type Histogram, type Meter, metrics } from "@opentelemetry/api";
import type { ToolSet } from "ai";
import { z } from "zod";
import type { Config } from "../config.ts";
import { type PlanGap, SERVICE_GAP_REASONS, TEMPLATED_GAP_REASONS } from "../plans/schema.js";
import { activeToolsFor } from "../tools/catalogue.js";

const METER_NAME = "ai-learning-path-planner";

interface Instruments {
  planCost: Histogram;
  planFanout: Histogram;
  planDuration: Histogram;
  planGapCount: Counter;
  planEscalationCount: Counter;
  toolDefinitionTokens: Histogram;
}

// The SDK's defaults start at 0 and jump to 5, which puts every cost and duration this
// service produces in one bucket. These are anchored on a planned run instead: a couple of
// minutes and a few tenths of a cent, against a decline at about 0.02 seconds and nothing.
//
// Cost climbs in half decades to a dollar, so a plan sits mid-scale and a ten-times regression
// moves three buckets. Duration is fine below a second, so a decline is never in a plan's
// bucket, then thirty seconds wide across the planned band, with a tail to five minutes.
// Fan-out is small integers, capped by MAX_SUBTOPICS.
export const COST_BOUNDARIES_USD = [0.0001, 0.0003, 0.001, 0.003, 0.01, 0.03, 0.1, 0.3, 1];
export const DURATION_BOUNDARIES_SECONDS = [0.1, 1, 10, 30, 60, 90, 120, 150, 180, 240, 300];
export const FANOUT_BOUNDARIES = [0, 1, 2, 3, 4, 5, 6, 8];

function build(meter: Meter): Instruments {
  return {
    planCost: meter.createHistogram("base14.plan.cost", {
      unit: "USD",
      description: "Cost of one plan run, summed over the lead and every researcher.",
      advice: { explicitBucketBoundaries: COST_BOUNDARIES_USD },
    }),
    planFanout: meter.createHistogram("base14.plan.fanout", {
      unit: "{subtopic}",
      description: "Subtopics researched per plan.",
      advice: { explicitBucketBoundaries: FANOUT_BOUNDARIES },
    }),
    planDuration: meter.createHistogram("base14.plan.duration", {
      unit: "s",
      description: "Wall clock time from accepting a request to completing its plan.",
      advice: { explicitBucketBoundaries: DURATION_BOUNDARIES_SECONDS },
    }),
    planGapCount: meter.createCounter("base14.plan.gap.count", {
      unit: "{gap}",
      description: "Gaps recorded in a plan, by the reason the gap was recorded.",
    }),
    planEscalationCount: meter.createCounter("base14.plan.escalation.count", {
      unit: "{escalation}",
      description: "Escalations from the small tier to the large tier, by trigger.",
    }),
    // Left on the SDK defaults: each role and catalogue is its own series carrying one value,
    // and deferred and full fall either side of the default 500 boundary.
    toolDefinitionTokens: meter.createHistogram("base14.gen_ai.tool_definition.tokens", {
      unit: "{token}",
      description: "Estimated tokens the active tool definitions add to each model call.",
    }),
  };
}

// Resolved lazily and rebuilt whenever the meter changes identity. Building them at module
// load would pin them to whichever provider existed at import time, which is the no-op one.
let cached: { meter: Meter; instruments: Instruments } | undefined;

function instruments(): Instruments {
  const meter = metrics.getMeter(METER_NAME);
  if (cached === undefined || cached.meter !== meter) {
    cached = { meter, instruments: build(meter) };
  }
  return cached.instruments;
}

// One counter, two readers: research_subtopic enforces the caps against these numbers and
// recordPlan reports them, so a run reports the fan-out its caps were applied to.
export interface RunCounters {
  subtopics: number;
  escalations: number;
}

export function newRunCounters(): RunCounters {
  return { subtopics: 0, escalations: 0 };
}

// Gap reasons are free text and two of them interpolate a cap or a path, so they cannot be tag
// values as they stand. SERVICE_GAP_REASONS and TEMPLATED_GAP_REASONS keep the writer and the
// match side by side, so a reword is one edit. A gap matching neither came from the model.
function gapReason(gap: PlanGap): string {
  const reason = gap.reason;
  for (const [tag, text] of Object.entries(SERVICE_GAP_REASONS)) {
    if (reason === text) return tag;
  }
  for (const [tag, templated] of Object.entries(TEMPLATED_GAP_REASONS)) {
    if (reason.includes(templated.match)) return tag;
  }
  return "model_reported";
}

function fanoutBucket(fanout: number): string {
  if (fanout === 0) return "0";
  if (fanout <= 3) return "1-3";
  if (fanout <= 8) return "4-8";
  return "9+";
}

// No tokeniser exists for a local Ollama model, so this is a character estimate of the JSON
// the provider receives, at four characters per token. The divisor is a stated convention, not
// a measurement: quote it whenever you quote the number.
const CHARS_PER_TOKEN = 4;

// z.toJSONSchema emits a $schema URL of about fifty characters that the provider never
// receives, so it is dropped before the estimate is taken.
function parametersOf(inputSchema: unknown): unknown {
  if (!(inputSchema instanceof z.ZodType)) {
    return undefined;
  }
  const schema = z.toJSONSchema(inputSchema) as Record<string, unknown>;
  delete schema.$schema;
  return schema;
}

function definitionOf(name: string, definition: unknown): unknown {
  if (typeof definition !== "object" || definition === null) {
    return { name };
  }
  const { description, inputSchema } = definition as {
    description?: unknown;
    inputSchema?: unknown;
  };
  return {
    name,
    description: typeof description === "string" ? description : undefined,
    parameters: parametersOf(inputSchema),
  };
}

export function toolDefinitionTokens(
  tools: ToolSet,
  role: "lead" | "researcher",
  config: Config,
): number {
  const definitions = activeToolsFor(role, config).map((name) => definitionOf(name, tools[name]));
  return Math.ceil(JSON.stringify(definitions).length / CHARS_PER_TOKEN);
}

export type PlanOutcome = "declined" | "planned" | "failed";

export interface PlanRunResult {
  status: PlanOutcome;
  durationSeconds: number;
  costUsd: number;
  counters: RunCounters;
  gaps: PlanGap[];
  catalogue: "deferred" | "full";
  toolDefinitionTokens: { lead: number; researcher: number };
}

// Once per run, on all three outcomes. A decline is an outcome, not an absence of one, and a
// histogram that only sees successes hides both the cheap half of the traffic and an outage.
export function recordPlan(result: PlanRunResult): void {
  const { planCost, planFanout, planDuration, planGapCount, planEscalationCount } = instruments();
  const fanout = result.counters.subtopics;

  // outcome as well as catalogue and fanout_bucket, or a declined run's zero and a failed
  // run's partial cost share a series with a finished plan's.
  planCost.record(result.costUsd, {
    catalogue: result.catalogue,
    fanout_bucket: fanoutBucket(fanout),
    outcome: result.status,
  });
  planFanout.record(fanout, { outcome: result.status });
  planDuration.record(result.durationSeconds, { outcome: result.status });

  for (const gap of result.gaps) {
    planGapCount.add(1, { reason: gapReason(gap) });
  }

  // One trigger today: confidence below the threshold after the small tier. Recorded at zero
  // too, so a run that escalated nothing is a run rather than a missing point.
  planEscalationCount.add(result.counters.escalations, { trigger: "low_confidence" });

  recordToolDefinitionTokens(result);
}

function recordToolDefinitionTokens(result: PlanRunResult): void {
  const { toolDefinitionTokens: tokens } = instruments();
  tokens.record(result.toolDefinitionTokens.lead, {
    role: "lead",
    catalogue: result.catalogue,
  });
  tokens.record(result.toolDefinitionTokens.researcher, {
    role: "researcher",
    catalogue: result.catalogue,
  });
}
