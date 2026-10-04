import { Agent, type AgentExecutionOptions } from "@mastra/core/agent";
import type { Config } from "../config.ts";
import { providerOptionsFor, selectModel } from "../llm/models.js";
import { type Plan, PlanSchema } from "../plans/schema.js";
import type { PlanRuntimeContext } from "../telemetry/enrich.js";
import { mastraInstance } from "../telemetry/mastra.js";
import { withPlanContext } from "../telemetry/plan-context.js";
import { activeToolsFor } from "../tools/catalogue.js";
import type { ResearcherHandle } from "../tools/research-subtopic.js";
import {
  hasResearched,
  LEAD_INSTRUCTIONS,
  LEAD_NUDGE,
  type LeadAgentDeps,
  type LeadLoopResult,
  type LeadRunner,
  leadTools,
  NUDGED_STEPS,
  PLAN_INSTRUCTIONS,
  RequiredToolCallMissing,
} from "./lead.js";
import {
  documentsOpened,
  FINDINGS_INSTRUCTIONS,
  findingsPrompt,
  RESEARCHER_INSTRUCTIONS,
  type ResearcherAgentDeps,
  type ResearcherFindings,
  ResearcherFindingsSchema,
  researchSubtopicPlaceholder,
} from "./researcher.js";

type AgentModel = ConstructorParameters<typeof Agent>[0]["model"];
type AgentTools = NonNullable<ConstructorParameters<typeof Agent>[0]["tools"]>;
type MastraProviderOptions = AgentExecutionOptions["providerOptions"];

// The same per-call options the AI SDK agents send, typed for Mastra's generate().
function mastraProviderOptions(config: Config): MastraProviderOptions {
  return providerOptionsFor(config) as MastraProviderOptions;
}

const LEAD_MAX_STEPS = 16;
const RESEARCHER_MAX_STEPS = 6;

// Mastra returns tool calls and results as chunks, with the tool's name, input and output under
// `payload`. The steps handed to prepareStep carry the same facts flat. These read either back
// into the shape runLeadPlan and documentsOpened take.
interface ToolChunk {
  toolName?: string;
  input?: unknown;
  output?: unknown;
  payload?: { toolName?: string; args?: unknown; result?: unknown };
}

interface LoopResult {
  text: string;
  steps: { text?: string; toolCalls?: ToolChunk[]; toolResults?: ToolChunk[] }[];
}

// Mastra's `text` joins the text of every step. The AI SDK's is the last step's alone, which
// is what the summary and the research notes are meant to be.
function finalText(result: LoopResult): string {
  return result.steps.at(-1)?.text ?? result.text;
}

function toolCallsOf(step: LoopResult["steps"][number]): { toolName: string; input: unknown }[] {
  return (step.toolCalls ?? []).map((call) => ({
    toolName: call.payload?.toolName ?? call.toolName ?? "",
    input: call.payload?.args ?? call.input,
  }));
}

function toLeadLoopResult(result: LoopResult): LeadLoopResult {
  return {
    text: finalText(result),
    steps: result.steps.map((step) => ({ toolCalls: toolCallsOf(step) })),
    // Every step's results, because research_subtopic is called on several of them.
    toolResults: result.steps.flatMap((step) =>
      (step.toolResults ?? []).map((toolResult) => ({
        toolName: toolResult.payload?.toolName ?? toolResult.toolName ?? "",
        output: toolResult.payload?.result ?? toolResult.output,
      })),
    ),
  };
}

function pick(tools: Record<string, unknown>, names: string[]): AgentTools {
  return Object.fromEntries(names.map((name) => [name, tools[name]])) as AgentTools;
}

// The model sees a prompt and tool content only when content capture is on. Without these
// Mastra records both on every span.
function tracingOptionsFor(config: Config) {
  return { hideInput: !config.captureMessageContent, hideOutput: !config.captureMessageContent };
}

