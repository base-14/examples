import type { LanguageModel } from "ai";
import {
  type ActiveTools,
  isStepCount,
  Output,
  type TelemetryOptions,
  ToolChoiceViolationError,
  ToolLoopAgent,
} from "ai";
import type { Config } from "../config.ts";
import { validateCitation } from "../corpus/citations.js";
import type { CorpusStore } from "../corpus/store.ts";
import { providerOptionsFor, selectModel } from "../llm/models.js";
import {
  type Plan,
  type PlanGap,
  PlanSchema,
  type PlanStep,
  type PlanWeek,
  SERVICE_GAP_REASONS,
  TEMPLATED_GAP_REASONS,
} from "../plans/schema.js";
import { PLAN_RUNTIME_CONTEXT_KEYS, type PlanRuntimeContext } from "../telemetry/enrich.js";
import type { RunCounters } from "../telemetry/metrics.ts";
import { activeToolsFor } from "../tools/catalogue.js";
import { checkCoverageTool } from "../tools/check-coverage.js";
import { corpusMapTool } from "../tools/corpus-map.js";
import { fetchExampleFileTool } from "../tools/fetch-example-file.js";
import { fetchSectionTool } from "../tools/fetch-section.js";
import { getRelatedTool } from "../tools/get-related.js";
import { listExamplesTool } from "../tools/list-examples.js";
import { outlineTool } from "../tools/outline.js";
import { researchSubtopicTool } from "../tools/research-subtopic.js";
import { searchDocsTool } from "../tools/search-docs.js";
import { buildResearcherAgent } from "./researcher.js";

// Set by the route handler, which owns the plan id and the counters. Left undefined by
// the unit tests, which build a lead agent with no run to attribute spans or metrics to.
export interface LeadRun {
  planId: string;
  counters: RunCounters;
}

export interface LeadAgentDeps {
  store: CorpusStore;
  config: Config;
  telemetry?: TelemetryOptions;
  model?: LanguageModel;
  researcherModels?: { small?: LanguageModel; large?: LanguageModel };
  run?: LeadRun;
}

// The loop gathers, the shaping call writes. Splitting the instructions the same way the
// calls are split is what keeps the loop from trying to emit a plan on a step that has
// tools in front of it.
const LEAD_INSTRUCTIONS =
  "You research a topic against base14's documentation and examples corpus so a learning " +
  "plan can be written from what you find. Break the topic into a small number of focused " +
  "subtopics and call research_subtopic once per subtopic to gather cited findings. Use " +
  "corpus_map to see what areas the corpus covers, check_coverage to check a subtopic " +
  "before researching it, and get_related to broaden a path you already have. When every " +
  "subtopic has been researched, stop calling tools and write a short plain-text summary: " +
  "one line per subtopic, naming the corpus paths the research returned for it and any " +
  "subtopic that returned nothing. Do not write the plan itself.";

// Added to the loop's instructions on any early step that has not researched anything yet,
// and withdrawn once one has. See prepareStep below for why prose alone was not enough and
// why this is not simply part of LEAD_INSTRUCTIONS: a directive that is true on step one
// and false on step six does not belong in a system prompt that is sent on every step.
const LEAD_NUDGE =
  "You have not researched any subtopic yet, so this step must be a tool call rather than " +
  "a written answer. Call corpus_map or check_coverage if you still have to decide which " +
  "subtopics to research, and call research_subtopic as soon as you have one.";

const PLAN_INSTRUCTIONS =
  "You turn researched findings into a multi-week learning plan for one topic, as " +
  "structured output. Give each week one subtopic and order the weeks so earlier weeks " +
  "come first. Every step cites a corpus path that appears in the findings you were given " +
  "and nothing else. Record a subtopic that has no findings as a gap rather than guessing " +
  "a citation.";

// The loop is nudged for this many steps, which is long enough for the lead to survey the
// corpus and check a subtopic's coverage before it has to start researching, and short
// enough that it still ends the loop itself once the research is done.
const NUDGED_STEPS = 6;

function hasResearched(steps: { toolCalls: { toolName: string }[] }[]): boolean {
  return steps.some((step) => step.toolCalls.some((call) => call.toolName === "research_subtopic"));
}

