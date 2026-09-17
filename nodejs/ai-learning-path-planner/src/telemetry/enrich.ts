import type { EnrichSpan } from "@ai-sdk/otel";
import type { Attributes } from "@opentelemetry/api";
import type { ReadableSpan, SpanProcessor } from "@opentelemetry/sdk-trace-base";
import type { LanguageModelUsage } from "ai";
import type { Config } from "../config.ts";
import { costOf } from "../llm/cost.js";

export const ATTR_PLAN_ID = "base14.plan.id";
export const ATTR_AGENT_ROLE = "base14.agent.role";
export const ATTR_SUBTOPIC = "base14.subtopic";
export const ATTR_TOOL_CATALOGUE = "base14.tool.catalogue";
export const ATTR_COST = "base14.gen_ai.cost";
export const ATTR_COST_SIMULATED = "base14.gen_ai.cost.simulated";

const ATTR_OPERATION_NAME = "gen_ai.operation.name";
const ATTR_REQUEST_MODEL = "gen_ai.request.model";
const ATTR_RESPONSE_MODEL = "gen_ai.response.model";
const ATTR_INPUT_TOKENS = "gen_ai.usage.input_tokens";
const ATTR_OUTPUT_TOKENS = "gen_ai.usage.output_tokens";
const ATTR_CACHE_READ_TOKENS = "gen_ai.usage.cache_read.input_tokens";

const AGENT_OPERATION = "invoke_agent";

// The only channel enrichSpan can read from: it fires at span creation and is told nothing
// about the call. A researcher is built per subtopic, so the subtopic rides along here.
export interface PlanRuntimeContext extends Record<string, unknown> {
  planId: string;
  agentRole: "lead" | "researcher";
  toolCatalogue: "deferred" | "full";
  subtopic?: string;
}

// The AI SDK drops every runtime context property from telemetry unless it is named here.
export const PLAN_RUNTIME_CONTEXT_KEYS = {
  planId: true,
  agentRole: true,
  toolCatalogue: true,
  subtopic: true,
} as const;

export const enrichSpan: EnrichSpan = ({ runtimeContext }) => {
  if (runtimeContext === undefined) {
    return undefined;
  }

  const attributes: Attributes = {};
  const { planId, agentRole, toolCatalogue, subtopic } = runtimeContext;

  if (typeof planId === "string") attributes[ATTR_PLAN_ID] = planId;
  if (typeof agentRole === "string") attributes[ATTR_AGENT_ROLE] = agentRole;
  if (typeof toolCatalogue === "string") attributes[ATTR_TOOL_CATALOGUE] = toolCatalogue;
  if (typeof subtopic === "string") attributes[ATTR_SUBTOPIC] = subtopic;

  return attributes;
};

const runCosts = new Map<string, number>();

// A late invoke_agent span can recreate an entry for a plan id already taken, in a
// long-running process. The cap bounds that.
const MAX_TRACKED_RUNS = 1024;

// A run's cost is the sum of its invoke_agent spans. chat spans carry token counts too, but
// adding both would count every model call twice.
//
// Eviction is least-recently-updated rather than insertion order, which matters: a run
// contributes spans over a minute or two, and evicting its partial total mid-run would let the
// remaining spans rebuild it from zero and report a plausible cost that is too low.
function addRunCost(planId: string, usd: number): void {
  const running = runCosts.get(planId);
  if (running === undefined && runCosts.size >= MAX_TRACKED_RUNS) {
    const oldest = runCosts.keys().next().value;
    if (oldest !== undefined) {
      runCosts.delete(oldest);
    }
  } else if (running !== undefined) {
    runCosts.delete(planId);
  }
  runCosts.set(planId, (running ?? 0) + usd);
}

export function takeRunCostUsd(planId: string): number {
  const usd = runCosts.get(planId) ?? 0;
  runCosts.delete(planId);
  return usd;
}

function numberAttribute(attributes: Attributes, key: string): number | undefined {
  const value = attributes[key];
  return typeof value === "number" ? value : undefined;
}

function stringAttribute(attributes: Attributes, key: string): string | undefined {
  const value = attributes[key];
  return typeof value === "string" ? value : undefined;
}

function usageFrom(input: number, output: number, cacheRead: number): LanguageModelUsage {
  return {
    inputTokens: input,
    inputTokenDetails: {
      noCacheTokens: Math.max(input - cacheRead, 0),
      cacheReadTokens: cacheRead,
      cacheWriteTokens: undefined,
    },
    outputTokens: output,
    outputTokenDetails: { textTokens: output, reasoningTokens: undefined },
    totalTokens: input + output,
  };
}

// Cost cannot come from enrichSpan: token counts do not exist at span creation. This reads them
// in onEnd, and is registered ahead of the exporting processor so the exporter sees them.
export class PlanCostSpanProcessor implements SpanProcessor {
  constructor(private readonly config: Config) {}

  onStart(): void {}

  onEnd(span: ReadableSpan): void {
    const attributes = span.attributes;
    const inputTokens = numberAttribute(attributes, ATTR_INPUT_TOKENS);
    const outputTokens = numberAttribute(attributes, ATTR_OUTPUT_TOKENS);
    if (inputTokens === undefined && outputTokens === undefined) {
      return;
    }

    const modelId =
      stringAttribute(attributes, ATTR_RESPONSE_MODEL) ??
      stringAttribute(attributes, ATTR_REQUEST_MODEL);
    if (modelId === undefined) {
      return;
    }

    const usage = usageFrom(
      inputTokens ?? 0,
      outputTokens ?? 0,
      numberAttribute(attributes, ATTR_CACHE_READ_TOKENS) ?? 0,
    );

    // A throw here lands on the SDK's export path with nothing tying it to a request.
    // assertPriceModelIsKnown rules out the one reachable case at boot; this catches the rest.
    let cost: { usd: number; simulated: boolean };
    try {
      cost = costOf(usage, modelId, this.config);
    } catch {
      return;
    }

    attributes[ATTR_COST] = cost.usd;
    attributes[ATTR_COST_SIMULATED] = cost.simulated;

    const planId = stringAttribute(attributes, ATTR_PLAN_ID);
    if (planId !== undefined && attributes[ATTR_OPERATION_NAME] === AGENT_OPERATION) {
      addRunCost(planId, cost.usd);
    }
  }

  forceFlush(): Promise<void> {
    return Promise.resolve();
  }

  shutdown(): Promise<void> {
    return Promise.resolve();
  }
}
