/**
 * Middleware behavioral tests — retry, fallback, error propagation.
 *
 * OTel is a no-op here (SDK not registered in test env). We verify behavior
 * via mock call counts and return values, not span/metric internals.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("@opentelemetry/api", () => {
  const span = {
    setAttribute: vi.fn(),
    addEvent: vi.fn(),
    recordException: vi.fn(),
    setStatus: vi.fn(),
    end: vi.fn(),
    spanContext: vi.fn().mockReturnValue({ traceId: "test-trace" }),
  };
  const instrument = { record: vi.fn(), add: vi.fn() };
  const meter = {
    createHistogram: vi.fn(() => instrument),
    createCounter: vi.fn(() => instrument),
  };
  return {
    trace: {
      getTracer: vi.fn(() => ({
        startActiveSpan: (_name: string, fn: (s: typeof span) => unknown) => fn(span),
      })),
    },
    metrics: { getMeter: vi.fn(() => meter) },
    SpanStatusCode: { OK: 1, ERROR: 2 },
  };
});

import { createSemconvMiddleware, withFallback, withSemconv } from "../../src/llm/middleware.ts";

// Minimal success result matching LanguageModelV3GenerateResult shape
function makeSuccessResult(text = "Result text") {
  return {
    content: [{ type: "text" as const, text }],
    finishReason: { unified: "stop", raw: "stop" },
    usage: {
      inputTokens: { total: 100 },
      outputTokens: { total: 50 },
    },
    response: { modelId: "test-model", id: "resp-123" },
  };
}

// biome-ignore lint/suspicious/noExplicitAny: minimal mock avoids full LanguageModelV3 shape
function makeModel(modelId = "test-model", doGenerate?: () => Promise<unknown>): any {
  return {
    specificationVersion: "v3",
    provider: "test",
    modelId,
    defaultObjectGenerationMode: undefined,
    supportedUrls: {},
    doGenerate: doGenerate ?? vi.fn().mockResolvedValue(makeSuccessResult()),
    doStream: vi.fn(),
  };
}

function callWrapGenerate(
  middleware: ReturnType<typeof createSemconvMiddleware>,
  doGenerate: () => Promise<unknown>,
) {
  // biome-ignore lint/suspicious/noExplicitAny: test helper avoids complex SDK types
  return (middleware.wrapGenerate as any)({
    doGenerate,
    doStream: vi.fn(),
    params: {
      prompt: [{ role: "user", content: [{ type: "text", text: "hello" }] }],
      inputFormat: "messages",
      mode: { type: "regular" },
    },
    model: makeModel(),
  });
}

describe("createSemconvMiddleware", () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("passes through a successful doGenerate result", async () => {
    const successResult = makeSuccessResult("hello");
    const doGenerate = vi.fn().mockResolvedValue(successResult);
    const middleware = createSemconvMiddleware("anthropic", "api.anthropic.com");

    const result = await callWrapGenerate(middleware, doGenerate);

    expect(result).toBe(successResult);
    expect(doGenerate).toHaveBeenCalledOnce();
  });

  it("retries on transient failure and returns the eventual success", async () => {
    const successResult = makeSuccessResult();
    const doGenerate = vi
      .fn()
      .mockRejectedValueOnce(new Error("transient"))
      .mockRejectedValueOnce(new Error("transient"))
      .mockResolvedValueOnce(successResult);
    const middleware = createSemconvMiddleware("anthropic", "api.anthropic.com");

    const promise = callWrapGenerate(middleware, doGenerate);

    // Advance timers to skip exponential backoff delays
    await vi.runAllTimersAsync();
    const result = await promise;

    expect(result).toBe(successResult);
    // 1 initial attempt + 2 retries = 3 total calls
    expect(doGenerate).toHaveBeenCalledTimes(3);
  });

  it("throws after exhausting all retries (3 attempts total)", async () => {
    const doGenerate = vi.fn().mockRejectedValue(new Error("permanent failure"));
    const middleware = createSemconvMiddleware("anthropic", "api.anthropic.com");

    const promise = callWrapGenerate(middleware, doGenerate);
    // Attach rejection handler before advancing timers to prevent unhandled rejection
    const assertion = expect(promise).rejects.toThrow("permanent failure");

    await vi.runAllTimersAsync();
    await assertion;

    expect(doGenerate).toHaveBeenCalledTimes(3);
  });
});

describe("withFallback", () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("calls fallback model when primary exhausts all retries", async () => {
    const fallbackResult = makeSuccessResult("from fallback");
    const primaryDoGenerate = vi.fn().mockRejectedValue(new Error("primary down"));
    const fallbackDoGenerate = vi.fn().mockResolvedValue(fallbackResult);

    const primaryModel = makeModel("primary", primaryDoGenerate);
    const fallbackModel = makeModel("fallback", fallbackDoGenerate);

    const wrappedPrimary = withSemconv(primaryModel, "anthropic", "api.anthropic.com");
    const wrappedFallback = withSemconv(fallbackModel, "openai", "api.openai.com");
    const modelWithFallback = withFallback(wrappedPrimary, "anthropic", wrappedFallback);

    // biome-ignore lint/suspicious/noExplicitAny: test-only call
    const promise = (modelWithFallback.doGenerate as any)({
      prompt: [{ role: "user", content: [{ type: "text", text: "hello" }] }],
      inputFormat: "messages",
      mode: { type: "regular" },
    });
    await vi.runAllTimersAsync();
    const result = await promise;

    expect(result).toBe(fallbackResult);
    expect(fallbackDoGenerate).toHaveBeenCalledOnce();
    // Primary was retried 3 times before giving up
    expect(primaryDoGenerate).toHaveBeenCalledTimes(3);
  });

  it("returns primary result when primary succeeds without fallback", async () => {
    const primaryResult = makeSuccessResult("from primary");
    const primaryDoGenerate = vi.fn().mockResolvedValue(primaryResult);
    const fallbackDoGenerate = vi.fn();

    const primaryModel = makeModel("primary", primaryDoGenerate);
    const fallbackModel = makeModel("fallback", fallbackDoGenerate);

    const wrappedPrimary = withSemconv(primaryModel, "anthropic", "api.anthropic.com");
    const wrappedFallback = withSemconv(fallbackModel, "openai", "api.openai.com");
    const modelWithFallback = withFallback(wrappedPrimary, "anthropic", wrappedFallback);

    // biome-ignore lint/suspicious/noExplicitAny: test-only call
    const promise = (modelWithFallback.doGenerate as any)({
      prompt: [{ role: "user", content: [{ type: "text", text: "hello" }] }],
      inputFormat: "messages",
      mode: { type: "regular" },
    });
    await vi.runAllTimersAsync();
    const result = await promise;

    expect(result).toBe(primaryResult);
    expect(fallbackDoGenerate).not.toHaveBeenCalled();
  });
});