// Build a new lead agent for every request. The MAX_SUBTOPICS and MAX_ESCALATIONS
// counters live in the research_subtopic tool's closure, which is created here, so they
// reset when this function is called and at no other time. A lead agent reused across
// requests carries its exhausted caps into the next one and refuses to research anything.
export function buildLeadAgent(deps: LeadAgentDeps) {
  const runtimeContext: PlanRuntimeContext | undefined =
    deps.run === undefined
      ? undefined
      : {
          planId: deps.run.planId,
          agentRole: "lead",
          toolCatalogue: deps.config.toolCatalogue,
        };

  const tools = {
    corpus_map: corpusMapTool(deps.store),
    check_coverage: checkCoverageTool(deps.store),
    get_related: getRelatedTool(deps.store),
    research_subtopic: researchSubtopicTool({
      store: deps.store,
      config: deps.config,
      counters: deps.run?.counters,
      buildResearcher: (opts) =>
        buildResearcherAgent({
          store: deps.store,
          config: deps.config,
          telemetry: deps.telemetry,
          planId: deps.run?.planId,
          subtopic: opts.subtopic,
          tier: opts.tier,
          model:
            opts.tier === "small" ? deps.researcherModels?.small : deps.researcherModels?.large,
        }),
    }),
    search_docs: searchDocsTool(deps.store),
    outline: outlineTool(deps.store),
    fetch_section: fetchSectionTool(deps.store),
    list_examples: listExamplesTool(deps.store),
    fetch_example_file: fetchExampleFileTool(deps.store),
  };

  const model = deps.model ?? selectModel("large", deps.config);
  const providerOptions = providerOptionsFor(deps.config);
  const telemetry = {
    includeRuntimeContext: PLAN_RUNTIME_CONTEXT_KEYS,
    recordInputs: deps.config.captureMessageContent,
    recordOutputs: deps.config.captureMessageContent,
  };

  // Two agents, not one, and the reason is the wire format rather than the design.
  // Output.object puts a json responseFormat on every call the agent makes, which
  // ollama-ai-provider-v2 turns into a `format` grammar on the request. `format` alongside
  // tool definitions stops qwen3.5 calling a tool at all: measured three runs each,
  // format plus think:false gave 0/3 tool calls, either one alone gave 3/3. The loop
  // therefore runs with tools and no response format, and one structured call after it
  // shapes the plan. prepareStep cannot do this - its return type covers toolChoice,
  // activeTools, tools and model, but not responseFormat.
  const loop = new ToolLoopAgent({
    id: "lead",
    model,
    instructions: LEAD_INSTRUCTIONS,
    tools,
    activeTools: activeToolsFor("lead", deps.config) as ActiveTools<typeof tools>,
    stopWhen: isStepCount(16),
    // Taking Output.object off the loop fixed the tool calls but left nothing except the
    // instructions telling the lead to research anything, and prose did not hold it: four
    // live runs fanned out 3, 3, 0 and 0 times, the zero runs calling corpus_map, then
    // check_coverage, then answering in prose. This requires a tool call while nothing has
    // been researched. It does not name the tool, because choosing between surveying the
    // corpus and researching a subtopic is the decision this example exists to show.
    //
    // toolChoice is the provider-agnostic half and is inert on Ollama: 0.32.15 accepts
    // tool_choice on /api/chat and ignores it, measured against "required", a named
    // function and the OpenAI-compatible endpoint. The instructions override is what
    // actually moves this model, so both are sent.
    prepareStep: ({ stepNumber, steps }) => {
      // The instructions are put back explicitly rather than left to fall through.
      // generate-text.ts carries a prepareStep instructions override forward into every
      // later step (instructionsForNextStep, generate-text.ts:1466), so returning nothing
      // here would leave "you have not researched anything yet" in front of the model for
      // the rest of the run, including the steps after it plainly had.
      if (stepNumber >= NUDGED_STEPS || hasResearched(steps)) {
        return { instructions: LEAD_INSTRUCTIONS };
      }
      return {
        toolChoice: "required",
        instructions: `${LEAD_INSTRUCTIONS}\n\n${LEAD_NUDGE}`,
      };
    },
    providerOptions,
    runtimeContext,
    telemetry: { functionId: "lead", ...telemetry, ...deps.telemetry },
  });

  // Carries the same runtimeContext as the loop, so its spans land on the run:
  // base14.plan.id is on them and PlanCostSpanProcessor adds this call's tokens to the
  // run's total, which keeps base14.gen_ai.cost a sum over the whole run.
  const shaper = new ToolLoopAgent({
    id: "lead-plan",
    model,
    instructions: PLAN_INSTRUCTIONS,
    tools: {},
    stopWhen: isStepCount(1),
    output: Output.object({ schema: PlanSchema }),
    providerOptions,
    runtimeContext,
    telemetry: { functionId: "lead-plan", ...telemetry, ...deps.telemetry },
  });

  return { tools, loop, shaper };
}

