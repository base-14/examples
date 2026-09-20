/**
 * The shared LLM gateway test vectors, driven through this example's model
 * wrappers and asserted against the in-memory span and metric exporters.
 *
 * The vectors name the failure class `Exception`, which is Python's base class.
 * The error class below carries the same name so `error.type` matches the
 * vector verbatim in both languages.
 */
import { readFileSync } from "node:fs";
import { SpanKind, SpanStatusCode, trace } from "@opentelemetry/api";
import { afterAll, beforeEach, describe, expect, it, vi } from "vitest";
import { withFallback, withSemconv } from "../../src/llm/middleware.ts";
import { modelPricing } from "../../src/llm/pricing.ts";
import {
  findSpan,
  metricCount,
  metricTotal,
  resetTelemetry,
  shutdownTelemetry,
} from "../telemetry.ts";
import {
  ANTHROPIC_TARGET,
  generateParams,
  generateResult,
  type MockResponse,
  OPENAI_TARGET,
  stubModel,
} from "./model-stub.ts";

class Exception extends Error {}

const CAPTURE_ENV = "OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT";

// biome-ignore lint/suspicious/noExplicitAny: vector files are free-form JSON
function loadVector(name: string): any {
  const path = new URL(`../../../../_shared/test-vectors/${name}`, import.meta.url).pathname;
  return JSON.parse(readFileSync(path, "utf-8"));
}

function anthropicModel(modelId: string, doGenerate: () => Promise<unknown>) {
  return withSemconv(stubModel(modelId, doGenerate), ANTHROPIC_TARGET, modelPricing(modelId));
}

function openaiModel(modelId: string, doGenerate: () => Promise<unknown>) {
  return withSemconv(stubModel(modelId, doGenerate), OPENAI_TARGET, modelPricing(modelId));
}

/** Cumulative totals the assertions below compare before and after a call. */
// biome-ignore lint/suspicious/noExplicitAny: vector metrics are free-form JSON
async function absentTotals(notExpected: any[]): Promise<number[]> {
  return Promise.all(notExpected.map((m) => metricTotal(m.metric, {})));
}

async function metricSnapshot(
  modelAttrs: Record<string, string>,
  // biome-ignore lint/suspicious/noExplicitAny: vector metrics are free-form JSON
  notExpected: any[],
) {
  return {
    inputTokens: await metricTotal("gen_ai.client.token.usage", {
      ...modelAttrs,
      "gen_ai.token.type": "input",
    }),
    outputTokens: await metricTotal("gen_ai.client.token.usage", {
      ...modelAttrs,
      "gen_ai.token.type": "output",
    }),
    durationCount: await metricCount("gen_ai.client.operation.duration", modelAttrs),
    cost: await metricTotal("base14.gen_ai.cost", modelAttrs),
    absent: await absentTotals(notExpected),
  };
}

beforeEach(() => {
  resetTelemetry();
  delete process.env[CAPTURE_ENV];
});

afterAll(async () => {
  await shutdownTelemetry();
});

describe("_shared/test-vectors/chat-completion.json", () => {
  const vector = loadVector("chat-completion.json");
  const request = vector.input;
  const mock: MockResponse = vector.mock_response;
  const expected = vector.expected_span;

  it("records the span attributes and metrics the vector expects", async () => {
    const model = anthropicModel(request.model, async () => generateResult(mock));
    const modelAttrs = { "gen_ai.request.model": request.model };
    const before = await metricSnapshot(modelAttrs, vector.not_expected);

    await model.doGenerate(
      generateParams(request.prompt, request.system, {
        temperature: request.temperature,
        maxOutputTokens: request.max_tokens,
      }),
    );

    const span = findSpan(expected.name);
    expect(span.kind).toBe(SpanKind.CLIENT);
    expect(span.status.code).not.toBe(SpanStatusCode.ERROR);

    for (const [key, value] of Object.entries(expected.attributes)) {
      if (key === "base14.gen_ai.cost_usd") {
        expect(span.attributes[key]).toBeCloseTo(value as number, 8);
      } else {
        expect(span.attributes[key]).toEqual(value);
      }
    }

    // Content capture is off, so the inference event is not expected here.
    expect(span.events).toEqual([]);

    const after = await metricSnapshot(modelAttrs, vector.not_expected);
    expect(after.inputTokens - before.inputTokens).toBe(mock.input_tokens);
    expect(after.outputTokens - before.outputTokens).toBe(mock.output_tokens);
    expect(after.durationCount - before.durationCount).toBe(1);
    expect(after.cost - before.cost).toBeCloseTo(expected.attributes["base14.gen_ai.cost_usd"], 8);
    expect(after.absent).toEqual(before.absent);
  });

  it("emits the inference event when content capture is on", async () => {
    process.env[CAPTURE_ENV] = "true";
    const model = anthropicModel(request.model, async () => generateResult(mock));

    await model.doGenerate(generateParams(request.prompt, request.system));

    const span = findSpan(expected.name);
    expect(span.events.map((e) => e.name)).toEqual([expected.events[0].name]);

    const attributes = span.events[0]?.attributes ?? {};
    expect(attributes["gen_ai.input.messages"]).toBe(request.prompt);
    expect(attributes["gen_ai.system_instructions"]).toBe(request.system);
    expect(attributes["gen_ai.output.messages"]).toBe(mock.content);
  });
});

