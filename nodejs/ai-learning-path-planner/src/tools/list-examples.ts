import { tool } from "ai";
import { z } from "zod";
import type { CorpusStore } from "../corpus/store.ts";

// list_examples matches on example metadata, so a broad topic matches a large part of the
// corpus: list_examples("otel") returns 123 hits and 18,587 characters against the
// shipped artifact, and "docker" returns 70. search_docs and get_related have always
// capped at 20. This caps the same way, and it is a fixed cap rather than a limit
// parameter so the model cannot opt out of it and the tool definition keeps its measured
// size. A capped result says so in the result, so the model is not left believing it saw
// everything.
const MAX_HITS = 20;

export function listExamplesTool(store: CorpusStore) {
  return tool({
    description: "Lists runnable examples in the corpus whose metadata matches a topic.",
    inputSchema: z.object({ topic: z.string() }),
    execute: async ({ topic }) => {
      const hits = store.listExamples(topic);
      if (hits.length <= MAX_HITS) {
        return { examples: hits, total: hits.length, truncated: false as const };
      }
      return {
        examples: hits.slice(0, MAX_HITS),
        total: hits.length,
        truncated: true as const,
        note:
          `Showing the first ${MAX_HITS} of ${hits.length} matching examples. ` +
          "Use a narrower topic to see the rest.",
      };
    },
  });
}