export type LeadAgent = ReturnType<typeof buildLeadAgent>;

export interface LeadRequest {
  topic: string;
}

export interface LeadOutcome {
  status: "declined" | "planned" | "failed";
  plan: Plan;
}

// Everything the shaping call is allowed to write a plan from: the loop's own summary
// plus the findings each researcher returned, verbatim. The findings are passed as JSON
// rather than folded into prose because they are the only source of a citation the plan
// may use, and validateCitation checks every path in the result against the store
// afterwards regardless.
function researchNotes(loop: {
  text: string;
  toolResults: { toolName: string; output: unknown }[];
}): string {
  // The outputs only, never the tool-result envelope around them. A live run handed the
  // whole envelope cited "call_obzm3sh9:tool-result:call_obzm3sh9:research_subtopic:output"
  // as a corpus path: the model read toolCallId as if it were data.
  const researched = loop.toolResults
    .filter((result) => result.toolName === "research_subtopic")
    .map((result) => result.output);
  const summary = loop.text.trim();

  return (
    `The research agent's summary:\n${summary.length > 0 ? summary : "(none)"}\n\n` +
    `The findings each subtopic researcher returned:\n${JSON.stringify(researched)}`
  );
}

function shapePrompt(topic: string, research: string): string {
  return (
    `Topic: ${topic}.\n\n${research}\n\n` +
    "Write the learning plan for this topic from the research above."
  );
}

interface InvalidStepRef {
  weekIndex: number;
  stepIndex: number;
  step: PlanStep;
}

function findInvalidSteps(plan: Plan, store: CorpusStore): InvalidStepRef[] {
  const invalid: InvalidStepRef[] = [];
  plan.weeks.forEach((week, weekIndex) => {
    week.steps.forEach((step, stepIndex) => {
      if (!validateCitation(store, step.path)) {
        invalid.push({ weekIndex, stepIndex, step });
      }
    });
  });
  return invalid;
}

function retryPrompt(topic: string, research: string, invalid: InvalidStepRef[]): string {
  const cited = invalid
    .map((ref) => `"${ref.step.title}" cited "${ref.step.path}", which is not a corpus path`)
    .join("; ");
  return (
    `${shapePrompt(topic, research)}\n\n` +
    "Earlier you produced a plan where these steps cited a path the corpus does not " +
    `have: ${cited}. Return the full plan again, correcting only those steps' citations ` +
    "to a corpus path that appears in the research above."
  );
}

// Runs after the model returns, never inside the prompt: the model's structured output is
// only ever accepted step by step through validateCitation, the same function the corpus
// module exposes for this and nothing else parses a citation path.
function reconcile(
  first: Plan,
  retry: Plan | undefined,
  invalid: InvalidStepRef[],
  store: CorpusStore,
): Plan {
  const gaps: PlanGap[] = [...first.gaps];

  const weeks: PlanWeek[] = first.weeks.map((week, weekIndex) => {
    const steps: PlanStep[] = [];

    week.steps.forEach((step, stepIndex) => {
      const wasInvalid = invalid.some(
        (ref) => ref.weekIndex === weekIndex && ref.stepIndex === stepIndex,
      );
      if (!wasInvalid) {
        steps.push(step);
        return;
      }

      const replacement = retry?.weeks[weekIndex]?.steps[stepIndex];
      if (replacement !== undefined && validateCitation(store, replacement.path)) {
        steps.push(replacement);
        return;
      }

      gaps.push({
        term: step.title,
        reason: TEMPLATED_GAP_REASONS.citation_invalid.write(step.path, step.title),
      });
    });

    return { subtopic: week.subtopic, steps };
  });

  return { topic: first.topic, weeks, gaps };
}

// The line between declining the whole request and carrying on with a gap: this check
// runs once, before the model is ever called, against the topic as a whole. If the corpus
// has nothing on the topic at all - not even a heading-only near miss - there is nothing
// for the lead to plan around, so the run declines without spending a token.
//
// coverage.mentioned already covers the near miss: corpus/store.ts sets it from
// strongPaths or headingPaths being non-empty, and derives nearMisses from headingPaths,
// so a topic with a near miss is a topic that is mentioned. The separate
// nearMisses.length === 0 clause that used to be here could never change the result.
// Coverage of
// an individual subtopic the lead identifies mid-run is a narrower question the model
// answers itself via the check_coverage tool, recording a gap and continuing rather than
// aborting the whole plan.
//
// Exported so routes/plans.ts can decide the HTTP status (422 vs 200) before the streaming
// response opens, using the exact same rule runLeadPlan uses to decide "declined" vs
// "planned" - one predicate, called from both places, rather than the same expression
// copied into two files where only one of them could be updated later.
export function isTopicOutOfRange(store: CorpusStore, topic: string): boolean {
  return !store.coverage(topic).mentioned;
}

