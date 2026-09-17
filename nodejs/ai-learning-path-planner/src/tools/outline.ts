import { tool } from "ai";
import { z } from "zod";
import type { CorpusStore } from "../corpus/store.ts";

export function outlineTool(store: CorpusStore) {
  return tool({
    description: "Returns the heading outline of a document at a corpus path.",
    inputSchema: z.object({ path: z.string() }),
    execute: async ({ path }) => ({ path, headings: store.outline(path) }),
  });
}
