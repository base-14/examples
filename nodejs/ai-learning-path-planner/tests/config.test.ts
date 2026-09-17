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

// F2. ollama-ai-provider-v2 builds request URLs as `${baseURL}${path}`, and its own
// default already ends in /api. A base URL without that suffix sends every model call to
// /chat, which 404s.
// Ruling 35. The default is the host form, not the container form: host.docker.internal
// does not resolve on the host, while a container gets the value it needs from
// compose.yaml. Both then work with no .env at all.
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

// Ruling 39. The floor is fixed, and it is not a ratio against the largest prompt anyone
// has happened to see. A sampled maximum is not a bound: it only ever grows, so a rule of
// the form "num_ctx must exceed the peak by half again" is guaranteed to read as broken the
// next time somebody measures, which is how this test got here. The observed peak is
// recorded in src/config.ts as an observation with the runs behind it and asserted on by
// nothing.
//
// 16384 is four times Ollama's own 4096 default, which was measurably too small, and it is
// the largest window that keeps qwen3.5:9B inside a 16 GB machine (5.91 GB against 6.47 GB
// at 32768). Lower it only if the VRAM budget changes, and raise it only on a measured
// overrun, which Ollama reports as done_reason "length" and the service surfaces as "No
// output generated" - not because a bigger number was observed in a sample.
const CONTEXT_WINDOW_FLOOR_TOKENS = 16384;

const OLLAMA_OWN_DEFAULT_NUM_CTX = 4096;

describe("loadConfig: the Ollama context window", () => {
  it("defaults to at least the floor a fan-out run was measured to need", () => {
    const numCtx = loadConfig({}).ollamaNumCtx;

    expect(numCtx).toBeGreaterThanOrEqual(CONTEXT_WINDOW_FLOOR_TOKENS);
    expect(numCtx).toBeGreaterThan(OLLAMA_OWN_DEFAULT_NUM_CTX);
  });

  it("is a number the provider can send, not a string off the environment", () => {
    expect(loadConfig({ OLLAMA_NUM_CTX: "8192" }).ollamaNumCtx).toBe(8192);
  });
});

// F3. Zod's .optional() treats an empty string as a present value, so PRICE_MODEL= (the
// value compose.yaml and .env.example both ship) reached assertPriceModelIsKnown as the
// literal empty string and threw at boot.
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

// F5. costOf returns zero with simulated: true when nothing names a price row, so the
// shipped configuration reported a cost of zero on an example whose subject is cost per
// completed task.
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
