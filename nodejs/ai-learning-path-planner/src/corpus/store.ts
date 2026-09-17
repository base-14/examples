import { readFile } from "node:fs/promises";
import { posix } from "node:path";
import { gunzipSync } from "node:zlib";
import type { CatalogueEntry, CorpusArea, CorpusArtifact, SectionEntry } from "./index-build.ts";

export interface SearchHit {
  path: string;
  title: string;
  area: CorpusArea;
  score: number;
  matchedFields: string[];
}

export interface ExampleHit {
  path: string;
  title: string;
  exampleDir: string;
}

export interface AreaSummary {
  area: CorpusArea;
  count: number;
}

export interface CorpusStats {
  documents: number;
  sections: number;
  headings: number;
  areas: AreaSummary[];
}

type FieldName = "title" | "keywords" | "description" | "headings";

// Title and keywords carry the strongest identity signal for a document, so they win a
// search outright. Description narrows a topic without naming it as directly. Headings
// are the weakest field: a term buried under one heading is a much softer match than a
// term the author chose to put in the title.
const FIELD_WEIGHTS: Record<FieldName, number> = {
  title: 10,
  keywords: 8,
  description: 4,
  headings: 2,
};

const FIELD_ORDER: FieldName[] = ["title", "keywords", "description", "headings"];

// The standard Docker Compose discovery names. An override or variant file such as
// compose.override.yaml or docker-compose.local.yml is not a standalone runnable entry
// point, so it is deliberately excluded from this set.
const COMPOSE_FILE_NAMES = new Set([
  "compose.yaml",
  "compose.yml",
  "docker-compose.yaml",
  "docker-compose.yml",
]);

const CANONICAL_AREAS: CorpusArea[] = [
  "docs",
  "example-readme",
  "collector-yaml",
  "dockerfile",
  "telemetry-source",
];

function tokenize(text: string): string[] {
  return text
    .toLowerCase()
    .split(/[^a-z0-9]+/)
    .filter((token) => token.length > 0);
}

export async function loadArtifact(path: string): Promise<CorpusArtifact> {
  const compressed = await readFile(path);
  const json = gunzipSync(compressed).toString("utf8");
  return JSON.parse(json) as CorpusArtifact;
}

export class CorpusStore {
  private readonly catalogue: CatalogueEntry[];
  private readonly sections: SectionEntry[];
  private readonly catalogueByPath: Map<string, CatalogueEntry>;
  // path -> heading -> every occurrence of that heading in document order. Nested
  // instead of a joined string key, so no delimiter choice can ever collide with a real
  // path or heading. An array, not a single section, because a document can carry the
  // same heading twice (the artifact stays a faithful record of the source document, so
  // this is not deduplicated at build time).
  private readonly sectionsByPath: Map<string, Map<string, SectionEntry[]>>;
  // token -> path -> which weighted fields of that path contained the token.
  private readonly index: Map<string, Map<string, Set<FieldName>>>;
  // path -> every token drawn from title, keywords, description, headings and the path
  // itself. Used only by listExamples, which treats the example's own directory name
  // (postgres, mongodb, fastify, ...) as a legitimate topic signal alongside its metadata.
  private readonly entryTokens: Map<string, Set<string>>;
  // The directory of every standard Docker Compose file in the corpus. A path is "under
  // a runnable example" only if it sits inside one of these directories.
  private readonly exampleDirs: Set<string>;

  constructor(artifact: CorpusArtifact) {
    this.catalogue = artifact.catalogue;
    this.sections = artifact.sections;
    this.catalogueByPath = new Map(this.catalogue.map((entry) => [entry.path, entry]));

    this.sectionsByPath = new Map();
    for (const section of this.sections) {
      let byHeading = this.sectionsByPath.get(section.path);
      if (byHeading === undefined) {
        byHeading = new Map();
        this.sectionsByPath.set(section.path, byHeading);
      }
      let occurrences = byHeading.get(section.heading);
      if (occurrences === undefined) {
        occurrences = [];
        byHeading.set(section.heading, occurrences);
      }
      occurrences.push(section);
    }

    this.index = new Map();
    this.entryTokens = new Map();
    this.exampleDirs = new Set();

    for (const entry of this.catalogue) {
      this.indexEntry(entry);
      if (COMPOSE_FILE_NAMES.has(posix.basename(entry.path))) {
        this.exampleDirs.add(posix.dirname(entry.path));
      }
    }
  }

  private indexEntry(entry: CatalogueEntry): void {
    const fieldTokens: Record<FieldName, string[]> = {
      title: tokenize(entry.title),
      keywords: entry.keywords.flatMap(tokenize),
      description: entry.description ? tokenize(entry.description) : [],
      headings: entry.headings.flatMap(tokenize),
    };

    const allTokens = new Set<string>(tokenize(entry.path));

    for (const field of FIELD_ORDER) {
      for (const token of fieldTokens[field]) {
        allTokens.add(token);

        let byPath = this.index.get(token);
        if (byPath === undefined) {
          byPath = new Map();
          this.index.set(token, byPath);
        }

        let fields = byPath.get(entry.path);
        if (fields === undefined) {
          fields = new Set();
          byPath.set(entry.path, fields);
        }
        fields.add(field);
      }
    }

    this.entryTokens.set(entry.path, allTokens);
  }

  private exampleDirFor(path: string): string | undefined {
    let best: string | undefined;
    for (const dir of this.exampleDirs) {
      if (path === dir || path.startsWith(`${dir}/`)) {
        if (best === undefined || dir.length > best.length) best = dir;
      }
    }
    return best;
  }

