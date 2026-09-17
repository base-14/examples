import { tool } from "ai";
import { z } from "zod";
import type { Config } from "../config.ts";
import { validateCitation } from "../corpus/citations.js";
import type { CorpusStore } from "../corpus/store.ts";
import { SERVICE_GAP_REASONS, TEMPLATED_GAP_REASONS } from "../plans/schema.js";
import { newRunCounters, type RunCounters } from "../telemetry/metrics.js";

export interface Finding {
  path: string;
  heading?: string;
  note: string;
}

export interface ResearchSubtopicResult {
  subtopic: string;
  findings: Finding[];
  confidence: number;
  escalated: boolean;
  gap?: { term: string; reason: string };
}

// The minimal shape this tool needs from a researcher agent, declared locally so this file
// never imports agents/researcher.ts. buildResearcher is injected by the caller, which keeps
// the dependency edge pointing one way.
export interface ResearcherHandle {
  generate(options: { prompt: string }): Promise<{ output: { findings: Finding[] } }>;
}

export interface ResearchSubtopicDeps {
  store: CorpusStore;
  config: Config;
  buildResearcher: (opts: { subtopic: string; tier: "small" | "large" }) => ResearcherHandle;
  counters?: RunCounters;
}

// Escalates to the large tier when fewer than half the findings carry a citation the store can
// validate; no findings at all scores 0 and needs no separate check. Confidence comes from
// validation outcomes, not from a number the model reports about itself.
const CONFIDENCE_THRESHOLD = 0.5;

function confidenceOf(total: number, valid: number): number {
  if (total === 0) return 0;
  return valid / total;
}

async function research(
  subtopic: string,
  tier: "small" | "large",
  deps: ResearchSubtopicDeps,
): Promise<{ findings: Finding[]; confidence: number }> {
  const researcher = deps.buildResearcher({ subtopic, tier });
  const result = await researcher.generate({ prompt: `Subtopic: ${subtopic}` });
  const raw = result.output.findings;
  const validFindings = raw.filter((finding) =>
    validateCitation(deps.store, finding.path, finding.heading),
  );
  return { findings: validFindings, confidence: confidenceOf(raw.length, validFindings.length) };
}

// Shared with the placeholder in agents/researcher.ts, so a researcher's tool definition
// matches the lead's under TOOL_CATALOGUE=full.
export const RESEARCH_SUBTOPIC_DESCRIPTION =
  "Researches one subtopic against the corpus and returns cited findings with a " +
  "confidence value. Escalates once to a larger model when confidence is low.";

export const RESEARCH_SUBTOPIC_INPUT_SCHEMA = z.object({ subtopic: z.string() });

// Once per lead agent, so the counters are shared across every call in a run and the caps
// apply to the run rather than to one subtopic.
export function researchSubtopicTool(deps: ResearchSubtopicDeps) {
  // The caller passes counters in so the caps and recordPlan use the same numbers. Without
  // them the tool keeps its own, which is what the unit tests use.
  const counters = deps.counters ?? newRunCounters();

  return tool({
    description: RESEARCH_SUBTOPIC_DESCRIPTION,
    inputSchema: RESEARCH_SUBTOPIC_INPUT_SCHEMA,
    execute: async ({ subtopic }): Promise<ResearchSubtopicResult> => {
      // After the gate, not before: base14.plan.fanout is subtopics researched, and a call the
      // cap turns away researches nothing. The refusal still returns its gap, which is the
      // other fact: one says how many were asked for, the other how many happened.
      if (counters.subtopics >= deps.config.maxSubtopics) {
        return {
          subtopic,
          findings: [],
          confidence: 0,
          escalated: false,
          gap: {
            term: subtopic,
            reason: TEMPLATED_GAP_REASONS.max_subtopics.write(deps.config.maxSubtopics),
          },
        };
      }
      counters.subtopics += 1;

      const first = await research(subtopic, "small", deps);
      if (first.confidence >= CONFIDENCE_THRESHOLD) {
        return {
          subtopic,
          findings: first.findings,
          confidence: first.confidence,
          escalated: false,
        };
      }

      if (counters.escalations >= deps.config.maxEscalations) {
        return {
          subtopic,
          findings: first.findings,
          confidence: first.confidence,
          escalated: false,
          gap: {
            term: subtopic,
            reason: SERVICE_GAP_REASONS.max_escalations,
          },
        };
      }

      counters.escalations += 1;
      const second = await research(subtopic, "large", deps);
      if (second.confidence >= CONFIDENCE_THRESHOLD) {
        return {
          subtopic,
          findings: second.findings,
          confidence: second.confidence,
          escalated: true,
        };
      }

      return {
        subtopic,
        findings: second.findings,
        confidence: second.confidence,
        escalated: true,
        gap: {
          term: subtopic,
          reason: SERVICE_GAP_REASONS.low_confidence,
        },
      };
    },
  });
}