describe("_shared/test-vectors/chat-with-retry.json", () => {
  const vector = loadVector("chat-with-retry.json");
  const setup = vector.setup;
  const success: MockResponse = vector.mock_behavior.attempt_2;
  const expected = vector.expected_span;
  const retryMetric = vector.expected_metrics.find(
    // biome-ignore lint/suspicious/noExplicitAny: vector metrics are free-form JSON
    (m: any) => m.name === "base14.gen_ai.retry.count",
  );

  it("keeps the span OK and counts one retry", async () => {
    const retriesBefore = await metricTotal("base14.gen_ai.retry.count", retryMetric.attrs);
    const absentBefore = await absentTotals(vector.not_expected);

    vi.useFakeTimers();
    const doGenerate = vi
      .fn()
      .mockRejectedValueOnce(new Exception("Rate limit"))
      .mockResolvedValueOnce(generateResult(success));
    const model = anthropicModel(setup.model, doGenerate);

    const promise = model.doGenerate(generateParams("Hello", "You are helpful."));
    await vi.runAllTimersAsync();
    await promise;
    vi.useRealTimers();

    const span = findSpan(expected.name);
    expect(span.status.code).not.toBe(SpanStatusCode.ERROR);
    for (const [key, value] of Object.entries(expected.attributes)) {
      expect(span.attributes[key]).toEqual(value);
    }

    expect(
      (await metricTotal("base14.gen_ai.retry.count", retryMetric.attrs)) - retriesBefore,
    ).toBe(retryMetric.value);
    expect(await absentTotals(vector.not_expected)).toEqual(absentBefore);
  });
});

describe("_shared/test-vectors/chat-with-fallback.json", () => {
  const vector = loadVector("chat-with-fallback.json");
  const setup = vector.setup;
  const fallbackMock: MockResponse = vector.mock_behavior.fallback;
  const [primaryExpected, fallbackExpected] = vector.expected_spans;
  const metricsByName = Object.fromEntries(
    // biome-ignore lint/suspicious/noExplicitAny: vector metrics are free-form JSON
    vector.expected_metrics.map((m: any) => [m.name, m]),
  );

  it("fails the primary span, succeeds on the fallback and records the switch", async () => {
    const retriesBefore = await metricTotal("base14.gen_ai.retry.count", {});
    const fallbacksBefore = await metricTotal(
      "base14.gen_ai.fallback.count",
      metricsByName["base14.gen_ai.fallback.count"].attrs,
    );
    const errorsBefore = await metricTotal(
      "base14.gen_ai.error.count",
      metricsByName["base14.gen_ai.error.count"].attrs,
    );
    const primaryTokensBefore = await metricTotal("gen_ai.client.token.usage", {
      "gen_ai.request.model": setup.primary_model,
    });

    vi.useFakeTimers();
    const primaryDoGenerate = vi.fn().mockRejectedValue(new Exception("Service unavailable"));
    const fallbackDoGenerate = vi.fn().mockResolvedValue(generateResult(fallbackMock));

    const model = withFallback(
      anthropicModel(setup.primary_model, primaryDoGenerate),
      ANTHROPIC_TARGET,
      openaiModel(setup.fallback_model, fallbackDoGenerate),
      OPENAI_TARGET,
    );

    const tracer = trace.getTracer("vectors-test");
    const promise = tracer.startActiveSpan("pipeline.run", async (parent) => {
      const result = await model.doGenerate(generateParams("Hello", "You are helpful."));
      parent.end();
      return result;
    });
    await vi.runAllTimersAsync();
    await promise;
    vi.useRealTimers();

    const primarySpan = findSpan(primaryExpected.name);
    expect(primarySpan.status.code).toBe(SpanStatusCode.ERROR);
    for (const [key, value] of Object.entries(primaryExpected.attributes)) {
      expect(primarySpan.attributes[key]).toEqual(value);
    }

    const fallbackSpan = findSpan(fallbackExpected.name);
    expect(fallbackSpan.status.code).not.toBe(SpanStatusCode.ERROR);
    for (const [key, value] of Object.entries(fallbackExpected.attributes)) {
      expect(fallbackSpan.attributes[key]).toEqual(value);
    }

    const parentSpan = findSpan("pipeline.run");
    expect(parentSpan.status.code).not.toBe(SpanStatusCode.ERROR);
    expect(parentSpan.attributes["gen_ai.fallback.triggered"]).toBe(true);
    const fallbackEvent = parentSpan.events.find((e) => e.name === "provider_fallback");
    expect(fallbackEvent?.attributes?.["base14.gen_ai.fallback.provider"]).toBe(
      setup.fallback_provider,
    );

    expect((await metricTotal("base14.gen_ai.retry.count", {})) - retriesBefore).toBe(
      metricsByName["base14.gen_ai.retry.count"].value,
    );
    expect(
      (await metricTotal(
        "base14.gen_ai.fallback.count",
        metricsByName["base14.gen_ai.fallback.count"].attrs,
      )) - fallbacksBefore,
    ).toBe(metricsByName["base14.gen_ai.fallback.count"].value);
    expect(
      (await metricTotal(
        "base14.gen_ai.error.count",
        metricsByName["base14.gen_ai.error.count"].attrs,
      )) - errorsBefore,
    ).toBe(metricsByName["base14.gen_ai.error.count"].value);

    // Token usage and cost belong to the provider that answered.
    expect(
      await metricTotal("gen_ai.client.token.usage", {
        "gen_ai.request.model": setup.fallback_model,
        "gen_ai.token.type": "input",
      }),
    ).toBe(fallbackMock.input_tokens);
    expect(
      await metricTotal("base14.gen_ai.cost", { "gen_ai.request.model": setup.fallback_model }),
    ).toBeGreaterThan(0);
    expect(
      await metricTotal("gen_ai.client.token.usage", {
        "gen_ai.request.model": setup.primary_model,
      }),
    ).toBe(primaryTokensBefore);
  });
});
