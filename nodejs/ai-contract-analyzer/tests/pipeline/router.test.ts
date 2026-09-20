import { readFileSync } from "node:fs";
import { describe, expect, it, vi } from "vitest";

vi.mock("../../src/providers.ts", () => ({
  getFastModel: vi.fn().mockReturnValue({
    model: "mock-fast-model",
    inputCostPerMToken: 0.8,
    outputCostPerMToken: 4,
  }),
}));

vi.mock("ai", () => ({
  Output: { object: (opts: unknown) => opts },
  generateText: vi.fn().mockResolvedValue({
    output: {
      document_type: "nda",
      complexity: "standard",
      requires_full_analysis: true,
    },
    usage: { inputTokens: 500, outputTokens: 30 },
  }),
}));

import { routeDocument } from "../../src/pipeline/route.ts";

describe("routeDocument", () => {
  it("returns route result with document_type, complexity, and cost", async () => {
    const result = await routeDocument("This Non-Disclosure Agreement is entered into...");

    expect(result.document_type).toBe("nda");
    expect(result.complexity).toBe("standard");
    expect(result.requires_full_analysis).toBe(true);
    expect(result.input_tokens).toBe(500);
    expect(result.cost_usd).toBeGreaterThan(0);
  });

  it("only passes the first 3000 chars to the model", async () => {
    const { generateText } = await import("ai");
    const longText = "x".repeat(10_000);

    await routeDocument(longText);

    const call = vi.mocked(generateText).mock.calls.at(-1)?.[0] as { prompt: string };
    expect(call.prompt.length).toBe(3000);
  });

  it("uses fast model for cost efficiency", async () => {
    const { getFastModel } = await import("../../src/providers.ts");

    await routeDocument("contract text");

    expect(vi.mocked(getFastModel)).toHaveBeenCalled();
  });
});

describe("routeDocument classifier prompt", () => {
  async function lastSystemPrompt(): Promise<string> {
    const { generateText } = await import("ai");
    const call = vi.mocked(generateText).mock.calls.at(-1)?.[0] as unknown as { system: string };
    return call.system;
  }

  it("defines every contract type the schema accepts", async () => {
    await routeDocument("contract text");
    const system = await lastSystemPrompt();

    for (const type of ["nda", "employment", "service_agreement", "lease", "partnership"]) {
      expect(system).toContain(`${type}:`);
    }
  });

  it("reserves unknown for text that is not a contract", async () => {
    await routeDocument("contract text");
    const system = await lastSystemPrompt();

    expect(system).toContain('Use "unknown" only when the text is not a contract');
    expect(system).not.toContain("if in doubt about document type");
  });

  it("asks for the single best match rather than a conservative one", async () => {
    await routeDocument("contract text");
    const system = await lastSystemPrompt();

    expect(system).toContain("single document type that best matches");
    expect(system).toContain("Always pick the closest of the five contract types");
  });
});

describe("routeDocument on the shipped sample", () => {
  const samplePath = new URL("../../data/contracts/sample-nda.txt", import.meta.url).pathname;

  it("classifies data/contracts/sample-nda.txt as an nda", async () => {
    const result = await routeDocument(readFileSync(samplePath, "utf8"));

    expect(result.document_type).toBe("nda");
  });

  it("sends the sample's heading to the classifier", async () => {
    const { generateText } = await import("ai");

    await routeDocument(readFileSync(samplePath, "utf8"));

    const call = vi.mocked(generateText).mock.calls.at(-1)?.[0] as unknown as { prompt: string };
    expect(call.prompt).toContain("NON-DISCLOSURE AGREEMENT");
  });
});