export function buildMastraResearcher(deps: ResearcherAgentDeps): ResearcherHandle {
  const runtimeContext: PlanRuntimeContext | undefined =
    deps.planId === undefined
      ? undefined
      : {
          planId: deps.planId,
          agentRole: "researcher",
          toolCatalogue: deps.config.toolCatalogue,
          subtopic: deps.subtopic,
        };

  // All nine, as the AI SDK researcher builds them: under TOOL_CATALOGUE=full the researcher
  // carries research_subtopic's definition too, behind a placeholder that declines the call.
  const tools = {
    ...leadTools({ store: deps.store, config: deps.config }, () => {
      throw new Error("research_subtopic is only meant to be called by the lead agent.");
    }),
    research_subtopic: researchSubtopicPlaceholder(),
  };
  const names = activeToolsFor("researcher", deps.config);

  const model = (deps.model ?? selectModel(deps.tier, deps.config)) as AgentModel;
  const providerOptions = mastraProviderOptions(deps.config);
  const tracingOptions = tracingOptionsFor(deps.config);
  const mastra = mastraInstance();

  const loop = new Agent({
    id: "researcher",
    name: "researcher",
    instructions: RESEARCHER_INSTRUCTIONS,
    model,
    tools: pick(tools, names),
    mastra,
  });
  const shaper = new Agent({
    id: "researcher-findings",
    name: "researcher-findings",
    instructions: FINDINGS_INSTRUCTIONS,
    model,
    mastra,
  });

  return {
    generate: ({ prompt }) =>
      withPlanContext(runtimeContext, async () => {
        const notes = (await loop.generate(prompt, {
          maxSteps: RESEARCHER_MAX_STEPS,
          providerOptions,
          tracingOptions,
        })) as unknown as LoopResult;
        const opened = documentsOpened(notes.steps.flatMap(toolCallsOf));
        const shaped = await shaper.generate(
          findingsPrompt(deps.subtopic, finalText(notes), opened),
          {
            structuredOutput: { schema: ResearcherFindingsSchema },
            providerOptions,
            tracingOptions,
          },
        );
        return { output: shaped.object as ResearcherFindings };
      }),
  };
}

// The Mastra counterpart of buildLeadAgent, behind the same runner interface: the same
// instructions, tools and two-call split, with Mastra's Agent running the loop.
export function buildMastraLeadAgent(deps: LeadAgentDeps) {
  const runtimeContext: PlanRuntimeContext | undefined =
    deps.run === undefined
      ? undefined
      : {
          planId: deps.run.planId,
          agentRole: "lead",
          toolCatalogue: deps.config.toolCatalogue,
        };

  const tools = leadTools(deps, (opts) =>
    buildMastraResearcher({
      store: deps.store,
      config: deps.config,
      planId: deps.run?.planId,
      subtopic: opts.subtopic,
      tier: opts.tier,
      model: opts.tier === "small" ? deps.researcherModels?.small : deps.researcherModels?.large,
    }),
  );

  const model = (deps.model ?? selectModel("large", deps.config)) as AgentModel;
  const providerOptions = mastraProviderOptions(deps.config);
  const tracingOptions = tracingOptionsFor(deps.config);
  const mastra = mastraInstance();

  const loop = new Agent({
    id: "lead",
    name: "lead",
    instructions: LEAD_INSTRUCTIONS,
    model,
    tools: pick(tools, activeToolsFor("lead", deps.config)),
    mastra,
  });
  const shaper = new Agent({
    id: "lead-plan",
    name: "lead-plan",
    instructions: PLAN_INSTRUCTIONS,
    model,
    mastra,
  });

  const runner: LeadRunner = {
    loop: {
      generate: ({ prompt }) =>
        withPlanContext(runtimeContext, async () => {
          const result = (await loop.generate(prompt, {
            maxSteps: LEAD_MAX_STEPS,
            providerOptions,
            tracingOptions,
            // The same nudge the AI SDK lead gets: a tool call is required, and said so, on the
            // early steps while nothing has been researched.
            prepareStep: ({ stepNumber, steps }) => {
              const taken = (steps as LoopResult["steps"]).map((step) => ({
                toolCalls: toolCallsOf(step),
              }));
              // Put back explicitly, as the AI SDK lead does: Mastra carries both overrides
              // into later steps, and a lead still required to call a tool never ends the loop.
              if (stepNumber >= NUDGED_STEPS || hasResearched(taken)) {
                return {
                  toolChoice: "auto",
                  systemMessages: [{ role: "system", content: LEAD_INSTRUCTIONS }],
                };
              }
              return {
                toolChoice: "required",
                systemMessages: [
                  { role: "system", content: `${LEAD_INSTRUCTIONS}\n\n${LEAD_NUDGE}` },
                ],
              };
            },
          })) as unknown as LoopResult;
          const mapped = toLeadLoopResult(result);
          // Mastra passes toolChoice to the provider and does not enforce it. A nudged step
          // that answered in prose ends the loop, so that is checked here.
          const answeredInProse =
            mapped.steps.length <= NUDGED_STEPS &&
            !hasResearched(mapped.steps) &&
            (mapped.steps.at(-1)?.toolCalls.length ?? 0) === 0;
          if (answeredInProse) {
            throw new RequiredToolCallMissing("the lead answered without calling a tool");
          }
          return mapped;
        }),
    },
    shaper: {
      generate: ({ prompt }) =>
        withPlanContext(runtimeContext, async () => {
          const shaped = await shaper.generate(prompt, {
            structuredOutput: { schema: PlanSchema },
            providerOptions,
            tracingOptions,
          });
          return { output: shaped.object as Plan };
        }),
    },
  };

  return { tools, ...runner };
}
