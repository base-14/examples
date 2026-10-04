import { context } from "@opentelemetry/api";
import { AsyncLocalStorageContextManager } from "@opentelemetry/context-async-hooks";
import {
  BasicTracerProvider,
  InMemorySpanExporter,
  SimpleSpanProcessor,
} from "@opentelemetry/sdk-trace-base";
import { afterAll, beforeAll, beforeEach, describe, expect, it } from "vitest";
import type { Config } from "../../src/config.ts";
import {
  ATTR_AGENT_ROLE,
  ATTR_CONVERSATION_ID,
  ATTR_COST,
  ATTR_PLAN_ID,
  ATTR_SUBTOPIC,
  MASTRA_SCOPE,
  PlanCostSpanProcessor,
  takeRunCostUsd,
} from "../../src/telemetry/enrich.ts";
import { MastraPlanSpanProcessor, withPlanContext } from "../../src/telemetry/plan-context.ts";

const config = {
  llmProvider: "ollama",
  priceModel: "gpt-5-nano",
} as Config;

const exporter = new InMemorySpanExporter();
const contextManager = new AsyncLocalStorageContextManager();

function providerWith(captureMessageContent: boolean): BasicTracerProvider {
  return new BasicTracerProvider({
    spanProcessors: [
      new MastraPlanSpanProcessor(captureMessageContent),
      new PlanCostSpanProcessor(config),
      new SimpleSpanProcessor(exporter),
    ],
  });
}

beforeAll(() => {
  context.setGlobalContextManager(contextManager.enable());
});

afterAll(() => {
  context.disable();
});

beforeEach(() => {
  exporter.reset();
});

const RUN = {
  planId: "plan-1",
  agentRole: "researcher",
  toolCatalogue: "deferred",
  subtopic: "tracing basics",
} as const;

describe("MastraPlanSpanProcessor", () => {
  it("puts the plan, conversation, role and subtopic on a Mastra span started in a plan context", async () => {
    const tracer = providerWith(false).getTracer(MASTRA_SCOPE);

    await withPlanContext(RUN, async () => {
      tracer.startSpan("chat gemma4:e2b").end();
    });

    const [span] = exporter.getFinishedSpans();
    expect(span?.attributes[ATTR_PLAN_ID]).toBe("plan-1");
    expect(span?.attributes[ATTR_CONVERSATION_ID]).toBe("plan-1");
    expect(span?.attributes[ATTR_AGENT_ROLE]).toBe("researcher");
    expect(span?.attributes[ATTR_SUBTOPIC]).toBe("tracing basics");
  });

  it("leaves a span from another instrumentation alone", async () => {
    const tracer = providerWith(false).getTracer("@opentelemetry/instrumentation-undici");

    await withPlanContext(RUN, async () => {
      tracer.startSpan("POST").end();
    });

    expect(exporter.getFinishedSpans()[0]?.attributes[ATTR_PLAN_ID]).toBeUndefined();
  });

  it("leaves a Mastra span outside a plan context without plan attributes", () => {
    providerWith(false).getTracer(MASTRA_SCOPE).startSpan("chat gemma4:e2b").end();

    expect(exporter.getFinishedSpans()[0]?.attributes[ATTR_PLAN_ID]).toBeUndefined();
  });

  it("removes prompt, response and tool content when content capture is off", () => {
    const span = providerWith(false).getTracer(MASTRA_SCOPE).startSpan("invoke_agent lead");
    span.setAttributes({
      "gen_ai.input.messages": "[]",
      "gen_ai.output.messages": "[]",
      "gen_ai.system_instructions": "You research a topic.",
      "gen_ai.tool.call.arguments": "{}",
      "gen_ai.tool.call.result": "{}",
      "mastra.agent_run.input": "Topic: tracing",
      "mastra.model_step.output": "{}",
      "gen_ai.agent.name": "lead",
    });
    span.end();

    expect(Object.keys(exporter.getFinishedSpans()[0]?.attributes ?? {})).toEqual([
      "gen_ai.agent.name",
    ]);
  });

  it("keeps the content when content capture is on", () => {
    const span = providerWith(true).getTracer(MASTRA_SCOPE).startSpan("invoke_agent lead");
    span.setAttribute("mastra.agent_run.input", "Topic: tracing");
    span.end();

    expect(exporter.getFinishedSpans()[0]?.attributes["mastra.agent_run.input"]).toBe(
      "Topic: tracing",
    );
  });
});

describe("a Mastra run's cost comes from its chat spans", () => {
  function chatSpan(scope: string, planId: string, operation: string): void {
    const span = providerWith(false).getTracer(scope).startSpan(`${operation} gemma4:e2b`);
    span.setAttributes({
      [ATTR_PLAN_ID]: planId,
      "gen_ai.operation.name": operation,
      "gen_ai.request.model": "gemma4:e2b",
      "gen_ai.usage.input_tokens": 1000,
      "gen_ai.usage.output_tokens": 100,
    });
    span.end();
  }

  it("adds a Mastra chat span's cost to the run total", () => {
    chatSpan(MASTRA_SCOPE, "plan-cost-1", "chat");

    const cost = exporter.getFinishedSpans()[0]?.attributes[ATTR_COST];
    expect(cost).toBeGreaterThan(0);
    expect(takeRunCostUsd("plan-cost-1")).toBe(cost);
  });

  it("does not add a chat span from another instrumentation, which the invoke_agent span covers", () => {
    chatSpan("ai", "plan-cost-2", "chat");

    expect(takeRunCostUsd("plan-cost-2")).toBe(0);
  });
});
