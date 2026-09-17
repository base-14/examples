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

// The SDK's default boundaries start at 0 and jump to 5, which puts every measurement
// this service produces into one bucket for cost and duration and makes a percentile on
// either meaningless.
//
// Anchored on six consecutive live runs of one in-range topic, through the containerised
// service on its shipped defaults: 72.7, 82.7, 89.9, 105.6, 131.7 and 152.3 seconds, at
// 0.0016 to 0.0031 USD each, fanning out to two or three subtopics. A declined run takes
// about 0.02 seconds and costs nothing, and a run that fails takes whatever it reached.
// The numbers in SPIKE-FINDINGS.md section 5, 21.75 to 25.60 seconds, were measured before
// the fan-out worked and are not what this service does.
//
// Cost climbs in half decades from a tenth of a measured run to a dollar, so a measured run
// sits mid-scale and a ten-times regression moves three buckets. Duration is fine below a
// second, so a decline is never in the same bucket as a plan, then thirty seconds wide
// across the whole measured band, so a p95 over planned runs says something, with a tail
// to five minutes. Fan-out is small integers and never exceeds MAX_SUBTOPICS, whose
// default is 8, because tools/research-subtopic.ts counts a subtopic only once the cap has
// let it through.
// tests/telemetry/metrics.test.ts holds the boundaries to those measurements.
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
    // Left on the SDK defaults on purpose. Each role and catalogue combination is its own
    // series carrying one value, and the measured values, 290 for the deferred lead and
    // 361 for the deferred researcher against 650 for either role on the full catalogue,
    // fall either side of the default 500 boundary, so switching catalogue mode is visible
    // without a custom scale.
    toolDefinitionTokens: meter.createHistogram("base14.gen_ai.tool_definition.tokens", {
      unit: "{token}",
      description: "Estimated tokens the active tool definitions add to each model call.",
    }),
  };
}

// The instruments are resolved lazily and rebuilt whenever the meter changes identity,
// which happens exactly once in the service (the global meter provider is a no-op until
// the SDK starts) and once per test that registers its own provider. Building them at
// module load would pin them to whichever provider was in place at import time.
let cached: { meter: Meter; instruments: Instruments } | undefined;

function instruments(): Instruments {
  const meter = metrics.getMeter(METER_NAME);
  if (cached === undefined || cached.meter !== meter) {
    cached = { meter, instruments: build(meter) };
  }
  return cached.instruments;
}

// Shared by research_subtopic, which enforces MAX_SUBTOPICS and MAX_ESCALATIONS against
// these same numbers, and by recordPlan, which reports them. One counter, two readers,
// so the fan-out a run reports is the fan-out its caps were applied to.
export interface RunCounters {
  subtopics: number;
  escalations: number;
}

export function newRunCounters(): RunCounters {
  return { subtopics: 0, escalations: 0 };
}

// Gap reasons are free text, and two of them carry a cap or a citation path, so they
// cannot be a tag value as they stand. Nothing is matched against a literal written in
// another file: the fixed reasons come from SERVICE_GAP_REASONS and are compared whole,
// and the two templated ones come from TEMPLATED_GAP_REASONS, which holds the writer and
// the fixed part of what it writes side by side. Rewording any of them changes the text
// and the match in one edit. A gap that matches none of them is one the lead model wrote
// itself.
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

// No tokeniser is available for a local Ollama model, so this is a character estimate of
// the JSON the provider receives for the active tools, at four characters per token. That
// divisor is a stated convention, not a measurement: Task 1's measured 4.8 characters per
// token came from prose, and JSON schema tokenizes differently enough that borrowing the
// prose ratio would not obviously be closer. Anything quoting these numbers should quote
// the divisor with them.
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

// Called once per run, from the route handler, on all three paths: planned, declined and
// failed. A declined run never builds a researcher, so it reports a fan-out of zero and no
// escalations, but it still reports on every instrument: a decline is an outcome of the
// service, not an absence of one, and a histogram that only ever sees successful runs
// hides the cheap half of the traffic. A failed run reports the fan-out it reached and the
// time it took to fail, which is what makes an outage visible in metrics at all.
export function recordPlan(result: PlanRunResult): void {
  const { planCost, planFanout, planDuration, planGapCount, planEscalationCount } = instruments();
  const fanout = result.counters.subtopics;

  // outcome as well as catalogue and fanout_bucket, because recordPlan runs on all three
  // outcomes: without it a declined run's zero and a failed run's partial cost sit in the
  // same series as a finished plan's and there is no way to filter them apart. Fan-out and
  // duration have always carried it.
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

  // Confidence below the threshold after the small tier is the only thing that escalates
  // (see tools/research-subtopic.ts), so the trigger is constant today. Recorded even
  // when the count is zero, so a run that escalated nothing is visible as a run rather
  // than as a missing point.
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
