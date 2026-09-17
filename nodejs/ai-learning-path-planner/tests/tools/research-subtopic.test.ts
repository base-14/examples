import { describe, expect, it } from "vitest";
import type { Config } from "../../src/config.ts";
import type { CorpusArtifact } from "../../src/corpus/index-build.ts";
import { CorpusStore } from "../../src/corpus/store.ts";
import { SERVICE_GAP_REASONS, TEMPLATED_GAP_REASONS } from "../../src/plans/schema.ts";
import { newRunCounters, type RunCounters } from "../../src/telemetry/metrics.ts";
import {
  type Finding,
  type ResearchSubtopicResult,
  researchSubtopicTool,
} from "../../src/tools/research-subtopic.ts";

function baseConfig(overrides: Partial<Config> = {}): Config {
  return {
    port: 3000,
    llmProvider: "ollama",
    ollamaBaseUrl: "http://host.docker.internal:11434/api",
    ollamaNumCtx: 32768,
    modelSmall: "gemma4:e2b",
    modelLarge: "qwen3.5:9B",
    priceModel: undefined,
    toolCatalogue: "deferred",
    maxSubtopics: 8,
    maxEscalations: 2,
    allowHostedProvider: false,
    captureMessageContent: false,
    ...overrides,
  };
}

const artifact: CorpusArtifact = {
  catalogue: [
    {
      path: "docs/guides/tracing.md",
      area: "docs",
      title: "Tracing basics",
      description: "Introduction to distributed tracing.",
      keywords: ["tracing"],
      headings: ["What is a trace"],
    },
    {
      path: "docs/guides/metrics.md",
      area: "docs",
      title: "Metrics basics",
      description: "Introduction to metrics.",
      keywords: ["metrics"],
      headings: ["Counters and gauges"],
    },
  ],
  sections: [
    {
      path: "docs/guides/tracing.md",
      heading: "What is a trace",
      text: "A trace represents the end-to-end journey of a single request.",
    },
    {
      path: "docs/guides/metrics.md",
      heading: "Counters and gauges",
      text: "A counter only goes up; a gauge can go up or down.",
    },
  ],
};

const VALID: Finding = { path: "docs/guides/tracing.md", note: "Real path." };
const ALSO_VALID: Finding = { path: "docs/guides/metrics.md", note: "Also a real path." };
const INVENTED: Finding = { path: "docs/guides/does-not-exist.md", note: "Made up." };
const ALSO_INVENTED: Finding = { path: "docs/guides/nor-this-one.md", note: "Also made up." };

interface Built {
  tier: "small" | "large";
  subtopic: string;
}

// Drives the real tool with a stub researcher, so what is asserted is the tool's own
// arithmetic rather than a model's. Each tier returns the findings it is given, and every
// researcher the tool builds is recorded, which is what "a subtopic was researched" means.
function harness(
  findings: { small: Finding[]; large?: Finding[] },
  overrides: Partial<Config> = {},
  counters: RunCounters = newRunCounters(),
) {
  const built: Built[] = [];
  const tool = researchSubtopicTool({
    store: new CorpusStore(artifact),
    config: baseConfig(overrides),
    counters,
    buildResearcher: ({ subtopic, tier }) => {
      built.push({ subtopic, tier });
      return {
        generate: async () => ({
          output: { findings: tier === "small" ? findings.small : (findings.large ?? []) },
        }),
      };
    },
  });

  const call = async (subtopic: string): Promise<ResearchSubtopicResult> => {
    const execute = tool.execute;
    if (execute === undefined) throw new Error("research_subtopic has no execute");
    return (await execute(
      { subtopic },
      {
        toolCallId: `call-${built.length + 1}`,
        messages: [],
      },
    )) as ResearchSubtopicResult;
  };

  return { built, call, counters };
}

