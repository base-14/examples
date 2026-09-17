import { tool } from "ai";
import { z } from "zod";
import type { CorpusStore } from "../corpus/store.ts";

export function checkCoverageTool(store: CorpusStore) {
  return tool({
    description:
      "Checks whether a term is covered by the corpus: mentioned in a title, keyword, " +
      "description or heading, plus any near-miss documents that only mention it in a heading.",
    inputSchema: z.object({ term: z.string() }),
    execute: async ({ term }) => {
      const coverage = store.coverage(term);
      return { term, mentioned: coverage.mentioned, nearMisses: coverage.nearMisses };
    },
  });
}
