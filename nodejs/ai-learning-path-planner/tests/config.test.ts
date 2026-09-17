import { describe, expect, it } from "vitest";
import { loadConfig } from "../src/config.ts";
import { costOf } from "../src/llm/cost.ts";

describe("loadConfig", () => {
  it("returns the documented default for every unset variable", () => {
    const config = loadConfig({});

    expect(config.port).toBe(3000);
    expect(config.llmProvider).toBe("ollama");
    expect(config.ollamaBaseUrl).toBe("http://localhost:11434/api");
    expect(config.ollamaNumCtx).toBe(16384);
    expect(config.modelSmall).toBe("gemma4:e2b");
    expect(config.modelLarge).toBe("qwen3.5:9B");
    // Not undefined: the Ollama path borrows a price row so an unconfigured run still
    // reports a cost. See the PRICE_MODEL block below.
    expect(config.priceModel).toBe("gpt-5-nano");
    expect(config.toolCatalogue).toBe("deferred");
    expect(config.maxSubtopics).toBe(8);
    expect(config.maxEscalations).toBe(2);
    expect(config.allowHostedProvider).toBe(false);
    expect(config.captureMessageContent).toBe(false);
  });

  it("reads every variable from the environment it is given, not from process.env", () => {
    const config = loadConfig({
      PORT: "8080",
      LLM_PROVIDER: "anthropic",
      OLLAMA_BASE_URL: "http://example.internal:11434/api",
      OLLAMA_NUM_CTX: "8192",
      MODEL_SMALL: "small-model",
      MODEL_LARGE: "large-model",
      PRICE_MODEL: "gpt-4o",
      TOOL_CATALOGUE: "full",
      MAX_SUBTOPICS: "4",
      MAX_ESCALATIONS: "1",
      ALLOW_HOSTED_PROVIDER: "true",
      OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT: "true",
    });

    expect(config).toEqual({
      port: 8080,
      llmProvider: "anthropic",
      ollamaBaseUrl: "http://example.internal:11434/api",
      ollamaNumCtx: 8192,
      modelSmall: "small-model",
      modelLarge: "large-model",
      priceModel: "gpt-4o",
      toolCatalogue: "full",
      maxSubtopics: 4,
      maxEscalations: 1,
      allowHostedProvider: true,
      captureMessageContent: true,
    });
  });

  it("rejects an unknown LLM_PROVIDER", () => {
    expect(() => loadConfig({ LLM_PROVIDER: "bogus" })).toThrow(/llmProvider/);
  });
});

// The provider builds request URLs as `${baseURL}${path}`, so a base URL without the /api
// suffix sends every model call to /chat, which 404s. The default is the host form;
// compose.yaml gives a container the value it needs.
describe("loadConfig: the Ollama base URL", () => {
  it("defaults to a base URL the provider can append its paths to", () => {
    expect(loadConfig({}).ollamaBaseUrl).toBe("http://localhost:11434/api");
  });

  it("keeps the /api suffix the provider needs on the shipped default", () => {
    expect(loadConfig({}).ollamaBaseUrl.endsWith("/api")).toBe(true);
  });

  it("names a host the service can resolve when it is not in a container", () => {
    expect(loadConfig({}).ollamaBaseUrl).not.toContain("host.docker.internal");
  });
});

// A fixed floor, not a ratio against the largest prompt anyone has seen: a sampled maximum
// only ever grows, so such a rule reads as broken the next time somebody measures. 16384 is
// four times Ollama's own default, which is too small, and the largest window that keeps
// qwen3.5:9B inside a 16 GB machine. Raise it on an overrun, not on a bigger sample.
const CONTEXT_WINDOW_FLOOR_TOKENS = 16384;

const OLLAMA_OWN_DEFAULT_NUM_CTX = 4096;

describe("loadConfig: the Ollama context window", () => {
  it("defaults to at least the floor a fan-out run needs", () => {
    const numCtx = loadConfig({}).ollamaNumCtx;

    expect(numCtx).toBeGreaterThanOrEqual(CONTEXT_WINDOW_FLOOR_TOKENS);
    expect(numCtx).toBeGreaterThan(OLLAMA_OWN_DEFAULT_NUM_CTX);
  });

  it("is a number the provider can send, not a string off the environment", () => {
    expect(loadConfig({ OLLAMA_NUM_CTX: "8192" }).ollamaNumCtx).toBe(8192);
  });
});

// Zod's .optional() treats an empty string as present, so PRICE_MODEL= -- the value
// compose.yaml and .env.example both ship -- reaches assertPriceModelIsKnown as "" and throws.
describe("loadConfig: an empty variable is an unset variable", () => {
  it("does not read PRICE_MODEL= as a price model named the empty string", () => {
    expect(loadConfig({ PRICE_MODEL: "" }).priceModel).not.toBe("");
  });

  it("falls back to the documented default for every variable set to the empty string", () => {
    const config = loadConfig({
      PORT: "",
      LLM_PROVIDER: "",
      OLLAMA_BASE_URL: "",
      MODEL_SMALL: "",
      MODEL_LARGE: "",
      TOOL_CATALOGUE: "",
      MAX_SUBTOPICS: "",
      MAX_ESCALATIONS: "",
      OLLAMA_NUM_CTX: "",
      ALLOW_HOSTED_PROVIDER: "",
      OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT: "",
    });

    expect(config).toEqual(loadConfig({}));
  });
});

// costOf returns zero with simulated: true when nothing names a price row, which would leave
// the shipped configuration reporting no cost on an example about cost.
describe("loadConfig: PRICE_MODEL on the Ollama path", () => {
  // The claim is that an unconfigured run reports a cost, not that some string is
  // present, so this prices a local model's token counts through the resolved default and
  // asserts the number that comes out. A PRICE_MODEL naming a row that is not in
  // _shared/pricing.json throws here rather than passing a toBeDefined().
  it("names a price row by default, so an unconfigured run still reports a cost", () => {
    const config = loadConfig({});
    const cost = costOf(
      {
        inputTokens: 1000,
        inputTokenDetails: {
          noCacheTokens: 1000,
          cacheReadTokens: 0,
          cacheWriteTokens: undefined,
        },
        outputTokens: 500,
        outputTokenDetails: { textTokens: 500, reasoningTokens: undefined },
        totalTokens: 1500,
      },
      config.modelSmall,
      config,
    );

    expect(cost.usd).toBeGreaterThan(0);
    expect(cost.simulated).toBe(true);
  });

  it("leaves PRICE_MODEL unset on a hosted provider, which prices its own models", () => {
    expect(loadConfig({ LLM_PROVIDER: "openai" }).priceModel).toBeUndefined();
  });

  it("still lets PRICE_MODEL be set explicitly", () => {
    expect(loadConfig({ PRICE_MODEL: "gpt-4o" }).priceModel).toBe("gpt-4o");
  });
});
