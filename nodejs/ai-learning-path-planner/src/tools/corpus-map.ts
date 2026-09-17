import { tool } from "ai";
import { z } from "zod";
import type { CorpusStore } from "../corpus/store.ts";

export function corpusMapTool(store: CorpusStore) {
  return tool({
    description:
      "Returns the areas of the corpus, how many documents each holds, and overall stats " +
      "(documents, sections, headings).",
    inputSchema: z.object({}),
    execute: async () => ({ areas: store.areas(), stats: store.stats() }),
  });
}
