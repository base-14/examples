/**
 * Middleware behaviour: retry, fallback, content-capture gating and pricing,
 * asserted against the in-memory span and metric exporters.
 */
import { SpanKind, SpanStatusCode } from "@opentelemetry/api";
import { afterAll, afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { withFallback, withSemconv } from "../../src/llm/middleware.ts";
import {
  findSpan,
  histogramBoundaries,
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

const RESPONSE: MockResponse = {
  content: "Answer text",
  input_tokens: 100,
  output_tokens: 50,
  model: "claude-sonnet-4",
  response_id: "msg_1",
  finish_reason: "end_turn",
};

const CAPTURE_ENV = "OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT";

beforeEach(() => {
  resetTelemetry();
  delete process.env[CAPTURE_ENV];
});

afterEach(() => {
  vi.useRealTimers();
  delete process.env[CAPTURE_ENV];
});

afterAll(async () => {
  await shutdownTelemetry();
});

describe("withSemconv", () => {
  it("names the span `chat {model}` and gives it CLIENT kind", async () => {
    const model = withSemconv(
      stubModel("claude-sonnet-4", async () => generateResult(RESPONSE)),
      ANTHROPIC_TARGET,
      { inputCostPerMToken: 3, outputCostPerMToken: 15 },
    );

    await model.doGenerate(generateParams("Hello", "Be brief.", { temperature: 0.2 }));

    const span = findSpan("chat claude-sonnet-4");
    expect(span.kind).toBe(SpanKind.CLIENT);
    expect(span.attributes["gen_ai.operation.name"]).toBe("chat");
    expect(span.attributes["gen_ai.provider.name"]).toBe("anthropic");
    expect(span.attributes["server.port"]).toBe(443);
    expect(span.attributes["gen_ai.request.temperature"]).toBe(0.2);
    expect(span.attributes["base14.gen_ai.cost_usd"]).toBeCloseTo(0.00105, 8);
  });

  it("costs an unknown model at zero rather than failing", async () => {
    const model = withSemconv(
      stubModel("qwen3.5:9B", async () => generateResult({ ...RESPONSE, model: "qwen3.5:9B" })),
      { semconvName: "ollama", serverAddress: "localhost", serverPort: 11434 },
      { inputCostPerMToken: 0, outputCostPerMToken: 0 },
    );

    await model.doGenerate(generateParams("Hello"));

    const span = findSpan("chat qwen3.5:9B");
    expect(span.attributes["base14.gen_ai.cost_usd"]).toBe(0);
    expect(span.attributes["server.port"]).toBe(11434);
  });

  it("emits no content event while capture is off", async () => {
    const model = withSemconv(
      stubModel("claude-sonnet-4", async () => generateResult(RESPONSE)),
      ANTHROPIC_TARGET,
    );

    await model.doGenerate(generateParams("Hello", "Be brief."));

    expect(findSpan("chat claude-sonnet-4").events).toEqual([]);
  });

  it("emits one scrubbed inference event when capture is on", async () => {
    process.env[CAPTURE_ENV] = "true";
    const model = withSemconv(
      stubModel("claude-sonnet-4", async () =>
        generateResult({ ...RESPONSE, content: "Reach me at reply@example.com" }),
      ),
      ANTHROPIC_TARGET,
    );

    await model.doGenerate(generateParams("Email owner@example.com", "Be brief."));

    const events = findSpan("chat claude-sonnet-4").events;
    expect(events.map((e) => e.name)).toEqual(["gen_ai.client.inference.operation.details"]);
    expect(events[0]?.attributes?.["gen_ai.input.messages"]).toBe("Email [EMAIL]");
    expect(events[0]?.attributes?.["gen_ai.output.messages"]).toBe("Reach me at [EMAIL]");
    expect(events[0]?.attributes?.["gen_ai.system_instructions"]).toBe("Be brief.");
  });

  it("omits system instructions when there is no system prompt", async () => {
    process.env[CAPTURE_ENV] = "true";
    const model = withSemconv(
      stubModel("claude-sonnet-4", async () => generateResult(RESPONSE)),
      ANTHROPIC_TARGET,
    );

    await model.doGenerate(generateParams("Hello"));

    const event = findSpan("chat claude-sonnet-4").events[0];
    expect(event?.attributes?.["gen_ai.system_instructions"]).toBeUndefined();
  });

  it("retries three times in total and then fails the span", async () => {
    vi.useFakeTimers();
    const doGenerate = vi.fn().mockRejectedValue(new Error("permanent failure"));
    const model = withSemconv(stubModel("claude-sonnet-4", doGenerate), ANTHROPIC_TARGET);

    const promise = model.doGenerate(generateParams("Hello"));
    const rejects = expect(promise).rejects.toThrow("permanent failure");
    await vi.runAllTimersAsync();
    await rejects;

    expect(doGenerate).toHaveBeenCalledTimes(3);

    const span = findSpan("chat claude-sonnet-4");
    expect(span.status.code).toBe(SpanStatusCode.ERROR);
    expect(span.attributes["error.type"]).toBe("Error");
    expect(await metricTotal("base14.gen_ai.retry.count", {})).toBe(2);
    expect(await metricTotal("base14.gen_ai.error.count", { "error.type": "Error" })).toBe(1);

    const failedAttrs = {
      "gen_ai.operation.name": "chat",
      "gen_ai.provider.name": "anthropic",
      "gen_ai.request.model": "claude-sonnet-4",
      "error.type": "Error",
    };
    for (const name of [
      "gen_ai.client.inference.operation.input_tokens",
      "gen_ai.client.inference.operation.output_tokens",
      "gen_ai.client.inference.duration",
    ]) {
      expect(await metricCount(name, failedAttrs)).toBe(1);
    }
    expect(await metricTotal("gen_ai.client.inference.operation.input_tokens", failedAttrs)).toBe(
      0,
    );
    expect(await metricTotal("gen_ai.client.inference.operation.output_tokens", failedAttrs)).toBe(
      0,
    );
  });

  it("records inference tokens and duration with the spec attributes and buckets", async () => {
    const model = withSemconv(
      stubModel("claude-haiku-4", async () => generateResult(RESPONSE)),
      ANTHROPIC_TARGET,
    );

    await model.doGenerate(generateParams("Hello"));

    const attrs = {
      "gen_ai.operation.name": "chat",
      "gen_ai.provider.name": "anthropic",
      "gen_ai.request.model": "claude-haiku-4",
    };
    expect(await metricTotal("gen_ai.client.inference.operation.input_tokens", attrs)).toBe(100);
    expect(await metricTotal("gen_ai.client.inference.operation.output_tokens", attrs)).toBe(50);
    expect(await metricCount("gen_ai.client.inference.duration", attrs)).toBe(1);
    expect(await metricCount("gen_ai.client.operation.duration", attrs)).toBe(0);
    expect(await metricCount("gen_ai.client.token.usage", {})).toBe(0);

    const tokenBuckets = [
      1, 4, 16, 64, 256, 1024, 4096, 16384, 65536, 262144, 1048576, 4194304, 16777216, 67108864,
    ];
    expect(await histogramBoundaries("gen_ai.client.inference.operation.input_tokens")).toEqual(
      tokenBuckets,
    );
    expect(await histogramBoundaries("gen_ai.client.inference.operation.output_tokens")).toEqual(
      tokenBuckets,
    );
    expect(await histogramBoundaries("gen_ai.client.inference.duration")).toEqual([
      0.01, 0.02, 0.04, 0.08, 0.16, 0.32, 0.64, 1.28, 2.56, 5.12, 10.24, 20.48, 40.96, 81.92,
    ]);
  });
});

describe("withFallback", () => {
  it("returns the primary result and leaves the caller span untouched", async () => {
    const fallbackDoGenerate = vi.fn();
    const model = withFallback(
      withSemconv(
        stubModel("claude-sonnet-4", async () => generateResult(RESPONSE)),
        ANTHROPIC_TARGET,
      ),
      ANTHROPIC_TARGET,
      stubModel("gpt-4.1-mini", fallbackDoGenerate),
      OPENAI_TARGET,
    );

    await model.doGenerate(generateParams("Hello"));

    expect(fallbackDoGenerate).not.toHaveBeenCalled();
    expect(await metricTotal("base14.gen_ai.fallback.count", {})).toBe(0);
  });
});
