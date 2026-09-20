/** A LanguageModelV3 stub whose `doGenerate` the tests drive directly. */
import type { LanguageModelV3 } from "@ai-sdk/provider";
import type { ProviderTarget } from "../../src/llm/provider-target.ts";

export const ANTHROPIC_TARGET: ProviderTarget = {
  semconvName: "anthropic",
  serverAddress: "api.anthropic.com",
  serverPort: 443,
};

export const OPENAI_TARGET: ProviderTarget = {
  semconvName: "openai",
  serverAddress: "api.openai.com",
  serverPort: 443,
};

export interface MockResponse {
  content: string;
  input_tokens: number;
  output_tokens: number;
  model: string;
  response_id: string;
  finish_reason: string;
}

export function generateResult(mock: MockResponse) {
  return {
    content: [{ type: "text" as const, text: mock.content }],
    finishReason: { unified: mock.finish_reason, raw: mock.finish_reason },
    usage: {
      inputTokens: { total: mock.input_tokens },
      outputTokens: { total: mock.output_tokens },
    },
    response: { modelId: mock.model, id: mock.response_id },
    warnings: [],
  };
}

export function stubModel(modelId: string, doGenerate: () => Promise<unknown>): LanguageModelV3 {
  return {
    specificationVersion: "v3",
    provider: "test",
    modelId,
    supportedUrls: {},
    doGenerate,
    doStream: async () => {
      throw new Error("streaming is not used in these tests");
    },
  } as unknown as LanguageModelV3;
}

export function generateParams(
  prompt: string,
  system?: string,
  options?: { temperature?: number; maxOutputTokens?: number },
) {
  const messages: Array<Record<string, unknown>> = [];
  if (system) messages.push({ role: "system", content: system });
  messages.push({ role: "user", content: [{ type: "text", text: prompt }] });
  return {
    prompt: messages,
    temperature: options?.temperature,
    maxOutputTokens: options?.maxOutputTokens,
    // biome-ignore lint/suspicious/noExplicitAny: the stub only needs the fields the middleware reads
  } as any;
}
