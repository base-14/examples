import { mkdir, readdir, readFile, stat, writeFile } from "node:fs/promises";
import { basename, dirname, extname, join, relative, sep } from "node:path";
import { promisify } from "node:util";
import { gzip } from "node:zlib";
import { parse as parseYaml } from "yaml";

const gzipAsync = promisify(gzip);

export type CorpusArea =
  | "docs"
  | "example-readme"
  | "collector-yaml"
  | "dockerfile"
  | "telemetry-source";

export interface CatalogueEntry {
  path: string;
  area: CorpusArea;
  title: string;
  sidebarLabel?: string;
  id?: string;
  sidebarPosition?: number;
  description?: string;
  keywords: string[];
  headings: string[];
}

export interface SectionEntry {
  path: string;
  heading: string;
  text: string;
}

export interface CorpusArtifact {
  catalogue: CatalogueEntry[];
  sections: SectionEntry[];
}

export interface BuildIndexOptions {
  docsRepo: string;
  examplesRepo: string;
}

// Directory names pruned at every level of the walk, not only at the root. A vendored
// or generated directory can appear nested inside any example, so the check has to run
// on every directory the walk visits.
const EXCLUDED_DIR_NAMES = new Set([
  "node_modules",
  ".git",
  "dist",
  "build",
  "out",
  "target",
  "bin",
  "obj",
  "vendor",
  ".venv",
  "Pods",
  "coverage",
  ".next",
  ".turbo",
  ".cache",
  "wt",
  ".worktrees",
  "static",
]);

const TELEMETRY_KEYWORDS = ["otel", "telemetry", "instrumentation", "tracing"];

const TELEMETRY_SOURCE_EXTENSIONS = new Set([
  "ts",
  "tsx",
  "js",
  "jsx",
  "py",
  "go",
  "java",
  "rs",
  "rb",
  "php",
  "cs",
  "kt",
  "dart",
  "ex",
  "exs",
]);

