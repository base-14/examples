import { mkdtemp, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { gzipSync } from "node:zlib";
import { afterAll, beforeAll, describe, expect, it } from "vitest";
import type { CorpusArtifact } from "../../src/corpus/index-build.ts";
import { CorpusStore, loadArtifact } from "../../src/corpus/store.ts";

// Sixteen catalogue entries spanning all five areas, built directly as a CorpusArtifact
// so the store is exercised with no file IO. Four example directories: one with
// compose.yaml, one reachable only through docker-compose.yml, one with only an override
// file (must never surface from listExamples), and hello-postgres-legacy with no compose
// file of any standard name at all.
const artifact: CorpusArtifact = {
  catalogue: [
    {
      path: "docs/guides/tracing.md",
      area: "docs",
      title: "Tracing basics",
      sidebarPosition: 1,
      description: "Introduction to distributed tracing.",
      keywords: ["tracing", "otel"],
      headings: ["What is a trace", "Spans and attributes"],
    },
    {
      path: "docs/guides/dashboards.md",
      area: "docs",
      title: "Dashboards",
      sidebarPosition: 2,
      description: "How to build a dashboard.",
      keywords: [],
      headings: ["Building metrics dashboards"],
    },
    {
      path: "docs/guides/logging.md",
      area: "docs",
      title: "Logging basics",
      sidebarPosition: 10,
      description: "How to configure structured logging.",
      keywords: [],
      headings: ["Structured logging", "Log correlation with trace context"],
    },
    {
      path: "docs/guides/metrics.md",
      area: "docs",
      title: "Metrics basics",
      sidebarPosition: 20,
      description: "Introduction to observability data collection.",
      keywords: ["metrics", "otel"],
      headings: ["Counters and gauges", "Exporting data"],
    },
    {
      // Matches "observability" only in its heading, never in title, keywords or
      // description, to pair against metrics.md's description-only match on the same
      // term (search: description above headings).
      path: "docs/guides/alerting.md",
      area: "docs",
      title: "Alerting basics",
      sidebarPosition: 30,
      description: "How to set up alert rules.",
      keywords: [],
      headings: ["Observability checklist for alerts"],
    },
    {
      // Both sections share the heading "Triage". The catalogue keeps both occurrences,
      // same as index-build.ts would emit for a real document with two same-named
      // sections; the store, not the generator, is responsible for not losing one.
      path: "docs/guides/incident-response.md",
      area: "docs",
      title: "Incident response",
      sidebarPosition: 40,
      description: "Steps for responding to an incident.",
      keywords: [],
      headings: ["Triage", "Triage"],
    },
    {
      path: "examples/nodejs/hello-postgres/compose.yaml",
      area: "collector-yaml",
      title: "compose.yaml",
      keywords: [],
      headings: ["compose.yaml"],
    },
    {
      path: "examples/nodejs/hello-postgres/README.md",
      area: "example-readme",
      title: "hello-postgres",
      description: "A Postgres-backed example.",
      keywords: ["postgres", "nodejs"],
      headings: [],
    },
    {
      path: "examples/nodejs/hello-postgres/Dockerfile",
      area: "dockerfile",
      title: "Dockerfile",
      keywords: [],
      headings: ["Dockerfile"],
    },
    {
      path: "examples/nodejs/hello-postgres/src/telemetry.ts",
      area: "telemetry-source",
      title: "telemetry.ts",
      keywords: [],
      headings: ["telemetry.ts"],
    },
    {
      path: "examples/nodejs/hello-postgres-legacy/README.md",
      area: "example-readme",
      title: "hello-postgres-legacy",
      description: "Legacy postgres example without a compose file.",
      keywords: ["postgres", "legacy"],
      headings: [],
    },
    {
      // Reachable only through docker-compose.yml, not compose.yaml.
      path: "examples/nodejs/hello-mongo/docker-compose.yml",
      area: "collector-yaml",
      title: "docker-compose.yml",
      keywords: [],
      headings: ["docker-compose.yml"],
    },
    {
      path: "examples/nodejs/hello-mongo/README.md",
      area: "example-readme",
      title: "hello-mongo",
      description: "A Mongo-backed example.",
      keywords: ["mongo", "nodejs"],
      headings: [],
    },
    {
      // Only an override file, no standalone compose file. Must never make this
      // directory count as a runnable example.
      path: "examples/nodejs/hello-redis-override/compose.override.yaml",
      area: "collector-yaml",
      title: "compose.override.yaml",
      keywords: [],
      headings: ["compose.override.yaml"],
    },
    {
      path: "examples/nodejs/hello-redis-override/README.md",
      area: "example-readme",
      title: "hello-redis-override",
      description: "A Redis-backed example kept behind an override compose file.",
      keywords: ["redis", "override"],
      headings: [],
    },
    {
      // Shares the "tracing" keyword with docs/guides/tracing.md but sits in a
      // different area, for the related() cross-area case.
      path: "examples/nodejs/otel-tracing-demo/README.md",
      area: "example-readme",
      title: "otel-tracing-demo",
      description: "An example that emits traces end to end.",
      keywords: ["tracing"],
      headings: [],
    },
  ],
  sections: [
    {
      path: "docs/guides/tracing.md",
      heading: "What is a trace",
      text: "A trace represents the end-to-end journey of a single request.",
    },
    {
      path: "docs/guides/tracing.md",
      heading: "Spans and attributes",
      text: "A span is one unit of work inside a trace, carrying its own attributes.",
    },
    {
      path: "docs/guides/dashboards.md",
      heading: "Building metrics dashboards",
      text: "Compose panels from your exported metrics.",
    },
    {
      path: "docs/guides/logging.md",
      heading: "Structured logging",
      text: "Emit logs as structured fields rather than free text.",
    },
    {
      path: "docs/guides/logging.md",
      heading: "Log correlation with trace context",
      text: "Attach the active trace id to every log line so logs and traces line up.",
    },
    {
      path: "docs/guides/metrics.md",
      heading: "Counters and gauges",
      text: "A counter only goes up; a gauge can go up or down.",
    },
    {
      path: "docs/guides/metrics.md",
      heading: "Exporting data",
      text: "Metrics are exported on an interval to the collector.",
    },
    {
      path: "docs/guides/alerting.md",
      heading: "Observability checklist for alerts",
      text: "Confirm the alert has an owner and a runbook link before it ships.",
    },
    {
      path: "docs/guides/incident-response.md",
      heading: "Triage",
      text: "First triage pass: acknowledge the page.",
    },
    {
      path: "docs/guides/incident-response.md",
      heading: "Triage",
      text: "Second triage pass: assign an owner and open a channel.",
    },
    {
      path: "examples/nodejs/hello-postgres/compose.yaml",
      heading: "compose.yaml",
      text: "services:\n  app:\n    build: .\n  postgres:\n    image: postgres:16\n",
    },
    {
      path: "examples/nodejs/hello-postgres/README.md",
      heading: "hello-postgres",
      text: "This example shows a Node.js service backed by Postgres.",
    },
    {
      path: "examples/nodejs/hello-postgres/Dockerfile",
      heading: "Dockerfile",
      text: 'FROM node:26-slim\nCMD ["node", "dist/index.js"]\n',
    },
    {
      path: "examples/nodejs/hello-postgres/src/telemetry.ts",
      heading: "telemetry.ts",
      text: "export function startTelemetry(): void {}\n",
    },
    {
      path: "examples/nodejs/hello-postgres-legacy/README.md",
      heading: "hello-postgres-legacy",
      text: "An older Postgres example kept for reference, with no compose file.",
    },
    {
      path: "examples/nodejs/hello-mongo/docker-compose.yml",
      heading: "docker-compose.yml",
      text: "services:\n  app:\n    build: .\n  mongo:\n    image: mongo:7\n",
    },
    {
      path: "examples/nodejs/hello-mongo/README.md",
      heading: "hello-mongo",
      text: "This example shows a Node.js service backed by Mongo.",
    },
    {
      path: "examples/nodejs/hello-redis-override/compose.override.yaml",
      heading: "compose.override.yaml",
      text: "services:\n  redis:\n    image: redis:7\n",
    },
    {
      path: "examples/nodejs/hello-redis-override/README.md",
      heading: "hello-redis-override",
      text: "This example shows a Node.js service backed by Redis, behind an override file.",
    },
    {
      path: "examples/nodejs/otel-tracing-demo/README.md",
      heading: "otel-tracing-demo",
      text: "This example emits traces for every request end to end.",
    },
  ],
};

const store = new CorpusStore(artifact);

describe("CorpusStore.search", () => {
  it("ranks a title and keyword match above a heading-only match", () => {
    const hits = store.search("metrics", 10);
    const paths = hits.map((hit) => hit.path);

    expect(paths[0]).toBe("docs/guides/metrics.md");
    expect(paths).toContain("docs/guides/dashboards.md");

    const top = hits[0];
    const heading = hits.find((hit) => hit.path === "docs/guides/dashboards.md");
    expect(top?.matchedFields.sort()).toEqual(["keywords", "title"]);
    expect(heading?.matchedFields).toEqual(["headings"]);
    expect(top?.score).toBeGreaterThan(heading?.score ?? Number.POSITIVE_INFINITY);
  });

  it("ranks a description-only match above a heading-only match", () => {
    // metrics.md matches "observability" only in its description. alerting.md matches
    // it only in a heading. description (weight 4) must outrank headings (weight 2),
    // which the title/keywords-vs-headings test above does not exercise.
    const hits = store.search("observability", 10);
    const paths = hits.map((hit) => hit.path);

    expect(paths[0]).toBe("docs/guides/metrics.md");
    expect(paths[1]).toBe("docs/guides/alerting.md");

    const descriptionHit = hits.find((hit) => hit.path === "docs/guides/metrics.md");
    const headingHit = hits.find((hit) => hit.path === "docs/guides/alerting.md");
    expect(descriptionHit?.matchedFields).toEqual(["description"]);
    expect(headingHit?.matchedFields).toEqual(["headings"]);
    expect(descriptionHit?.score).toBeGreaterThan(headingHit?.score ?? Number.POSITIVE_INFINITY);
  });

  it("respects the limit", () => {
    expect(store.search("metrics", 1)).toHaveLength(1);
  });

  it("returns no hits for a term absent from every catalogue field", () => {
    expect(store.search("kubernetes", 10)).toEqual([]);
  });
});

describe("CorpusStore.outline", () => {
  it("returns headings only, never section text", () => {
    expect(store.outline("docs/guides/tracing.md")).toEqual([
      "What is a trace",
      "Spans and attributes",
    ]);
  });

  it("de-duplicates a heading that appears twice in one document", () => {
    expect(store.outline("docs/guides/incident-response.md")).toEqual(["Triage"]);
  });

  it("returns an empty array for a path outside the artifact", () => {
    expect(store.outline("docs/guides/does-not-exist.md")).toEqual([]);
  });
});

describe("CorpusStore.fetchSection", () => {
  it("fetches a known section by path and heading", () => {
    const section = store.fetchSection("docs/guides/tracing.md", "Spans and attributes");
    expect(section?.text).toBe(
      "A span is one unit of work inside a trace, carrying its own attributes.",
    );
  });

  it("joins two occurrences of the same heading in document order, dropping neither", () => {
    const section = store.fetchSection("docs/guides/incident-response.md", "Triage");
    expect(section?.text).toBe(
      "First triage pass: acknowledge the page.\n\nSecond triage pass: assign an owner and open a channel.",
    );
  });

  it("returns undefined for a heading that does not exist on the path", () => {
    expect(store.fetchSection("docs/guides/tracing.md", "Not a real heading")).toBeUndefined();
  });
});

describe("CorpusStore.coverage", () => {
  it("returns false with no near misses for a term in no document", () => {
    expect(store.coverage("kubernetes")).toEqual({ mentioned: false, nearMisses: [] });
  });

  it("returns true with no near misses for a term in a title and keyword", () => {
    expect(store.coverage("tracing")).toEqual({ mentioned: true, nearMisses: [] });
  });

  it("returns true with a near miss for a term that appears only in a heading", () => {
    expect(store.coverage("correlation")).toEqual({
      mentioned: true,
      nearMisses: ["docs/guides/logging.md"],
    });
  });
});

describe("CorpusStore.related", () => {
  it("prefers a keyword-sharing document over one that is merely sidebarPosition-adjacent", () => {
    const related = store.related("docs/guides/tracing.md", 6);
    const paths = related.map((entry) => entry.path);

    const metricsIndex = paths.indexOf("docs/guides/metrics.md");
    const dashboardsIndex = paths.indexOf("docs/guides/dashboards.md");
    const loggingIndex = paths.indexOf("docs/guides/logging.md");

    // metrics.md shares the "otel" keyword but sits nine sidebar positions further away
    // than dashboards.md, which shares no keyword but sits one position away. Keyword
    // overlap wins the disagreement, so metrics.md outranks both same-area, zero-overlap
    // neighbors, and the closer of those two neighbors still outranks the farther one.
    expect(metricsIndex).toBeGreaterThanOrEqual(0);
    expect(metricsIndex).toBeLessThan(dashboardsIndex);
    expect(dashboardsIndex).toBeLessThan(loggingIndex);
  });

  it("lets a keyword-sharing document in a different area outrank a same-area adjacent one", () => {
    // otel-tracing-demo/README.md shares the "tracing" keyword with the source but sits
    // in a different area, so its sidebarPosition adjacency is Infinity by definition.
    // It still outranks dashboards.md, which is same-area and one position away but
    // shares no keyword: the overlap key is area-agnostic by design.
    const related = store.related("docs/guides/tracing.md", 6);
    const paths = related.map((entry) => entry.path);

    const crossAreaIndex = paths.indexOf("examples/nodejs/otel-tracing-demo/README.md");
    const adjacentIndex = paths.indexOf("docs/guides/dashboards.md");
    expect(crossAreaIndex).toBeGreaterThanOrEqual(0);
    expect(adjacentIndex).toBeGreaterThanOrEqual(0);
    expect(crossAreaIndex).toBeLessThan(adjacentIndex);
  });

  it("returns an empty array for a path outside the artifact", () => {
    expect(store.related("docs/guides/does-not-exist.md", 3)).toEqual([]);
  });
});

describe("CorpusStore.areas", () => {
  it("counts the fixture's areas", () => {
    expect(store.areas()).toEqual([
      { area: "docs", count: 6 },
      { area: "example-readme", count: 5 },
      { area: "collector-yaml", count: 3 },
      { area: "dockerfile", count: 1 },
      { area: "telemetry-source", count: 1 },
    ]);
  });

  it("reports zero for a canonical area absent from a smaller artifact", () => {
    const docsOnly = new CorpusStore({
      catalogue: [
        {
          path: "docs/only.md",
          area: "docs",
          title: "Only doc",
          keywords: [],
          headings: [],
        },
      ],
      sections: [],
    });

    expect(docsOnly.areas()).toEqual([
      { area: "docs", count: 1 },
      { area: "example-readme", count: 0 },
      { area: "collector-yaml", count: 0 },
      { area: "dockerfile", count: 0 },
      { area: "telemetry-source", count: 0 },
    ]);
  });
});

describe("CorpusStore.stats", () => {
  it("summarizes documents, sections, headings and areas", () => {
    expect(store.stats()).toEqual({
      documents: 16,
      sections: 20,
      headings: 15,
      areas: store.areas(),
    });
  });
});

describe("CorpusStore.listExamples", () => {
  it("returns only entries under an example directory that has a compose.yaml", () => {
    const hits = store.listExamples("postgres");
    const paths = hits.map((hit) => hit.path).sort();

    expect(paths).toEqual([
      "examples/nodejs/hello-postgres/Dockerfile",
      "examples/nodejs/hello-postgres/README.md",
      "examples/nodejs/hello-postgres/compose.yaml",
      "examples/nodejs/hello-postgres/src/telemetry.ts",
    ]);
    expect(paths).not.toContain("examples/nodejs/hello-postgres-legacy/README.md");
  });

  it("returns entries under a directory reachable only through docker-compose.yml", () => {
    const hits = store.listExamples("mongo");
    const paths = hits.map((hit) => hit.path).sort();

    expect(paths).toEqual([
      "examples/nodejs/hello-mongo/README.md",
      "examples/nodejs/hello-mongo/docker-compose.yml",
    ]);
  });

  it("excludes a directory that holds only an override compose file", () => {
    expect(store.listExamples("redis")).toEqual([]);
  });

  it("reports the compose file's own directory as exampleDir", () => {
    const hits = store.listExamples("postgres");
    for (const hit of hits) {
      expect(hit.exampleDir).toBe("examples/nodejs/hello-postgres");
    }
  });

  it("returns an empty array when no entry matches the topic", () => {
    expect(store.listExamples("kubernetes")).toEqual([]);
  });
});

describe("CorpusStore.fetchExampleFile", () => {
  it("fetches the whole text of a whole-file entry", () => {
    const text = store.fetchExampleFile("examples/nodejs/hello-postgres/compose.yaml");
    expect(text).toContain("image: postgres:16");
  });

  it("returns undefined for a path with no sections", () => {
    expect(store.fetchExampleFile("examples/nodejs/does-not-exist.yaml")).toBeUndefined();
  });
});

describe("CorpusStore.getEntry", () => {
  it("returns the catalogue entry for a known path", () => {
    expect(store.getEntry("docs/guides/tracing.md")?.title).toBe("Tracing basics");
  });

  it("returns undefined for a path outside the artifact", () => {
    expect(store.getEntry("docs/guides/does-not-exist.md")).toBeUndefined();
  });
});

describe("loadArtifact", () => {
  let tempRoot: string;

  beforeAll(async () => {
    tempRoot = await mkdtemp(join(tmpdir(), "corpus-store-"));
  });

  afterAll(async () => {
    await rm(tempRoot, { recursive: true, force: true });
  });

  it("decompresses a gzipped artifact file back into a CorpusArtifact", async () => {
    const target = join(tempRoot, "corpus.json.gz");
    await writeFile(target, gzipSync(JSON.stringify(artifact)));

    const restored = await loadArtifact(target);
    expect(restored).toEqual(artifact);
  });
});