  search(query: string, limit: number): SearchHit[] {
    const queryTokens = Array.from(new Set(tokenize(query)));
    const scores = new Map<string, { score: number; fields: Set<FieldName> }>();

    for (const token of queryTokens) {
      const byPath = this.index.get(token);
      if (byPath === undefined) continue;

      for (const [path, fields] of byPath) {
        const entryScore = scores.get(path) ?? { score: 0, fields: new Set<FieldName>() };
        for (const field of fields) {
          entryScore.score += FIELD_WEIGHTS[field];
          entryScore.fields.add(field);
        }
        scores.set(path, entryScore);
      }
    }

    const hits: SearchHit[] = [];
    for (const [path, { score, fields }] of scores) {
      const entry = this.catalogueByPath.get(path);
      if (entry === undefined) continue;
      hits.push({
        path,
        title: entry.title,
        area: entry.area,
        score,
        matchedFields: FIELD_ORDER.filter((field) => fields.has(field)),
      });
    }

    hits.sort((a, b) => b.score - a.score || a.path.localeCompare(b.path));
    return hits.slice(0, limit);
  }

  outline(path: string): string[] {
    const headings = this.catalogueByPath.get(path)?.headings ?? [];
    // A document can carry the same heading twice (see sectionsByPath); outline()
    // de-duplicates so every heading it lists is fetchable exactly once and agrees with
    // what fetchSection returns.
    return Array.from(new Set(headings));
  }

  fetchSection(path: string, heading: string): SectionEntry | undefined {
    const occurrences = this.sectionsByPath.get(path)?.get(heading);
    if (occurrences === undefined || occurrences.length === 0) return undefined;
    // A single occurrence returns unchanged. Two or more occurrences of the same
    // heading in one document are joined in document order by a blank line, so a
    // fetch never silently drops the earlier occurrences the way a plain overwrite did.
    return { path, heading, text: occurrences.map((section) => section.text).join("\n\n") };
  }

  listExamples(topic: string): ExampleHit[] {
    const queryTokens = tokenize(topic);
    if (queryTokens.length === 0) return [];

    const hits: ExampleHit[] = [];
    for (const entry of this.catalogue) {
      const exampleDir = this.exampleDirFor(entry.path);
      if (exampleDir === undefined) continue;

      const tokens = this.entryTokens.get(entry.path);
      if (tokens === undefined) continue;

      const matches = queryTokens.some((token) => tokens.has(token));
      if (!matches) continue;

      hits.push({ path: entry.path, title: entry.title, exampleDir });
    }

    hits.sort((a, b) => a.path.localeCompare(b.path));
    return hits;
  }

  fetchExampleFile(path: string): string | undefined {
    const sections = this.sections.filter((section) => section.path === path);
    if (sections.length === 0) return undefined;
    return sections.map((section) => section.text).join("\n\n");
  }

  coverage(term: string): { mentioned: boolean; nearMisses: string[] } {
    const tokens = tokenize(term);
    const strongPaths = new Set<string>();
    const headingPaths = new Set<string>();

    for (const token of tokens) {
      const byPath = this.index.get(token);
      if (byPath === undefined) continue;

      for (const [path, fields] of byPath) {
        if (fields.has("title") || fields.has("keywords") || fields.has("description")) {
          strongPaths.add(path);
        } else if (fields.has("headings")) {
          headingPaths.add(path);
        }
      }
    }

    const nearMisses = Array.from(headingPaths)
      .filter((path) => !strongPaths.has(path))
      .sort();

    return { mentioned: strongPaths.size > 0 || headingPaths.size > 0, nearMisses };
  }

  related(path: string, limit: number): CatalogueEntry[] {
    const source = this.catalogueByPath.get(path);
    if (source === undefined) return [];

    const sourceKeywords = new Set(source.keywords.map((keyword) => keyword.toLowerCase()));

    const scored: { entry: CatalogueEntry; overlap: number; adjacency: number }[] = [];
    for (const entry of this.catalogue) {
      if (entry.path === path) continue;

      const overlap = entry.keywords.filter((keyword) =>
        sourceKeywords.has(keyword.toLowerCase()),
      ).length;

      // Adjacency is only meaningful within the same area, because sidebarPosition
      // orders siblings in one sidebar, not the whole corpus. A cross-area entry, or
      // either side missing a position, sorts last on this key.
      let adjacency = Number.POSITIVE_INFINITY;
      if (
        entry.area === source.area &&
        source.sidebarPosition !== undefined &&
        entry.sidebarPosition !== undefined
      ) {
        adjacency = Math.abs(entry.sidebarPosition - source.sidebarPosition);
      }

      scored.push({ entry, overlap, adjacency });
    }

    scored.sort((a, b) => {
      if (b.overlap !== a.overlap) return b.overlap - a.overlap;
      if (a.adjacency !== b.adjacency) return a.adjacency - b.adjacency;
      return a.entry.path.localeCompare(b.entry.path);
    });

    return scored.slice(0, limit).map((s) => s.entry);
  }

  areas(): AreaSummary[] {
    const counts = new Map<CorpusArea, number>();
    for (const entry of this.catalogue) {
      counts.set(entry.area, (counts.get(entry.area) ?? 0) + 1);
    }
    return CANONICAL_AREAS.map((area) => ({ area, count: counts.get(area) ?? 0 }));
  }

  stats(): CorpusStats {
    const headings = this.catalogue.reduce((total, entry) => total + entry.headings.length, 0);
    return {
      documents: this.catalogue.length,
      sections: this.sections.length,
      headings,
      areas: this.areas(),
    };
  }

  // Ground truth for whether a path exists in the loaded artifact at all. outline()
  // cannot answer this on its own: a valid path with no headings and an invalid path
  // both return an empty array. validateCitation needs the distinction, so citations.ts
  // uses this rather than re-deriving it from outline().
  getEntry(path: string): CatalogueEntry | undefined {
    return this.catalogueByPath.get(path);
  }
}
