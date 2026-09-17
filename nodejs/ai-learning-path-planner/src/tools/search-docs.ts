import { tool } from "ai";
import { z } from "zod";
import type { CorpusStore } from "../corpus/store.ts";

const DEFAULT_LIMIT = 5;

export function searchDocsTool(store: CorpusStore) {
  return tool({
    description:
      "Lexical search over the documentation and examples corpus. Returns matching corpus " +
      "paths, titles and areas ranked by relevance.",
    inputSchema: z.object({
      query: z.string().describe("Search terms, for example a technology or topic name."),
      limit: z.number().int().positive().max(20).optional(),
    }),
    execute: async ({ query, limit }) => store.search(query, limit ?? DEFAULT_LIMIT),
  });
}
