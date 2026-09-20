import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { thinkingOff } from "../../src/llm/thinking-off.ts";

const originalFetch = globalThis.fetch;

function sentInit(): RequestInit & { timeout?: boolean } {
  return vi.mocked(globalThis.fetch).mock.calls.at(-1)?.[1] as RequestInit & { timeout?: boolean };
}

function sentBody(): Record<string, unknown> {
  return JSON.parse(String(sentInit().body));
}

describe("thinkingOff", () => {
  beforeEach(() => {
    globalThis.fetch = vi.fn().mockResolvedValue(new Response("{}")) as unknown as typeof fetch;
  });

  afterEach(() => {
    globalThis.fetch = originalFetch;
  });

  it("disables thinking on a responses request", async () => {
    await thinkingOff("http://localhost:11434/v1/responses", {
      method: "POST",
      body: JSON.stringify({ model: "qwen3.5:9B", input: "hello" }),
    });

    expect(sentBody().reasoning).toEqual({ effort: "none" });
    expect(sentBody().reasoning_effort).toBeUndefined();
  });

  it("disables thinking on a chat completions request", async () => {
    await thinkingOff("http://localhost:11434/v1/chat/completions", {
      method: "POST",
      body: JSON.stringify({ model: "qwen3.5:9B", messages: [] }),
    });

    expect(sentBody().reasoning_effort).toBe("none");
    expect(sentBody().reasoning).toBeUndefined();
  });

  it("keeps the rest of the body intact", async () => {
    await thinkingOff("http://localhost:11434/v1/responses", {
      method: "POST",
      body: JSON.stringify({ model: "qwen3.5:9B", max_output_tokens: 8000 }),
    });

    const body = sentBody();
    expect(body.model).toBe("qwen3.5:9B");
    expect(body.max_output_tokens).toBe(8000);
  });

  it("leaves an embeddings request alone", async () => {
    await thinkingOff("http://localhost:11434/v1/embeddings", {
      method: "POST",
      body: JSON.stringify({ model: "embeddinggemma", input: ["a"] }),
    });

    expect(sentBody().reasoning_effort).toBeUndefined();
    expect(sentBody().reasoning).toBeUndefined();
    expect(sentInit().timeout).toBe(false);
  });

  it("turns off Bun's fetch timeout on a chat request", async () => {
    await thinkingOff("http://localhost:11434/v1/responses", {
      method: "POST",
      body: JSON.stringify({ model: "qwen3.5:9B", input: "hello" }),
    });

    expect(sentInit().timeout).toBe(false);
  });

  it("passes a non-string body through untouched", async () => {
    const body = new Uint8Array([1, 2, 3]);

    await thinkingOff("http://localhost:11434/v1/responses", { method: "POST", body });

    expect(vi.mocked(globalThis.fetch).mock.calls.at(-1)?.[1]?.body).toBe(body);
  });

  it("passes a body that is not JSON through untouched", async () => {
    await thinkingOff("http://localhost:11434/v1/responses", {
      method: "POST",
      body: "not json",
    });

    expect(sentInit().body).toBe("not json");
    expect(sentInit().timeout).toBe(false);
  });
});
