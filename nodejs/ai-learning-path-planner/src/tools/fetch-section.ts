import { tool } from "ai";
import { z } from "zod";
import type { CorpusStore } from "../corpus/store.ts";

export function fetchSectionTool(store: CorpusStore) {
  return tool({
    description: "Fetches the text of one section of a document, by corpus path and heading.",
    inputSchema: z.object({
      path: z.string(),
      heading: z.string().describe("A heading exactly as returned by outline."),
    }),
    execute: async ({ path, heading }) => {
      const section = store.fetchSection(path, heading);
      if (section === undefined) {
        return { path, heading, found: false as const, text: undefined };
      }
      return { path, heading, found: true as const, text: section.text };
    },
  });
}
