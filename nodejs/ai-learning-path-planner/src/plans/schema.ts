import { z } from "zod";

// kind distinguishes a step that points at documentation prose from a step that points
// at a runnable example, so a consumer can render the two differently. It is not read by
// validateCitation - only path decides whether a step's citation is real.
export const PlanStepSchema = z.object({
  title: z.string(),
  path: z.string(),
  kind: z.enum(["doc", "example"]),
  why: z.string(),
});

export const PlanGapSchema = z.object({
  term: z.string(),
  reason: z.string(),
});

// subtopic is constrained rather than left open because a live run produced a week of
// {"subtopic":"","steps":[]}, which is not a week. The nested arrays are deliberately left
// unconstrained: this schema is sent to the provider as a generation grammar, and a
// minimum length on weeks or steps that the findings cannot satisfy fails the whole call,
// which is a worse outcome than an empty array runLeadPlan can check for afterwards.
export const PlanWeekSchema = z.object({
  subtopic: z.string().min(1),
  steps: z.array(PlanStepSchema),
});

export const PlanSchema = z.object({
  topic: z.string(),
  weeks: z.array(PlanWeekSchema),
  gaps: z.array(PlanGapSchema),
});

export type PlanStep = z.infer<typeof PlanStepSchema>;
export type PlanWeek = z.infer<typeof PlanWeekSchema>;
export type PlanGap = z.infer<typeof PlanGapSchema>;
export type Plan = z.infer<typeof PlanSchema>;

// The gap reasons the service writes itself, as opposed to the ones the lead model writes.
// telemetry/metrics.ts turns a run's gaps into the reason tag on base14.plan.gap.count by
// matching these, so the text is declared once and read from both ends. It used to be a
// sentence in agents/lead.ts matched by a fragment of itself in telemetry/metrics.ts:
// rewording either one left the whole suite green and silently retagged the metric as
// model_reported, which is a metric quietly changing meaning rather than a test failing.
export const SERVICE_GAP_REASONS = {
  no_tool_call: "The lead agent answered without calling a tool, so nothing was researched.",
  no_research: "The lead agent finished without researching any subtopic.",
  topic_out_of_range: "The corpus has no coverage of this topic at all.",
  max_escalations: "Research confidence was low and MAX_ESCALATIONS was already reached.",
  low_confidence: "Research confidence stayed low even after escalating to the large tier.",
  service_error: "The run failed before the lead agent returned, so nothing was researched.",
} as const;

export type ServiceGapReason = keyof typeof SERVICE_GAP_REASONS;

// Two of the service's own reasons name a cap or a citation path, so they cannot be
// compared whole the way the fixed ones above are. Each is declared here as a writer and
// the fixed part of what it writes, and the writer builds its sentence out of that same
// fixed part, so there is still exactly one string and rewording it moves both the text
// and the match together.
const MAX_SUBTOPICS_TEXT = "was already reached; this subtopic was not researched.";
const CITATION_INVALID_TEXT = "did not validate, even after one retry.";

export const TEMPLATED_GAP_REASONS = {
  max_subtopics: {
    match: MAX_SUBTOPICS_TEXT,
    write: (cap: number): string => `MAX_SUBTOPICS (${cap}) ${MAX_SUBTOPICS_TEXT}`,
  },
  citation_invalid: {
    match: CITATION_INVALID_TEXT,
    write: (path: string, title: string): string =>
      `The citation "${path}" for step "${title}" ${CITATION_INVALID_TEXT}`,
  },
} as const;

export type TemplatedGapReason = keyof typeof TEMPLATED_GAP_REASONS;

// Every tag base14.plan.gap.count can carry. The service's own reasons plus
// model_reported, which is what a gap the lead model wrote itself is tagged.
// tests/telemetry/enrich.test.ts asserts one run per entry.
export const GAP_REASON_TAGS = [
  ...(Object.keys(SERVICE_GAP_REASONS) as ServiceGapReason[]),
  ...(Object.keys(TEMPLATED_GAP_REASONS) as TemplatedGapReason[]),
  "model_reported",
] as const;