// Confidence is the fraction of a researcher's findings whose citation the store can
// validate, and it is the only thing that decides escalation. Nothing else in the suite
// supplies a mixed or an all-invalid findings set, so without these the filter in
// research() can be deleted and every other test stays green while a researcher that
// invents every path reports full confidence and is believed.
describe("research_subtopic: confidence comes from citation validation", () => {
  it("reports confidence 1 and does not escalate when every citation validates", async () => {
    const { built, call } = harness({ small: [VALID, ALSO_VALID] });

    const result = await call("tracing");

    expect(result.confidence).toBe(1);
    expect(result.escalated).toBe(false);
    expect(result.findings).toEqual([VALID, ALSO_VALID]);
    expect(built).toEqual([{ subtopic: "tracing", tier: "small" }]);
  });

  it("reports the fraction that validated, not the count returned", async () => {
    const { call } = harness({ small: [VALID, ALSO_VALID, INVENTED, ALSO_INVENTED] });

    const result = await call("tracing");

    expect(result.confidence).toBe(0.5);
    expect(result.findings).toEqual([VALID, ALSO_VALID]);
  });

  it("drops the invented citations from the findings it returns", async () => {
    const { call } = harness({ small: [VALID, INVENTED, ALSO_VALID] });

    const result = await call("tracing");

    expect(result.escalated).toBe(false);
    expect(result.findings.map((finding) => finding.path)).toEqual([
      "docs/guides/tracing.md",
      "docs/guides/metrics.md",
    ]);
  });

  it("escalates to the large tier when fewer than half the citations validate", async () => {
    const { built, call } = harness({
      small: [VALID, INVENTED, ALSO_INVENTED],
      large: [VALID, ALSO_VALID],
    });

    const result = await call("tracing");

    expect(built).toEqual([
      { subtopic: "tracing", tier: "small" },
      { subtopic: "tracing", tier: "large" },
    ]);
    expect(result.escalated).toBe(true);
    expect(result.confidence).toBe(1);
    expect(result.gap).toBeUndefined();
  });

  it("does not escalate at exactly the threshold", async () => {
    const { built, call } = harness({ small: [VALID, INVENTED], large: [VALID] });

    const result = await call("tracing");

    expect(result.confidence).toBe(0.5);
    expect(result.escalated).toBe(false);
    expect(built).toEqual([{ subtopic: "tracing", tier: "small" }]);
  });

  it("records a gap when the large tier's citations do not validate either", async () => {
    const { call } = harness({ small: [INVENTED], large: [INVENTED, ALSO_INVENTED] });

    const result = await call("tracing");

    expect(result.escalated).toBe(true);
    expect(result.confidence).toBe(0);
    expect(result.findings).toEqual([]);
    expect(result.gap?.reason).toBe(SERVICE_GAP_REASONS.low_confidence);
  });

  it("validates a finding's heading as well as its path", async () => {
    const withHeading: Finding = {
      path: "docs/guides/tracing.md",
      heading: "What is a trace",
      note: "Real heading.",
    };
    const wrongHeading: Finding = {
      path: "docs/guides/tracing.md",
      heading: "No such heading",
      note: "Heading the document does not have.",
    };
    const { call } = harness({ small: [withHeading, wrongHeading], large: [] });

    const result = await call("tracing");

    expect(result.confidence).toBe(0.5);
    expect(result.findings).toEqual([withHeading]);
  });

  it("treats a researcher that returned nothing as no confidence at all", async () => {
    const { built, call } = harness({ small: [], large: [] });

    const result = await call("tracing");

    expect(result.confidence).toBe(0);
    expect(result.escalated).toBe(true);
    expect(built.map((entry) => entry.tier)).toEqual(["small", "large"]);
  });
});

// base14.plan.fanout is recorded straight off counters.subtopics and its description is
// "subtopics researched per plan". A call the cap turns away researches nothing, so it
// must not move that counter, and the gap it returns must still be produced.
describe("research_subtopic: the fan-out counter counts subtopics researched", () => {
  it("counts the researched subtopics and not the refused ones", async () => {
    const { built, call, counters } = harness({ small: [VALID] }, { maxSubtopics: 3 });

    const results: ResearchSubtopicResult[] = [];
    for (const subtopic of ["a", "b", "c", "d", "e", "f", "g"]) {
      results.push(await call(subtopic));
    }

    expect(built).toHaveLength(3);
    expect(counters.subtopics).toBe(3);
    expect(counters.subtopics).toBe(built.length);

    const refused = results.filter((result) => result.gap !== undefined);
    expect(refused).toHaveLength(4);
    expect(refused[0]?.gap?.reason).toBe(TEMPLATED_GAP_REASONS.max_subtopics.write(3));
    expect(refused.map((result) => result.gap?.term)).toEqual(["d", "e", "f", "g"]);
  });

  it("never counts more subtopics than MAX_SUBTOPICS allows", async () => {
    const { call, counters } = harness({ small: [VALID] }, { maxSubtopics: 1 });

    await call("a");
    await call("b");
    await call("c");

    expect(counters.subtopics).toBe(1);
  });

  it("counts an escalated subtopic once, not once per tier", async () => {
    const { built, call, counters } = harness({ small: [INVENTED], large: [VALID] });

    await call("a");

    expect(built.map((entry) => entry.tier)).toEqual(["small", "large"]);
    expect(counters.subtopics).toBe(1);
    expect(counters.escalations).toBe(1);
  });
});
