import type { LanguageModel } from "ai";
import {
  type ActiveTools,
  isStepCount,
  Output,
  type TelemetryOptions,
  ToolLoopAgent,
  tool,
} from "ai";
import { z } from "zod";
import type { Config } from "../config.ts";
import type { CorpusStore } from "../corpus/store.ts";
import { providerOptionsFor, selectModel } from "../llm/models.js";
import { PLAN_RUNTIME_CONTEXT_KEYS, type PlanRuntimeContext } from "../telemetry/enrich.js";
import { activeToolsFor } from "../tools/catalogue.js";
import { checkCoverageTool } from "../tools/check-coverage.js";
import { corpusMapTool } from "../tools/corpus-map.js";
import { fetchExampleFileTool } from "../tools/fetch-example-file.js";
import { fetchSectionTool } from "../tools/fetch-section.js";
import { getRelatedTool } from "../tools/get-related.js";
import { listExamplesTool } from "../tools/list-examples.js";
import { outlineTool } from "../tools/outline.js";
import {
  RESEARCH_SUBTOPIC_DESCRIPTION,
  RESEARCH_SUBTOPIC_INPUT_SCHEMA,
} from "../tools/research-subtopic.js";
import { searchDocsTool } from "../tools/search-docs.js";

export const ResearcherFindingSchema = z.object({
  path: z.string(),
  heading: z.string().optional(),
  note: z.string(),
});

export const ResearcherFindingsSchema = z.object({
  subtopic: z.string(),
  findings: z.array(ResearcherFindingSchema),
});

export type ResearcherFindings = z.infer<typeof ResearcherFindingsSchema>;

export interface ResearcherAgentDeps {
  store: CorpusStore;
  config: Config;
  subtopic: string;
  tier: "small" | "large";
  telemetry?: TelemetryOptions;
  model?: LanguageModel;
  planId?: string;
}

const RESEARCHER_INSTRUCTIONS =
  "You research one subtopic of a learning plan against base14's documentation and " +
  "examples corpus. Use search_docs to find candidate documents, then outline and " +
  "fetch_section to read them, and list_examples and fetch_example_file for runnable " +
  "examples. When you have read enough, stop calling tools and write a short plain-text " +
  "note per document you actually read: the corpus path, the heading, and one sentence " +
  "on what it shows. Do not mention a path you have not read.";

const FINDINGS_INSTRUCTIONS =
  "You turn research notes into structured findings for one subtopic. Report one finding " +
  "per corpus path that appears in the notes, with the heading it came from and a one " +
  "sentence note on what it shows. Report nothing that is not in the notes.";

// TOOL_CATALOGUE=full puts research_subtopic's name, description and input schema in
// front of a researcher too, so Task 9 can measure the same input-token difference on
// both roles. A researcher's instructions never ask it to call this tool, and giving it a
// real, working implementation here would mean this file builds a researcher agent that
// itself builds researcher agents on demand, an unbounded recursion with no product
// purpose. The placeholder keeps the token-relevant tool definition identical to the
// lead's real one while declining to do any work if it is ever called.
function researchSubtopicPlaceholder() {
  return tool({
    description: RESEARCH_SUBTOPIC_DESCRIPTION,
    inputSchema: RESEARCH_SUBTOPIC_INPUT_SCHEMA,
    execute: async () => ({
      error: "research_subtopic is only meant to be called by the lead agent.",
    }),
  });
}

