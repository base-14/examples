import { describe, expect, it } from "vitest";
import { validateCitation } from "../../src/corpus/citations.ts";
import type { CorpusArtifact } from "../../src/corpus/index-build.ts";
import { CorpusStore } from "../../src/corpus/store.ts";

const artifact: CorpusArtifact = {
  catalogue: [
    {
      path: "docs/guides/tracing.md",
      area: "docs",
      title: "Tracing basics",
      sidebarPosition: 1,
      description: "Introduction to distributed tracing.",
      keywords: ["tracing"],
      headings: ["What is a trace"],
    },
    {
      path: "examples/nodejs/hello-postgres/compose.yaml",
      area: "collector-yaml",
      title: "compose.yaml",
      keywords: [],
      headings: ["compose.yaml"],
    },
  ],
  sections: [
    {
      path: "docs/guides/tracing.md",
      heading: "What is a trace",
      text: "A trace represents the end-to-end journey of a single request.",
    },
    {
      path: "examples/nodejs/hello-postgres/compose.yaml",
      heading: "compose.yaml",
      text: "services:\n  app:\n    build: .\n",
    },
  ],
};

const store = new CorpusStore(artifact);

describe("validateCitation", () => {
  it("accepts a path that exists in the artifact, with no heading", () => {
    expect(validateCitation(store, "docs/guides/tracing.md")).toBe(true);
  });

  it("rejects a path outside the artifact", () => {
    expect(validateCitation(store, "docs/guides/does-not-exist.md")).toBe(false);
  });

  it("accepts a path and heading that both exist", () => {
    expect(validateCitation(store, "docs/guides/tracing.md", "What is a trace")).toBe(true);
  });

  it("rejects a heading that does not exist on an otherwise valid path", () => {
    expect(validateCitation(store, "docs/guides/tracing.md", "Not a real heading")).toBe(false);
  });

  it("rejects a heading on a path that does not exist", () => {
    expect(validateCitation(store, "docs/guides/does-not-exist.md", "What is a trace")).toBe(false);
  });

  it("accepts the synthetic heading of a whole-file entry", () => {
    expect(
      validateCitation(store, "examples/nodejs/hello-postgres/compose.yaml", "compose.yaml"),
    ).toBe(true);
  });

  it("rejects a path traversal string not present in the artifact", () => {
    expect(validateCitation(store, "../../etc/passwd")).toBe(false);
  });

  it("rejects an absolute path not present in the artifact", () => {
    expect(validateCitation(store, "/etc/passwd")).toBe(false);
  });
});
