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

// Set by the route handler, which owns the plan id and the counters. Undefined in unit tests,
// which have no run to attribute spans or metrics to.
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

// The loop gathers, the shaping call writes. Splitting the instructions the same way keeps the
// loop from trying to emit a plan on a step that still has tools in front of it.
const LEAD_INSTRUCTIONS =
  "You research a topic against base14's documentation and examples corpus so a learning " +
  "plan can be written from what you find. Break the topic into a small number of focused " +
  "subtopics and call research_subtopic once per subtopic to gather cited findings. Use " +
  "corpus_map to see what areas the corpus covers, check_coverage to check a subtopic " +
  "before researching it, and get_related to broaden a path you already have. When every " +
  "subtopic has been researched, stop calling tools and write a short plain-text summary: " +
  "one line per subtopic, naming the corpus paths the research returned for it and any " +
  "subtopic that returned nothing. Do not write the plan itself.";

// Added on any early step that has researched nothing, withdrawn once one has. A directive
// true on step one and false on step six does not belong in the system prompt.
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

// Long enough for the lead to survey the corpus before it has to research, short enough that
// it still ends the loop itself afterwards.
const NUDGED_STEPS = 6;

function hasResearched(steps: { toolCalls: { toolName: string }[] }[]): boolean {
  return steps.some((step) => step.toolCalls.some((call) => call.toolName === "research_subtopic"));
}

// A new lead agent per request. The MAX_SUBTOPICS and MAX_ESCALATIONS counters live in the
// research_subtopic closure created here, so a reused agent carries exhausted caps forward.
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

  // Two agents, not one, because of the wire format. Output.object puts a json responseFormat
  // on every call, which the provider turns into a `format` grammar, and `format` alongside
  // tool definitions stops this model calling a tool at all. So the loop runs with tools and no
  // response format, and a second structured call shapes the plan. prepareStep cannot do it:
  // its return type covers toolChoice, activeTools, tools and model, but not responseFormat.
  const loop = new ToolLoopAgent({
    id: "lead",
    model,
    instructions: LEAD_INSTRUCTIONS,
    tools,
    activeTools: activeToolsFor("lead", deps.config) as ActiveTools<typeof tools>,
    stopWhen: isStepCount(16),
    // With no response format on the loop, prose alone did not hold the lead to researching
    // anything, so a tool call is required while nothing has been researched. The tool is not
    // named: choosing between surveying and researching is the decision this example shows.
    //
    // toolChoice is the provider-agnostic half and is inert on Ollama, which accepts
    // tool_choice and ignores it. The instructions override is what moves this model, so both
    // are sent, and the AI SDK enforces toolChoice client-side.
    prepareStep: ({ stepNumber, steps }) => {
      // Put back explicitly: the SDK carries a prepareStep instructions override forward into
      // every later step, so returning nothing would leave the nudge in front of the model for
      // the rest of the run.
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

  // The same runtimeContext as the loop, so its spans carry base14.plan.id and its tokens land
  // in the run's cost total.
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

// Everything the shaping call may write a plan from: the loop's summary plus each researcher's
// findings, verbatim, as JSON rather than prose because they are the only source of a citation
// the plan may use. validateCitation checks the result against the store regardless.
function researchNotes(loop: {
  text: string;
  toolResults: { toolName: string; output: unknown }[];
}): string {
  // The outputs only, never the tool-result envelope: handed the envelope, the model cites the
  // toolCallId as if it were a corpus path.
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

// After the model returns, never inside the prompt: structured output is accepted step by step
// through validateCitation, and nothing else parses a citation path.
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

// Declining the whole request, as against carrying on with a gap. Runs once against the whole
// topic before any model call, so a topic the corpus does not mention at all costs nothing.
// coverage.mentioned already covers near misses, which corpus/store.ts derives from the same
// heading paths. Coverage of one subtopic mid-run is the model's own check_coverage call, which
// records a gap and continues.
//
// Exported so routes/plans.ts can pick 422 against 200 before the stream opens, from the same
// predicate runLeadPlan uses.
export function isTopicOutOfRange(store: CorpusStore, topic: string): boolean {
  return !store.coverage(topic).mentioned;
}

// A run with no steps is not a plan, and neither is one that produced steps without
// researching. Both halves are needed: a plan of nothing but gaps has zero steps, and a lead
// that spends every nudged step on corpus_map and check_coverage violates no toolChoice, then
// answers in prose, and the shaping call can still write steps whose citations validate from
// real paths in that summary.
//
// The failure carries a gap, because failed otherwise covers both an outage and a run that
// found nothing, and only the reason separates them on base14.plan.gap.count.
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

  // The SDK throws when a step required to call a tool answers in prose, which is the only way
  // the requirement has teeth on Ollama. Caught here because the throw can only happen while
  // nothing has been researched: a failed outcome carries metrics and a gap, a throw neither.
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
  // Off the loop's own steps, not the run counters, which are optional and count researcher
  // starts across the whole run.
  const researched = hasResearched(loop.steps);

  const first = await agent.shaper.generate({ prompt: shapePrompt(request.topic, research) });
  const invalid = findInvalidSteps(first.output, store);

  if (invalid.length === 0) {
    return outcomeFor(first.output, researched);
  }

  // Only the shaping call is repeated: a wrong citation is a writing mistake, not a gap in what
  // was read, so re-running the tool loop would double the run for nothing.
  const retry = await agent.shaper.generate({
    prompt: retryPrompt(request.topic, research, invalid),
  });
  const plan = reconcile(first.output, retry.output, invalid, store);

  return outcomeFor(plan, researched);
}
