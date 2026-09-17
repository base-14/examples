import type { Config } from "../config.ts";

// The two tool sets are disjoint: four over the whole-corpus view and the fan-out, five that
// read one document at a time. Both agents build all nine; activeToolsFor decides which of
// them a role's model sees, so TOOL_CATALOGUE=full changes neither agent's tool map.
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
