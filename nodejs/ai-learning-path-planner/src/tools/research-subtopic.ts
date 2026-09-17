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

// The minimal shape this tool needs from a researcher agent. Kept local rather than
// importing ToolLoopAgent's own return type, so this file never has to import
// agents/researcher.ts - buildResearcher is injected by the caller (agents/lead.ts and
// agents/researcher.ts's own full-catalogue tool set), which is what actually knows how to
// build one. That keeps the one real dependency edge (researcher depends on the corpus
// tools, research_subtopic depends on a researcher) pointing one way only.
export interface ResearcherHandle {
  generate(options: { prompt: string }): Promise<{ output: { findings: Finding[] } }>;
}

export interface ResearchSubtopicDeps {
  store: CorpusStore;
  config: Config;
  buildResearcher: (opts: { subtopic: string; tier: "small" | "large" }) => ResearcherHandle;
  counters?: RunCounters;
}

// A researcher's findings escalate to the large tier when fewer than half of them carry a
// citation the store can validate, or when it returned no findings at all (confidenceOf(0,
// 0) is 0, below the threshold, so "zero cited findings" needs no separate check).
// Confidence is computed from validation outcomes rather than read as a number the model
// reports on itself: a small local model's self-declared confidence is not grounded in
// anything the store can check, while the fraction of findings that actually cite a real
// corpus path is exactly what validateCitation already tells us for free.
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

// Shared by researchSubtopicTool below and by agents/researcher.ts's
// researchSubtopicPlaceholder, which needs the same name, description and input schema so
// a researcher's tool definition matches the lead's under TOOL_CATALOGUE=full, without
// this file ever importing agents/researcher.ts.
export const RESEARCH_SUBTOPIC_DESCRIPTION =
  "Researches one subtopic against the corpus and returns cited findings with a " +
  "confidence value. Escalates once to a larger model when confidence is low.";

export const RESEARCH_SUBTOPIC_INPUT_SCHEMA = z.object({ subtopic: z.string() });

// Built once per lead agent instance (see agents/lead.ts), so the subtopic and escalation
// counters are shared across every research_subtopic call the lead makes during one run,
// not reset per call. That is what lets them enforce MAX_SUBTOPICS and
// MAX_ESCALATIONS as caps on the whole run rather than per subtopic.
export function researchSubtopicTool(deps: ResearchSubtopicDeps) {
  // The caller passes counters in when the run is being measured, so the numbers the caps
  // are enforced against are the same numbers recordPlan reports. Without them the tool
  // keeps its own, which is what the unit tests use.
  const counters = deps.counters ?? newRunCounters();

  return tool({
    description: RESEARCH_SUBTOPIC_DESCRIPTION,
    inputSchema: RESEARCH_SUBTOPIC_INPUT_SCHEMA,
    execute: async ({ subtopic }): Promise<ResearchSubtopicResult> => {
      // Counted after the gate, not before it. counters.subtopics is what recordPlan
      // publishes as base14.plan.fanout, whose description is "subtopics researched per
      // plan", and a call the cap turns away researches nothing. Counting it first
      // reported a fan-out of seven for a run that built three researchers, and pushed
      // base14.plan.cost into a fanout_bucket the run never reached. The refusal still
      // returns its gap: the gap says a subtopic was asked for and not researched, and
      // the counter says how many were, which are two different facts.
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
