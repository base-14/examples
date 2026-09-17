import type { Config } from "../config.ts";

// The lead and researcher tool sets are disjoint by design: four tools that only ever
// touch the whole-corpus view and the fan-out, five that only ever read one document or
// example at a time. Both agents always build all nine tool definitions (see lead.ts and
// researcher.ts); activeToolsFor is the only thing that decides which of the nine a given
// role's model actually sees, so TOOL_CATALOGUE=full can hand every agent all nine without
// either agent's tool map changing shape.
export const LEAD_TOOL_NAMES = [
  "corpus_map",
  "check_coverage",
  "get_related",
  "research_subtopic",
] as const;

export const RESEARCHER_TOOL_NAMES = [
  "search_docs",
  "outline",
  "fetch_section",
  "list_examples",
  "fetch_example_file",
] as const;

export const ALL_TOOL_NAMES = [...LEAD_TOOL_NAMES, ...RESEARCHER_TOOL_NAMES] as const;

export function activeToolsFor(role: "lead" | "researcher", config: Config): string[] {
  if (config.toolCatalogue === "full") {
    return [...ALL_TOOL_NAMES];
  }
  return role === "lead" ? [...LEAD_TOOL_NAMES] : [...RESEARCHER_TOOL_NAMES];
}