const HEADING_PATTERN = /^(#{1,6})\s+(.+?)\s*$/;

// Matches an ATX code fence delimiter line: up to three leading spaces, then a run of
// three or more backticks or tildes, then an optional info string (opening fence) or
// trailing whitespace (closing fence).
const FENCE_PATTERN = /^ {0,3}(`{3,}|~{3,})(.*)$/;

async function walk(root: string): Promise<string[]> {
  let rootStat: Awaited<ReturnType<typeof stat>>;
  try {
    rootStat = await stat(root);
  } catch {
    throw new Error(`Repository root does not exist or is not readable: ${root}`);
  }
  if (!rootStat.isDirectory()) {
    throw new Error(`Repository root is not a directory: ${root}`);
  }

  const files: string[] = [];

  // Subdirectories encountered mid-walk are allowed to fail (permissions, broken
  // symlinks) without aborting the run; only the root itself is a hard error.
  async function visit(dir: string): Promise<void> {
    const entries = await readdir(dir, { withFileTypes: true }).catch(() => []);
    for (const entry of entries) {
      if (entry.isDirectory()) {
        if (EXCLUDED_DIR_NAMES.has(entry.name)) continue;
        await visit(join(dir, entry.name));
      } else if (entry.isFile()) {
        files.push(join(dir, entry.name));
      }
    }
  }

  await visit(root);
  return files;
}

function toPosixPath(path: string): string {
  return path.split(sep).join("/");
}

function classifyExampleFile(absolutePath: string): CorpusArea | undefined {
  const name = basename(absolutePath);

  if (name === "README.md") return "example-readme";

  const ext = extname(name).slice(1).toLowerCase();
  if (ext === "yaml" || ext === "yml") return "collector-yaml";
  if (name === "Dockerfile" || name.startsWith("Dockerfile.")) return "dockerfile";

  const lowerName = name.toLowerCase();
  if (TELEMETRY_KEYWORDS.some((keyword) => lowerName.includes(keyword))) {
    if (ext === "md" || ext === "map") return undefined;
    return "telemetry-source";
  }

  const segments = toPosixPath(absolutePath).toLowerCase().split("/");
  const inTelemetryDir = segments.some((segment) => TELEMETRY_KEYWORDS.includes(segment));
  if (inTelemetryDir && TELEMETRY_SOURCE_EXTENSIONS.has(ext)) {
    return "telemetry-source";
  }

  return undefined;
}

interface Frontmatter {
  title?: string;
  sidebar_label?: string;
  id?: string;
  sidebar_position?: number;
  description?: string;
  keywords?: string[];
}

function splitFrontmatter(content: string): { frontmatter: Frontmatter; body: string } {
  const lines = content.split("\n");
  if (lines[0]?.trim() !== "---") {
    return { frontmatter: {}, body: content };
  }

  let closingIndex = -1;
  for (let i = 1; i < lines.length; i++) {
    if (lines[i]?.trim() === "---") {
      closingIndex = i;
      break;
    }
  }
  if (closingIndex === -1) {
    return { frontmatter: {}, body: content };
  }

  const rawFrontmatter = lines.slice(1, closingIndex).join("\n");
  const body = lines.slice(closingIndex + 1).join("\n");
  const parsed = parseYaml(rawFrontmatter);
  const frontmatter = typeof parsed === "object" && parsed !== null ? (parsed as Frontmatter) : {};
  return { frontmatter, body };
}

interface RawSection {
  heading: string;
  text: string;
  synthetic: boolean;
}

interface OpenFence {
  char: string;
  length: number;
}

function splitSections(body: string, fallbackHeading: string): RawSection[] {
  const lines = body.split("\n");
  const sections: RawSection[] = [];
  let currentHeading: string | undefined;
  let currentLines: string[] = [];
  let openFence: OpenFence | undefined;

  const flush = () => {
    const text = currentLines.join("\n").trim();
    if (currentHeading !== undefined) {
      sections.push({ heading: currentHeading, text, synthetic: false });
    } else if (text.length > 0) {
      sections.push({ heading: fallbackHeading, text, synthetic: true });
    }
  };

  for (const line of lines) {
    const fenceMatch = line.match(FENCE_PATTERN);
    if (fenceMatch?.[1] !== undefined) {
      const char = fenceMatch[1][0] as string;
      const length = fenceMatch[1].length;
      const trailing = fenceMatch[2] ?? "";

      if (openFence === undefined) {
        // Any fence run of three or more opens a fence, whatever follows it on the line.
        openFence = { char, length };
      } else if (char === openFence.char && length >= openFence.length && trailing.trim() === "") {
        // Only a matching, unadorned fence of at least the same length closes it.
        openFence = undefined;
      }
      currentLines.push(line);
      continue;
    }

    if (openFence !== undefined) {
      // Inside a fence, nothing is a heading, ATX-looking or otherwise.
      currentLines.push(line);
      continue;
    }

    const match = line.match(HEADING_PATTERN);
    if (match?.[2] !== undefined) {
      flush();
      currentHeading = match[2].trim();
      currentLines = [];
    } else {
      currentLines.push(line);
    }
  }
  flush();

  if (sections.length === 0) {
    sections.push({ heading: fallbackHeading, text: body.trim(), synthetic: true });
  }

  return sections;
}

function deriveFallbackTitle(absolutePath: string): string {
  const name = basename(absolutePath);
  const ext = extname(name);
  return ext ? name.slice(0, -ext.length) : name;
}

interface BuiltEntry {
  catalogue: CatalogueEntry;
  sections: SectionEntry[];
}

async function buildMarkdownEntry(
  absolutePath: string,
  relativePath: string,
  area: CorpusArea,
): Promise<BuiltEntry> {
  const raw = await readFile(absolutePath, "utf8");
  const { frontmatter, body } = splitFrontmatter(raw);
  const fallbackTitle = frontmatter.title ?? deriveFallbackTitle(absolutePath);
  const rawSections = splitSections(body, fallbackTitle);
  const headings = rawSections
    .filter((section) => !section.synthetic)
    .map((section) => section.heading);

  const catalogue: CatalogueEntry = {
    path: relativePath,
    area,
    title: fallbackTitle,
    sidebarLabel: frontmatter.sidebar_label,
    id: frontmatter.id,
    sidebarPosition:
      typeof frontmatter.sidebar_position === "number" ? frontmatter.sidebar_position : undefined,
    description: frontmatter.description,
    keywords: Array.isArray(frontmatter.keywords) ? frontmatter.keywords : [],
    headings,
  };

  const sections: SectionEntry[] = rawSections.map((section) => ({
    path: relativePath,
    heading: section.heading,
    text: section.text,
  }));

  return { catalogue, sections };
}

async function buildWholeFileEntry(
  absolutePath: string,
  relativePath: string,
  area: CorpusArea,
): Promise<BuiltEntry> {
  const raw = await readFile(absolutePath, "utf8");
  const heading = basename(absolutePath);

  const catalogue: CatalogueEntry = {
    path: relativePath,
    area,
    title: heading,
    keywords: [],
    headings: [heading],
  };

  const sections: SectionEntry[] = [{ path: relativePath, heading, text: raw.trim() }];
  return { catalogue, sections };
}

export async function buildIndex(opts: BuildIndexOptions): Promise<CorpusArtifact> {
  const catalogue: CatalogueEntry[] = [];
  const sections: SectionEntry[] = [];

  const docsRoot = join(opts.docsRepo, "docs");
  const docFiles = (await walk(docsRoot))
    .filter((file) => {
      const ext = extname(file).toLowerCase();
      return ext === ".md" || ext === ".mdx";
    })
    .sort();

  for (const file of docFiles) {
    const relativePath = toPosixPath(join("docs", relative(docsRoot, file)));
    const entry = await buildMarkdownEntry(file, relativePath, "docs");
    catalogue.push(entry.catalogue);
    sections.push(...entry.sections);
  }

  const exampleFiles = (await walk(opts.examplesRepo)).sort();
  for (const file of exampleFiles) {
    const area = classifyExampleFile(file);
    if (!area) continue;

    const relativePath = toPosixPath(join("examples", relative(opts.examplesRepo, file)));
    const entry =
      area === "example-readme"
        ? await buildMarkdownEntry(file, relativePath, area)
        : await buildWholeFileEntry(file, relativePath, area);
    catalogue.push(entry.catalogue);
    sections.push(...entry.sections);
  }

  return { catalogue, sections };
}

// The other half of corpus/store.ts's loadArtifact, and it lives here rather than in
// scripts/build-index.ts so the compression the shipped artifact is written with is the
// same code a test can run. data/corpus.json.gz is 873 documents of text: uncompressed it
// is large enough to matter in a git repository and in an image layer. Returns the
// compressed size so the script can report it.
export async function writeArtifact(artifact: CorpusArtifact, outputPath: string): Promise<number> {
  await mkdir(dirname(outputPath), { recursive: true });
  const compressed = await gzipAsync(JSON.stringify(artifact));
  await writeFile(outputPath, compressed);
  return compressed.length;
}
