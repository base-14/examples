import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { buildIndex, type CatalogueEntry, writeArtifact } from "../src/corpus/index-build.js";

function requireEnv(name: string): string {
  const value = process.env[name];
  if (!value) {
    throw new Error(
      `${name} is required. Set it to the absolute path of the repository before running make index.`,
    );
  }
  return value;
}

function countByArea(catalogue: CatalogueEntry[]): Map<string, number> {
  const counts = new Map<string, number>();
  for (const entry of catalogue) {
    counts.set(entry.area, (counts.get(entry.area) ?? 0) + 1);
  }
  return counts;
}

async function main(): Promise<void> {
  const docsRepo = requireEnv("DOCS_REPO");
  const examplesRepo = requireEnv("EXAMPLES_REPO");

  console.log(`Indexing docs from ${docsRepo} and examples from ${examplesRepo}.`);
  const artifact = await buildIndex({ docsRepo, examplesRepo });

  console.log(`Catalogue entries: ${artifact.catalogue.length}`);
  for (const [area, count] of countByArea(artifact.catalogue)) {
    console.log(`  ${area}: ${count}`);
  }
  console.log(`Section entries: ${artifact.sections.length}`);

  const scriptDir = dirname(fileURLToPath(import.meta.url));
  const outputPath = join(scriptDir, "..", "data", "corpus.json.gz");
  const compressedBytes = await writeArtifact(artifact, outputPath);

  console.log(`Uncompressed JSON size: ${JSON.stringify(artifact).length} bytes`);
  console.log(`Compressed artifact size: ${compressedBytes} bytes`);
  console.log(`Wrote ${outputPath}`);
}

main().catch((error) => {
  console.error("Failed to build the corpus index.");
  console.error(error instanceof Error ? error.message : error);
  process.exit(1);
});
