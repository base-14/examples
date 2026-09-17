import { describe, expect, it } from "vitest";
import type { CorpusArtifact } from "../../src/corpus/index-build.ts";
import { CorpusStore } from "../../src/corpus/store.ts";
import { fetchExampleFileTool } from "../../src/tools/fetch-example-file.ts";
import { listExamplesTool } from "../../src/tools/list-examples.ts";

// The two tools that used to return whatever the corpus held. Against the shipped
// artifact that is 123 hits for list_examples("otel") and 121,025 characters for the
// largest single fetch_example_file, on a 16,384 token context window. Both now cap, and
// a capped result says so.
const BIG_FILE = "examples/nodejs/big/README.md";
const HUGE_TEXT = "x".repeat(60_000);
// A docs path, deliberately in no example directory, so nothing beside it makes it an
// example. Ruling 50: fetch_example_file serves any corpus path, docs included.
const DOCS_FILE = "docs/instrument/apps/auto-instrumentation/nodejs.md";

function artifactWith(exampleCount: number): CorpusArtifact {
  const catalogue: CorpusArtifact["catalogue"] = [];
  const sections: CorpusArtifact["sections"] = [];
  for (let index = 0; index < exampleCount; index += 1) {
    const dir = `examples/nodejs/tracing-${index}`;
    const path = `${dir}/README.md`;
    catalogue.push({
      path,
      area: "example-readme",
      title: `Tracing example ${index}`,
      description: "An example that mentions otel.",
      keywords: ["otel"],
      headings: [],
    });
    sections.push({ path, heading: "", text: "otel example body." });
    // A path counts as an example only when a compose file sits beside it, so every
    // fixture example needs one. See CorpusStore's exampleDirs.
    catalogue.push({
      path: `${dir}/compose.yaml`,
      area: "collector-yaml",
      title: "compose.yaml",
      keywords: [],
      headings: ["compose.yaml"],
    });
    sections.push({ path: `${dir}/compose.yaml`, heading: "compose.yaml", text: "services:" });
  }
  catalogue.push({
    path: "examples/nodejs/big/compose.yaml",
    area: "collector-yaml",
    title: "compose.yaml",
    keywords: [],
    headings: ["compose.yaml"],
  });
  sections.push({
    path: "examples/nodejs/big/compose.yaml",
    heading: "compose.yaml",
    text: "services:",
  });
  catalogue.push({
    path: BIG_FILE,
    area: "example-readme",
    title: "Big example",
    description: "A very long file.",
    keywords: ["big"],
    headings: [],
  });
  sections.push({ path: BIG_FILE, heading: "", text: HUGE_TEXT });
  catalogue.push({
    path: DOCS_FILE,
    area: "docs",
    title: "Auto-instrumentation for Node.js",
    description: "A docs page, not an example.",
    keywords: ["otel"],
    headings: ["Install"],
  });
  sections.push({ path: DOCS_FILE, heading: "Install", text: "npm install the sdk." });
  return { catalogue, sections };
}

async function run<T>(
  tool: { execute?: (input: never, options: never) => Promise<unknown> },
  input: unknown,
): Promise<T> {
  const execute = tool.execute;
  if (execute === undefined) throw new Error("the tool has no execute");
  return (await execute(
    input as never,
    {
      toolCallId: "call-1",
      messages: [],
    } as never,
  )) as T;
}

interface ListResult {
  examples: { path: string }[];
  total: number;
  truncated: boolean;
  note?: string;
}

interface FetchResult {
  path: string;
  found: boolean;
  text?: string;
  truncated: boolean;
  note?: string;
}

describe("list_examples caps its result", () => {
  it("returns at most twenty examples for a topic that matches far more", async () => {
    const tool = listExamplesTool(new CorpusStore(artifactWith(123)));

    const result = await run<ListResult>(tool, { topic: "otel" });

    expect(result.examples).toHaveLength(20);
    expect(result.total).toBe(123);
  });

  it("says in the result that it was truncated, and how much was left out", async () => {
    const tool = listExamplesTool(new CorpusStore(artifactWith(123)));

    const result = await run<ListResult>(tool, { topic: "otel" });

    expect(result.truncated).toBe(true);
    expect(result.note).toContain("123");
    expect(result.note).toContain("20");
  });

  it("returns every match, untruncated, when the topic matches few", async () => {
    const tool = listExamplesTool(new CorpusStore(artifactWith(3)));

    const result = await run<ListResult>(tool, { topic: "otel" });

    expect(result.examples).toHaveLength(3);
    expect(result.total).toBe(3);
    expect(result.truncated).toBe(false);
    expect(result.note).toBeUndefined();
  });
});

describe("fetch_example_file caps its result", () => {
  it("returns no more text than a fraction of the context window", async () => {
    const tool = fetchExampleFileTool(new CorpusStore(artifactWith(1)));

    const result = await run<FetchResult>(tool, { path: BIG_FILE });

    expect(result.found).toBe(true);
    expect(result.text?.length).toBe(24_000);
    expect(result.text?.length).toBeLessThan(HUGE_TEXT.length);
  });

  it("says in the result that it was truncated, and what to call instead", async () => {
    const tool = fetchExampleFileTool(new CorpusStore(artifactWith(1)));

    const result = await run<FetchResult>(tool, { path: BIG_FILE });

    expect(result.truncated).toBe(true);
    expect(result.note).toContain("60000");
    expect(result.note).toContain("fetch_section");
  });

  it("returns a short file whole", async () => {
    const tool = fetchExampleFileTool(new CorpusStore(artifactWith(1)));

    const result = await run<FetchResult>(tool, {
      path: "examples/nodejs/tracing-0/README.md",
    });

    expect(result.text).toBe("otel example body.");
    expect(result.truncated).toBe(false);
    expect(result.note).toBeUndefined();
  });

  it("still reports a path the corpus does not have as not found", async () => {
    const tool = fetchExampleFileTool(new CorpusStore(artifactWith(1)));

    const result = await run<FetchResult>(tool, { path: "examples/nope.md" });

    expect(result.found).toBe(false);
    expect(result.text).toBeUndefined();
    expect(result.truncated).toBe(false);
  });
});

// Ruling 50. The tool is named for examples and serves the whole corpus, because a
// researcher reading one subtopic needs a docs page as readily as an example file. The
// behaviour is the one to keep, so the description was widened to match it and these pin
// the behaviour the description now promises. Narrowing execute to example directories
// would fail both.
describe("fetch_example_file serves any corpus path, not only example files", () => {
  it("returns a docs page that sits in no example directory", async () => {
    const store = new CorpusStore(artifactWith(1));
    const tool = fetchExampleFileTool(store);

    expect(store.listExamples("otel").map((hit) => hit.path)).not.toContain(DOCS_FILE);

    const result = await run<FetchResult>(tool, { path: DOCS_FILE });

    expect(result.found).toBe(true);
    expect(result.text).toContain("npm install the sdk.");
  });

  it("describes itself as serving any corpus path, so the model knows it can", () => {
    const tool = fetchExampleFileTool(new CorpusStore(artifactWith(1))) as {
      description?: string;
    };

    expect(tool.description).toContain("any corpus path");
  });
});