// A run that produced no steps did not produce a plan, and neither did a run that produced
// steps without researching anything. A live run returned "planned" in 21 seconds with
// three weeks of empty steps and invented gap reasons after the loop researched nothing,
// and base14.plan.duration and base14.plan.cost recorded it as a successful plan.
//
// Both halves are needed. Zero steps across all weeks catches the first: a week recorded as
// a gap legitimately has no steps, so nothing is asserted about individual weeks, and a plan
// of nothing but gaps is exactly the run this is here to catch. The research check catches
// the case the step count cannot see: the lead can spend every nudged step on corpus_map
// and check_coverage, which is not a toolChoice violation because it is calling tools, then
// answer in prose once the nudge is withdrawn, and the shaping call can write steps whose
// citations validate because it read real paths out of that summary. Fan-out 0, steps
// non-zero, and without this it would be recorded as a plan.
//
// A run that failed for want of research says so in a gap, because failed otherwise covers
// both an outage and a run that simply found nothing, and only the gap reason separates
// them on base14.plan.gap.count.
//
// A topic the corpus does not cover is a different thing and still declines, above, before
// a token is spent.
function outcomeFor(plan: Plan, researched: boolean): LeadOutcome {
  const steps = plan.weeks.reduce((total, week) => total + week.steps.length, 0);

  if (!researched) {
    return {
      status: "failed",
      plan: {
        ...plan,
        gaps: [...plan.gaps, { term: plan.topic, reason: SERVICE_GAP_REASONS.no_research }],
      },
    };
  }

  return { status: steps === 0 ? "failed" : "planned", plan };
}

export async function runLeadPlan(
  agent: LeadAgent,
  request: LeadRequest,
  store: CorpusStore,
): Promise<LeadOutcome> {
  if (isTopicOutOfRange(store, request.topic)) {
    return {
      status: "declined",
      plan: {
        topic: request.topic,
        weeks: [],
        gaps: [
          {
            term: request.topic,
            reason: SERVICE_GAP_REASONS.topic_out_of_range,
          },
        ],
      },
    };
  }

  // The SDK enforces toolChoice itself: a step that was required to call a tool and
  // answered in prose throws rather than returning. That is the only way the requirement
  // has teeth on Ollama, which accepts tool_choice and ignores it (measured on 0.32.15,
  // see prepareStep in buildLeadAgent). Caught here rather than left to the route's error
  // path: the throw can only happen while nothing has been researched, so there is nothing
  // to shape a plan from, and a failed outcome carries the run's metrics and a gap that
  // says why, where an unhandled throw carries neither.
  let loop: Awaited<ReturnType<typeof agent.loop.generate>>;
  try {
    loop = await agent.loop.generate({ prompt: `Topic: ${request.topic}` });
  } catch (error) {
    if (!ToolChoiceViolationError.isInstance(error)) {
      throw error;
    }
    return {
      status: "failed",
      plan: {
        topic: request.topic,
        weeks: [],
        gaps: [
          {
            term: request.topic,
            reason: SERVICE_GAP_REASONS.no_tool_call,
          },
        ],
      },
    };
  }

  const research = researchNotes(loop);
  // Read off the loop's own steps rather than off the run counters, so this says what the
  // lead did on this request and nothing else: the counters are optional (the unit tests
  // build a lead with no run) and count researcher starts across the whole run.
  const researched = hasResearched(loop.steps);

  const first = await agent.shaper.generate({ prompt: shapePrompt(request.topic, research) });
  const invalid = findInvalidSteps(first.output, store);

  if (invalid.length === 0) {
    return outcomeFor(first.output, researched);
  }

  // Only the shaping call is repeated, not the loop. The research is already gathered and
  // a wrong citation is a writing mistake, not a gap in what was read, so re-running
  // sixteen steps of tool calls to correct one path would double the run for nothing.
  const retry = await agent.shaper.generate({
    prompt: retryPrompt(request.topic, research, invalid),
  });
  const plan = reconcile(first.output, retry.output, invalid, store);

  return outcomeFor(plan, researched);
}