export function buildResearcherAgent(deps: ResearcherAgentDeps) {
  // A researcher agent is built once per subtopic, so the subtopic can ride in the
  // runtime context and reach every span of this agent's run. enrichSpan has no other
  // way to see it: it is handed no tool name and no tool input.
  const runtimeContext: PlanRuntimeContext | undefined =
    deps.planId === undefined
      ? undefined
      : {
          planId: deps.planId,
          agentRole: "researcher",
          toolCatalogue: deps.config.toolCatalogue,
          subtopic: deps.subtopic,
        };

  // All nine tools are always built, on both agents; activeTools (via activeToolsFor) is
  // what actually restricts what the model sees, per role and TOOL_CATALOGUE. That keeps
  // this file's tool map identically shaped regardless of catalogue mode.
  const tools = {
    search_docs: searchDocsTool(deps.store),
    outline: outlineTool(deps.store),
    fetch_section: fetchSectionTool(deps.store),
    list_examples: listExamplesTool(deps.store),
    fetch_example_file: fetchExampleFileTool(deps.store),
    corpus_map: corpusMapTool(deps.store),
    check_coverage: checkCoverageTool(deps.store),
    get_related: getRelatedTool(deps.store),
    research_subtopic: researchSubtopicPlaceholder(),
  };

  const model = deps.model ?? selectModel(deps.tier, deps.config);
  const providerOptions = providerOptionsFor(deps.config);
  const telemetry = {
    includeRuntimeContext: PLAN_RUNTIME_CONTEXT_KEYS,
    recordInputs: deps.config.captureMessageContent,
    recordOutputs: deps.config.captureMessageContent,
  };

  // Split for the same reason the lead is (see agents/lead.ts): Output.object puts a json
  // responseFormat on every call, ollama-ai-provider-v2 turns that into a `format`
  // grammar, and `format` in front of tool definitions stops the model calling a tool.
  // A researcher that calls no tool reads nothing, so its findings cite paths it never
  // fetched and every one of them fails validateCitation.
  const loop = new ToolLoopAgent({
    id: `researcher-${deps.subtopic}`,
    model,
    instructions: RESEARCHER_INSTRUCTIONS,
    tools,
    activeTools: activeToolsFor("researcher", deps.config) as ActiveTools<typeof tools>,
    stopWhen: isStepCount(6),
    providerOptions,
    runtimeContext,
    telemetry: { functionId: "researcher", ...telemetry, ...deps.telemetry },
  });

  const shaper = new ToolLoopAgent({
    id: `researcher-findings-${deps.subtopic}`,
    model,
    instructions: FINDINGS_INSTRUCTIONS,
    tools: {},
    stopWhen: isStepCount(1),
    output: Output.object({ schema: ResearcherFindingsSchema }),
    providerOptions,
    runtimeContext,
    telemetry: { functionId: "researcher-findings", ...telemetry, ...deps.telemetry },
  });

  // generate() runs both halves, so research_subtopic still calls one thing and gets
  // structured findings back (see tools/research-subtopic.ts's ResearcherHandle). tools is
  // the loop's, which is what toolDefinitionTokens counts.
  return {
    tools: loop.tools,
    loop,
    shaper,
    async generate({ prompt }: { prompt: string }) {
      const notes = await loop.generate({ prompt });
      return shaper.generate({
        prompt: findingsPrompt(deps.subtopic, notes.text, documentsOpened(notes.toolCalls)),
      });
    },
  };
}

interface DocumentRef {
  path: string;
  heading?: string;
}

// The loop writes prose, and prose does not reliably carry the paths it came from. Given
// only the prose, the shaping call invents citations, every finding fails
// validateCitation, the subtopic escalates and comes back as a gap - which is what live
// runs produced. The paths are therefore read back off the tool calls the loop actually
// made, which is a record of what it opened rather than a claim about it.
function documentsOpened(toolCalls: { input: unknown }[]): DocumentRef[] {
  const refs = new Map<string, DocumentRef>();

  for (const call of toolCalls) {
    const input = call.input as { path?: unknown; heading?: unknown } | undefined;
    if (typeof input?.path !== "string") {
      continue;
    }
    const heading = typeof input.heading === "string" ? input.heading : undefined;
    refs.set(`${input.path}\u0000${heading ?? ""}`, { path: input.path, heading });
  }

  return [...refs.values()];
}

function findingsPrompt(subtopic: string, notes: string, opened: DocumentRef[]): string {
  const trimmed = notes.trim();
  return (
    `Subtopic: ${subtopic}.\n\n` +
    `The documents you opened, as corpus path and heading:\n${JSON.stringify(opened)}\n\n` +
    `Your notes on them:\n${trimmed.length > 0 ? trimmed : "(none)"}\n\n` +
    "Report these as structured findings, citing only the paths listed above."
  );
}
