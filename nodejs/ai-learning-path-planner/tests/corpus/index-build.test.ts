import { mkdir, mkdtemp, readFile, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { dirname, join } from "node:path";
import { afterAll, beforeAll, describe, expect, it } from "vitest";
import { buildIndex, type CorpusArtifact, writeArtifact } from "../../src/corpus/index-build.ts";
import { loadArtifact } from "../../src/corpus/store.ts";

const INTRO_MD = `---
title: Getting started
sidebar_label: Getting Started
id: getting-started
sidebar_position: 1
description: How to get the planner running locally.
keywords:
  - planner
  - setup
---

## Install dependencies

Run npm install before anything else.

## Configure the environment

Copy .env.example to .env and set DOCS_REPO and EXAMPLES_REPO.
`;

// A fenced shell block with heading-shaped comments inside it. The fence must not be
// read as markdown structure: "# Verify ..." and "## Step two" are bash comments, not
// headings, and the fence character run below the block does not close early because it
// is shorter than the one that opened it.
const RUNBOOK_MD = `---
title: Rotate credentials
description: Zero-downtime credential rotation runbook.
---

## Rotate the credential

Run the following steps in order.

\`\`\`\`bash
# Verify the current credential's keyId before rotating, so step 4
# knows which one to revoke.
echo "capture keyId"

## Step two
echo "not a real heading, still inside the fence"

\`\`\`
still inside the fence: a shorter run of backticks does not close it
\`\`\`\`

## Confirm rotation

Check the audit log for the new credential.
`;

const IGNORED_MD = `# Ignored package doc

This file lives under node_modules and must never reach the catalogue.
`;

const README_MD = `---
title: hello-world
description: A minimal Node.js example instrumented with OpenTelemetry.
keywords:
  - nodejs
  - hello-world
---

This example shows the smallest possible instrumented Node.js service. Run make dev to start it locally against the collector.
`;

const OTEL_YAML = `receivers:
  otlp:
    protocols:
      grpc:
      http:

exporters:
  debug: {}

service:
  pipelines:
    traces:
      receivers: [otlp]
      exporters: [debug]
`;

const DOCKERFILE = `FROM node:26-slim
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
CMD ["node", "dist/index.js"]
`;

const TELEMETRY_TS = `import { NodeSDK } from "@opentelemetry/sdk-node";

export function startTelemetry(): void {
  const sdk = new NodeSDK({});
  sdk.start();
}
`;

const APP_TS = `export function computeTotal(items: number[]): number {
  return items.reduce((sum, item) => sum + item, 0);
}
`;

const LEFT_PAD_README = `# left-pad

Not part of the corpus.
`;

async function writeFixtureFile(
  root: string,
  relativePath: string,
  content: string,
): Promise<void> {
  const target = join(root, relativePath);
  await mkdir(dirname(target), { recursive: true });
  await writeFile(target, content, "utf8");
}

let tempRoot: string;
let docsRepo: string;
let examplesRepo: string;
let artifact: CorpusArtifact;

beforeAll(async () => {
  tempRoot = await mkdtemp(join(tmpdir(), "corpus-index-build-"));
  docsRepo = join(tempRoot, "docs-repo");
  examplesRepo = join(tempRoot, "examples-repo");

  await writeFixtureFile(docsRepo, "docs/guides/intro.md", INTRO_MD);
  await writeFixtureFile(docsRepo, "docs/guides/runbook.md", RUNBOOK_MD);
  await writeFixtureFile(docsRepo, "docs/node_modules/pkg/ignored.md", IGNORED_MD);

  await writeFixtureFile(examplesRepo, "nodejs/hello-world/README.md", README_MD);
  await writeFixtureFile(examplesRepo, "nodejs/hello-world/config/otel-collector.yaml", OTEL_YAML);
  await writeFixtureFile(examplesRepo, "nodejs/hello-world/Dockerfile", DOCKERFILE);
  await writeFixtureFile(examplesRepo, "nodejs/hello-world/src/telemetry.ts", TELEMETRY_TS);
  await writeFixtureFile(examplesRepo, "nodejs/hello-world/src/app.ts", APP_TS);
  await writeFixtureFile(
    examplesRepo,
    "nodejs/hello-world/node_modules/left-pad/README.md",
    LEFT_PAD_README,
  );

  artifact = await buildIndex({ docsRepo, examplesRepo });
});

afterAll(async () => {
  await rm(tempRoot, { recursive: true, force: true });
});

describe("buildIndex", () => {
  it("indexes docs markdown, example READMEs, collector YAML, Dockerfiles and telemetry source", () => {
    const paths = artifact.catalogue.map((entry) => entry.path).sort();
    expect(paths).toEqual([
      "docs/guides/intro.md",
      "docs/guides/runbook.md",
      "examples/nodejs/hello-world/Dockerfile",
      "examples/nodejs/hello-world/README.md",
      "examples/nodejs/hello-world/config/otel-collector.yaml",
      "examples/nodejs/hello-world/src/telemetry.ts",
    ]);
  });

  it("excludes application source and node_modules content", () => {
    const paths = artifact.catalogue.map((entry) => entry.path);

    expect(paths).not.toContain("examples/nodejs/hello-world/src/app.ts");
    expect(paths.some((path) => path.includes("node_modules"))).toBe(false);
  });

  it("parses frontmatter and headings for the docs markdown entry", () => {
    const entry = artifact.catalogue.find((candidate) => candidate.path === "docs/guides/intro.md");

    expect(entry).toBeDefined();
    expect(entry?.area).toBe("docs");
    expect(entry?.title).toBe("Getting started");
    expect(entry?.sidebarLabel).toBe("Getting Started");
    expect(entry?.id).toBe("getting-started");
    expect(entry?.sidebarPosition).toBe(1);
    expect(entry?.description).toBe("How to get the planner running locally.");
    expect(entry?.keywords).toEqual(["planner", "setup"]);
    expect(entry?.headings).toEqual(["Install dependencies", "Configure the environment"]);
  });

  it("splits a heading-delimited document into one section per heading", () => {
    const sections = artifact.sections.filter((section) => section.path === "docs/guides/intro.md");

    expect(sections).toHaveLength(2);
    expect(sections[0]?.heading).toBe("Install dependencies");
    expect(sections[0]?.text).toContain("npm install");
    expect(sections[1]?.heading).toBe("Configure the environment");
    expect(sections[1]?.text).toContain("DOCS_REPO");
  });

  it("yields one section for a document with no headings", () => {
    const readmePath = "examples/nodejs/hello-world/README.md";
    const sections = artifact.sections.filter((section) => section.path === readmePath);

    expect(sections).toHaveLength(1);
    expect(sections[0]?.text).toContain("smallest possible instrumented");

    const entry = artifact.catalogue.find((candidate) => candidate.path === readmePath);
    expect(entry?.area).toBe("example-readme");
    expect(entry?.headings).toEqual([]);
  });

  it("indexes YAML, Dockerfile and telemetry source whole with a synthetic heading", () => {
    const yamlPath = "examples/nodejs/hello-world/config/otel-collector.yaml";
    const yamlEntry = artifact.catalogue.find((candidate) => candidate.path === yamlPath);
    expect(yamlEntry?.area).toBe("collector-yaml");
    expect(yamlEntry?.headings).toEqual(["otel-collector.yaml"]);

    const dockerPath = "examples/nodejs/hello-world/Dockerfile";
    const dockerEntry = artifact.catalogue.find((candidate) => candidate.path === dockerPath);
    expect(dockerEntry?.area).toBe("dockerfile");
    expect(dockerEntry?.headings).toEqual(["Dockerfile"]);

    const telemetryPath = "examples/nodejs/hello-world/src/telemetry.ts";
    const telemetryEntry = artifact.catalogue.find((candidate) => candidate.path === telemetryPath);
    expect(telemetryEntry?.area).toBe("telemetry-source");
    expect(telemetryEntry?.headings).toEqual(["telemetry.ts"]);

    const yamlSections = artifact.sections.filter((section) => section.path === yamlPath);
    expect(yamlSections).toHaveLength(1);
    expect(yamlSections[0]?.text).toContain("receivers");
  });

  it("does not read heading-shaped comment lines inside a fenced code block as headings", () => {
    const runbookPath = "docs/guides/runbook.md";
    const entry = artifact.catalogue.find((candidate) => candidate.path === runbookPath);

    expect(entry?.headings).toEqual(["Rotate the credential", "Confirm rotation"]);

    const sections = artifact.sections.filter((section) => section.path === runbookPath);
    expect(sections).toHaveLength(2);
    expect(sections[0]?.heading).toBe("Rotate the credential");
    expect(sections[0]?.text).toContain("# Verify the current credential's keyId before rotating");
    expect(sections[0]?.text).toContain("## Step two");
    expect(sections[1]?.heading).toBe("Confirm rotation");
    expect(sections[1]?.text).toContain("Check the audit log");

    const headingTexts = sections.map((section) => section.heading);
    expect(headingTexts).not.toContain(
      "Verify the current credential's keyId before rotating, so step 4",
    );
    expect(headingTexts).not.toContain("Step two");
  });

  // The write half of the artifact's round trip, against the function scripts/build-index.ts
  // calls, read back by the function src/index.ts boots with. The test this replaced gzipped
  // and gunzipped a value it already held, so it asserted that node:zlib and JSON.parse are
  // inverses and could not fail on any change to this repository.
  it("writes the artifact gzipped, so loadArtifact reads back what buildIndex produced", async () => {
    const outputPath = join(tempRoot, "written", "corpus.json.gz");

    const compressedBytes = await writeArtifact(artifact, outputPath);

    const onDisk = await readFile(outputPath);
    // The gzip magic number. Written as plain JSON the first two bytes are 0x7b 0x22.
    expect([onDisk[0], onDisk[1]]).toEqual([0x1f, 0x8b]);
    expect(compressedBytes).toBe(onDisk.length);
    expect(compressedBytes).toBeLessThan(JSON.stringify(artifact).length);

    const restored = await loadArtifact(outputPath);
    expect(restored).toEqual(artifact);

    const paths = restored.catalogue.map((entry) => entry.path);
    expect(paths).not.toContain("examples/nodejs/hello-world/src/app.ts");
    expect(paths.some((path) => path.includes("node_modules"))).toBe(false);
  });
});

describe("buildIndex against a missing repository root", () => {
  it("fails with an error naming the missing path instead of returning an empty artifact", async () => {
    const missingDocsRepo = join(tempRoot, "does-not-exist");

    await expect(buildIndex({ docsRepo: missingDocsRepo, examplesRepo })).rejects.toThrow(
      missingDocsRepo,
    );
  });
});
