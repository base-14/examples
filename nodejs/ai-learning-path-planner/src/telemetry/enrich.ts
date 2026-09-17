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

// Passed to every ToolLoopAgent as its runtimeContext, which is the only channel
// enrichSpan can read from: it fires when a span is created and receives nothing about
// the call itself. A researcher agent is built per subtopic, so subtopic can ride along
// here and land on every span of that agent's run.
export interface PlanRuntimeContext extends Record<string, unknown> {
  planId: string;
  agentRole: "lead" | "researcher";
  toolCatalogue: "deferred" | "full";
  subtopic?: string;
}

// Runtime context reaches enrichSpan only for the keys named here: the AI SDK drops
// every runtime context property from telemetry unless it is explicitly included. Passed
// to both agents as telemetry.includeRuntimeContext.
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

// takeRunCostUsd is the only delete site, and a late invoke_agent span can recreate an
// entry for a plan id that has already been taken, in a process that runs for as long as
// the service does. The cap bounds that.
const MAX_TRACKED_RUNS = 1024;

// One run's cost is the sum of its invoke_agent spans: the lead's own run plus one per
// researcher. chat spans carry token counts too, but adding those as well would count
// every model call twice.
//
// Eviction is least-recently-updated, not insertion order, and the difference is not
// cosmetic. A run contributes one span per researcher over the twenty-odd seconds it takes,
// so under insertion order a busy service could evict a run's partial total while the run
// was still going. Its remaining spans would then rebuild the entry from zero and the run
// would report a cost that looks plausible and is too low - worse than a missing value,
// which at least announces itself. Deleting before setting moves a run back to the newest
// position on every span it contributes, so only runs that have gone genuinely quiet for
// 1024 other runs are evicted.
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

// Cost cannot come from enrichSpan: token counts do not exist when a span is created.
// This processor reads them in onEnd instead and writes the cost into the span's
// attributes. Register it ahead of the exporting processor so the exporter sees the span
// after the attributes are on it.
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

    // A throw here would surface on the SDK's span-export path, with nothing to tie it
    // back to the request that produced the span. The one reachable throw in costOf, an
    // unknown PRICE_MODEL, is already ruled out at boot by assertPriceModelIsKnown; this
    // keeps anything else from escaping into the exporter.
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
