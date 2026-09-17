import { Hono } from "hono";
import { describe, expect, it } from "vitest";
import type { CorpusArtifact } from "../../src/corpus/index-build.ts";
import { CorpusStore } from "../../src/corpus/store.ts";
import { corpusRoutes } from "../../src/routes/corpus.ts";

const artifact: CorpusArtifact = {
  catalogue: [
    {
      path: "docs/guides/tracing.md",
      area: "docs",
      title: "Tracing basics",
      description: "Introduction to distributed tracing.",
      keywords: ["tracing"],
      headings: ["What is a trace", "Why it matters"],
    },
    {
      path: "examples/postgres/README.md",
      area: "example-readme",
      title: "Postgres example",
      description: "A runnable Postgres example.",
      keywords: ["postgres"],
      headings: ["Setup"],
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
      heading: "Why it matters",
      text: "Traces connect logs and metrics to a single request.",
    },
    {
      path: "examples/postgres/README.md",
      heading: "Setup",
      text: "docker compose up.",
    },
  ],
};

describe("GET /corpus/stats", () => {
  // The numbers the fixture above really holds, not store.stats() compared to itself:
  // the route's whole body is c.json(deps.store.stats()), so both sides of that comparison
  // move together and it passes whatever stats() starts returning.
  it("returns the counts the loaded artifact really holds", async () => {
    const corpusStore = new CorpusStore(artifact);
    const app = new Hono().route("/", corpusRoutes({ store: corpusStore }));

    const res = await app.request("/corpus/stats");

    expect(res.status).toBe(200);
    expect(await res.json()).toEqual({
      documents: 2,
      sections: 3,
      headings: 3,
      areas: [
        { area: "docs", count: 1 },
        { area: "example-readme", count: 1 },
        { area: "collector-yaml", count: 0 },
        { area: "dockerfile", count: 0 },
        { area: "telemetry-source", count: 0 },
      ],
    });
  });

  it("does not carry an index build time, only documents, sections, headings and areas", async () => {
    const corpusStore = new CorpusStore(artifact);
    const app = new Hono().route("/", corpusRoutes({ store: corpusStore }));

    const res = await app.request("/corpus/stats");
    const body = await res.json();

    expect(Object.keys(body).sort()).toEqual(["areas", "documents", "headings", "sections"]);
  });
});
